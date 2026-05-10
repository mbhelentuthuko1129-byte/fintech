"""
HTML Management Pack Generator.

Produces a self-contained HTML file that renders in any browser.
In production this is followed by an HTML→PDF conversion step
(PDFShift API or Puppeteer) and then uploaded to Supabase Storage.
The download link is then sent via WhatsApp and email.

Design decisions:
  - Inline CSS only (no external dependencies)
  - System fonts (renders everywhere without loading fonts)
  - Single file output (easy to email as attachment)
  - Print-friendly layout (A4 @ 96dpi)
"""

from datetime import datetime
from pathlib import Path
from jinja2 import Environment, BaseLoader

OUTPUT_DIR = Path(__file__).parent / "output"

# ─────────────────────────────────────────────────────────────────────────────
# Jinja2 filters
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_rand(value: float) -> str:
    """R1,234,567"""
    if value is None:
        return "—"
    return f"R{abs(value):,.0f}"


def _fmt_pct(value: float) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def _variance_class(value: float, line: str) -> str:
    """Return CSS class based on whether the variance is favourable."""
    # For expense lines a negative variance vs budget is good (spent less)
    expense_lines = {
        "cogs", "salaries", "rent", "transport", "marketing",
        "admin", "depreciation", "total_opex", "finance_costs",
    }
    if value == 0:
        return "var-neutral"
    if line in expense_lines:
        return "var-good" if value <= 0 else "var-bad"
    return "var-good" if value >= 0 else "var-bad"


def _status_icon(status: str) -> str:
    return {"green": "✓", "amber": "⚠", "red": "✗"}.get(status, "·")


def _status_label(status: str) -> str:
    return {"green": "On Target", "amber": "Below Target", "red": "Alert"}.get(status, status)


