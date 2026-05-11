#!/usr/bin/env python3
"""
Terminal preview of the management pack.
Reads from the SQLite database and prints a formatted report.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "output" / "financepulse.db"

RESET  = "\033[0m";  BOLD  = "\033[1m";  DIM   = "\033[2m"
GREEN  = "\033[92m"; AMBER = "\033[93m"; RED   = "\033[91m"
BLUE   = "\033[94m"; CYAN  = "\033[96m"; WHITE = "\033[97m"
GREY   = "\033[90m"; PURP  = "\033[95m"; BG_DK = "\033[48;5;17m"

W = 72

def rule(char="─"): print(f"  {GREY}{char * W}{RESET}")
def blank(): print()

def header_box(title, subtitle, period):
    bar = "═" * W
    print(f"\n{BLUE}╔{bar}╗{RESET}")
    pad = W - len(title) - 2
    print(f"{BLUE}║{RESET}  {BOLD}{WHITE}{title}{RESET}{' ' * pad}  {BLUE}║{RESET}")
    pad = W - len(subtitle) - 2
    print(f"{BLUE}║{RESET}  {GREY}{subtitle}{RESET}{' ' * pad}  {BLUE}║{RESET}")
    pad = W - len(period) - 10
    print(f"{BLUE}║{RESET}  {CYAN}Period: {BOLD}{period}{RESET}{' ' * pad}  {BLUE}║{RESET}")
    print(f"{BLUE}╚{bar}╝{RESET}\n")

def section(title):
    blank()
    print(f"  {BOLD}{WHITE}{title.upper()}{RESET}")
    rule()

def traffic(status):
    return {
        "green": f"{GREEN}●{RESET}",
        "amber": f"{AMBER}●{RESET}",
        "red":   f"{RED}●{RESET}",
    }.get(status, "·")

def var_colour(value, is_revenue_line=True):
    if value is None or value == 0: return GREY
    good = value > 0 if is_revenue_line else value < 0
    return GREEN if good else RED

def fmt(amount):
    if amount is None: return "—"
    return f"R{abs(amount):>12,.0f}"

def fmt_pct(v):
    if v is None: return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Client + period ───────────────────────────────────────────────────
    run = dict(conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone())
    client = dict(conn.execute(
        "SELECT * FROM clients WHERE id = ?", (run["client_id"],)
    ).fetchone())
    period = run["period"]

    header_box(
        client["name"],
        f"Management Accounts  |  {client['industry']}",
        period,
    )

    # ── KPIs ──────────────────────────────────────────────────────────────
    section("Key Performance Indicators")
    kpis = [dict(r) for r in conn.execute(
        "SELECT * FROM kpis WHERE run_id = ?", (run["id"],)
    ).fetchall()]

    col_w = 26
    for kpi in kpis:
        dot    = traffic(kpi["status"])
        val    = f"{kpi['value']}{kpi['unit']}"
        tgt    = f"target {kpi['target']}{kpi['unit']}"
        status = {"green": f"{GREEN}ON TARGET{RESET}",
                  "amber": f"{AMBER}BELOW TARGET{RESET}",
                  "red":   f"{RED}  ALERT{RESET}"}.get(kpi["status"], "")
        pad = col_w - len(kpi["kpi_label"])
        print(f"  {dot}  {BOLD}{kpi['kpi_label']}{RESET}{' ' * pad}"
              f"  {BOLD}{val:<14}{RESET}  {GREY}{tgt:<18}{RESET}  {status}")

    # ── Alerts ────────────────────────────────────────────────────────────
    alerts = [dict(r) for r in conn.execute(
        "SELECT * FROM alerts WHERE run_id = ?", (run["id"],)
    ).fetchall()]

    if alerts:
        blank()
        section("Alerts Triggered")
        for a in alerts:
            icon = f"{RED}▲{RESET}" if a["severity"] == "HIGH" else f"{AMBER}▲{RESET}"
            col  = RED if a["severity"] == "HIGH" else AMBER
            print(f"  {icon}  {col}[{a['severity']}]{RESET}  {a['kpi_label']}: {a['message']}")

    # ── Income Statement ──────────────────────────────────────────────────
    section("Income Statement")

    rows = {r["line_item"]: dict(r) for r in conn.execute(
        "SELECT * FROM actuals_monthly WHERE run_id = ?", (run["id"],)
    ).fetchall()}

    hdr = (f"  {'Line Item':<26}  {'Actual':>14}  {'Budget':>14}  "
           f"{'Prior Month':>14}  {'Var Budget':>10}  {'%':>7}")
    print(f"{GREY}{hdr}{RESET}")
    rule()

    GROUPS = [
        ("REVENUE",           ["revenue"],                              True),
        ("COST OF SALES",     ["cogs"],                                 False),
        ("GROSS PROFIT",      ["gross_profit"],                         True),
        ("OPERATING EXPENSES",["salaries","rent","transport",
                               "marketing","admin","depreciation",
                               "total_opex"],                           False),
        ("EBITDA",            ["ebitda"],                               True),
        ("FINANCE COSTS",     ["finance_costs"],                        False),
        ("NET PROFIT",        ["net_profit"],                           True),
    ]

    LABELS = {
        "revenue": "Revenue", "cogs": "Cost of Sales",
        "gross_profit": "Gross Profit", "gross_margin_pct": "  Gross Margin %",
        "salaries": "  Salaries & Wages", "rent": "  Rent & Occupancy",
        "transport": "  Transport & Logistics", "marketing": "  Marketing",
        "admin": "  Administration", "depreciation": "  Depreciation",
        "total_opex": "Total Operating Expenses",
        "ebit": "EBIT", "ebitda": "EBITDA", "ebitda_margin_pct": "  EBITDA Margin %",
        "finance_costs": "Finance Costs",
        "net_profit": "Net Profit Before Tax", "net_margin_pct": "  Net Margin %",
    }

    BOLD_LINES = {"revenue","gross_profit","total_opex","ebitda","net_profit"}
    MARGIN_LINES = {"gross_margin_pct","ebitda_margin_pct","net_margin_pct"}

    printed_groups = set()
    for group_label, lines, rev_like in GROUPS:
        # Print group header
        if group_label not in printed_groups:
            blank()
            print(f"  {GREY}{BOLD}{group_label}{RESET}")
            printed_groups.add(group_label)

        for line in lines:
            if line not in rows: continue
            r   = rows[line]
            lbl = LABELS.get(line, line)
            is_bold = line in BOLD_LINES

            vc  = var_colour(r["vs_budget"], rev_like)
            b   = BOLD if is_bold else ""

            print(f"  {b}{lbl:<26}{RESET}"
                  f"  {b}{fmt(r['actual']):>14}{RESET}"
                  f"  {GREY}{fmt(r['budget']):>14}{RESET}"
                  f"  {GREY}{fmt(r['prior']):>14}{RESET}"
                  f"  {vc}{fmt(r['vs_budget']):>10}{RESET}"
                  f"  {vc}{fmt_pct(r['vs_budget_pct']):>7}{RESET}")

            # Print margin line immediately after GP, EBITDA, Net Profit
            margin_key = {
                "gross_profit": "gross_margin_pct",
                "ebitda":       "ebitda_margin_pct",
                "net_profit":   "net_margin_pct",
            }.get(line)
            if margin_key and margin_key in rows:
                m = rows[margin_key]
                vc2 = var_colour(m["vs_budget"], True)
                print(f"  {DIM}{LABELS[margin_key]:<26}"
                      f"  {m['actual']:>13.1f}%"
                      f"  {GREY}{m['budget']:>13.1f}%{RESET}"
                      f"  {GREY}{m['prior']:>13.1f}%{RESET}"
                      f"  {vc2}{fmt_pct(m['vs_budget']):>10}{RESET}"
                      f"  {DIM}{'':>7}{RESET}")

        rule("·")

    # ── Balance Sheet ─────────────────────────────────────────────────────
    section("Balance Sheet")

    bs_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM balance_sheet_monthly WHERE run_id = ?", (run["id"],)
    ).fetchall()]

    def _bs_group(type_label, type_key):
        items = [r for r in bs_rows if r["account_type"] == type_key]
        if not items: return 0
        print(f"  {GREY}{type_label}{RESET}")
        total = 0
        for r in items:
            print(f"    {r['account_name']:<38}  {fmt(r['amount']):>14}")
            total += r["amount"]
        print(f"  {BOLD}  {'Total ' + type_label:<38}  {fmt(total):>14}{RESET}")
        blank()
        return total

    col1 = [
        ("CURRENT ASSETS",         "current_asset"),
        ("NON-CURRENT ASSETS",     "noncurrent_asset"),
    ]
    col2 = [
        ("CURRENT LIABILITIES",    "current_liability"),
        ("NON-CURRENT LIABILITIES","noncurrent_liability"),
        ("EQUITY",                 "equity"),
    ]

    print(f"  {BOLD}{'ASSETS':<44}{'LIABILITIES & EQUITY'}{RESET}")
    rule()

    totals = {}
    for label, key in col1 + col2:
        totals[key] = _bs_group(label, key)

    ta = totals.get("current_asset",0) + totals.get("noncurrent_asset",0)
    tl = totals.get("current_liability",0) + totals.get("noncurrent_liability",0)
    te = totals.get("equity",0)

    rule()
    print(f"  {BOLD}{'TOTAL ASSETS':<44}{fmt(ta):>14}{RESET}")
    print(f"  {BOLD}{'TOTAL LIABILITIES + EQUITY':<44}{fmt(tl + te):>14}{RESET}")

    # ── Commentary ────────────────────────────────────────────────────────
    section("Management Commentary")

    raw_text = conn.execute(
        "SELECT raw_text, source FROM commentary WHERE run_id = ?", (run["id"],)
    ).fetchone()

    if raw_text:
        source, text = raw_text["source"], raw_text["raw_text"]
        sections_order = [
            "EXECUTIVE SUMMARY", "REVENUE & GROSS PROFIT",
            "COST ANALYSIS", "BALANCE SHEET & LIQUIDITY",
        ]
        current, current_lines = None, []
        parsed = {}
        for line in text.strip().splitlines():
            s = line.strip()
            matched = next((h for h in sections_order if s.upper().startswith(h)), None)
            if matched:
                if current: parsed[current] = " ".join(current_lines)
                current, current_lines = matched, []
            elif s and current:
                current_lines.append(s)
        if current: parsed[current] = " ".join(current_lines)

        for heading in sections_order:
            body = parsed.get(heading, "")
            if not body: continue
            blank()
            print(f"  {PURP}{BOLD}{heading}{RESET}")
            # Word-wrap at ~68 chars
            words = body.split()
            line_buf, cur_len = [], 0
            for word in words:
                if cur_len + len(word) + 1 > 68:
                    print(f"    {' '.join(line_buf)}")
                    line_buf, cur_len = [word], len(word)
                else:
                    line_buf.append(word)
                    cur_len += len(word) + 1
            if line_buf:
                print(f"    {' '.join(line_buf)}")

        blank()
        print(f"  {GREY}Source: {source}{RESET}")

    # ── Delivery simulation ───────────────────────────────────────────────
    section("Delivery Log")
    print(f"  {GREEN}✓{RESET}  EMAIL      sipho@ndlovusupplies.co.za          (MD)")
    print(f"  {GREEN}✓{RESET}  EMAIL      zanele@ndlovusupplies.co.za         (FM)")
    print(f"  {CYAN}✓{RESET}  WHATSAPP   +27821234567                       (MD)")
    print(f"  {BLUE}✓{RESET}  DASHBOARD  financepulse.app/dashboard/ndlovu")

    blank()
    bar = "═" * W
    print(f"{GREEN}╔{bar}╗{RESET}")
    print(f"{GREEN}║{RESET}  {BOLD}{WHITE}END OF MANAGEMENT PACK  ·  {period}  ·  Run #{run['id']}{RESET}"
          + " " * (W - 38 - len(period)) + f"  {GREEN}║{RESET}")
    print(f"{GREEN}╚{bar}╝{RESET}\n")

    conn.close()


if __name__ == "__main__":
    main()
