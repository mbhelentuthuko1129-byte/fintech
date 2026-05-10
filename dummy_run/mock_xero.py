"""
Mock Xero API — simulates the Xero Reports API response structure.

In production this module is replaced by live HTTP calls to:
  GET https://api.xero.com/api.xro/2.0/Reports/ProfitAndLoss
  GET https://api.xero.com/api.xro/2.0/Reports/BalanceSheet

Authentication uses OAuth2 — the access token is stored per-client in Supabase
and refreshed automatically by n8n before each monthly extraction.

Fictional client: Ndlovu Building Supplies (Pty) Ltd
Industry:         Wholesale — Building & Construction Materials
Location:         Johannesburg (Spartan warehouse, Sandton office)
Revenue:          ~R8M/month
Employees:        45
Accounting system: Xero (Johannesburg timezone, ZAR base currency)
"""


def get_financial_data() -> dict:
    """
    Return a dict mirroring what the real Xero P&L and Balance Sheet APIs return.
    Amounts are signed: revenue is positive, expenses are negative.
    """
    return {
        # ── Client metadata (stored in Supabase clients table) ───────────────
        "client": {
            "name":       "Ndlovu Building Supplies (Pty) Ltd",
            "tenant_id":  "ndlovu-bldg-0a1b2c3d-4e5f",
            "reg_number": "2018/123456/07",
            "vat_number": "4850123456",
            "industry":   "Wholesale — Building & Construction Materials",
            "currency":   "ZAR",
            "contacts": {
                "md": {
                    "name":     "Sipho Ndlovu",
                    "email":    "sipho@ndlovusupplies.co.za",
                    "whatsapp": "+27821234567",
                },
                "fm": {
                    "name":  "Zanele Dlamini",
                    "email": "zanele@ndlovusupplies.co.za",
                },
            },
        },

        # ── Period ────────────────────────────────────────────────────────────
        "period": {
            "month":       4,
            "year":        2026,
            "label":       "April 2026",
            "prior_label": "March 2026",
        },

        # ── Profit & Loss account lines ───────────────────────────────────────
        # Each entry = one Xero nominal account.
        # Revenue > 0  |  Expenses < 0  (Xero convention)
        "profit_loss": {
            "current": [
                # ── Revenue ──────────────────────────────────────────────────
                {"code": "4000", "name": "Hardware & Tools Sales",         "amount":  4_250_000},
                {"code": "4001", "name": "Cement & Building Materials",    "amount":  2_400_000},
                {"code": "4002", "name": "Timber & Wood Products",         "amount":  1_200_000},
                # ── Cost of Sales ─────────────────────────────────────────────
                {"code": "5000", "name": "Cost of Goods — Hardware",       "amount": -2_762_500},
                {"code": "5001", "name": "Cost of Goods — Cement",         "amount": -1_560_000},
                {"code": "5002", "name": "Cost of Goods — Timber",         "amount": -  780_000},
                # ── Salaries & Wages ──────────────────────────────────────────
                {"code": "6000", "name": "Basic Salaries",                 "amount": -  650_000},
                {"code": "6001", "name": "Overtime Pay",                   "amount": -   85_000},
                {"code": "6002", "name": "UIF & SDL Contributions",        "amount": -   45_000},
                {"code": "6003", "name": "Medical Aid Contributions",      "amount": -   76_000},
                # ── Rent & Occupancy ──────────────────────────────────────────
                {"code": "6100", "name": "Warehouse Rent — Spartan",       "amount": -  145_000},
                {"code": "6101", "name": "Office Rent — Sandton",          "amount": -   37_000},
                # ── Transport & Logistics ─────────────────────────────────────
                {"code": "6200", "name": "Delivery Fleet Fuel",            "amount": -  125_000},
                {"code": "6201", "name": "Vehicle Maintenance",            "amount": -   48_000},
                {"code": "6202", "name": "Third-party Logistics",          "amount": -  145_000},
                # ── Marketing ────────────────────────────────────────────────
                {"code": "6300", "name": "Digital Advertising",            "amount": -   43_000},
                {"code": "6301", "name": "Trade Promotions & Events",      "amount": -   40_000},
                # ── Administration ────────────────────────────────────────────
                {"code": "6400", "name": "Office Supplies & Stationery",   "amount": -   28_000},
                {"code": "6401", "name": "Telephone & Internet",           "amount": -   35_000},
                {"code": "6402", "name": "Bank Charges",                   "amount": -   28_000},
                {"code": "6403", "name": "Professional Fees",              "amount": -   57_000},
                # ── Depreciation ──────────────────────────────────────────────
                {"code": "6500", "name": "Depreciation — Fleet",           "amount": -   65_000},
                {"code": "6501", "name": "Depreciation — Equipment",       "amount": -   30_000},
                # ── Finance Costs ─────────────────────────────────────────────
                {"code": "7000", "name": "Interest on Term Loan",          "amount": -   95_000},
                {"code": "7001", "name": "Bank Overdraft Interest",        "amount": -   33_000},
            ],

            "prior": [
                # March 2026 actuals
                {"code": "4000", "name": "Hardware & Tools Sales",         "amount":  4_420_000},
                {"code": "4001", "name": "Cement & Building Materials",    "amount":  2_480_000},
                {"code": "4002", "name": "Timber & Wood Products",         "amount":  1_305_000},
                {"code": "5000", "name": "Cost of Goods — Hardware",       "amount": -2_873_000},
                {"code": "5001", "name": "Cost of Goods — Cement",         "amount": -1_612_000},
                {"code": "5002", "name": "Cost of Goods — Timber",         "amount": -  848_250},
                {"code": "6000", "name": "Basic Salaries",                 "amount": -  638_000},
                {"code": "6001", "name": "Overtime Pay",                   "amount": -   78_000},
                {"code": "6002", "name": "UIF & SDL Contributions",        "amount": -   44_000},
                {"code": "6003", "name": "Medical Aid Contributions",      "amount": -   82_000},
                {"code": "6100", "name": "Warehouse Rent — Spartan",       "amount": -  145_000},
                {"code": "6101", "name": "Office Rent — Sandton",          "amount": -   37_000},
                {"code": "6200", "name": "Delivery Fleet Fuel",            "amount": -  118_000},
                {"code": "6201", "name": "Vehicle Maintenance",            "amount": -   32_000},
                {"code": "6202", "name": "Third-party Logistics",          "amount": -  145_000},
                {"code": "6300", "name": "Digital Advertising",            "amount": -   47_000},
                {"code": "6301", "name": "Trade Promotions & Events",      "amount": -   44_000},
                {"code": "6400", "name": "Office Supplies & Stationery",   "amount": -   26_000},
                {"code": "6401", "name": "Telephone & Internet",           "amount": -   35_000},
                {"code": "6402", "name": "Bank Charges",                   "amount": -   27_000},
                {"code": "6403", "name": "Professional Fees",              "amount": -   55_000},
                {"code": "6500", "name": "Depreciation — Fleet",           "amount": -   65_000},
                {"code": "6501", "name": "Depreciation — Equipment",       "amount": -   30_000},
                {"code": "7000", "name": "Interest on Term Loan",          "amount": -   95_000},
                {"code": "7001", "name": "Bank Overdraft Interest",        "amount": -   31_000},
            ],
        },

        # ── Balance Sheet ─────────────────────────────────────────────────────
        "balance_sheet": {
            "current": [
                # Current Assets
                {"code": "1000", "name": "Standard Bank — Cheque Account", "type": "current_asset",        "amount": 1_245_000},
                {"code": "1100", "name": "Trade Debtors",                   "type": "current_asset",        "amount": 13_500_000},
                {"code": "1101", "name": "Other Debtors & Deposits",        "type": "current_asset",        "amount": 125_000},
                {"code": "1200", "name": "Inventory",                       "type": "current_asset",        "amount": 6_200_000},
                {"code": "1300", "name": "Prepayments",                     "type": "current_asset",        "amount": 185_000},
                # Non-current Assets
                {"code": "1500", "name": "Property, Plant & Equipment (Net)", "type": "noncurrent_asset",   "amount": 3_850_000},
                # Current Liabilities
                {"code": "2000", "name": "Trade Creditors",                 "type": "current_liability",    "amount": 8_200_000},
                {"code": "2100", "name": "VAT Payable",                     "type": "current_liability",    "amount": 245_000},
                {"code": "2101", "name": "PAYE & SDL Payable",              "type": "current_liability",    "amount": 118_000},
                {"code": "2200", "name": "Accruals",                        "type": "current_liability",    "amount": 320_000},
                # Non-current Liabilities
                {"code": "2500", "name": "Standard Bank Term Loan",         "type": "noncurrent_liability", "amount": 5_800_000},
                # Equity
                {"code": "3000", "name": "Share Capital",                   "type": "equity",               "amount": 500_000},
                {"code": "3100", "name": "Retained Earnings",               "type": "equity",               "amount": 9_922_000},
            ]
        },

        # ── Budget (uploaded once by client during onboarding) ────────────────
        # In production this lives in Supabase, keyed by client_id + period.
        "budget": {
            "revenue":       8_500_000,
            "cogs":          5_525_000,
            "salaries":        820_000,
            "rent":            180_000,
            "transport":       300_000,
            "marketing":        90_000,
            "admin":           140_000,
            "depreciation":     95_000,
            "finance_costs":   125_000,
        },
    }
