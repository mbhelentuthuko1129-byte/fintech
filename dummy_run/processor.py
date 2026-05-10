"""
Data processor: chart-of-accounts mapping → variance calculation → KPI computation.

In production:
  - ACCOUNT_MAP lives in Supabase table `chart_of_accounts_mapping`, keyed by client_id.
  - KPI_THRESHOLDS live in Supabase table `client_kpis`, keyed by client_id.
  - This module runs inside an n8n "Execute Code" node or a Python microservice.

The hardest onboarding task is building ACCOUNT_MAP for each client.
Every business has a different chart of accounts — this mapping is what turns
messy raw Xero data into clean, comparable management account line items.
"""

# ── Chart of accounts → standard category ────────────────────────────────────
# Key  = Xero account code (string)
# Value = standard reporting category used in management accounts
# This mapping is configured once per client during onboarding (3–8 hours work).

ACCOUNT_MAP: dict[str, str] = {
    # Revenue
    "4000": "revenue",      "4001": "revenue",       "4002": "revenue",
    # Cost of Sales
    "5000": "cogs",         "5001": "cogs",          "5002": "cogs",
    # Salaries & Wages
    "6000": "salaries",     "6001": "salaries",      "6002": "salaries",     "6003": "salaries",
    # Rent & Occupancy
    "6100": "rent",         "6101": "rent",
    # Transport & Logistics
    "6200": "transport",    "6201": "transport",     "6202": "transport",
    # Marketing
    "6300": "marketing",    "6301": "marketing",
    # Administration
    "6400": "admin",        "6401": "admin",         "6402": "admin",        "6403": "admin",
    # Depreciation
    "6500": "depreciation", "6501": "depreciation",
    # Finance Costs
    "7000": "finance_costs","7001": "finance_costs",
}

OPEX_CATEGORIES = ["salaries", "rent", "transport", "marketing", "admin", "depreciation"]

