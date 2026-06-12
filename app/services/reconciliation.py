"""Phase 2 reconciliation: match ALL incoming Stitch transactions against
PoP submissions — not just the one being verified right now — and surface
what's left over to the business owner:

  * unmatched transactions  -> money arrived that nobody claimed
  * unmatched submissions   -> claims never confirmed by money arriving

The pairing logic is pure; orchestration (DB/Stitch/WhatsApp) lives below it.
"""

import logging
from typing import Any

from pydantic import BaseModel

from app.config import get_settings
from app.models.schemas import BankTransaction, PoPExtraction, Verdict
from app.services import db, stitch, whatsapp
from app.services.matching import find_matching_transaction

logger = logging.getLogger(__name__)


class ReconciliationPair(BaseModel):
    submission_id: str
    transaction: BankTransaction


class ReconciliationOutcome(BaseModel):
    pairs: list[ReconciliationPair]
    unmatched_submission_ids: list[str]
    unmatched_transactions: list[BankTransaction]


def pair_submissions_with_transactions(
    submissions: list[tuple[str, PoPExtraction]],
    transactions: list[BankTransaction],
    *,
    window_hours: int = 72,
    amount_tolerance_cents: int = 0,
) -> ReconciliationOutcome:
    """Greedy 1:1 pairing, oldest submission first. A transaction settles at
    most one submission — two customers can't both claim the same deposit."""
    available = list(transactions)
    pairs: list[ReconciliationPair] = []
    unmatched_subs: list[str] = []

    for submission_id, extraction in submissions:
        match = find_matching_transaction(
            extraction,
            available,
            window_hours=window_hours,
            amount_tolerance_cents=amount_tolerance_cents,
        )
        if match is None:
            unmatched_subs.append(submission_id)
        else:
            pairs.append(ReconciliationPair(submission_id=submission_id, transaction=match))
            available = [t for t in available if t.id != match.id]

    return ReconciliationOutcome(
        pairs=pairs,
        unmatched_submission_ids=unmatched_subs,
        unmatched_transactions=available,
    )


def format_reconciliation_digest(
    business_name: str,
    verified_count: int,
    unmatched_transactions: list[BankTransaction],
    unmatched_submission_count: int,
) -> str | None:
    """Owner-facing digest. Returns None when there's nothing worth sending."""
    if verified_count == 0 and not unmatched_transactions and unmatched_submission_count == 0:
        return None

    lines = [f"🧾 *Reconciliation — {business_name}*", ""]
    if verified_count:
        lines.append(f"✅ {verified_count} pending PoP(s) now confirmed by your bank.")
    if unmatched_transactions:
        lines.append(f"💰 {len(unmatched_transactions)} payment(s) received with no matching PoP:")
        for tx in unmatched_transactions[:5]:
            ref = tx.reference or tx.description or "no reference"
            lines.append(f"  • {tx.currency} {tx.amount:,.2f} — {ref} ({tx.date:%d %b})")
        if len(unmatched_transactions) > 5:
            lines.append(f"  …and {len(unmatched_transactions) - 5} more")
    if unmatched_submission_count:
        lines.append(
            f"⚠️ {unmatched_submission_count} PoP(s) still have no matching money in the bank. "
            "Check these before releasing goods."
        )
    return "\n".join(lines)


# --- orchestration --------------------------------------------------------------


def reconcile_business(business: dict[str, Any]) -> dict[str, int]:
    """Full reconciliation for one tenant. Returns counters for the run log."""
    settings = get_settings()
    business_id = business["id"]

    transactions = stitch.fetch_recent_incoming_transactions(
        business["stitch_account_id"], lookback_days=30
    )
    db.sync_bank_transactions(business_id, transactions)

    open_subs = db.get_open_submissions(business_id)
    submissions: list[tuple[str, PoPExtraction]] = []
    for row in open_subs:
        try:
            submissions.append((row["id"], PoPExtraction.model_validate(row["extracted_data"])))
        except Exception:
            logger.exception("skipping submission with bad extraction payload", extra={"submission_id": row["id"]})

    unreconciled = db.get_unreconciled_transactions(business_id)
    candidate_txs = [
        BankTransaction(
            id=r["stitch_transaction_id"],
            amount=float(r["amount"]),
            currency=r["currency"],
            reference=r["reference"],
            description=r["description"],
            date=_parse_ts(r["transaction_date"]),
        )
        for r in unreconciled
    ]

    outcome = pair_submissions_with_transactions(
        submissions,
        candidate_txs,
        window_hours=settings.match_time_window_hours,
        amount_tolerance_cents=settings.amount_tolerance_cents,
    )

    verified = 0
    for pair in outcome.pairs:
        db.update_submission(
            pair.submission_id,
            {
                "verdict": Verdict.VERIFIED.value,
                "matched_transaction_id": pair.transaction.id,
                "decided_at": "now()",
            },
        )
        db.mark_transaction_reconciled(business_id, pair.transaction.id, pair.submission_id)
        db.insert_verification_log(
            pair.submission_id,
            business_id,
            Verdict.VERIFIED.value,
            0.9,
            [{"name": "reconciliation_match", "passed": True, "detail": f"matched {pair.transaction.id}"}],
        )
        # Close the loop on debt: a verified payment settles open reminders
        # for that customer at the same amount.
        sub = next((s for s in open_subs if s["id"] == pair.submission_id), None)
        if sub and sub.get("customer_id"):
            db.mark_reminders_paid(business_id, sub["customer_id"], pair.transaction.amount)
        verified += 1

    digest = format_reconciliation_digest(
        business.get("name", "your business"),
        verified,
        outcome.unmatched_transactions,
        len(outcome.unmatched_submission_ids),
    )
    owner = business.get("owner_whatsapp_number")
    if digest and owner:
        try:
            whatsapp.send_text(business["whatsapp_phone_number_id"], owner, digest)
        except Exception:
            logger.exception("failed to send reconciliation digest", extra={"business_id": business_id})

    return {
        "verified": verified,
        "unmatched_transactions": len(outcome.unmatched_transactions),
        "unmatched_submissions": len(outcome.unmatched_submission_ids),
    }


def reconcile_all_businesses() -> dict[str, Any]:
    """Nightly entry point (n8n): reconcile every Stitch-linked tenant."""
    if not stitch.is_configured():
        return {"businesses": 0, "skipped": "stitch not configured"}

    summary: dict[str, Any] = {"businesses": 0, "verified": 0, "unmatched_transactions": 0, "unmatched_submissions": 0, "errors": 0}
    for business in db.get_stitch_linked_businesses():
        summary["businesses"] += 1
        try:
            result = reconcile_business(business)
            for key in ("verified", "unmatched_transactions", "unmatched_submissions"):
                summary[key] += result[key]
        except Exception:
            summary["errors"] += 1
            logger.exception("reconciliation failed for business", extra={"business_id": business.get("id")})

    logger.info("reconciliation run complete", extra=summary)
    return summary


def _parse_ts(raw: str):
    from datetime import datetime

    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
