"""Phase 3 order management: catalog, order intake, status tracking, and the
hook that links verified PoP submissions to the orders they pay for.

Pure helpers (totals, status transitions, payment matching, message formatting)
sit on top; WhatsApp/DB orchestration below.
"""

import logging
import re
from typing import Any

from app.models.schemas import OrderStatus, PoPExtraction
from app.services.matching import amounts_match, references_match

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING_PAYMENT: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.FULFILLED, OrderStatus.CANCELLED},
    OrderStatus.FULFILLED: set(),
    OrderStatus.CANCELLED: set(),
}


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def order_total(resolved_items: list[tuple[dict[str, Any], int]]) -> float:
    return round(sum(float(p["price"]) * qty for p, qty in resolved_items), 2)


def find_order_for_payment(
    extraction: PoPExtraction,
    open_orders: list[dict[str, Any]],
    *,
    customer_id: str | None = None,
) -> dict[str, Any] | None:
    """Which open order does a verified payment settle?

    Strongest signal: the payment reference contains the order number (that's
    what we tell customers to use). Fallback: same customer + exact amount.
    """
    for order in open_orders:
        if references_match(extraction.reference_number, order["order_number"]):
            return order
    if customer_id is not None and extraction.amount is not None:
        candidates = [
            o
            for o in open_orders
            if o.get("customer_id") == customer_id
            and amounts_match(extraction.amount, float(o["total_amount"]))
        ]
        if len(candidates) == 1:
            return candidates[0]
    return None


# --- message formatting ----------------------------------------------------------


def format_catalog(business_name: str, products: list[dict[str, Any]]) -> str:
    if not products:
        return f"*{business_name}* has no products listed yet. Please tell us what you need."
    lines = [f"🛒 *{business_name} — price list*", ""]
    for p in products:
        lines.append(f"• {p['name']} — ZAR {float(p['price']):,.2f}")
    lines += ["", 'To order, reply e.g.: "order 2x ' + products[0]["name"] + '"']
    return "\n".join(lines)


def format_order_confirmation(
    order_number: str,
    resolved_items: list[tuple[dict[str, Any], int]],
    total: float,
    payment_instructions: str | None,
) -> str:
    lines = [f"🧾 *Order {order_number} received*", ""]
    for product, qty in resolved_items:
        lines.append(f"• {qty} x {product['name']} — ZAR {float(product['price']) * qty:,.2f}")
    lines += ["", f"*Total: ZAR {total:,.2f}*", ""]
    if payment_instructions:
        lines.append(f"Pay to: {payment_instructions}")
    lines += [
        f"Please use *{order_number}* as your payment reference, then send your "
        "proof of payment here. We'll confirm as soon as the payment is verified.",
    ]
    return "\n".join(lines)


_STATUS_TEXT = {
    OrderStatus.PENDING_PAYMENT: "awaiting payment",
    OrderStatus.PAID: "paid — being prepared",
    OrderStatus.FULFILLED: "fulfilled",
    OrderStatus.CANCELLED: "cancelled",
}


def format_order_status(order: dict[str, Any]) -> str:
    status = OrderStatus(order["status"])
    return (
        f"Order *{order['order_number']}*: {_STATUS_TEXT[status]}\n"
        f"Total: ZAR {float(order['total_amount']):,.2f}"
    )


HELP_TEXT = (
    "Hi! I can help you with:\n"
    '• *catalog* — see products and prices\n'
    '• *order 2x bread, 1x milk* — place an order\n'
    '• *status ORD-12* — check your order\n'
    "Or send a proof-of-payment screenshot and we'll verify it."
)

OWNER_HELP_TEXT = (
    "Owner commands:\n"
    "• *add product <name> <price>*\n"
    "• *orders* — open orders\n"
    "• *fulfil ORD-12* / *cancel ORD-12*\n"
    "Customer commands (catalog/order/status) also work."
)


# --- orchestration ----------------------------------------------------------------


def _digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def handle_inbound_text(
    phone_number_id: str, sender_wa_id: str, sender_name: str | None, text: str
) -> None:
    """Entry point for WhatsApp text messages (called from the webhook)."""
    from app.services import db, whatsapp
    from app.services.order_chat import Intent, parse_customer_command, parse_owner_command

    business = db.get_business_by_phone_number_id(phone_number_id)
    if business is None:
        return
    is_owner = _digits(sender_wa_id) == _digits(business.get("owner_whatsapp_number"))
    command = parse_owner_command(text) if is_owner else parse_customer_command(text)

    try:
        reply = _execute_command(business, sender_wa_id, sender_name, text, command, is_owner)
    except Exception:
        logger.exception("order command failed", extra={"intent": command.intent.value})
        reply = "Sorry, something went wrong handling that. Please try again."
    if reply:
        whatsapp.send_text(phone_number_id, sender_wa_id, reply)