# ── KPI alert thresholds (configured per client during onboarding) ─────────────
KPI_THRESHOLDS = {
    "gross_margin_pct":      {"target": 35.0, "direction": "above", "tolerance": -1.5},
    "ebitda_margin_pct":     {"budget_tolerance_pct": -5.0},   # alert if >5% below budget
    "net_margin_pct":        {"budget_tolerance_pct": -8.0},
    "debtor_days":           {"target": 45.0, "direction": "below"},
    "current_ratio":         {"target": 1.50, "direction": "above"},
    "revenue_vs_budget_pct": {"threshold": -5.0},              # alert if >5% below budget
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sum_category(lines: list[dict], category: str) -> float:
    """Sum absolute values of all account lines that map to `category`."""
    return sum(
        abs(line["amount"])
        for line in lines
        if ACCOUNT_MAP.get(line["code"]) == category
    )


def _build_income_statement(lines: list[dict]) -> dict:
    """Collapse raw Xero lines into a standard income statement structure."""
    rev  = _sum_category(lines, "revenue")
    cogs = _sum_category(lines, "cogs")
    gp   = rev - cogs
    sal  = _sum_category(lines, "salaries")
    rnt  = _sum_category(lines, "rent")
    trn  = _sum_category(lines, "transport")
    mkt  = _sum_category(lines, "marketing")
    adm  = _sum_category(lines, "admin")
    dep  = _sum_category(lines, "depreciation")
    fin  = _sum_category(lines, "finance_costs")
    opex = sal + rnt + trn + mkt + adm + dep
    ebit = gp - opex

    return {
        "revenue":           rev,
        "cogs":              cogs,
        "gross_profit":      gp,
        "gross_margin_pct":  round(gp / rev * 100, 1) if rev else 0.0,
        "salaries":          sal,
        "rent":              rnt,
        "transport":         trn,
        "marketing":         mkt,
        "admin":             adm,
        "depreciation":      dep,
        "total_opex":        opex,
        "ebit":              ebit,
        "ebitda":            ebit + dep,
        "ebitda_margin_pct": round((ebit + dep) / rev * 100, 1) if rev else 0.0,
        "finance_costs":     fin,
        "net_profit":        ebit - fin,
        "net_margin_pct":    round((ebit - fin) / rev * 100, 1) if rev else 0.0,
    }


def _build_budget_is(budget: dict) -> dict:
    """Convert the flat budget dict into the same income statement shape."""
    rev  = budget["revenue"]
    cogs = budget["cogs"]
    gp   = rev - cogs
    opex = (budget["salaries"] + budget["rent"] + budget["transport"]
            + budget["marketing"] + budget["admin"] + budget["depreciation"])
    ebit = gp - opex
    fin  = budget["finance_costs"]
    dep  = budget["depreciation"]

    return {
        "revenue":           rev,
        "cogs":              cogs,
        "gross_profit":      gp,
        "gross_margin_pct":  round(gp / rev * 100, 1),
        "salaries":          budget["salaries"],
        "rent":              budget["rent"],
        "transport":         budget["transport"],
        "marketing":         budget["marketing"],
        "admin":             budget["admin"],
        "depreciation":      dep,
        "total_opex":        opex,
        "ebit":              ebit,
        "ebitda":            ebit + dep,
        "ebitda_margin_pct": round((ebit + dep) / rev * 100, 1),
        "finance_costs":     fin,
        "net_profit":        ebit - fin,
        "net_margin_pct":    round((ebit - fin) / rev * 100, 1),
    }


def _build_balance_sheet(bs_lines: list[dict]) -> dict:
    """Organise raw balance sheet lines into asset / liability / equity buckets."""
    def _group(type_: str) -> dict:
        return {l["name"]: l["amount"] for l in bs_lines if l["type"] == type_}

    ca  = _group("current_asset")
    nca = _group("noncurrent_asset")
    cl  = _group("current_liability")
    ncl = _group("noncurrent_liability")
    eq  = _group("equity")

    return {
        "current_assets":             ca,
        "noncurrent_assets":          nca,
        "current_liabilities":        cl,
        "noncurrent_liabilities":     ncl,
        "equity":                     eq,
        "total_current_assets":       sum(ca.values()),
        "total_noncurrent_assets":    sum(nca.values()),
        "total_assets":               sum(ca.values()) + sum(nca.values()),
        "total_current_liabilities":  sum(cl.values()),
        "total_noncurrent_liabilities": sum(ncl.values()),
        "total_liabilities":          sum(cl.values()) + sum(ncl.values()),
        "total_equity":               sum(eq.values()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def normalize(raw: dict) -> dict:
    """
    Map raw Xero output into clean, structured management account data.
    Returns the canonical `normalized` dict consumed by all downstream steps.
    """
    return {
        "client":  raw["client"],
        "period":  raw["period"],
        "income_statement": {
            "current": _build_income_statement(raw["profit_loss"]["current"]),
            "prior":   _build_income_statement(raw["profit_loss"]["prior"]),
            "budget":  _build_budget_is(raw["budget"]),
        },
        "balance_sheet": _build_balance_sheet(raw["balance_sheet"]["current"]),
        "raw_account_lines": {
            "current": raw["profit_loss"]["current"],
            "prior":   raw["profit_loss"]["prior"],
        },
    }


IS_LINES = [
    "revenue", "cogs", "gross_profit",
    "salaries", "rent", "transport", "marketing", "admin", "depreciation",
    "total_opex", "ebit", "ebitda", "finance_costs", "net_profit",
]
PCT_LINES = ["gross_margin_pct", "ebitda_margin_pct", "net_margin_pct"]


def calculate_variances(normalized: dict) -> dict:
    """
    For every income statement line compute:
      - actual / budget / prior values
      - absolute variance vs budget and vs prior
      - percentage variance vs budget and vs prior

    Variance sign convention (matches management account norms):
      Revenue:    positive variance = above budget (good)
      Expenses:   positive variance = over budget  (bad) — caller interprets sign
    """
    cur = normalized["income_statement"]["current"]
    bud = normalized["income_statement"]["budget"]
    pri = normalized["income_statement"]["prior"]

    variances: dict = {}

    for line in IS_LINES:
        a, b, p = cur[line], bud[line], pri[line]
        vb = a - b
        vp = a - p
        variances[line] = {
            "actual":        a,
            "budget":        b,
            "prior":         p,
            "vs_budget":     vb,
            "vs_budget_pct": round(vb / b * 100, 1) if b else 0.0,
            "vs_prior":      vp,
            "vs_prior_pct":  round(vp / p * 100, 1) if p else 0.0,
        }

    for line in PCT_LINES:
        a, b, p = cur[line], bud[line], pri[line]
        variances[line] = {
            "actual":    a,
            "budget":    b,
            "prior":     p,
            "vs_budget": round(a - b, 1),
            "vs_prior":  round(a - p, 1),
        }

    return variances


def compute_kpis(normalized: dict) -> dict:
    """
    Compute the 7 standard KPIs and assign a traffic-light status.
    Status: 'green' | 'amber' | 'red'
    """
    cur = normalized["income_statement"]["current"]
    bud = normalized["income_statement"]["budget"]
    bs  = normalized["balance_sheet"]
    rev = cur["revenue"]

    # Debtor days = (Trade Debtors / Annualised Revenue) × 365
    trade_debtors  = bs["current_assets"].get("Trade Debtors", 0)
    annual_rev     = rev * 12
    debtor_days    = round((trade_debtors / annual_rev) * 365, 1) if annual_rev else 0.0

    # Creditor days = (Trade Creditors / Annualised COGS) × 365
    trade_creditors = bs["current_liabilities"].get("Trade Creditors", 0)
    annual_cogs     = cur["cogs"] * 12
    creditor_days   = round((trade_creditors / annual_cogs) * 365, 1) if annual_cogs else 0.0

    # Current ratio = Current Assets / Current Liabilities
    current_ratio = round(
        bs["total_current_assets"] / bs["total_current_liabilities"], 2
    ) if bs["total_current_liabilities"] else 0.0

    # Revenue vs budget %
    rev_vs_bud_pct = round((rev - bud["revenue"]) / bud["revenue"] * 100, 1) if bud["revenue"] else 0.0

    def _status_threshold(value: float, target: float, direction: str,
                           tolerance: float = 0.0) -> str:
        """Return green/amber/red based on distance from target."""
        if direction == "above":
            if value >= target + tolerance:
                return "green"
            if value >= target - 3:
                return "amber"
            return "red"
        else:  # direction == "below"
            if value <= target:
                return "green"
            if value <= target * 1.20:
                return "amber"
            return "red"

    return {
        "gross_margin_pct": {
            "label":  "Gross Margin",
            "value":  cur["gross_margin_pct"],
            "budget": bud["gross_margin_pct"],
            "target": 35.0,
            "unit":   "%",
            "status": _status_threshold(cur["gross_margin_pct"], 35.0, "above", -1.5),
        },
        "ebitda_margin_pct": {
            "label":  "EBITDA Margin",
            "value":  cur["ebitda_margin_pct"],
            "budget": bud["ebitda_margin_pct"],
            "target": bud["ebitda_margin_pct"],
            "unit":   "%",
            "status": (
                "green" if cur["ebitda_margin_pct"] >= bud["ebitda_margin_pct"] * 0.95
                else "amber" if cur["ebitda_margin_pct"] >= bud["ebitda_margin_pct"] * 0.85
                else "red"
            ),
        },
        "net_margin_pct": {
            "label":  "Net Profit Margin",
            "value":  cur["net_margin_pct"],
            "budget": bud["net_margin_pct"],
            "target": bud["net_margin_pct"],
            "unit":   "%",
            "status": (
                "green" if cur["net_margin_pct"] >= bud["net_margin_pct"] * 0.92
                else "amber"
            ),
        },
        "revenue_vs_budget_pct": {
            "label":  "Revenue vs Budget",
            "value":  rev_vs_bud_pct,
            "budget": 0.0,
            "target": 0.0,
            "unit":   "%",
            "status": (
                "green" if rev_vs_bud_pct >= -2.0
                else "amber" if rev_vs_bud_pct >= -8.0
                else "red"
            ),
        },
        "debtor_days": {
            "label":  "Debtor Days",
            "value":  debtor_days,
            "budget": 45.0,
            "target": 45.0,
            "unit":   " days",
            "status": _status_threshold(debtor_days, 45.0, "below"),
        },
        "creditor_days": {
            "label":  "Creditor Days",
            "value":  creditor_days,
            "budget": 50.0,
            "target": 50.0,
            "unit":   " days",
            "status": "green",
        },
        "current_ratio": {
            "label":  "Current Ratio",
            "value":  current_ratio,
            "budget": 1.50,
            "target": 1.50,
            "unit":   "x",
            "status": _status_threshold(current_ratio, 1.50, "above"),
        },
    }


def check_alerts(kpis: dict) -> list[dict]:
    """
    Convert red/amber KPIs into structured alert objects.
    In production these are sent via WhatsApp (360Dialog) and email (Gmail API)
    by the n8n delivery workflow immediately after KPI computation.
    """
    alerts: list[dict] = []

    severity_map = {"red": "HIGH", "amber": "MEDIUM"}

    for key, kpi in kpis.items():
        if kpi["status"] in ("red", "amber"):
            severity = severity_map[kpi["status"]]
            val_str  = f"{kpi['value']}{kpi['unit']}"
            tgt_str  = f"{kpi['target']}{kpi['unit']}"

            alerts.append({
                "kpi":      kpi["label"],
                "severity": severity,
                "message":  (
                    f"{kpi['label']} is {val_str} "
                    f"({'above' if key == 'debtor_days' else 'below'} target of {tgt_str})"
                ),
                "whatsapp": (
                    f"*FinancePulse {'🔴 Alert' if severity == 'HIGH' else '🟡 Notice'}*\n"
                    f"*{kpi['label']}*: {val_str}  |  Target: {tgt_str}\n"
                    f"Please review your FinancePulse dashboard for details."
                ),
            })

    # Highest severity first
    alerts.sort(key=lambda a: 0 if a["severity"] == "HIGH" else 1)
    return alerts
