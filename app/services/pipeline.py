"""End-to-end Phase 1 pipeline for one inbound PoP image.

Steps (mirrors the core workflow spec):
  1. webhook receives an image message (routes/webhook.py)
  2. download + store image, compute hashes
  3. cross-tenant duplicate check
  4. Claude Vision structured extraction
  5. persist submission, match/create customer
  6-8. decision engine -> verdict (FAKE / VERIFIED / SUSPICIOUS / PENDING)
  9. reply to the business owner on WhatsApp
"""

import logging
import uuid
from typing import Any

from app.config import get_settings
from app.models.schemas import DecisionResult, PoPExtraction, Verdict
from app.services import db, stitch, whatsapp
from app.services.decision_engine import decide
from app.services.hashing import perceptual_hash, sha256_hex
from app.services.vision import analyse_pop_image

logger = logging.getLogger(__name__)


def process_image_message(
    phone_number_id: str,
    sender_wa_id: str,
    sender_name: str | None,
    media_id: str,
    message_id: str,
) -> None:
    settings = get_settings()

    business = db.get_business_by_phone_number_id(phone_number_id)
    if business is None:
        logger.warning("no business registered for phone_number_id", extra={"phone_number_id": phone_number_id})
        return
    business_id = business["id"]
    owner_number = business.get("owner_whatsapp_number") or sender_wa_id

    # Idempotency: Meta retries webhook deliveries on slow/missing ACKs.
    if message_id and db.submission_exists(message_id):
        logger.info("duplicate webhook delivery ignored", extra={"message_id": message_id})
        return

    # Tier enforcement: usage_counters vs the business's monthly limit.
    limit = business.get("monthly_verification_limit") or 0
    if limit and db.get_usage_count(business_id) >= limit:
        logger.warning("monthly verification limit reached", extra={"business_id": business_id, "limit": limit})
        try:
            whatsapp.send_text(
                phone_number_id,
                owner_number,
                f"⚠️ You've reached your monthly limit of {limit} PoP verifications "
                f"on the {business.get('pricing_tier', 'starter').title()} plan. "
                "This screenshot was NOT checked. Upgrade your plan to keep verifying.",
            )
        except Exception:
            logger.exception("failed to send limit-reached notice")
        return

    # 2. Download, hash, store.
    image_bytes, mime_type = whatsapp.download_media(media_id)
    sha256 = sha256_hex(image_bytes)
    phash = perceptual_hash(image_bytes)
    storage_path = f"{business_id}/{uuid.uuid4()}.{'png' if 'png' in mime_type else 'jpg'}"
    try:
        db.upload_image(storage_path, image_bytes, mime_type)
    except Exception:
        logger.exception("image upload failed; continuing without stored copy")
        storage_path = None

    # 3. Cross-tenant duplicate check (strongest fraud signal).
    duplicate = db.find_duplicate_submission(sha256, phash)
    is_duplicate = duplicate is not None
    if is_duplicate:
        logger.warning(
            "duplicate PoP image detected",
            extra={"business_id": business_id, "original_submission_id": duplicate["id"]},
        )

    # 4. Vision extraction (still run on duplicates so the owner sees what was claimed).
    extraction = analyse_pop_image(image_bytes, mime_type)

    # 5. Customer record + submission row.
    customer = db.upsert_customer(business_id, sender_wa_id, sender_name or extraction.sender_name)
    submission = db.insert_submission(
        {
            "business_id": business_id,
            "customer_id": customer["id"],
            "customer_phone_hash": db.hash_phone(sender_wa_id),
            "whatsapp_message_id": message_id,
            "image_sha256": sha256,
            "image_phash": phash,
            "image_storage_path": storage_path,
            "extracted_data": extraction.model_dump(mode="json"),
            "verdict": Verdict.PENDING.value,
        }
    )

    # 6-8. Bank data + decision.
    transactions = []
    bank_data_available = False
    if stitch.is_configured() and business.get("stitch_linked") and business.get("stitch_account_id"):
        try:
            transactions = stitch.fetch_recent_incoming_transactions(business["stitch_account_id"])
            db.sync_bank_transactions(business_id, transactions)
            bank_data_available = True
        except Exception:
            logger.exception("stitch fetch failed; falling back to PENDING")

    decision = decide(
        extraction,
        is_duplicate=is_duplicate,
        bank_data_available=bank_data_available,
        transactions=transactions,
        min_confidence=settings.min_extraction_confidence,
        window_hours=settings.match_time_window_hours,
        amount_tolerance_cents=settings.amount_tolerance_cents,
    )

    db.update_submission(
        submission["id"],
        {
            "verdict": decision.verdict.value,
            "matched_transaction_id": decision.matched_transaction_id,
            "decided_at": "now()",
        },
    )
    db.insert_verification_log(
        submission["id"],
        business_id,
        decision.verdict.value,
        decision.confidence,
        [c.model_dump() for c in decision.checks],
    )
    db.increment_usage(business_id)

    # Phase 3: a verified payment may settle an open order.
    settled_order = None
    if decision.verdict == Verdict.VERIFIED:
        from app.services.orders import settle_order_for_submission

        settled_order = settle_order_for_submission(
            business, submission["id"], extraction, customer["id"]
        )

    # 9. Notify the business owner.
    message = whatsapp.format_verdict_message(extraction, decision)
    if settled_order:
        message += f"\n\n🧾 Order *{settled_order}* marked as paid."
    try:
        whatsapp.send_text(phone_number_id, owner_number, message)
    except Exception:
        logger.exception("failed to deliver verdict to owner", extra={"submission_id": submission["id"]})

    logger.info(
        "submission processed",
        extra={
            "submission_id": submission["id"],
            "business_id": business_id,
            "verdict": decision.verdict.value,
            "duplicate": is_duplicate,
        },
    )