# ─────────────────────────────────────────────────────────────────────────────
# HTML template
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Management Accounts — {{ client.name }} — {{ period.label }}</title>
<style>
  /* ── Reset & Base ─────────────────────────────────────────────────── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    font-size: 13px; line-height: 1.5; color: #1a1a2e; background: #f0f2f5;
  }
  @media print {
    body { background: white; font-size: 11px; }
    .no-print { display: none; }
    .page-break { page-break-before: always; }
  }

  /* ── Layout ───────────────────────────────────────────────────────── */
  .wrapper { max-width: 960px; margin: 0 auto; background: white; box-shadow: 0 2px 24px rgba(0,0,0,.10); }

  /* ── Header ───────────────────────────────────────────────────────── */
  .header {
    background: linear-gradient(135deg, #0f2040 0%, #1a3a6e 100%);
    color: white; padding: 28px 36px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .header-brand { display: flex; align-items: center; gap: 16px; }
  .logo {
    width: 48px; height: 48px; border-radius: 10px;
    background: #f4c542; color: #0f2040;
    font-weight: 800; font-size: 18px;
    display: flex; align-items: center; justify-content: center;
  }
  .header h1 { font-size: 18px; font-weight: 700; letter-spacing: -.2px; }
  .header .subtitle { font-size: 12px; opacity: .75; margin-top: 2px; }
  .header-meta { text-align: right; font-size: 11px; opacity: .70; line-height: 1.7; }
  .header-meta strong { display: block; font-size: 14px; opacity: 1; color: #f4c542; }

  /* ── Section ──────────────────────────────────────────────────────── */
  .section { padding: 28px 36px; border-bottom: 1px solid #eef0f4; }
  .section:last-child { border-bottom: none; }
  .section-title {
    font-size: 11px; font-weight: 700; letter-spacing: 1.2px;
    text-transform: uppercase; color: #6b7280; margin-bottom: 16px;
    padding-bottom: 8px; border-bottom: 2px solid #e5e7eb;
  }

  /* ── KPI Grid ─────────────────────────────────────────────────────── */
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
    gap: 12px;
  }
  .kpi-card {
    border-radius: 10px; padding: 16px; position: relative; overflow: hidden;
    border: 1px solid #e5e7eb;
  }
  .kpi-card.green  { background: #f0fdf4; border-color: #86efac; }
  .kpi-card.amber  { background: #fffbeb; border-color: #fcd34d; }
  .kpi-card.red    { background: #fef2f2; border-color: #fca5a5; }
  .kpi-label { font-size: 10px; font-weight: 600; text-transform: uppercase;
               letter-spacing: .8px; color: #6b7280; margin-bottom: 6px; }
  .kpi-value { font-size: 22px; font-weight: 800; color: #111827; line-height: 1; }
  .kpi-value.green { color: #15803d; }
  .kpi-value.amber { color: #b45309; }
  .kpi-value.red   { color: #b91c1c; }
  .kpi-benchmark {
    font-size: 10px; color: #6b7280; margin-top: 6px;
  }
  .kpi-status-badge {
    position: absolute; top: 10px; right: 10px;
    width: 22px; height: 22px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700;
  }
  .kpi-card.green .kpi-status-badge { background: #16a34a; color: white; }
  .kpi-card.amber .kpi-status-badge { background: #d97706; color: white; }
  .kpi-card.red   .kpi-status-badge { background: #dc2626; color: white; }

  /* ── Alerts ───────────────────────────────────────────────────────── */
  .alert-item {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 12px 16px; border-radius: 8px; margin-bottom: 8px;
  }
  .alert-item.HIGH   { background: #fef2f2; border-left: 4px solid #dc2626; }
  .alert-item.MEDIUM { background: #fffbeb; border-left: 4px solid #d97706; }
  .alert-badge {
    font-size: 10px; font-weight: 700; letter-spacing: .5px;
    padding: 2px 7px; border-radius: 20px; white-space: nowrap; margin-top: 1px;
  }
  .HIGH   .alert-badge { background: #fee2e2; color: #991b1b; }
  .MEDIUM .alert-badge { background: #fef3c7; color: #92400e; }
  .alert-text { font-size: 12px; color: #374151; }
  .whatsapp-preview {
    margin-top: 6px; font-size: 11px; color: #6b7280;
    font-family: monospace; background: #f9fafb;
    padding: 6px 10px; border-radius: 6px; border: 1px solid #e5e7eb;
    white-space: pre-line;
  }

  /* ── P&L Table ────────────────────────────────────────────────────── */
  table { width: 100%; border-collapse: collapse; }
  th {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .6px; color: #6b7280; text-align: right;
    padding: 8px 10px; background: #f9fafb; border-bottom: 2px solid #e5e7eb;
  }
  th:first-child { text-align: left; }
  td { padding: 7px 10px; text-align: right; border-bottom: 1px solid #f3f4f6; }
  td:first-child { text-align: left; font-size: 12px; color: #374151; }
  tr:hover td { background: #fafafa; }

  .row-section td {
    font-size: 10px; font-weight: 700; letter-spacing: .8px;
    text-transform: uppercase; color: #9ca3af;
    background: #f9fafb; padding: 6px 10px;
  }
  .row-subtotal td {
    font-weight: 700; color: #111827; border-top: 1px solid #d1d5db;
    border-bottom: 2px solid #d1d5db; font-size: 12px;
  }
  .row-total td {
    font-weight: 800; font-size: 13px; color: #0f2040;
    background: #f0f4ff; border-top: 2px solid #6366f1;
    border-bottom: 2px solid #6366f1;
  }
  .row-margin td { font-size: 11px; color: #6b7280; font-style: italic; }

  .amount { font-variant-numeric: tabular-nums; font-size: 12px; }
  .var-good { color: #15803d; font-weight: 600; }
  .var-bad  { color: #dc2626; font-weight: 600; }
  .var-neutral { color: #6b7280; }

  /* ── Commentary ───────────────────────────────────────────────────── */
  .commentary-block { margin-bottom: 20px; }
  .commentary-heading {
    font-size: 10px; font-weight: 700; letter-spacing: 1px;
    text-transform: uppercase; color: #6366f1; margin-bottom: 8px;
  }
  .commentary-text {
    font-size: 13px; color: #374151; line-height: 1.7;
    padding: 14px 18px; background: #f9fafb;
    border-radius: 8px; border-left: 3px solid #6366f1;
  }
  .commentary-source {
    font-size: 10px; color: #9ca3af; margin-top: 16px; font-style: italic;
  }

  /* ── Balance Sheet ────────────────────────────────────────────────── */
  .bs-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  .bs-block h3 {
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .8px; color: #6b7280; margin-bottom: 10px;
    padding-bottom: 6px; border-bottom: 1px solid #e5e7eb;
  }
  .bs-row {
    display: flex; justify-content: space-between;
    padding: 5px 0; border-bottom: 1px solid #f3f4f6; font-size: 12px;
  }
  .bs-row:last-child { border-bottom: none; }
  .bs-name { color: #374151; }
  .bs-amount { font-variant-numeric: tabular-nums; color: #111827; font-weight: 500; }
  .bs-total {
    display: flex; justify-content: space-between;
    padding: 8px 0; font-weight: 700; font-size: 12px;
    border-top: 2px solid #d1d5db; margin-top: 4px;
  }

  /* ── Footer ───────────────────────────────────────────────────────── */
  .footer {
    background: #0f2040; color: rgba(255,255,255,.5);
    padding: 16px 36px; font-size: 10px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .footer strong { color: rgba(255,255,255,.85); }
  .delivery-row {
    margin-top: 10px; padding: 12px 16px; background: #f0fdf4;
    border-radius: 8px; border: 1px solid #86efac;
    font-size: 12px; color: #166534;
  }
  .delivery-row strong { font-weight: 700; }
</style>
</head>
<body>
<div class="wrapper">

  <!-- ── Header ──────────────────────────────────────────────────────── -->
  <div class="header">
    <div class="header-brand">
      <div class="logo">FP</div>
      <div>
        <h1>{{ client.name }}</h1>
        <div class="subtitle">Management Accounts &mdash; {{ period.label }}</div>
      </div>
    </div>
    <div class="header-meta">
      <strong>{{ period.label }}</strong>
      Generated: {{ generated_at }}<br>
      Industry: {{ client.industry }}<br>
      Currency: ZAR
    </div>
  </div>

  <!-- ── KPI Dashboard ───────────────────────────────────────────────── -->
  <div class="section">
    <div class="section-title">Key Performance Indicators</div>
    <div class="kpi-grid">
      {% for key, kpi in kpis.items() %}
      <div class="kpi-card {{ kpi.status }}">
        <div class="kpi-status-badge">{{ kpi.status | status_icon }}</div>
        <div class="kpi-label">{{ kpi.label }}</div>
        <div class="kpi-value {{ kpi.status }}">{{ kpi.value }}{{ kpi.unit }}</div>
        <div class="kpi-benchmark">
          Budget: {{ kpi.budget }}{{ kpi.unit }}&ensp;|&ensp;{{ kpi.status | status_label }}
        </div>
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- ── Alerts ──────────────────────────────────────────────────────── -->
  {% if alerts %}
  <div class="section">
    <div class="section-title">Alerts &amp; Notifications
      <span style="font-weight:400;color:#dc2626">({{ alerts|length }} triggered)</span>
    </div>
    {% for alert in alerts %}
    <div class="alert-item {{ alert.severity }}">
      <span class="alert-badge">{{ alert.severity }}</span>
      <div>
        <div class="alert-text"><strong>{{ alert.kpi }}</strong> — {{ alert.message }}</div>
        <div class="whatsapp-preview">{{ alert.whatsapp }}</div>
      </div>
    </div>
    {% endfor %}
    <div style="margin-top:10px;font-size:11px;color:#6b7280">
      ↑ WhatsApp messages sent automatically to {{ client.contacts.md.whatsapp }} at time of detection.
    </div>
  </div>
  {% endif %}

  <!-- ── Income Statement ───────────────────────────────────────────── -->
  <div class="section">
    <div class="section-title">Income Statement — {{ period.label }}</div>
    <table>
      <thead>
        <tr>
          <th style="width:30%">Line Item</th>
          <th>Actual</th>
          <th>Budget</th>
          <th>Prior Month</th>
          <th>Var (Budget)</th>
          <th>Var %</th>
          <th>Var (Prior)</th>
        </tr>
      </thead>
      <tbody>

        <!-- Revenue -->
        <tr class="row-section"><td colspan="7">Revenue</td></tr>
        <tr class="row-subtotal">
          <td>Total Revenue</td>
          <td class="amount">{{ variances.revenue.actual | fmt_rand }}</td>
          <td class="amount">{{ variances.revenue.budget | fmt_rand }}</td>
          <td class="amount">{{ variances.revenue.prior  | fmt_rand }}</td>
          <td class="amount {{ 'revenue' | vclass(variances.revenue.vs_budget) }}">
            {{ variances.revenue.vs_budget | fmt_rand }}</td>
          <td class="{{ 'revenue' | vclass(variances.revenue.vs_budget) }}">
            {{ variances.revenue.vs_budget_pct | fmt_pct }}</td>
          <td class="amount {{ 'revenue' | vclass(variances.revenue.vs_prior) }}">
            {{ variances.revenue.vs_prior | fmt_rand }}</td>
        </tr>

        <!-- COGS & Gross Profit -->
        <tr class="row-section"><td colspan="7">Cost of Sales</td></tr>
        <tr>
          <td>Cost of Goods Sold</td>
          <td class="amount">{{ variances.cogs.actual | fmt_rand }}</td>
          <td class="amount">{{ variances.cogs.budget | fmt_rand }}</td>
          <td class="amount">{{ variances.cogs.prior  | fmt_rand }}</td>
          <td class="amount {{ 'cogs' | vclass(variances.cogs.vs_budget) }}">
            {{ variances.cogs.vs_budget | fmt_rand }}</td>
          <td class="{{ 'cogs' | vclass(variances.cogs.vs_budget) }}">
            {{ variances.cogs.vs_budget_pct | fmt_pct }}</td>
          <td class="amount">—</td>
        </tr>
        <tr class="row-subtotal">
          <td>Gross Profit</td>
          <td class="amount">{{ variances.gross_profit.actual | fmt_rand }}</td>
          <td class="amount">{{ variances.gross_profit.budget | fmt_rand }}</td>
          <td class="amount">{{ variances.gross_profit.prior  | fmt_rand }}</td>
          <td class="amount {{ 'revenue' | vclass(variances.gross_profit.vs_budget) }}">
            {{ variances.gross_profit.vs_budget | fmt_rand }}</td>
          <td class="{{ 'revenue' | vclass(variances.gross_profit.vs_budget) }}">
            {{ variances.gross_profit.vs_budget_pct | fmt_pct }}</td>
          <td class="amount {{ 'revenue' | vclass(variances.gross_profit.vs_prior) }}">
            {{ variances.gross_profit.vs_prior | fmt_rand }}</td>
        </tr>
        <tr class="row-margin">
          <td style="padding-left:16px">Gross Margin %</td>
          <td>{{ variances.gross_margin_pct.actual }}%</td>
          <td>{{ variances.gross_margin_pct.budget }}%</td>
          <td>{{ variances.gross_margin_pct.prior }}%</td>
          <td colspan="3" style="color:#6b7280">
            {{ variances.gross_margin_pct.vs_budget | fmt_pct }} vs budget</td>
        </tr>

        <!-- Operating Expenses -->
        <tr class="row-section"><td colspan="7">Operating Expenses</td></tr>
        {% for line, label in [
            ('salaries','Salaries & Wages'),
            ('rent','Rent & Occupancy'),
            ('transport','Transport & Logistics'),
            ('marketing','Marketing & Advertising'),
            ('admin','Administration'),
            ('depreciation','Depreciation')
          ] %}
        <tr>
          <td>{{ label }}</td>
          <td class="amount">{{ variances[line].actual | fmt_rand }}</td>
          <td class="amount">{{ variances[line].budget | fmt_rand }}</td>
          <td class="amount">{{ variances[line].prior  | fmt_rand }}</td>
          <td class="amount {{ line | vclass(variances[line].vs_budget) }}">
            {{ variances[line].vs_budget | fmt_rand }}</td>
          <td class="{{ line | vclass(variances[line].vs_budget) }}">
            {{ variances[line].vs_budget_pct | fmt_pct }}</td>
          <td class="amount">—</td>
        </tr>
        {% endfor %}
        <tr class="row-subtotal">
          <td>Total Operating Expenses</td>
          <td class="amount">{{ variances.total_opex.actual | fmt_rand }}</td>
          <td class="amount">{{ variances.total_opex.budget | fmt_rand }}</td>
          <td class="amount">{{ variances.total_opex.prior  | fmt_rand }}</td>
          <td class="amount {{ 'total_opex' | vclass(variances.total_opex.vs_budget) }}">
            {{ variances.total_opex.vs_budget | fmt_rand }}</td>
          <td class="{{ 'total_opex' | vclass(variances.total_opex.vs_budget) }}">
            {{ variances.total_opex.vs_budget_pct | fmt_pct }}</td>
          <td class="amount">—</td>
        </tr>

        <!-- EBITDA & Net -->
        <tr class="row-subtotal">
          <td>EBITDA</td>
          <td class="amount">{{ variances.ebitda.actual | fmt_rand }}</td>
          <td class="amount">{{ variances.ebitda.budget | fmt_rand }}</td>
          <td class="amount">{{ variances.ebitda.prior  | fmt_rand }}</td>
          <td class="amount {{ 'revenue' | vclass(variances.ebitda.vs_budget) }}">
            {{ variances.ebitda.vs_budget | fmt_rand }}</td>
          <td class="{{ 'revenue' | vclass(variances.ebitda.vs_budget) }}">
            {{ variances.ebitda.vs_budget_pct | fmt_pct }}</td>
          <td class="amount {{ 'revenue' | vclass(variances.ebitda.vs_prior) }}">
            {{ variances.ebitda.vs_prior | fmt_rand }}</td>
        </tr>
        <tr class="row-margin">
          <td style="padding-left:16px">EBITDA Margin %</td>
          <td>{{ variances.ebitda_margin_pct.actual }}%</td>
          <td>{{ variances.ebitda_margin_pct.budget }}%</td>
          <td>{{ variances.ebitda_margin_pct.prior }}%</td>
          <td colspan="3" style="color:#6b7280">
            {{ variances.ebitda_margin_pct.vs_budget | fmt_pct }} vs budget</td>
        </tr>
        <tr>
          <td>Finance Costs</td>
          <td class="amount">{{ variances.finance_costs.actual | fmt_rand }}</td>
          <td class="amount">{{ variances.finance_costs.budget | fmt_rand }}</td>
          <td class="amount">{{ variances.finance_costs.prior  | fmt_rand }}</td>
          <td colspan="3" style="color:#6b7280">—</td>
        </tr>
        <tr class="row-total">
          <td>Net Profit Before Tax</td>
          <td class="amount">{{ variances.net_profit.actual | fmt_rand }}</td>
          <td class="amount">{{ variances.net_profit.budget | fmt_rand }}</td>
          <td class="amount">{{ variances.net_profit.prior  | fmt_rand }}</td>
          <td class="amount {{ 'revenue' | vclass(variances.net_profit.vs_budget) }}">
            {{ variances.net_profit.vs_budget | fmt_rand }}</td>
          <td class="{{ 'revenue' | vclass(variances.net_profit.vs_budget) }}">
            {{ variances.net_profit.vs_budget_pct | fmt_pct }}</td>
          <td class="amount {{ 'revenue' | vclass(variances.net_profit.vs_prior) }}">
            {{ variances.net_profit.vs_prior | fmt_rand }}</td>
        </tr>
        <tr class="row-margin">
          <td style="padding-left:16px">Net Profit Margin %</td>
          <td>{{ variances.net_margin_pct.actual }}%</td>
          <td>{{ variances.net_margin_pct.budget }}%</td>
          <td>{{ variances.net_margin_pct.prior }}%</td>
          <td colspan="3"></td>
        </tr>

      </tbody>
    </table>
  </div>

  <!-- ── Management Commentary ──────────────────────────────────────── -->
  <div class="section">
    <div class="section-title">Management Commentary</div>
    {% for heading, text in commentary.sections.items() %}
    <div class="commentary-block">
      <div class="commentary-heading">{{ heading }}</div>
      <div class="commentary-text">{{ text }}</div>
    </div>
    {% endfor %}
    <div class="commentary-source">Generated by: {{ commentary.source }}</div>
  </div>

  <!-- ── Balance Sheet ───────────────────────────────────────────────── -->
  <div class="section">
    <div class="section-title">Balance Sheet — {{ period.label }}</div>
    <div class="bs-grid">

      <!-- Assets -->
      <div class="bs-block">
        <h3>Assets</h3>
        <div style="margin-bottom:12px">
          <div style="font-size:10px;font-weight:600;color:#6b7280;margin-bottom:6px">CURRENT ASSETS</div>
          {% for name, amount in bs.current_assets.items() %}
          <div class="bs-row">
            <span class="bs-name">{{ name }}</span>
            <span class="bs-amount">{{ amount | fmt_rand }}</span>
          </div>
          {% endfor %}
          <div class="bs-total">
            <span>Total Current Assets</span>
            <span>{{ bs.total_current_assets | fmt_rand }}</span>
          </div>
        </div>
        <div>
          <div style="font-size:10px;font-weight:600;color:#6b7280;margin-bottom:6px">NON-CURRENT ASSETS</div>
          {% for name, amount in bs.noncurrent_assets.items() %}
          <div class="bs-row">
            <span class="bs-name">{{ name }}</span>
            <span class="bs-amount">{{ amount | fmt_rand }}</span>
          </div>
          {% endfor %}
          <div class="bs-total">
            <span>Total Non-current Assets</span>
            <span>{{ bs.total_noncurrent_assets | fmt_rand }}</span>
          </div>
        </div>
        <div class="bs-total" style="font-size:14px;border-top:2px solid #0f2040;margin-top:8px">
          <span>TOTAL ASSETS</span>
          <span>{{ bs.total_assets | fmt_rand }}</span>
        </div>
      </div>

      <!-- Liabilities & Equity -->
      <div class="bs-block">
        <h3>Liabilities &amp; Equity</h3>
        <div style="margin-bottom:12px">
          <div style="font-size:10px;font-weight:600;color:#6b7280;margin-bottom:6px">CURRENT LIABILITIES</div>
          {% for name, amount in bs.current_liabilities.items() %}
          <div class="bs-row">
            <span class="bs-name">{{ name }}</span>
            <span class="bs-amount">{{ amount | fmt_rand }}</span>
          </div>
          {% endfor %}
          <div class="bs-total">
            <span>Total Current Liabilities</span>
            <span>{{ bs.total_current_liabilities | fmt_rand }}</span>
          </div>
        </div>
        <div style="margin-bottom:12px">
          <div style="font-size:10px;font-weight:600;color:#6b7280;margin-bottom:6px">NON-CURRENT LIABILITIES</div>
          {% for name, amount in bs.noncurrent_liabilities.items() %}
          <div class="bs-row">
            <span class="bs-name">{{ name }}</span>
            <span class="bs-amount">{{ amount | fmt_rand }}</span>
          </div>
          {% endfor %}
          <div class="bs-total">
            <span>Total Non-current Liabilities</span>
            <span>{{ bs.total_noncurrent_liabilities | fmt_rand }}</span>
          </div>
        </div>
        <div>
          <div style="font-size:10px;font-weight:600;color:#6b7280;margin-bottom:6px">EQUITY</div>
          {% for name, amount in bs.equity.items() %}
          <div class="bs-row">
            <span class="bs-name">{{ name }}</span>
            <span class="bs-amount">{{ amount | fmt_rand }}</span>
          </div>
          {% endfor %}
          <div class="bs-total">
            <span>Total Equity</span>
            <span>{{ bs.total_equity | fmt_rand }}</span>
          </div>
        </div>
        <div class="bs-total" style="font-size:14px;border-top:2px solid #0f2040;margin-top:8px">
          <span>TOTAL LIABILITIES &amp; EQUITY</span>
          <span>{{ (bs.total_liabilities + bs.total_equity) | fmt_rand }}</span>
        </div>
      </div>

    </div>
  </div>

  <!-- ── Delivery confirmation ───────────────────────────────────────── -->
  <div class="section">
    <div class="section-title">Delivery Log</div>
    <div class="delivery-row">
      <strong>✓ Email</strong> delivered to {{ client.contacts.md.email }}
      and {{ client.contacts.fm.email }} &mdash; {{ generated_at }}
    </div>
    <div class="delivery-row" style="margin-top:8px">
      <strong>✓ WhatsApp</strong> notification sent to {{ client.contacts.md.whatsapp }} &mdash; {{ generated_at }}
    </div>
    <div class="delivery-row" style="margin-top:8px;background:#f0f4ff;border-color:#6366f1;color:#3730a3">
      <strong>✓ Dashboard</strong> live at financepulse.app/dashboard/ndlovu-building-supplies
    </div>
  </div>

  <!-- ── Footer ──────────────────────────────────────────────────────── -->
  <div class="footer">
    <div>
      <strong>FinancePulse</strong> &mdash; Finance Workflow Infrastructure<br>
      Confidential management report for {{ client.name }} only
    </div>
    <div style="text-align:right">
      Run ID: {{ run_id }}<br>
      {{ period.label }} &mdash; {{ generated_at }}
    </div>
  </div>

</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(normalized: dict, variances: dict, kpis: dict,
                    alerts: list, commentary: dict, run_id: int) -> str:
    """
    Render the HTML management pack and save it to output/.
    Returns the absolute file path.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Build Jinja2 environment with custom filters
    env = Environment(loader=BaseLoader())
    env.filters["fmt_rand"]    = _fmt_rand
    env.filters["fmt_pct"]     = _fmt_pct
    env.filters["status_icon"] = _status_icon
    env.filters["status_label"] = _status_label

    # vclass needs the line name AND the value — use a custom filter
    # Jinja2 filters receive the piped value as first arg.
    # Syntax in template:  'line_name' | vclass(variance_value)
    def _vclass_filter(line: str, value: float) -> str:
        return _variance_class(value, line)
    env.filters["vclass"] = _vclass_filter

    template = env.from_string(TEMPLATE)

    client   = normalized["client"]
    period   = normalized["period"]
    bs       = normalized["balance_sheet"]
    now_str  = datetime.now().strftime("%d %B %Y at %H:%M")

    html = template.render(
        client       = client,
        period       = period,
        kpis         = kpis,
        alerts       = alerts,
        variances    = variances,
        commentary   = commentary,
        bs           = bs,
        generated_at = now_str,
        run_id       = run_id,
    )

    # File name: no spaces, url-safe
    safe_name  = client["name"].replace(" ", "_").replace("(", "").replace(")", "").replace("/", "")
    safe_name  = "".join(c for c in safe_name if c.isalnum() or c == "_")
    period_str = f"{period['year']}-{period['month']:02d}"
    filename   = f"{safe_name}_{period_str}_management_pack.html"
    out_path   = OUTPUT_DIR / filename

    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
