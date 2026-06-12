-- Phase 4: automated invoicing + sales reporting.
-- Apply AFTER schema.sql, 0002_phase2.sql and 0003_phase3.sql.

-- ============================================================================
-- businesses: invoice numbering + SA VAT details
-- ============================================================================
alter table businesses
  add column if not exists invoice_seq integer not null default 0,
  add column if not exists vat_registered boolean not null default false,
  add column if not exists vat_number text,
  add column if not exists vat_rate numeric(5,2) not null default 15.00;

create or replace function next_invoice_seq(b_id uuid) returns integer
language sql volatile as $$
  update businesses set invoice_seq = invoice_seq + 1 where id = b_id
  returning invoice_seq
$$;

-- ============================================================================
-- invoices — tied to orders and customers
-- ============================================================================
create table if not exists invoices (
  id              uuid primary key default uuid_generate_v4(),
  business_id     uuid not null references businesses(id) on delete cascade,
  customer_id     uuid not null references customers(id) on delete cascade,
  order_id        uuid not null references orders(id) on delete cascade,
  invoice_number  text not null,                -- 'INV-00042'
  status          text not null default 'issued'
                  check (status in ('issued', 'paid', 'void')),
  subtotal        numeric(12,2) not null,
  vat_amount      numeric(12,2) not null default 0,
  total_amount    numeric(12,2) not null,
  currency        text not null default 'ZAR',
  pdf_storage_path text,
  issued_at       timestamptz not null default now(),
  due_date        date,
  created_at      timestamptz not null default now(),
  unique (business_id, invoice_number),
  unique (order_id)                              -- one invoice per order
);

alter table invoices enable row level security;
create policy invoices_tenant_all on invoices
  for all using (business_id = auth_business_id());

-- Private bucket for generated PDFs.
insert into storage.buckets (id, name, public)
values ('invoices', 'invoices', false)
on conflict (id) do nothing;

create policy invoices_tenant_read on storage.objects
  for select using (
    bucket_id = 'invoices'
    and (storage.foldername(name))[1] = auth_business_id()::text
  );

-- ============================================================================
-- Reporting views for Retool (security_invoker -> tenant RLS applies)
-- ============================================================================

-- Revenue & order volume per month.
create or replace view v_sales_monthly
with (security_invoker = on) as
select
  business_id,
  date_trunc('month', created_at)::date as month,
  count(*)                                                         as orders_placed,
  count(*) filter (where status in ('paid', 'fulfilled'))          as orders_paid,
  count(*) filter (where status = 'cancelled')                     as orders_cancelled,
  coalesce(sum(total_amount) filter (where status in ('paid', 'fulfilled')), 0) as revenue
from orders
group by business_id, date_trunc('month', created_at)::date;

-- Verification volume & fraud rate per month.
create or replace view v_fraud_stats_monthly
with (security_invoker = on) as
select
  business_id,
  date_trunc('month', created_at)::date as month,
  count(*)                                            as submissions,
  count(*) filter (where verdict = 'VERIFIED')        as verified,
  count(*) filter (where verdict = 'FAKE')            as fake,
  count(*) filter (where verdict = 'SUSPICIOUS')      as suspicious,
  count(*) filter (where verdict = 'PENDING')         as pending,
  round(
    count(*) filter (where verdict in ('FAKE', 'SUSPICIOUS'))::numeric
      / nullif(count(*), 0) * 100, 1
  ) as fraud_rate_pct
from pop_submissions
group by business_id, date_trunc('month', created_at)::date;

-- Top customers by paid revenue.
create or replace view v_top_customers
with (security_invoker = on) as
select
  o.business_id,
  o.customer_id,
  c.name,
  c.phone,
  count(*) filter (where o.status in ('paid', 'fulfilled'))                       as paid_orders,
  coalesce(sum(o.total_amount) filter (where o.status in ('paid', 'fulfilled')), 0) as total_revenue,
  max(o.created_at)                                                                as last_order_at
from orders o
join customers c on c.id = o.customer_id
group by o.business_id, o.customer_id, c.name, c.phone;
