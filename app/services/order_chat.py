"""Conversational order intake over WhatsApp text messages.

Deterministic parsing first (cheap, predictable, fully unit-tested); a Claude
structured-output fallback handles free-text orders the grammar misses
("hi can I get two white loaves and a coke please").

Customer commands:
    catalog | menu | prices            -> product list
    order 2x bread, 1x milk            -> create an order
    status ORD-12                      -> order status
Owner commands (messages from the owner's number):
    add product <name> <price>
    orders                             -> open orders
    fulfil ORD-12 | cancel ORD-12
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    CATALOG = "catalog"
    ORDER = "order"
    STATUS = "status"
    ADD_PRODUCT = "add_product"
    LIST_ORDERS = "list_orders"
    FULFIL = "fulfil"
    CANCEL = "cancel"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class ParsedItem:
    name: str
    quantity: int = 1


@dataclass
class ParsedCommand:
    intent: Intent
    items: list[ParsedItem] = field(default_factory=list)
    order_number: str | None = None
    product_name: str | None = None
    price: float | None = None


_CATALOG_WORDS = {"catalog", "catalogue", "menu", "price", "prices", "pricelist", "price list", "products"}
_HELP_WORDS = {"help", "hi", "hello", "start"}
_ORDER_NO_RE = re.compile(r"\b(ord[-\s]?\d+)\b", re.IGNORECASE)


def _normalise_order_number(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    return f"ORD-{int(digits)}" if digits else raw.upper()


def parse_items(raw: str) -> list[ParsedItem]:
    """Parse "2x bread, milk x1, 3 eggs" into items. Unrecognised quantity
    defaults to 1."""
    items: list[ParsedItem] = []
    for part in re.split(r"[,\n;]| and ", raw):
        part = part.strip().strip(".")
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[xX]?\s+(.+)$", part)  # "2x bread" / "2 bread"
        if m:
            items.append(ParsedItem(name=m.group(2).strip(), quantity=int(m.group(1))))
            continue
        m = re.match(r"^(.+?)\s*[xX]\s*(\d+)$", part)  # "bread x2"
        if m:
            items.append(ParsedItem(name=m.group(1).strip(), quantity=int(m.group(2))))
            continue
        items.append(ParsedItem(name=part, quantity=1))
    return [i for i in items if i.name]


def parse_customer_command(text: str) -> ParsedCommand:
    cleaned = text.strip()
    lower = cleaned.lower()

    if lower in _CATALOG_WORDS:
        return ParsedCommand(intent=Intent.CATALOG)
    if lower in _HELP_WORDS:
        return ParsedCommand(intent=Intent.HELP)

    if lower.startswith("status"):
        m = _ORDER_NO_RE.search(cleaned)
        return ParsedCommand(
            intent=Intent.STATUS,
            order_number=_normalise_order_number(m.group(1)) if m else None,
        )

    if lower.startswith("order"):
        rest = cleaned[len("order"):].strip(" :,-")
        items = parse_items(rest)
        if items:
            return ParsedCommand(intent=Intent.ORDER, items=items)
        return ParsedCommand(intent=Intent.HELP)

    return ParsedCommand(intent=Intent.UNKNOWN)


_ADD_PRODUCT_RE = re.compile(
    r"^add\s+product\s+(.+?)\s+[rR]?(\d+(?:[.,]\d{1,2})?)$", re.IGNORECASE
)


def parse_owner_command(text: str) -> ParsedCommand:
    cleaned = text.strip()
    lower = cleaned.lower()

    m = _ADD_PRODUCT_RE.match(cleaned)
    if m:
        return ParsedCommand(
            intent=Intent.ADD_PRODUCT,
            product_name=m.group(1).strip(),
            price=float(m.group(2).replace(",", ".")),
        )
    if lower in {"orders", "open orders", "list orders"}:
        return ParsedCommand(intent=Intent.LIST_ORDERS)
    for verb, intent in (("fulfil", Intent.FULFIL), ("fulfill", Intent.FULFIL), ("done", Intent.FULFIL), ("cancel", Intent.CANCEL)):
        if lower.startswith(verb):
            m = _ORDER_NO_RE.search(cleaned)
            if m:
                return ParsedCommand(intent=intent, order_number=_normalise_order_number(m.group(1)))

    # Owners can use customer commands too (catalog, status, ...).
    return parse_customer_command(text)


# --- product resolution ----------------------------------------------------------


def resolve_items(
    items: list[ParsedItem], products: list[dict[str, Any]]
) -> tuple[list[tuple[dict[str, Any], int]], list[str]]:
    """Match parsed item names to catalog products: exact name, then SKU,
    then unique substring. Returns (resolved [(product, qty)], unresolved names)."""
    resolved: list[tuple[dict[str, Any], int]] = []
    unresolved: list[str] = []
    for item in items:
        needle = item.name.lower().strip()
        exact = [p for p in products if p["name"].lower() == needle]
        if not exact:
            exact = [p for p in products if (p.get("sku") or "").lower() == needle]
        if exact:
            resolved.append((exact[0], item.quantity))
            continue
        partial = [p for p in products if needle in p["name"].lower() or p["name"].lower() in needle]
        if len(partial) == 1:
            resolved.append((partial[0], item.quantity))
        else:
            unresolved.append(item.name)
    return resolved, unresolved


# --- Claude fallback for free-text orders ----------------------------------------


class LLMOrderItem(BaseModel):
    product_name: str = Field(description="The product the customer wants, matched to the catalog if possible.")
    quantity: int = Field(ge=1, description="How many they asked for; 1 if unstated.")


class LLMOrderIntent(BaseModel):
    is_order: bool = Field(
        description="True only if the message is clearly an attempt to order products; false for greetings, questions, complaints."
    )
    items: list[LLMOrderItem] = Field(default_factory=list, description="Requested items; empty if is_order is false.")


def parse_order_with_llm(text: str, products: list[dict[str, Any]]) -> list[ParsedItem]:
    """Free-text fallback. Returns [] if the message isn't an order attempt."""
    import anthropic

    from app.config import get_settings

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    catalog = "\n".join(f"- {p['name']} (ZAR {float(p['price']):.2f})" for p in products) or "(empty)"

    response = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=(
            "You read WhatsApp messages sent to a South African small business and decide "
            "whether the customer is trying to place an order. Match requested items to the "
            "catalog below where possible; keep the customer's wording when there is no match.\n\n"
            f"Catalog:\n{catalog}"
        ),
        messages=[{"role": "user", "content": text}],
        output_format=LLMOrderIntent,
    )
    intent = response.parsed_output
    if intent is None or not intent.is_order:
        return []
    return [ParsedItem(name=i.product_name, quantity=i.quantity) for i in intent.items]
