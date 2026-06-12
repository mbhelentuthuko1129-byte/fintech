from datetime import datetime, timedelta

from app.models.schemas import BankTransaction, PoPExtraction
from app.services.matching import (
    amounts_match,
    find_matching_transaction,
    parse_claimed_datetime,
    references_match,
    within_window,
)

NOW = datetime(2026, 6, 10, 12, 0, 0)


def make_extraction(**overrides) -> PoPExtraction:
    base = {
        "is_payment_proof": True,
        "amount": 1500.00,
        "currency": "ZAR",
        "reference_number": "INV-2041",
        "bank_name": "FNB",
        "sender_name": "T Mokoena",
        "recipient_name": "Acme Wholesale",
        "date_time": NOW.isoformat(),
        "tamper_flags": [],
        "confidence": 0.92,
    }
    base.update(overrides)
    return PoPExtraction(**base)


def make_tx(**overrides) -> BankTransaction:
    base = {
        "id": "tx-1",
        "amount": 1500.00,
        "currency": "ZAR",
        "reference": "INV-2041",
        "description": "FNB OB Pmt INV-2041",
        "date": NOW,
    }
    base.update(overrides)
    return BankTransaction(**base)


class TestAmountsMatch:
    def test_exact(self):
        assert amounts_match(1500.00, 1500.00)

    def test_cents_differ(self):
        assert not amounts_match(1500.00, 1500.01)

    def test_tolerance(self):
        assert amounts_match(1500.00, 1500.01, tolerance_cents=1)

    def test_float_rounding(self):
        # 0.1 + 0.2 style float noise must not break exact matching
        assert amounts_match(0.30, 0.1 + 0.2)


class TestReferencesMatch:
    def test_exact(self):
        assert references_match("INV-2041", "INV-2041")

    def test_case_and_punctuation_insensitive(self):
        assert references_match("inv 2041", "INV-2041")

    def test_substring_bank_truncation(self):
        assert references_match("INV-2041", "FNB OB PMT INV2041")

    def test_no_match(self):
        assert not references_match("INV-2041", "INV-9999")

    def test_empty_never_matches(self):
        assert not references_match(None, "INV-2041")
        assert not references_match("INV-2041", "")


class TestWithinWindow:
    def test_inside(self):
        assert within_window(NOW, NOW + timedelta(hours=24), 72)

    def test_outside(self):
        assert not within_window(NOW, NOW + timedelta(hours=100), 72)

    def test_unknown_claimed_time_passes(self):
        assert within_window(None, NOW, 72)


class TestParseClaimedDatetime:
    def test_iso(self):
        assert parse_claimed_datetime("2026-06-10T12:00:00") == NOW

    def test_garbage_returns_none(self):
        assert parse_claimed_datetime("10 June, around noon") is None

    def test_none(self):
        assert parse_claimed_datetime(None) is None


class TestFindMatchingTransaction:
    def test_full_match(self):
        match = find_matching_transaction(make_extraction(), [make_tx()])
        assert match is not None and match.id == "tx-1"

    def test_amount_only_is_not_enough(self):
        ext = make_extraction(reference_number=None, date_time=None)
        assert find_matching_transaction(ext, [make_tx(reference=None, description=None)]) is None

    def test_amount_plus_time_matches(self):
        ext = make_extraction(reference_number=None)
        match = find_matching_transaction(ext, [make_tx(reference=None, description=None)])
        assert match is not None

    def test_amount_mismatch_excludes(self):
        assert find_matching_transaction(make_extraction(amount=999.99), [make_tx()]) is None

    def test_no_amount_extracted(self):
        assert find_matching_transaction(make_extraction(amount=None), [make_tx()]) is None

    def test_prefers_reference_match_among_candidates(self):
        decoy = make_tx(id="decoy", reference="OTHER", description=None)
        target = make_tx(id="target")
        match = find_matching_transaction(make_extraction(), [decoy, target])
        assert match is not None and match.id == "target"

    def test_reference_match_in_description(self):
        tx = make_tx(reference=None, description="ACME INV2041 EFT")
        match = find_matching_transaction(make_extraction(date_time=None), [tx])
        assert match is not None
