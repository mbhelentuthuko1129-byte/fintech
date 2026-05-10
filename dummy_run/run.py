#!/usr/bin/env python3
"""
FinancePulse — Monthly Processing Engine
=========================================
Dummy run demonstrating the full business workflow for one client, one period.

In production this orchestration is handled by n8n:
  - Trigger:    Schedule node (1st working day of month, 06:00 SAST)
  - Each step:  n8n sub-workflow calling these same functions via HTTP or
                "Execute Code" nodes
  - Delivery:   n8n HTTP Request → WhatsApp (360Dialog) + Gmail API

Run locally:
  cd dummy_run
  python run.py
"""

import sys
import time
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Terminal colours (ANSI — works on Linux/macOS)
# ─────────────────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"
GREY   = "\033[90m"


def _r(amount: float) -> str:
    return f"R{abs(amount):>13,.0f}"


def _pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def _traffic(status: str) -> str:
    return {
        "green": f"{GREEN}●{RESET}",
        "amber": f"{YELLOW}●{RESET}",
        "red":   f"{RED}●{RESET}",
    }.get(status, "·")


def _tick(msg: str) -> None:
    print(f"    {GREEN}✓{RESET}  {msg}")


def _info(msg: str) -> None:
    print(f"       {GREY}{msg}{RESET}")


def _warn(msg: str) -> None:
    print(f"    {YELLOW}⚠{RESET}  {msg}")


def _elapsed(t: float) -> str:
    return f"{GREY}⏱  {time.time() - t:.2f}s{RESET}"


# ─────────────────────────────────────────────────────────────────────────────
# UI blocks
# ─────────────────────────────────────────────────────────────────────────────

def _banner(client_name: str, period: str) -> None:
    width = 64
    bar   = "═" * width
    now   = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    print()
    print(f"{BLUE}╔{bar}╗{RESET}")
    print(f"{BLUE}║{RESET}  {BOLD}{WHITE}FinancePulse  ▸  Monthly Processing Engine{RESET}"
          + " " * (width - 42) + f"{BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  {GREY}{'─' * (width - 2)}{RESET}  {BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  Client  : {BOLD}{client_name}{RESET}"
          + " " * max(0, width - 11 - len(client_name)) + f"{BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  Period  : {CYAN}{period}{RESET}"
          + " " * max(0, width - 11 - len(period)) + f"{BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  Run at  : {GREY}{now}{RESET}"
          + " " * max(0, width - 11 - len(now)) + f"{BLUE}║{RESET}")
    print(f"{BLUE}╚{bar}╝{RESET}")
    print()


def _step_header(number: int, total: int, label: str, sub: str) -> None:
    tag  = f"[{number}/{total}]"
    line = f"  {BOLD}{CYAN}{tag}{RESET}  {BOLD}{label}{RESET}  {GREY}── {sub}{RESET}"
    print()
    print("  " + "─" * 60)
    print(line)
    print()


def _step_done(t_start: float) -> None:
    print(f"\n    {_elapsed(t_start)}")


