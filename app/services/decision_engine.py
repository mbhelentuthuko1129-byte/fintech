"""Decision engine: combines duplicate detection, OCR confidence, tamper flags
and bank-match status into a single verdict.

Pure functions only — this is the most heavily unit-tested part of the system.

Verdict semantics:
  FAKE        duplicate image reused elsewhere, or clear forgery signals
  SUSPICIOUS  tamper flags / not actually a PoP / bank data contradicts the claim
  VERIFIED    extracted claim matches a real incoming transaction
  PENDING     nothing wrong, but bank data can't confirm yet (EFT lag, no Stitch link)
"""

from app.models.schemas import (
    BankTransaction,
    CheckResult,
    DecisionResult,
    PoPExtraction,
    Verdict,
)
from app.services.matching import find_matching_transaction

# Flags that on their own indicate deliberate editing rather than a bad photo.
STRONG_TAMPER_FLAGS = {"font_mismatch", "edited_text_region", "inconsistent_metadata"}


def decide(
    extraction: PoPExtraction,
    *,
    is_duplicate: bool,
    bank_data_available: bool,
    transactions: list[BankTransaction] | None = None,
    min_confidence: float = 0.5,
    window_hours: int = 72,
    amount_tolerance_cents: int = 0,
) -> DecisionResult:
    checks: list[CheckResult] = []
    transactions = transactions or []

    # 1. Duplicate image across any tenant is the strongest fraud signal.
    checks.append(
        CheckResult(
            name="duplicate_image",
            passed=not is_duplicate,
            detail="Image was previously submitted (possibly to another business)" if is_duplicate else None,
        )
    )
    if is_duplicate:
        return DecisionResult(verdict=Verdict.FAKE, confidence=0.95, checks=checks)

    # 2. Not a payment proof at all.
    checks.append(
        CheckResult(
            name="is_payment_proof",
            passed=extraction.is_payment_proof,
            detail=None if extraction.is_payment_proof else "Image does not look like a proof of payment",
        )
    )
    if not extraction.is_payment_proof:
        return DecisionResult(verdict=Verdict.SUSPICIOUS, confidence=0.8, checks=checks)

    # 3. Visual tampering.
    flags = {f.value for f in extraction.tamper_flags}
    strong = flags & STRONG_TAMPER_FLAGS
    checks.append(
        CheckResult(
            name="tamper_flags",
            passed=not flags,
            detail=f"Tamper signals: {', '.join(sorted(flags))}" if flags else None,
        )
    )
    if strong:
        return DecisionResult(verdict=Verdict.SUSPICIOUS, confidence=0.85, checks=checks)

    # 4. Extraction quality.
    low_confidence = extraction.confidence < min_confidence
    checks.append(
        CheckResult(
            name="extraction_confidence",
            passed=not low_confidence,
            detail=f"Low OCR confidence ({extraction.confidence:.2f})" if low_confidence else None,
        )
    )

    # 5. Bank verification.
    if not bank_data_available:
        checks.append(
            CheckResult(name="bank_match", passed=True, detail="Bank data not available yet — queued for re-check")
        )
        return DecisionResult(verdict=Verdict.PENDING, confidence=0.5, checks=checks)

    match = find_matching_transaction(
        extraction,
        transactions,
        window_hours=window_hours,
        amount_tolerance_cents=amount_tolerance_cents,
    )
    if match is not None:
        checks.append(CheckResult(name="bank_match", passed=True))
        # A matching real transaction means money actually arrived; that
        # overrides soft signals like weak tamper flags or low OCR confidence.
        return DecisionResult(
            verdict=Verdict.VERIFIED,
            confidence=min(0.95, 0.7 + extraction.confidence * 0.25),
            matched_transaction_id=match.id,
            checks=checks,
        )

    checks.append(
        CheckResult(name="bank_match", passed=False, detail="No matching incoming transaction found")
    )
    # Mismatch with weak/no tamper flags can still be EFT lag — but only if the
    # screenshot is recent enough that the money may not have cleared. We keep it
    # simple for Phase 1: bank data available + no match + soft flags => SUSPICIOUS,
    # nightly re-check (n8n) will flip PENDINGs; owner is told why it's suspicious.
    if flags or low_confidence:
        return DecisionResult(verdict=Verdict.SUSPICIOUS, confidence=0.8, checks=checks)
    return DecisionResult(verdict=Verdict.PENDING, confidence=0.55, checks=checks)
