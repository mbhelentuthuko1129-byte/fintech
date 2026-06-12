from datetime import date

from app.services.invoices import (
    InvoiceData,
    InvoiceLine,
    build_invoice_data,
    format_invoice_number,
    format_sales_report,
    render_invoice_pdf,
    vat_portion,
)

BUSINESS = {
    "id": "b1",
    "name": "Acme Wholesale",
    "vat_registered": True,
    "vat_number": "4123456789",
    "vat_rate": 15.0,
    "payment_instructions": "FNB 62011112222, Acme Wholesale",
}

CUSTOMER = {"id": "c1", "name": "Thabo M", "phone": "27821234567"}

ORDER = {
    "id": "o1",
    "order_number": "ORD-12",
    "total_amount": 230.00,
    "currency": "ZAR",
    "status": "paid",
    "customer_id": "c1",
}

ITEMS = [
    {"description": "White Bread", "quantity": 4, "unit_price": 22.50, "line_total": 90.00},
    {"description": "Milk 2L", "quantity": 2, "unit_price": 38.00, "line_total": 76.00},
    {"description": "Eggs 18s", "quantity": 1, "unit_price": 64.00, "line_total": 64.00},
]


class TestInvoiceNumber:
    def test_zero_padded(self):
        assert format_invoice_number(42) == "INV-00042"

    def test_large_seq_not_truncated(self):
        assert format_invoice_number(123456) == "INV-123456"


class TestVatPortion:
    def test_15_percent_inclusive(self):
        # ZAR 115 inclusive -> ZAR 15 VAT
        assert vat_portion(115.00, 15.0) == 15.00

    def test_rounding(self):
        assert vat_portion(230.00, 15.0) == 30.00

    def test_zero_total(self):
        assert vat_portion(0.0, 15.0) == 0.0


class TestBuildInvoiceData:
    def test_vat_registered_business(self):
        data = build_invoice_data(BUSINESS, CUSTOMER, ORDER, ITEMS, "INV-00001", issued_on=date(2026, 6, 12))
        assert data.title == "TAX INVOICE"
        assert data.vat_amount == 30.00
        assert data.subtotal == 200.00
        assert data.total == 230.00
        assert data.paid is True
        assert len(data.lines) == 3

    def test_non_vat_business_has_no_vat_line(self):
        business = {**BUSINESS, "vat_registered": False}
        data = build_invoice_data(business, CUSTOMER, ORDER, ITEMS, "INV-00001")
        assert data.title == "INVOICE"
        assert data.vat_number is None
        assert data.vat_amount == 0.0
        assert data.subtotal == data.total

    def test_unpaid_order(self):
        order = {**ORDER, "status": "pending_payment"}
        data = build_invoice_data(BUSINESS, CUSTOMER, ORDER | order, ITEMS, "INV-00001")
        assert data.paid is False

    def test_customer_without_name(self):
        data = build_invoice_data(BUSINESS, {"id": "c1", "name": None, "phone": "278"}, ORDER, ITEMS, "INV-1")
        assert data.customer_name == "Customer"


class TestRenderPdf:
    def make_data(self, **overrides) -> InvoiceData:
        base = dict(
            invoice_number="INV-00001",
            business_name="Acme",
            customer_name="Thabo",
            customer_phone="27821234567",
            order_number="ORD-12",
            issued_on=date(2026, 6, 12),
            lines=[InvoiceLine("White Bread", 2, 22.50, 45.00)],
            total=45.00,
            vat_rate=15.0,
            vat_amount=5.87,
            subtotal=39.13,
            vat_number="4123456789",
            payment_instructions="FNB 123",
            paid=False,
        )
        base.update(overrides)
        return InvoiceData(**base)

    def test_produces_valid_pdf_bytes(self):
        pdf = render_invoice_pdf(self.make_data())
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000

    def test_many_lines_paginate_without_error(self):
        lines = [InvoiceLine(f"Item {i}", 1, 10.0, 10.0) for i in range(80)]
        pdf = render_invoice_pdf(self.make_data(lines=lines, total=800.0))
        assert pdf.startswith(b"%PDF")

    def test_paid_invoice_renders(self):
        pdf = render_invoice_pdf(self.make_data(paid=True))
        assert pdf.startswith(b"%PDF")


class TestSalesReport:
    STATS = {
        "orders_placed": 10,
        "orders_paid": 7,
        "revenue": 4350.00,
        "invoices_issued": 7,
        "submissions": 20,
        "verified": 14,
        "pending": 3,
        "suspicious": 2,
        "fake": 1,
        "top_customers": [{"name": "Thabo", "phone": "278", "total_revenue": 900.0}],
    }

    def test_contains_key_figures(self):
        report = format_sales_report("Acme", "June 2026", self.STATS)
        assert "ZAR 4,350.00" in report
        assert "10 placed, 7 paid" in report
        assert "fake: 1" in report

    def test_fraud_rate(self):
        # (2 suspicious + 1 fake) / 20 = 15%
        report = format_sales_report("Acme", "June 2026", self.STATS)
        assert "Fraud rate: 15.0%" in report

    def test_zero_submissions_no_division_error(self):
        stats = {**self.STATS, "submissions": 0, "suspicious": 0, "fake": 0}
        report = format_sales_report("Acme", "June 2026", stats)
        assert "Fraud rate: 0.0%" in report

    def test_top_customers_listed(self):
        report = format_sales_report("Acme", "June 2026", self.STATS)
        assert "Thabo: ZAR 900.00" in report
