from datetime import datetime

from app.models.schemas import BankTransaction, PoPExtraction
from app.services.reconciliation import (
    format_reconciliation_digest,
    pair_submissions_with_transactions,
)

NOW = datetime(2026, 6, 10, 12, 0, 0)


def make_extraction(amount: float, ref: str | None, dt: datetime = NOW) -> PoPExtraction:
    return PoPExtraction(
        is_payment_proof=True,
        amount=amount,
        currency="ZAR",
        reference_number=ref,
        bank_name="FNB",
        date_time=dt.isoformat(),
        tamper_flags=[],
        confidence=0.9,
    )


def make_tx(tx_id: str, amount: float, ref: str | None, dt: datetime = NOW) -> BankTransaction:
    return BankTransaction(id=tx_id, amount=amount, reference=ref, date=dt)


class TestPairing:
    def test_simple_one_to_one(self):
        outcome = pair_submissions_with_transactions(
            [("sub-1", make_extraction(100.0, "A"))],
            [make_tx("tx-1", 100.0, "A")],
        )
        assert len(outcome.pairs) == 1
        assert outcome.pairs[0].submission_id == "sub-1"
        assert outcome.pairs[0].transaction.id == "tx-1"
        assert not outcome.unmatched_submission_ids
        assert not outcome.unmatched_transactions

    def test_transaction_settles_only_one_submission(self):
        # Two customers claim the same deposit — only one can match.
        subs = [
            ("sub-1", make_extraction(100.0, "A")),
            ("sub-2", make_extraction(100.0, "A")),
        ]
        outcome = pair_submissions_with_transactions(subs, [make_tx("tx-1", 100.0, "A")])
        assert len(outcome.pairs) == 1
        assert outcome.unmatched_submission_ids == ["sub-2"]

    def test_oldest_submission_wins_the_contested_transaction(self):
        subs = [
            ("oldest", make_extraction(100.0, "A")),
            ("newest", make_extraction(100.0, "A")),
        ]
        outcome = pair_submissions_with_transactions(subs, [make_tx("tx-1", 100.0, "A")])
        assert outcome.pairs[0].submission_id == "oldest"

    def test_unmatched_both_ways(self):
        subs = [("sub-1", make_extraction(100.0, "A"))]
        txs = [make_tx("tx-other", 999.0, "Z")]
        outcome = pair_submissions_with_transactions(subs, txs)
        assert not outcome.pairs
        assert outcome.unmatched_submission_ids == ["sub-1"]
        assert [t.id for t in outcome.unmatched_transactions] == ["tx-other"]

    def test_multiple_pairs_resolve_independently(self):
        subs = [
            ("sub-1", make_extraction(100.0, "A")),
            ("sub-2", make_extraction(250.5, "B")),
        ]
        txs = [make_tx("tx-2", 250.5, "B"), make_tx("tx-1", 100.0, "A")]
        outcome = pair_submissions_with_transactions(subs, txs)
        matched = {p.submission_id: p.transaction.id for p in outcome.pairs}
        assert matched == {"sub-1": "tx-1", "sub-2": "tx-2"}

    def test_empty_inputs(self):
        outcome = pair_submissions_with_transactions([], [])
        assert not outcome.pairs
        assert not outcome.unmatched_submission_ids
        assert not outcome.unmatched_transactions


class TestDigest:
    def test_nothing_to_report_returns_none(self):
        assert format_reconciliation_digest("Acme", 0, [], 0) is None

    def test_verified_only(self):
        digest = format_reconciliation_digest("Acme", 3, [], 0)
        assert digest is not None
        assert "3 pending PoP(s) now confirmed" in digest

    def test_unmatched_transactions_listed(self):
        txs = [make_tx("tx-1", 1500.0, "INV-9")]
        digest = format_reconciliation_digest("Acme", 0, txs, 0)
        assert digest is not None
        assert "1,500.00" in digest and "INV-9" in digest

    def test_unmatched_transaction_list_truncated_at_five(self):
        txs = [make_tx(f"tx-{i}", 10.0 + i, f"R{i}") for i in range(8)]
        digest = format_reconciliation_digest("Acme", 0, txs, 0)
        assert digest is not None
        assert "…and 3 more" in digest

    def test_unmatched_submissions_warning(self):
        digest = format_reconciliation_digest("Acme", 0, [], 2)
        assert digest is not None
        assert "2 PoP(s) still have no matching money" in digest
