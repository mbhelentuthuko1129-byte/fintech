# Roadmap & Deferred Items

## Phase 2 — Reconciliation, Reminders & Debtors (next, post-launch)

- [ ] **Bank reconciliation view**: match *all* incoming Stitch transactions against
      `pop_submissions`; surface unmatched transactions and unmatched submissions to
      the owner. Schema is ready (`bank_transactions.reconciled`,
      `pop_submissions.matched_transaction_id`); build the matching job (extend
      `recheck_pending_submissions`) and a Retool reconciliation page.
- [ ] **Payment reminders**: n8n workflow scanning `customers` with outstanding
      balances; sends scheduled WhatsApp reminders via template messages
      (template approval required from Meta). Uses `reminder_schedule` (table exists,
      no logic yet).
- [ ] **Debtor management**: Retool view over `customers` + `pop_submissions` +
      `bank_transactions` with aging buckets (current / 30 / 60 / 90+ days). Add a
      job to maintain `customers.outstanding_balance`.

## Phase 3 — WhatsApp Order Management

- [ ] Product/service catalog tables (`products`, `orders`, `order_items`) per tenant.
- [ ] Conversational order intake (WhatsApp interactive messages / list replies).
- [ ] Order status tracking; link orders to `pop_submissions` and `customers`.
- [ ] Keep this a distinct module that integrates with — not replaces — the
      verification core.

## Phase 4 — Automated Invoicing & Sales Reporting

- [ ] PDF invoice generation (numbering, templating) tied to orders and customers.
- [ ] Sales reporting dashboard in Retool: revenue, verification volume, fraud rate,
      top customers.

## Deferred items identified during Phase 1

- [ ] **Tier enforcement**: `usage_counters` is metered and
      `businesses.monthly_verification_limit` exists, but limits aren't enforced.
      Wire a check at the top of the pipeline + an upgrade nudge message.
- [ ] **PayFast billing** for the SaaS itself (subscriptions per tier).
- [ ] **Stitch account linking flow**: user-consent OAuth so businesses can link
      their bank account from WhatsApp/onboarding; currently `stitch_account_id`
      is set manually. Verify the GraphQL transaction query against a Stitch
      sandbox account (schema fields assumed from docs).
- [ ] **pHash duplicate check at scale**: currently compares against the most
      recent 2000 submissions in app code. Move to a Postgres Hamming-distance
      function (or pgvector) when volume grows.
- [ ] **Webhook idempotency**: Meta retries deliveries; dedupe on
      `whatsapp_message_id` before processing (unique index + early return).
- [ ] **EXIF/metadata checks**: forwarded WhatsApp images are stripped of EXIF,
      so Phase 1 relies on Claude Vision + hashing; revisit raw-metadata heuristics
      for images sent as documents.
- [ ] **SendGrid email alerts** (owner digest / suspicious-activity alerts).
- [ ] **Owner vs customer conversations**: Phase 1 assumes PoPs arrive on the
      business's number and the verdict goes to the configured owner number.
      Support group-chat and multi-staff routing (Enterprise multi-number) later.
- [ ] **Rate limiting / queueing**: background tasks run in-process; move to a
      worker queue (e.g. Redis + RQ) before high volume.
- [ ] **Retool dashboard**: build the actual dashboard (submissions, verdicts,
      usage) reading via an RLS-scoped JWT per tenant.