def recheck_pending_submissions() -> dict[str, Any]:
    """Re-run bank matching for PENDING submissions. Called nightly by n8n
    (and usable ad hoc). Returns a summary for the workflow log."""
    settings = get_settings()
    pending = db.get_pending_submissions()
    summary = {"checked": 0, "verified": 0, "still_pending": 0, "errors": 0}

    tx_cache: dict[str, list] = {}
    for row in pending:
        summary["checked"] += 1
        business = row["businesses"]
        try:
            extraction = PoPExtraction.model_validate(row["extracted_data"])
            if not (stitch.is_configured() and business.get("stitch_linked") and business.get("stitch_account_id")):
                summary["still_pending"] += 1
                continue
            account_id = business["stitch_account_id"]
            if account_id not in tx_cache:
                tx_cache[account_id] = stitch.fetch_recent_incoming_transactions(account_id, lookback_days=14)
                db.sync_bank_transactions(business["id"], tx_cache[account_id])

            decision = decide(
                extraction,
                is_duplicate=False,  # duplicates never reach PENDING
                bank_data_available=True,
                transactions=tx_cache[account_id],
                min_confidence=settings.min_extraction_confidence,
                window_hours=settings.match_time_window_hours,
                amount_tolerance_cents=settings.amount_tolerance_cents,
            )
            if decision.verdict == Verdict.VERIFIED:
                summary["verified"] += 1
                db.update_submission(
                    row["id"],
                    {"verdict": decision.verdict.value, "matched_transaction_id": decision.matched_transaction_id, "decided_at": "now()"},
                )
                db.insert_verification_log(
                    row["id"], business["id"], decision.verdict.value, decision.confidence,
                    [c.model_dump() for c in decision.checks],
                )
                _notify_owner_recheck(business, extraction, decision)
            else:
                summary["still_pending"] += 1
        except Exception:
            summary["errors"] += 1
            logger.exception("recheck failed for submission", extra={"submission_id": row.get("id")})

    logger.info("pending recheck complete", extra=summary)
    return summary


def _notify_owner_recheck(business: dict[str, Any], extraction: PoPExtraction, decision: DecisionResult) -> None:
    owner = business.get("owner_whatsapp_number")
    if not owner:
        return
    try:
        whatsapp.send_text(
            business["whatsapp_phone_number_id"],
            owner,
            whatsapp.format_verdict_message(extraction, decision),
        )
    except Exception:
        logger.exception("failed to send recheck notification")
