"""Phase 4 invoicing: numbered PDF invoices tied to orders and customers,
delivered over WhatsApp as documents.

Pure parts (numbering, VAT math, invoice data assembly, PDF rendering from
data) are unit-tested; storage/WhatsApp orchestration sits at the bottom.

SA convention: catalog prices are VAT-inclusive. For a VAT-registered business
the invoice shows the VAT portion carved out of the total (15% by default);
non-registered businesses get a plain invoice with no VAT line.
"""

import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

logger = logging.getLogger(__name__)


def format_invoice_number(seq: int) -> str:
    return f"INV-{seq:05d}"


def vat_portion(total_inclusive: float, vat_rate: float) -> float:
    """VAT carved out of a VAT-inclusive total: total * r / (100 + r)."""
    return round(total_inclusive * vat_rate / (100 + vat_rate), 2)


@dataclass
class InvoiceLine:
    description: str
    quantity: int
    unit_price: float
    line_total: float


@dataclass
class InvoiceData:
    invoice_number: str
    business_name: str
    customer_name: str
    customer_phone: str
    order_number: str
    issued_on: date
    lines: list[InvoiceLine] = field(default_factory=list)
    currency: str = "ZAR"
    total: float = 0.0
    vat_rate: float = 15.0
    vat_amount: float = 0.0
    subtotal: float = 0.0
    vat_number: str | None = None
    payment_instructions: str | None = None
    paid: bool = False

    @property
    def title(self) -> str:
        return "TAX INVOICE" if self.vat_number else "INVOICE"


def build_invoice_data(
    business: dict[str, Any],
    customer: dict[str, Any],
    order: dict[str, Any],
    items: list[dict[str, Any]],
    invoice_number: str,
    *,
    issued_on: date | None = None,
) -> InvoiceData:
    """Assemble everything the PDF needs from DB rows. Pure."""
    total = float(order["total_amount"])
    vat_registered = bool(business.get("vat_registered"))
    vat_rate = float(business.get("vat_rate") or 15.0)
    vat_amount = vat_portion(total, vat_rate) if vat_registered else 0.0

    return InvoiceData(
        invoice_number=invoice_number,
        business_name=business.get("name", ""),
        vat_number=business.get("vat_number") if vat_registered else None,
        customer_name=customer.get("name") or "Customer",
        customer_phone=customer.get("phone", ""),
        order_number=order["order_number"],
        issued_on=issued_on or date.today(),
        lines=[
            InvoiceLine(
                description=i["description"],
                quantity=int(i["quantity"]),
                unit_price=float(i["unit_price"]),
                line_total=float(i["line_total"]),
            )
            for i in items
        ],
        currency=order.get("currency", "ZAR"),
        total=total,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        subtotal=round(total - vat_amount, 2),
        payment_instructions=business.get("payment_instructions"),
        paid=order.get("status") in ("paid", "fulfilled"),
    )


# --- PDF rendering ----------------------------------------------------------------


def render_invoice_pdf(data: InvoiceData) -> bytes:
    buf = io.BytesIO()
    page_w, page_h = A4
    c = Canvas(buf, pagesize=A4)
    left, right = 20 * mm, page_w - 20 * mm
    y = page_h - 25 * mm

    def money(v: float) -> str:
        return f"{data.currency} {v:,.2f}"

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, data.business_name)
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(right, y, data.title)
    y -= 7 * mm
    c.setFont("Helvetica", 9)
    if data.vat_number:
        c.drawString(left, y, f"VAT No: {data.vat_number}")
    c.drawRightString(right, y, f"{data.invoice_number}  ·  {data.issued_on:%d %b %Y}")
    y -= 5 * mm
    c.drawRightString(right, y, f"Order: {data.order_number}")
    if data.paid:
        c.setFillColor(colors.HexColor("#1a7f37"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, y, "PAID")
        c.setFillColor(colors.black)
    y -= 10 * mm

    # Bill to
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Billed to:")
    c.setFont("Helvetica", 10)
    c.drawString(left + 25 * mm, y, f"{data.customer_name}  ({data.customer_phone})")
    y -= 12 * mm

    # Table header
    qty_x, unit_x = right - 70 * mm, right - 40 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "Description")
    c.drawRightString(qty_x, y, "Qty")
    c.drawRightString(unit_x, y, "Unit")
    c.drawRightString(right, y, "Amount")
    y -= 2 * mm
    c.setStrokeColor(colors.grey)
    c.line(left, y, right, y)
    y -= 6 * mm

    c.setFont("Helvetica", 9)
    for line in data.lines:
        c.drawString(left, y, line.description[:60])
        c.drawRightString(qty_x, y, str(line.quantity))
        c.drawRightString(unit_x, y, money(line.unit_price))
        c.drawRightString(right, y, money(line.line_total))
        y -= 6 * mm
        if y < 50 * mm:  # crude page break; SME invoices rarely exceed one page
            c.showPage()
            y = page_h - 25 * mm
            c.setFont("Helvetica", 9)

    y -= 2 * mm
    c.line(left, y, right, y)
    y -= 8 * mm

    # Totals
    if data.vat_number:
        c.setFont("Helvetica", 10)
        c.drawRightString(unit_x, y, "Subtotal (excl. VAT):")
        c.drawRightString(right, y, money(data.subtotal))
        y -= 6 * mm
        c.drawRightString(unit_x, y, f"VAT @ {data.vat_rate:g}%:")
        c.drawRightString(right, y, money(data.vat_amount))
        y -= 7 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(unit_x, y, "Total:")
    c.drawRightString(right, y, money(data.total))
    y -= 14 * mm

    # Footer
    c.setFont("Helvetica", 9)
    if not data.paid:
        if data.payment_instructions:
            c.drawString(left, y, f"Pay to: {data.payment_instructions}")
            y -= 5 * mm
        c.drawString(left, y, f"Please use {data.order_number} as your payment reference.")
    else:
        c.drawString(left, y, "Thank you for your payment.")

    c.showPage()
    c.save()
    return buf.getvalue()


