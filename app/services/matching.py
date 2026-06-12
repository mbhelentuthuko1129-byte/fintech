"""Pure matching logic: claimed PoP details vs real Stitch transactions.

No I/O here — callers fetch candidate transactions and pass them in, which
keeps this unit-testable and reusable for Phase 2 reconciliation.
"""

import re
from datetime import datetime, timedelta

from app.models.schemas import BankTransaction, PoPExtraction


def _normalise_reference(ref: str | None) -> str:
    if not ref:
        return ""
    return re.sub(r"[^a-z0-9]", "", ref.lower())


def amounts_match(claimed: float, actual: float, tolerance_cents: int = 0) -> bool:
    return abs(round(claimed * 100) - round(actual * 100)) <= tolerance_cents


def references_match(claimed: str | None, actual: str | None) -> bool:
    """Match on normalised reference; substring counts because banks often
    truncate or prefix the customer-entered reference."""
    a, b = _normalise_reference(claimed), _normalise_reference(actual)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def within_window(claimed: datetime | None, actual: datetime, window_hours: int) -> bool:
    """If the screenshot date is unreadable we don't fail on time alone —
    amount + reference still have to agree."""
    if claimed is None:
        return True
    if claimed.tzinfo is None and actual.tzinfo is not None:
        actual = actual.replace(tzinfo=None)
    elif claimed.tzinfo is not None and actual.tzinfo is None:
        claimed = claimed.replace(tzinfo=None)
    return abs(actual - claimed) <= timedelta(hours=window_hours)


def parse_claimed_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def find_matching_transaction(
    extraction: PoPExtraction,
    transactions: list[BankTransaction],
    *,
    window_hours: int = 72,
    amount_tolerance_cents: int = 0,
) -> BankTransaction | None:
    """Return the best matching incoming transaction, or None.

    A match requires the amount to agree and at least one corroborating
    signal: matching reference, or claimed timestamp within the window.
    Amount-only matches are too weak to auto-verify.
    """
    if extraction.amount is None:
        return None

    claimed_dt = parse_claimed_datetime(extraction.date_time)

    best: BankTransaction | None = None
    best_score = 0
    for tx in transactions:
        if not amounts_match(extraction.amount, tx.amount, amount_tolerance_cents):
            continue
        ref_ok = references_match(extraction.reference_number, tx.reference) or references_match(
            extraction.reference_number, tx.description
        )
        time_ok = claimed_dt is not None and within_window(claimed_dt, tx.date, window_hours)
        score = (2 if ref_ok else 0) + (1 if time_ok else 0)
        if score > best_score:
            best, best_score = tx, score

    return best if best_score >= 1 else None
