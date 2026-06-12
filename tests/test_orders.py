from app.models.schemas import OrderStatus, PoPExtraction
from app.services.orders import (
    can_transition,
    find_order_for_payment,
    format_order_confirmation,
    order_total,
)

PRODUCTS = [
    {"id": "p1", "name": "White Bread", "price": 22.50},
    {"id": "p2", "name": "Milk 2L", "price": 38.00},
]


def make_extraction(amount: float | None, reference: str | None) -> PoPExtraction:
    return PoPExtraction(
        is_payment_proof=True,
        amount=amount,
        currency="ZAR",
        reference_number=reference,
        bank_name="FNB",
        tamper_flags=[],
        confidence=0.9,
    )


def make_order(order_number: str, total: float, customer_id: str = "c1") -> dict:
    return {
        "id": f"id-{order_number}",
        "order_number": order_number,
        "total_amount": total,
        "customer_id": customer_id,
        "status": "pending_payment",
    }


class TestTransitions:
    def test_pending_to_paid(self):
        assert can_transition(OrderStatus.PENDING_PAYMENT, OrderStatus.PAID)

    def test_pending_to_cancelled(self):
        assert can_transition(OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED)

    def test_paid_to_fulfilled(self):
        assert can_transition(OrderStatus.PAID, OrderStatus.FULFILLED)

    def test_pending_cannot_skip_to_fulfilled(self):
        assert not can_transition(OrderStatus.PENDING_PAYMENT, OrderStatus.FULFILLED)

    def test_terminal_states(self):
        for terminal in (OrderStatus.FULFILLED, OrderStatus.CANCELLED):
            for target in OrderStatus:
                assert not can_transition(terminal, target)


class TestOrderTotal:
    def test_total(self):
        assert order_total([(PRODUCTS[0], 2), (PRODUCTS[1], 1)]) == 83.00

    def test_empty(self):
        assert order_total([]) == 0.0

    def test_rounding(self):
        assert order_total([({"price": 0.1}, 3)]) == 0.30


class TestFindOrderForPayment:
    def test_reference_contains_order_number(self):
        orders = [make_order("ORD-12", 83.00)]
        match = find_order_for_payment(make_extraction(83.00, "ORD-12"), orders)
        assert match is not None and match["order_number"] == "ORD-12"

    def test_reference_with_bank_noise(self):
        orders = [make_order("ORD-12", 83.00)]
        match = find_order_for_payment(make_extraction(83.00, "FNB PMT ORD12"), orders)
        assert match is not None

    def test_reference_beats_amount_heuristic(self):
        orders = [make_order("ORD-1", 50.00, customer_id="c1"), make_order("ORD-2", 50.00, customer_id="c2")]
        match = find_order_for_payment(make_extraction(50.00, "ORD-2"), orders, customer_id="c1")
        assert match is not None and match["order_number"] == "ORD-2"

    def test_customer_amount_fallback(self):
        orders = [make_order("ORD-5", 120.00, customer_id="c9")]
        match = find_order_for_payment(make_extraction(120.00, "no ref"), orders, customer_id="c9")
        assert match is not None and match["order_number"] == "ORD-5"

    def test_ambiguous_amount_fallback_declines(self):
        # Same customer, two open orders at the same amount: don't guess.
        orders = [
            make_order("ORD-5", 120.00, customer_id="c9"),
            make_order("ORD-6", 120.00, customer_id="c9"),
        ]
        assert find_order_for_payment(make_extraction(120.00, None), orders, customer_id="c9") is None

    def test_wrong_customer_no_fallback(self):
        orders = [make_order("ORD-5", 120.00, customer_id="c9")]
        assert find_order_for_payment(make_extraction(120.00, None), orders, customer_id="other") is None

    def test_no_match(self):
        orders = [make_order("ORD-5", 120.00)]
        assert find_order_for_payment(make_extraction(99.0, "X"), orders) is None


class TestConfirmationMessage:
    def test_includes_reference_instruction_and_payment_details(self):
        msg = format_order_confirmation("ORD-9", [(PRODUCTS[0], 2)], 45.00, "FNB 62011112222, Acme")
        assert "ORD-9" in msg
        assert "ZAR 45.00" in msg
        assert "payment reference" in msg
        assert "FNB 62011112222" in msg

    def test_without_payment_instructions(self):
        msg = format_order_confirmation("ORD-9", [(PRODUCTS[0], 1)], 22.50, None)
        assert "Pay to:" not in msg