def _execute_command(
    business: dict[str, Any],
    sender_wa_id: str,
    sender_name: str | None,
    raw_text: str,
    command,
    is_owner: bool,
) -> str | None:
    from app.services import db
    from app.services.order_chat import Intent, parse_order_with_llm, resolve_items

    business_id = business["id"]

    if command.intent == Intent.CATALOG:
        return format_catalog(business.get("name", ""), db.list_products(business_id))

    if command.intent == Intent.STATUS:
        if not command.order_number:
            return "Which order? Reply e.g.: status ORD-12"
        order = db.get_order_by_number(business_id, command.order_number)
        if order is None:
            return f"I couldn't find order {command.order_number}."
        return format_order_status(order)

    if command.intent == Intent.HELP:
        return OWNER_HELP_TEXT if is_owner else HELP_TEXT

    if command.intent == Intent.ADD_PRODUCT:
        db.upsert_product(business_id, command.product_name, command.price)
        return f"✅ Added *{command.product_name}* at ZAR {command.price:,.2f}."

    if command.intent == Intent.LIST_ORDERS:
        open_orders = db.get_open_orders(business_id)
        if not open_orders:
            return "No open orders."
        lines = ["*Open orders:*"]
        for o in open_orders[:15]:
            lines.append(f"• {o['order_number']} — ZAR {float(o['total_amount']):,.2f} ({_STATUS_TEXT[OrderStatus(o['status'])]})")
        return "\n".join(lines)

    if command.intent in (Intent.FULFIL, Intent.CANCEL):
        target = OrderStatus.FULFILLED if command.intent == Intent.FULFIL else OrderStatus.CANCELLED
        order = db.get_order_by_number(business_id, command.order_number)
        if order is None:
            return f"I couldn't find order {command.order_number}."
        if not can_transition(OrderStatus(order["status"]), target):
            return f"Order {command.order_number} is {_STATUS_TEXT[OrderStatus(order['status'])]} — can't mark it {target.value}."
        db.update_order_status(order["id"], target.value)
        return f"✅ Order {command.order_number} marked {target.value.replace('_', ' ')}."

    items = command.items
    if command.intent == Intent.UNKNOWN and not is_owner:
        # Free-text fallback: maybe it's an order in natural language.
        try:
            items = parse_order_with_llm(raw_text, db.list_products(business_id))
        except Exception:
            logger.exception("LLM order parse failed")
            items = []
        if not items:
            return HELP_TEXT
    elif command.intent == Intent.UNKNOWN:
        return OWNER_HELP_TEXT

    # ORDER flow (deterministic or LLM-parsed items).
    products = db.list_products(business_id)
    resolved, unresolved = resolve_items(items, products)
    if unresolved:
        known = ", ".join(p["name"] for p in products) or "nothing yet"
        return (
            f"I couldn't find: {', '.join(unresolved)}.\n"
            f"Available products: {known}.\nReply *catalog* for prices."
        )
    if not resolved:
        return HELP_TEXT

    customer = db.upsert_customer(business_id, sender_wa_id, sender_name)
    total = order_total(resolved)
    order = db.create_order(business_id, customer["id"], resolved, total)
    return format_order_confirmation(
        order["order_number"], resolved, total, business.get("payment_instructions")
    )


def settle_order_for_submission(
    business_id: str,
    submission_id: str,
    extraction: PoPExtraction,
    customer_id: str | None,
) -> str | None:
    """Called when a PoP submission becomes VERIFIED: if the payment settles an
    open order, mark it paid and link the submission. Returns the order number
    (for the owner notification) or None."""
    from app.services import db

    open_orders = db.get_open_orders(business_id)
    order = find_order_for_payment(extraction, open_orders, customer_id=customer_id)
    if order is None:
        return None
    db.update_order_status(order["id"], OrderStatus.PAID.value, paid=True, pop_submission_id=submission_id)
    db.update_submission(submission_id, {"order_id": order["id"]})
    logger.info(
        "order settled by verified PoP",
        extra={"order_number": order["order_number"], "submission_id": submission_id},
    )
    return order["order_number"]