# --- orchestration ----------------------------------------------------------------


def issue_invoice_for_order(
    business: dict[str, Any],
    order: dict[str, Any],
    *,
    send_to_customer: bool = True,
) -> dict[str, Any] | None:
    """Generate (or re-render) the invoice for an order, store the PDF, and
    deliver it over WhatsApp. Idempotent per order: an existing invoice keeps
    its number and is re-rendered rather than duplicated."""
    from app.services import db, whatsapp

    business_id = business["id"]
    customer = db.get_customer(order["customer_id"])
    if customer is None:
        logger.warning("order has no customer; skipping invoice", extra={"order_id": order["id"]})
        return None
    items = db.get_order_items(order["id"])
    if not items:
        logger.warning("order has no items; skipping invoice", extra={"order_id": order["id"]})
        return None

    existing = db.get_invoice_by_order(order["id"])
    if existing:
        invoice_number = existing["invoice_number"]
    else:
        invoice_number = format_invoice_number(db.next_invoice_seq(business_id))

    data = build_invoice_data(business, customer, order, items, invoice_number)
    pdf_bytes = render_invoice_pdf(data)

    storage_path = f"{business_id}/{invoice_number}.pdf"
    try:
        db.upload_invoice_pdf(storage_path, pdf_bytes)
    except Exception:
        logger.exception("invoice PDF upload failed; continuing with delivery")
        storage_path = existing.get("pdf_storage_path") if existing else None

    if existing:
        invoice = existing
        db.update_invoice(
            existing["id"],
            {"status": "paid" if data.paid else "issued", "pdf_storage_path": storage_path},
        )
    else:
        invoice = db.create_invoice(
            {
                "business_id": business_id,
                "customer_id": customer["id"],
                "order_id": order["id"],
                "invoice_number": invoice_number,
                "status": "paid" if data.paid else "issued",
                "subtotal": data.subtotal,
                "vat_amount": data.vat_amount,
                "total_amount": data.total,
                "currency": data.currency,
                "pdf_storage_path": storage_path,
                "issued_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    if send_to_customer:
        caption = (
            f"Invoice {invoice_number} for order {order['order_number']}"
            + (" — paid, thank you!" if data.paid else f" — total {data.currency} {data.total:,.2f}")
        )
        try:
            whatsapp.send_document(
                business["whatsapp_phone_number_id"],
                customer["phone"],
                pdf_bytes,
                filename=f"{invoice_number}.pdf",
                caption=caption,
            )
        except Exception:
            logger.exception("failed to deliver invoice PDF", extra={"invoice_number": invoice_number})

    logger.info("invoice issued", extra={"invoice_number": invoice_number, "order_number": order["order_number"]})
    return invoice


# --- WhatsApp sales report (owner `report` command) --------------------------------


def format_sales_report(business_name: str, period_label: str, stats: dict[str, Any]) -> str:
    revenue = float(stats.get("revenue", 0))
    submissions = int(stats.get("submissions", 0))
    flagged = int(stats.get("fake", 0)) + int(stats.get("suspicious", 0))
    fraud_rate = (flagged / submissions * 100) if submissions else 0.0

    lines = [
        f"📊 *{business_name} — {period_label}*",
        "",
        f"Revenue (paid orders): ZAR {revenue:,.2f}",
        f"Orders: {stats.get('orders_placed', 0)} placed, {stats.get('orders_paid', 0)} paid",
        f"Invoices issued: {stats.get('invoices_issued', 0)}",
        "",
        f"PoP checks: {submissions}",
        f"  ✅ verified: {stats.get('verified', 0)}",
        f"  ⏳ pending: {stats.get('pending', 0)}",
        f"  ⚠️ suspicious: {stats.get('suspicious', 0)}",
        f"  🚫 fake: {stats.get('fake', 0)}",
        f"Fraud rate: {fraud_rate:.1f}%",
    ]
    top = stats.get("top_customers") or []
    if top:
        lines += ["", "*Top customers:*"]
        for c in top[:3]:
            lines.append(f"  • {c.get('name') or c.get('phone')}: ZAR {float(c.get('total_revenue', 0)):,.2f}")
    return "\n".join(lines)