def _summary(normalized: dict, variances: dict, kpis: dict,
             alerts: list, report_path: str, run_id: int) -> None:
    """Print the final summary box."""
    cur    = normalized["income_statement"]["current"]
    client = normalized["client"]
    period = normalized["period"]["label"]

    width = 64
    bar   = "═" * width

    def _row(label: str, value: str, note: str = "", icon: str = "") -> None:
        content = f"  {label:<22}{BOLD}{value}{RESET}  {GREY}{note}{RESET}  {icon}"
        pad = max(0, width - 2 - len(label) - len(value) - len(note) - 4)
        print(f"{GREEN}║{RESET}  {label:<22}{BOLD}{WHITE}{value}{RESET}  "
              f"{GREY}{note}{RESET}{' ' * pad}{icon}  {GREEN}║{RESET}")

    rev_var_pct  = variances["revenue"]["vs_budget_pct"]
    gm           = cur["gross_margin_pct"]
    ebitda_m     = cur["ebitda_margin_pct"]
    np_m         = cur["net_margin_pct"]

    rev_icon   = f"{GREEN}✓{RESET}" if rev_var_pct >= -2 else (f"{YELLOW}⚠{RESET}" if rev_var_pct >= -8 else f"{RED}✗{RESET}")
    gm_icon    = f"{GREEN}✓{RESET}" if gm >= 33.5 else f"{YELLOW}⚠{RESET}"
    ebitda_icon= f"{YELLOW}⚠{RESET}" if ebitda_m < 15.9 else f"{GREEN}✓{RESET}"

    fname = Path(report_path).name if report_path else "—"

    print()
    print(f"{GREEN}╔{bar}╗{RESET}")
    print(f"{GREEN}║{RESET}  {BOLD}{WHITE}PROCESSING COMPLETE{RESET}"
          + " " * (width - 19) + f"  {GREEN}║{RESET}")
    print(f"{GREEN}║{RESET}  {GREY}{'─' * (width - 2)}{RESET}  {GREEN}║{RESET}")
    print(f"{GREEN}║{RESET}  {BOLD}Client{RESET}  : {client['name']}"
          + " " * max(0, width - 9 - len(client['name'])) + f"  {GREEN}║{RESET}")
    print(f"{GREEN}║{RESET}  {BOLD}Period{RESET}  : {period}"
          + " " * max(0, width - 9 - len(period)) + f"  {GREEN}║{RESET}")
    print(f"{GREEN}║{RESET}  {GREY}{'─' * (width - 2)}{RESET}  {GREEN}║{RESET}")

    def _fin_row(label, amount, note, icon):
        val = f"R{abs(amount):,.0f}"
        pad = max(0, width - 4 - len(label) - len(val) - len(note) - 4)
        print(f"{GREEN}║{RESET}  {label:<22}{BOLD}{WHITE}{val}{RESET}   "
              f"{GREY}{note:<18}{RESET}{' ' * pad}{icon}  {GREEN}║{RESET}")

    _fin_row("Revenue",      cur["revenue"],     f"vs budget {_pct(rev_var_pct)}",  rev_icon)
    _fin_row("Gross Profit", cur["gross_profit"],f"margin {gm}%",                   gm_icon)
    _fin_row("EBITDA",       cur["ebitda"],      f"margin {ebitda_m}%",             ebitda_icon)
    _fin_row("Net Profit",   cur["net_profit"],  f"margin {np_m}%",                 "")

    print(f"{GREEN}║{RESET}  {GREY}{'─' * (width - 2)}{RESET}  {GREEN}║{RESET}")

    alert_str = f"{len(alerts)} alert(s) triggered"
    print(f"{GREEN}║{RESET}  Alerts fired  : {RED if alerts else GREEN}{alert_str}{RESET}"
          + " " * max(0, width - 18 - len(alert_str)) + f"  {GREEN}║{RESET}")

    report_str = fname[:50] + ("…" if len(fname) > 50 else "")
    print(f"{GREEN}║{RESET}  Report        : {CYAN}{report_str}{RESET}"
          + " " * max(0, width - 18 - len(report_str)) + f"  {GREEN}║{RESET}")

    db_str = "output/financepulse.db"
    print(f"{GREEN}║{RESET}  Database      : {GREY}{db_str}{RESET}"
          + " " * max(0, width - 18 - len(db_str)) + f"  {GREEN}║{RESET}")

    run_str = f"#{run_id}"
    print(f"{GREEN}║{RESET}  Run ID        : {GREY}{run_str}{RESET}"
          + " " * max(0, width - 18 - len(run_str)) + f"  {GREEN}║{RESET}")

    print(f"{GREEN}║{RESET}  {GREY}{'─' * (width - 2)}{RESET}  {GREEN}║{RESET}")
    print(f"{GREEN}║{RESET}  {BOLD}Delivery (simulated){RESET}"
          + " " * (width - 21) + f"  {GREEN}║{RESET}")

    md_email = client["contacts"]["md"]["email"]
    fm_email = client["contacts"]["fm"]["email"]
    wa_num   = client["contacts"]["md"]["whatsapp"]

    for label, dest in [("EMAIL", md_email), ("EMAIL", fm_email), ("WHATSAPP", wa_num)]:
        line = f"{label:<10}{dest}"
        pad  = max(0, width - 4 - len(line))
        print(f"{GREEN}║{RESET}  {GREEN}✓{RESET} {GREY}{label:<10}{RESET}{dest}"
              + " " * pad + f"  {GREEN}║{RESET}")

    print(f"{GREEN}╚{bar}╝{RESET}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main workflow
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    sys.path.insert(0, str(Path(__file__).parent))

    # ── Step 1: Extract ────────────────────────────────────────────────────
    from mock_xero import get_financial_data

    t0 = time.time()
    raw = get_financial_data()
    client_name = raw["client"]["name"]
    period_label = raw["period"]["label"]

    _banner(client_name, period_label)

    _step_header(1, 6, "EXTRACT", "Pulling data from Xero API")
    t = time.time()
    n_current = len(raw["profit_loss"]["current"])
    n_prior   = len(raw["profit_loss"]["prior"])
    n_bs      = len(raw["balance_sheet"]["current"])
    _tick(f"Connected  →  tenant: {raw['client']['tenant_id']}")
    _tick(f"P&L accounts pulled    : {n_current} lines  ({period_label})")
    _tick(f"Prior period pulled    : {n_prior} lines  ({raw['period']['prior_label']})")
    _tick(f"Balance sheet pulled   : {n_bs} lines")
    _tick(f"Budget data loaded     : {len(raw['budget'])} categories")
    _step_done(t)

    # ── Step 2: Normalize ──────────────────────────────────────────────────
    from processor import normalize, ACCOUNT_MAP, OPEX_CATEGORIES

    _step_header(2, 6, "NORMALIZE", "Mapping chart of accounts → standard categories")
    t = time.time()
    normalized = normalize(raw)
    is_cur = normalized["income_statement"]["current"]

    from collections import Counter
    category_counts = Counter(
        ACCOUNT_MAP.get(line["code"], "unmapped")
        for line in raw["profit_loss"]["current"]
    )
    for cat, count in sorted(category_counts.items()):
        amount = is_cur.get(cat, 0)
        if amount:
            _tick(f"{cat:<16}  {count} accounts  →  R{amount:,.0f}")
        else:
            _tick(f"{cat:<16}  {count} accounts")
    unmapped = [l for l in raw["profit_loss"]["current"]
                if l["code"] not in ACCOUNT_MAP]
    if unmapped:
        _warn(f"{len(unmapped)} account(s) unmapped — check ACCOUNT_MAP")
    _step_done(t)

    # ── Step 3: Variances & KPIs ───────────────────────────────────────────
    from processor import calculate_variances, compute_kpis, check_alerts

    _step_header(3, 6, "VARIANCES & KPIs", "Computing variances and traffic-light KPIs")
    t = time.time()

    variances = calculate_variances(normalized)
    kpis      = compute_kpis(normalized)
    alerts    = check_alerts(kpis)

    # Print key variances
    key_lines = [
        ("Revenue",      "revenue",      True),
        ("Gross Profit", "gross_profit", True),
        ("Total OpEx",   "total_opex",   False),
        ("EBITDA",       "ebitda",       True),
        ("Net Profit",   "net_profit",   True),
    ]
    print(f"    {'Line Item':<18} {'Actual':>14}  {'Budget':>14}  {'Var (Budget)':>14}  {'Var %':>8}")
    print("    " + "─" * 74)
    for label, key, fav_positive in key_lines:
        v   = variances[key]
        vb  = v["vs_budget"]
        vbp = v["vs_budget_pct"]
        col = GREEN if (vb >= 0) == fav_positive else RED
        print(f"    {label:<18} {_r(v['actual'])}  {_r(v['budget'])}  "
              f"{col}{_r(vb)}{RESET}  {col}{_pct(vbp):>8}{RESET}")

    print()
    print(f"    {'KPI':<25} {'Value':>10}  {'Target':>10}  {'Status'}")
    print("    " + "─" * 60)
    for key, kpi in kpis.items():
        icon  = _traffic(kpi["status"])
        label = kpi["status_label"] if "status_label" in kpi else kpi["status"].upper()
        status_text = {"green": "ON TARGET", "amber": "BELOW TARGET", "red": "ALERT"}.get(kpi["status"], "")
        col   = {"green": GREEN, "amber": YELLOW, "red": RED}.get(kpi["status"], "")
        print(f"    {icon}  {kpi['label']:<23} {str(kpi['value']) + kpi['unit']:>10}  "
              f"{str(kpi['target']) + kpi['unit']:>10}  {col}{status_text}{RESET}")

    print()
    if alerts:
        for alert in alerts:
            severity_col = RED if alert["severity"] == "HIGH" else YELLOW
            print(f"    {severity_col}▲  [{alert['severity']}]{RESET}  {alert['message']}")
    else:
        print(f"    {GREEN}✓  No alerts triggered{RESET}")

    _step_done(t)

    # ── Step 4: AI Commentary ──────────────────────────────────────────────
    from ai_commentary import generate_commentary

    _step_header(4, 6, "COMMENTARY", "Generating AI variance commentary")
    t = time.time()
    commentary = generate_commentary(
        variances, kpis,
        client_name  = client_name,
        period       = period_label,
    )
    _tick(f"Source      : {commentary['source']}")
    _tick(f"Word count  : {commentary['words']} words")
    _tick(f"Sections    : {', '.join(commentary['sections'].keys())}")
    print()
    for heading, text in list(commentary["sections"].items())[:1]:
        print(f"    {GREY}Preview — {heading}:{RESET}")
        preview = text[:200] + ("…" if len(text) > 200 else "")
        print(f"    {DIM}{preview}{RESET}")
    _step_done(t)

    # ── Step 5: Database ───────────────────────────────────────────────────
    import database as db

    _step_header(5, 6, "DATABASE", "Persisting results to SQLite (→ Supabase in production)")
    t = time.time()
    db.initialize()
    run_id, counts = db.store_results(
        normalized, variances, kpis, commentary, alerts,
        report_path="(pending)"
    )
    _tick(f"Run #{run_id} created")
    _tick(f"Income statement lines stored : {counts['income_statement_lines']}")
    _tick(f"KPIs stored                   : {counts['kpis']}")
    _tick(f"Alerts stored                 : {counts['alerts']}")
    _tick(f"Balance sheet lines stored    : {counts['balance_sheet_lines']}")
    _tick(f"Database file                 : output/financepulse.db")
    _step_done(t)

    # ── Step 6: Report ─────────────────────────────────────────────────────
    from report import generate_report

    _step_header(6, 6, "REPORT", "Generating HTML management pack")
    t = time.time()
    report_path = generate_report(normalized, variances, kpis, alerts, commentary, run_id)
    _tick(f"HTML rendered  (7 sections)")
    _tick(f"Saved          → {report_path}")
    _info("In production: upload to Supabase Storage → send PDF link via WhatsApp + email")
    _step_done(t)

    # ── Delivery simulation ────────────────────────────────────────────────
    contacts = raw["client"]["contacts"]
    print()
    print(f"  {GREY}── Delivery Simulation {'─' * 37}{RESET}")
    for channel, destination, detail in [
        ("EMAIL",    contacts["md"]["email"], "(Management Pack PDF attached)"),
        ("EMAIL",    contacts["fm"]["email"], "(Management Pack PDF attached)"),
        ("WHATSAPP", contacts["md"]["whatsapp"], "(PDF link + alert summary)"),
        ("DASHBOARD","financepulse.app/dashboard/ndlovu", "(auto-refreshed)"),
    ]:
        col = GREEN if channel == "EMAIL" else (CYAN if channel == "WHATSAPP" else BLUE)
        print(f"    {col}✓  {channel:<12}{RESET}  {destination:<40}  {GREY}{detail}{RESET}")

    # ── Final summary ──────────────────────────────────────────────────────
    _summary(normalized, variances, kpis, alerts, report_path, run_id)

    total = time.time() - t0
    print(f"  {GREY}Total elapsed: {total:.2f}s  |  "
          f"Open {Path(report_path).name} in your browser to view the management pack.{RESET}")
    print()


if __name__ == "__main__":
    main()
