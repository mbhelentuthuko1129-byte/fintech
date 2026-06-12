-- WhatsApp PoP Verification — Supabase schema (Phase 1, designed for Phase 2-4)
--
-- Apply with: supabase db push  (or paste into the SQL editor)
--
-- Multi-tenancy model:
--   * The FastAPI backend connects with the service-role key (bypasses RLS) —
--     required for the cross-tenant duplicate-image check.
--   * Every other client (Retool, future tenant APIs) is constrained by RLS:
--     a row is visible only if the JWT's business_id claim matches.
--     Convention: the JWT carries `business_id` in app_metadata.

create extension if not exists "uuid-ossp";

-- Helper: current tenant from the JWT (returns NULL for anon).
create or replace function auth_business_id() returns uuid
language sql stable as $$
  select nullif(
    coalesce(
      current_setting('request.jwt.claims', true)::jsonb -> 'app_metadata' ->> 'business_id',
      current_setting('request.jwt.claims', true)::jsonb ->> 'business_id'
    ), ''
  )::uuid
$$;

-- ============================================================================
-- businesses — tenant record
-- ============================================================================
create table if not exists businesses (
  id                        uuid primary key default uuid_generate_v4(),
  name                      text not null,
  whatsapp_phone_number_id  text not null unique,   -- Meta phone_number_id for this tenant's WABA number
  owner_whatsapp_number     text,                   -- where verdicts are sent
  contact_email             text,
  pricing_tier              text not null default 'starter'
                            check (pricing_tier in ('starter', 'growth', 'enterprise')),
  monthly_verification_limit integer not null default 50,  -- tier enforcement, applied later
  stitch_linked             boolean not null default false,
  stitch_account_id         text,
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);

-- ============================================================================
-- customers — per-tenant customer records (foundation for Phase 2 debtors)
-- ============================================================================
create table if not exists customers (
  id           uuid primary key default uuid_generate_v4(),
  business_id  uuid not null references businesses(id) on delete cascade,
  phone        text not null,
  name         text,
  -- Phase 2: outstanding balance is derived from submissions/invoices, but a
  -- cached figure keeps the debtor view cheap.
  outstanding_balance numeric(12,2) not null default 0,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (business_id, phone)
);

-- ============================================================================
-- pop_submissions — every screenshot received
-- ============================================================================
create table if not exists pop_submissions (
  id                    uuid primary key default uuid_generate_v4(),
  business_id           uuid not null references businesses(id) on delete cascade,
  customer_id           uuid references customers(id) on delete set null,
  customer_phone_hash   text,                       -- sha256 of sender number (privacy-safe analytics)
  whatsapp_message_id   text,
  image_sha256          text not null,
  image_phash           text,                       -- perceptual hash for near-duplicate detection
  image_storage_path    text,
  extracted_data        jsonb,                      -- raw Claude Vision extraction
  verdict               text not null default 'PENDING'
                        check (verdict in ('VERIFIED', 'PENDING', 'SUSPICIOUS', 'FAKE')),
  matched_transaction_id text,                      -- stitch transaction id when VERIFIED
  created_at            timestamptz not null default now(),
  decided_at            timestamptz
);

create index if not exists idx_pop_submissions_sha256 on pop_submissions (image_sha256);
create index if not exists idx_pop_submissions_business on pop_submissions (business_id, created_at desc);
create index if not exists idx_pop_submissions_verdict on pop_submissions (verdict) where verdict = 'PENDING';

-- ============================================================================
-- bank_transactions — synced from Stitch per business (Phase 2 reconciliation)
-- ============================================================================
create table if not exists bank_transactions (
  id                     uuid primary key default uuid_generate_v4(),
  business_id            uuid not null references businesses(id) on delete cascade,
  stitch_transaction_id  text not null,
  amount                 numeric(12,2) not null,
  currency               text not null default 'ZAR',
  reference              text,
  description            text,
  transaction_date       timestamptz not null,
  -- Phase 2: reconciliation status against pop_submissions
  reconciled             boolean not null default false,
  created_at             timestamptz not null default now(),
  unique (business_id, stitch_transaction_id)
);

create index if not exists idx_bank_tx_business_date on bank_transactions (business_id, transaction_date desc);

-- ============================================================================
-- verification_log — audit trail of decision engine runs
-- ============================================================================
create table if not exists verification_log (
  id            uuid primary key default uuid_generate_v4(),
  submission_id uuid not null references pop_submissions(id) on delete cascade,
  business_id   uuid not null references businesses(id) on delete cascade,
  verdict       text not null,
  confidence    numeric(4,3) not null,
  checks        jsonb not null default '[]',  -- [{name, passed, detail}]
  created_at    timestamptz not null default now()
);

create index if not exists idx_verification_log_submission on verification_log (submission_id);

-- ============================================================================
-- usage_counters — per-business monthly verification counts (tier enforcement)
-- ============================================================================
create table if not exists usage_counters (
  id                 uuid primary key default uuid_generate_v4(),
  business_id        uuid not null references businesses(id) on delete cascade,
  period             text not null,               -- 'YYYY-MM'
  verification_count integer not null default 0,
  updated_at         timestamptz not null default now(),
  unique (business_id, period)
);

-- ============================================================================
-- reminder_schedule — Phase 2 placeholder (payment reminders). Table only;
-- no application logic yet.
-- ============================================================================
create table if not exists reminder_schedule (
  id           uuid primary key default uuid_generate_v4(),
  business_id  uuid not null references businesses(id) on delete cascade,
  customer_id  uuid not null references customers(id) on delete cascade,
  due_amount   numeric(12,2) not null,
  due_date     date not null,
  status       text not null default 'scheduled'
               check (status in ('scheduled', 'sent', 'paid', 'cancelled')),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- ============================================================================
-- Row Level Security — each business sees only its own rows.
-- The service-role key (backend) bypasses all of this by design.
-- ============================================================================
alter table businesses        enable row level security;
alter table customers         enable row level security;
alter table pop_submissions   enable row level security;
alter table bank_transactions enable row level security;
alter table verification_log  enable row level security;
alter table usage_counters    enable row level security;
alter table reminder_schedule enable row level security;

create policy businesses_tenant_select on businesses
  for select using (id = auth_business_id());
create policy businesses_tenant_update on businesses
  for update using (id = auth_business_id());

create policy customers_tenant_all on customers
  for all using (business_id = auth_business_id());

create policy pop_submissions_tenant_all on pop_submissions
  for all using (business_id = auth_business_id());

create policy bank_transactions_tenant_all on bank_transactions
  for all using (business_id = auth_business_id());

create policy verification_log_tenant_select on verification_log
  for select using (business_id = auth_business_id());

create policy usage_counters_tenant_select on usage_counters
  for select using (business_id = auth_business_id());

create policy reminder_schedule_tenant_all on reminder_schedule
  for all using (business_id = auth_business_id());

-- ============================================================================
-- Storage bucket for PoP images (private; backend uploads via service role)
-- ============================================================================
insert into storage.buckets (id, name, public)
values ('pop-images', 'pop-images', false)
on conflict (id) do nothing;

create policy pop_images_tenant_read on storage.objects
  for select using (
    bucket_id = 'pop-images'
    and (storage.foldername(name))[1] = auth_business_id()::text
  );

-- updated_at maintenance
create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

do $$
declare t text;
begin
  foreach t in array array['businesses','customers','usage_counters','reminder_schedule'] loop
    execute format(
      'drop trigger if exists trg_%1$s_updated_at on %1$s;
       create trigger trg_%1$s_updated_at before update on %1$s
       for each row execute function set_updated_at()', t);
  end loop;
end $$;
