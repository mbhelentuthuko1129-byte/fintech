from datetime import datetime

from app.models.schemas import BankTransaction, PoPExtraction, TamperFlag, Verdict
from app.services.decision_engine import decide

NOW = datetime(2026, 6, 10, 12, 0, 0)


def make_extraction(**overrides) -> PoPExtraction:
    base = {
        "is_payment_proof": True,
        "amount": 1500.00,
        "currency": "ZAR",
        "reference_number": "INV-2041",
        "bank_name": "Capitec",
        "sender_name": "T Mokoena",
        "recipient_name": "Acme Wholesale",
        "date_time": NOW.isoformat(),
        "tamper_flags": [],
        "confidence": 0.92,
    }
    base.update(overrides)
    return PoPExtraction(**base)


def matching_tx() -> BankTransaction:
    return BankTransaction(id="tx-1", amount=1500.00, reference="INV-2041", date=NOW)


class TestDuplicate:
    def test_duplicate_is_fake_regardless_of_anything_else(self):
        result = decide(
            make_extraction(),
            is_duplicate=True,
            bank_data_available=True,
            transactions=[matching_tx()],
        )
        assert result.verdict == Verdict.FAKE
        assert any("previously submitted" in r for r in result.reasons)


class TestNotAPoP:
    def test_non_pop_image_is_suspicious(self):
        result = decide(
            make_extraction(is_payment_proof=False),
            is_duplicate=False,
            bank_data_available=False,
        )
        assert result.verdict == Verdict.SUSPICIOUS


class TestTamperFlags:
    def test_strong_tamper_flag_is_suspicious_even_without_bank_data(self):
        result = decide(
            make_extraction(tamper_flags=[TamperFlag.FONT_MISMATCH]),
            is_duplicate=False,
            bank_data_available=False,
        )
        assert result.verdict == Verdict.SUSPICIOUS

    def test_edited_text_region_is_suspicious(self):
        result = decide(
            make_extraction(tamper_flags=[TamperFlag.EDITED_TEXT_REGION]),
            is_duplicate=False,
            bank_data_available=True,
            transactions=[matching_tx()],
        )
        assert result.verdict == Verdict.SUSPICIOUS

    def test_weak_flag_with_bank_match_still_verifies(self):
        # Money actually arrived — a blurry/rescreenshotted image shouldn't block it.
        result = decide(
            make_extraction(tamper_flags=[TamperFlag.RESOLUTION_ARTIFACT]),
            is_duplicate=False,
            bank_data_available=True,
            transactions=[matching_tx()],
        )
        assert result.verdict == Verdict.VERIFIED

    def test_weak_flag_without_bank_match_is_suspicious(self):
        result = decide(
            make_extraction(tamper_flags=[TamperFlag.RESOLUTION_ARTIFACT]),
            is_duplicate=False,
            bank_data_available=True,
            transactions=[],
        )
        assert result.verdict == Verdict.SUSPICIOUS


class TestBankVerification:
    def test_clean_with_match_is_verified(self):
        result = decide(
            make_extraction(),
            is_duplicate=False,
            bank_data_available=True,
            transactions=[matching_tx()],
        )
        assert result.verdict == Verdict.VERIFIED
        assert result.matched_transaction_id == "tx-1"

    def test_clean_without_bank_data_is_pending(self):
        result = decide(make_extraction(), is_duplicate=False, bank_data_available=False)
        assert result.verdict == Verdict.PENDING

    def test_clean_with_bank_data_but_no_match_is_pending(self):
        # EFT lag: clean screenshot, money just not there yet.
        result = decide(
            make_extraction(),
            is_duplicate=False,
            bank_data_available=True,
            transactions=[BankTransaction(id="other", amount=42.00, reference="X", date=NOW)],
        )
        assert result.verdict == Verdict.PENDING

    def test_low_confidence_without_match_is_suspicious(self):
        result = decide(
            make_extraction(confidence=0.3),
            is_duplicate=False,
            bank_data_available=True,
            transactions=[],
        )
        assert result.verdict == Verdict.SUSPICIOUS

    def test_low_confidence_with_match_still_verifies(self):
        result = decide(
            make_extraction(confidence=0.3),
            is_duplicate=False,
            bank_data_available=True,
            transactions=[matching_tx()],
        )
        assert result.verdict == Verdict.VERIFIED


class TestChecksAudit:
    def test_every_decision_carries_checks(self):
        result = decide(make_extraction(), is_duplicate=False, bank_data_available=False)
        names = {c.name for c in result.checks}
        assert {"duplicate_image", "is_payment_proof", "tamper_flags", "extraction_confidence", "bank_match"} <= names

    def test_confidence_bounds(self):
        for kwargs in (
            {"is_duplicate": True, "bank_data_available": False},
            {"is_duplicate": False, "bank_data_available": False},
            {"is_duplicate": False, "bank_data_available": True, "transactions": [matching_tx()]},
        ):
            result = decide(make_extraction(), **kwargs)
            assert 0.0 <= result.confidence <= 1.0
