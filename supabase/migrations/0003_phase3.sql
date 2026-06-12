-- Phase 3: WhatsApp order management.
-- Apply AFTER supabase/schema.sql and migrations/0002_phase2.sql.

-- ============================================================================
-- businesses: per-tenant order numbering + payment instructions shown to
-- customers when an order is confirmed.
-- ============================================================================
alter table businesses
  add column if not exists order_seq integer not null default 0,
  add column if not exists payment_instructions text;  -- e.g. "FNB 62012345678, Acme Wholesale"

-- Atomic order-number allocation (called via RPC).
create or replace function next_order_seq(b_id uuid) returns integer
language sql volatile as $$
  update businesses set order_seq = order_seq + 1 where id = b_id
  returning order_seq
$$;

-- ============================================================================
-- products — per-tenant catalog
-- ============================================================================
create table if not exists products (
  id           uuid primary key default uuid_generate_v4(),
  business_id  uuid not null references businesses(id) on delete cascade,
  name         text not null,
  sku          text,
  price        numeric(12,2) not null check (price >= 0),
  currency     text not null default 'ZAR',
  active       boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (business_id, name)
);

-- ============================================================================
-- orders — order intake + status tracking
-- ============================================================================
create table if not exists orders (
  id            uuid primary key default uuid_generate_v4(),
  business_id   uuid not null references businesses(id) on delete cascade,
  customer_id   uuid not null references customers(id) on delete cascade,
  order_number  text not null,                -- 'ORD-<seq>', used as the payment reference
  status        text not null default 'pending_payment'
                check (status in ('pending_payment', 'paid', 'fulfilled', 'cancelled')),
  total_amount  numeric(12,2) not null,
  currency      text not null default 'ZAR',
  pop_submission_id uuid references pop_submissions(id) on delete set null,
  paid_at       timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (business_id, order_number)
);

create index if not exists idx_orders_open
  on orders (business_id, created_at desc) where status = 'pending_payment';

create table if not exists order_items (
  id          uuid primary key default uuid_generate_v4(),
  order_id    uuid not null references orders(id) on delete cascade,
  product_id  uuid references products(id) on delete set null,
  description text not null,                  -- denormalised name (catalog may change later)
  quantity    integer not null check (quantity > 0),
  unit_price  numeric(12,2) not null,
  line_total  numeric(12,2) not null
);

-- A PoP submission can be linked to the order it pays for.
alter table pop_submissions
  add column if not exists order_id uuid references orders(id) on delete set null;

-- ============================================================================
-- RLS
-- ============================================================================
alter table products    enable row level security;
alter table orders      enable row level security;
alter table order_items enable row level security;

create policy products_tenant_all on products
  for all using (business_id = auth_business_id());

create policy orders_tenant_all on orders
  for all using (business_id = auth_business_id());

create policy order_items_tenant_all on order_items
  for all using (
    exists (select 1 from orders o where o.id = order_id and o.business_id = auth_business_id())
  );

-- updated_at maintenance (reuses set_updated_at() from the base schema)
do $$
declare t text;
begin
  foreach t in array array['products','orders'] loop
    execute format(
      'drop trigger if exists trg_%1$s_updated_at on %1$s;
       create trigger trg_%1$s_updated_at before update on %1$s
       for each row execute function set_updated_at()', t);
  end loop;
end $$;
