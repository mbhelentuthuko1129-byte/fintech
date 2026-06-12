# WhatsApp PoP Fraud Verification ("WhatsApp OS")

Detects fake, edited, or reused proof-of-payment (PoP) screenshots that customers
send to South African SMEs over WhatsApp — before goods are released. A WhatsApp-native
bot receives the screenshot, extracts the claimed payment details with Claude Vision,
cross-checks them against real bank transactions via Stitch, and replies with a verdict
in seconds: **VERIFIED / PENDING / SUSPICIOUS / FAKE**.

This repo contains the Phase 1 MVP. The data model already accommodates Phase 2
(reconciliation, reminders, debtors) — see [TODO.md](TODO.md).

## Architecture

```mermaid
flowchart TD
    WA[Customer sends PoP image\nWhatsApp Business number] -->|webhook| IN[1 Ingress\nFastAPI /webhook\nsignature verified]
    IN --> MED[2 Media handling\ndownload via Graph API\nstore in Supabase Storage]
    MED --> HASH[pHash + SHA-256]
    HASH --> DUP{3/4 Tamper detection\nduplicate across ALL tenants?}
    MED --> VIS[3 Vision/OCR\nClaude Vision structured JSON\namount, ref, bank, tamper flags]
    VIS --> DEC
    DUP --> DEC[6 Decision engine\npure functions, unit tested]
    STITCH[5 Bank verification\nStitch API incoming transactions] --> DEC
    DEC -->|verdict| NOTIF[7 Notification\nWhatsApp reply to owner]
    DEC --> DB[(8 Persistence/Audit\nSupabase Postgres + RLS)]
    N8N[9 Automation\nn8n nightly recheck] -->|POST /internal/recheck-pending| DEC
    DB --> RETOOL[Retool dashboard\nreads via RLS-scoped JWT]
```

**Verdict logic** (see `app/services/decision_engine.py`):

| Condition | Verdict |
|---|---|
| Image hash seen before (any tenant) | `FAKE` |
| Not a payment proof, or strong tamper flags (edited text, font mismatch) | `SUSPICIOUS` |
| Claim matches a real incoming Stitch transaction (amount + reference/time) | `VERIFIED` |
| Clean image but no bank data / money not reflected yet | `PENDING` → nightly re-check |

## Project layout

```
app/
  main.py               FastAPI app
  config.py             env-driven settings
  logging_config.py     JSON structured logging
  routes/
    webhook.py          WhatsApp webhook (GET verify, POST events)
    internal.py         n8n automation endpoints (shared-secret auth)
  services/
    pipeline.py         orchestrates the 9-step workflow
    vision.py           Claude Vision structured extraction
    decision_engine.py  verdict logic (pure, tested)
    matching.py         PoP claim <-> bank transaction matching (pure, tested)
    hashing.py          perceptual + SHA-256 hashing
    whatsapp.py         Cloud API client + signature verification
    stitch.py           Stitch open-banking client
    db.py               Supabase persistence
  models/schemas.py     Pydantic models (also the Claude structured-output schema)
supabase/schema.sql     all tables + RLS policies + storage bucket
tests/                  decision engine + matching unit tests
```

## Setup

### 1. Prerequisites

- Python 3.11+
- A Supabase project
- A Meta App with WhatsApp Business platform access (phone number ID + permanent token)
- An Anthropic API key
- Stitch client credentials (optional for local dev — without them all verdicts degrade to `PENDING`)

### 2. Database

Apply `supabase/schema.sql` in the Supabase SQL editor (or `supabase db push`).
Then register a tenant:

```sql
insert into businesses (name, whatsapp_phone_number_id, owner_whatsapp_number, pricing_tier)
values ('Acme Wholesale', '<META_PHONE_NUMBER_ID>', '27821234567', 'growth');
```

### 3. Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
uvicorn app.main:app --reload
```

Expose the webhook with a tunnel (e.g. `ngrok http 8000`) and register
`https://<tunnel>/webhook` in the Meta App dashboard using `WHATSAPP_VERIFY_TOKEN`.

### 4. Tests

```bash
pytest
```

### 5. Docker

```bash
docker build -t pop-verify .
docker run --env-file .env -p 8000:8000 pop-verify
```

### 6. n8n nightly reconciliation

Create an n8n workflow (self-hosted on Railway) with:
1. **Cron** node — daily, e.g. 02:00 SAST
2. **HTTP Request** node — `POST https://<api>/internal/recheck-pending`
   with header `X-Internal-Api-Key: $INTERNAL_API_KEY`

The endpoint re-matches all `PENDING` submissions against fresh Stitch data,
flips matches to `VERIFIED`, and notifies owners on WhatsApp.

## Environment variables

See [.env.example](.env.example) for the full annotated list: WhatsApp Cloud API
(verify token, app secret, access token), Anthropic, Stitch, Supabase
(service-role key), the n8n shared secret, and decision-engine tuning knobs.
All secrets come from the environment — nothing is hardcoded.

## Multi-tenancy & security

- Webhook signature verification (`X-Hub-Signature-256`) is mandatory; unsigned
  requests are rejected.
- RLS is enabled on every table. Tenants (Retool, future APIs) authenticate with
  a JWT carrying `business_id`; the backend uses the service-role key because the
  duplicate-image check is deliberately **cross-tenant** (a screenshot reused at
  another business is the strongest fraud signal).
- Customer phone numbers are stored hashed on `pop_submissions`; the per-tenant
  `customers` table holds the real number for Phase 2 reminders.
- Usage is metered per business per month in `usage_counters`; tier limits are a
  column on `businesses`, ready for enforcement when billing (PayFast) lands.

## How Phases 2–4 build on this schema

- **Phase 2 — Reconciliation, reminders, debtors:** `bank_transactions` already
  stores every synced Stitch transaction with a `reconciled` flag; reconciliation
  is a view over it joined to `pop_submissions.matched_transaction_id`.
  `reminder_schedule` exists (table only) and `customers.outstanding_balance`
  is the cached debtor figure. The nightly n8n hook generalises into the full
  reconciliation + reminder dispatcher.
- **Phase 3 — Orders:** a new `orders` module links to `customers` and
  `pop_submissions` by FK; the verification core is untouched.
- **Phase 4 — Invoicing & reporting:** invoices hang off orders/customers;
  `verification_log` + `usage_counters` already feed the fraud-rate and volume
  reporting in Retool.
