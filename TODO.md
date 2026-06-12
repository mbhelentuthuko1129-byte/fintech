# Roadmap & Deferred Items

## Phase 2 — Reconciliation, Reminders & Debtors (BUILT)

- [x] **Bank reconciliation**: `app/services/reconciliation.py` + nightly
      `/internal/reconcile`; unmatched money/claims surfaced to the owner via
      WhatsApp digest and to Retool via `v_unreconciled_transactions` /
      `v_unmatched_submissions`.
- [x] **Payment reminders**: `app/services/reminders.py` + daily
      `/internal/send-reminders`; cadence + cap configurable; uses `reminder_schedule`.
- [x] **Debtor management**: `v_debtors` view with aging buckets;
      `customers.outstanding_balance` maintained by trigger.

### Phase 2 follow-ups

- [ ] **Meta template messages for reminders**: free-form messages only deliver
      inside the 24-hour customer-service window. Reminders to customers who
      haven't messaged recently need an approved WhatsApp template
      (`/messages` with `type: template`). Current implementation will silently
      fail outside the window for cold contacts.
- [ ] **Reminder creation UX**: rows are created via Retool today; Phase 3
      should auto-create them from orders/invoices, and a WhatsApp owner command
      ("remind 0821234567 R1500 INV-9 by Friday") is a natural Growth-tier feature.
- [ ] **Retool pages**: build the actual dashboards on `v_debtors`,
      `v_unreconciled_transactions`, `v_unmatched_submissions`.
- [ ] **Reminder settle heuristics**: reconciliation marks reminders paid only on
      exact customer + amount match; partial payments and overpayments need rules.

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

- [x] **Tier enforcement**: pipeline now rejects submissions past
      `monthly_verification_limit` and nudges the owner to upgrade. (Phase 2)
- [x] **Webhook idempotency**: unique index on `whatsapp_message_id` + early
      return in the pipeline. (Phase 2)
- [ ] **PayFast billing** for the SaaS itself (subscriptions per tier; limits
      per tier should move from the manual column to tier config when billing lands).
- [ ] **Stitch account linking flow**: user-consent OAuth so businesses can link
      their bank account from WhatsApp/onboarding; currently `stitch_account_id`
      is set manually. Verify the GraphQL transaction query against a Stitch
      sandbox account (schema fields assumed from docs).
- [ ] **pHash duplicate check at scale**: currently compares against the most
      recent 2000 submissions in app code. Move to a Postgres Hamming-distance
      function (or pgvector) when volume grows.
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
