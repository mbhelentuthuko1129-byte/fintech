-- Phase 2: reconciliation, reminders, debtor management.
-- Apply AFTER supabase/schema.sql.

-- ============================================================================
-- Webhook idempotency: Meta retries deliveries; never process a message twice.
-- ============================================================================
create unique index if not exists uq_pop_submissions_wa_message
  on pop_submissions (whatsapp_message_id)
  where whatsapp_message_id is not null and whatsapp_message_id <> '';

-- ============================================================================
-- Reconciliation: link bank transactions back to the submission they settle.
-- ============================================================================
alter table bank_transactions
  add column if not exists matched_submission_id uuid references pop_submissions(id) on delete set null,
  add column if not exists reconciled_at timestamptz;

create index if not exists idx_bank_tx_unreconciled
  on bank_transactions (business_id) where reconciled = false;

-- ============================================================================
-- Reminders: cadence tracking on reminder_schedule.
-- ============================================================================
alter table reminder_schedule
  add column if not exists reference text,            -- e.g. invoice/order ref shown to the customer
  add column if not exists send_count integer not null default 0,
  add column if not exists last_sent_at timestamptz;

create index if not exists idx_reminders_due
  on reminder_schedule (due_date) where status in ('scheduled', 'sent');

-- ============================================================================
-- customers.outstanding_balance is derived from open reminder_schedule rows.
-- Maintained by trigger so the debtor view stays cheap.
-- ============================================================================
create or replace function refresh_customer_outstanding() returns trigger
language plpgsql as $$
declare
  cid uuid;
begin
  foreach cid in array array_remove(array[
      case when tg_op <> 'INSERT' then old.customer_id end,
      case when tg_op <> 'DELETE' then new.customer_id end
    ], null)
  loop
    update customers set outstanding_balance = coalesce((
      select sum(due_amount) from reminder_schedule
      where customer_id = cid and status in ('scheduled', 'sent')
    ), 0)
    where id = cid;
  end loop;
  return null;
end $$;

drop trigger if exists trg_reminders_outstanding on reminder_schedule;
create trigger trg_reminders_outstanding
  after insert or update or delete on reminder_schedule
  for each row execute function refresh_customer_outstanding();

-- ============================================================================
-- Views for Retool. security_invoker makes the underlying RLS apply to the
-- querying role, so a tenant-scoped JWT only ever sees its own rows.
-- ============================================================================

-- Debtor view with aging buckets (current, 30, 60, 90, 90+ days overdue).
create or replace view v_debtors
with (security_invoker = on) as
select
  c.business_id,
  c.id           as customer_id,
  c.name,
  c.phone,
  c.outstanding_balance,
  min(r.due_date)                                  as oldest_due_date,
  greatest(current_date - min(r.due_date), 0)      as max_days_overdue,
  sum(r.due_amount) filter (where r.due_date >= current_date)                                          as bucket_current,
  sum(r.due_amount) filter (where current_date - r.due_date between 1 and 30)                          as bucket_30,
  sum(r.due_amount) filter (where current_date - r.due_date between 31 and 60)                         as bucket_60,
  sum(r.due_amount) filter (where current_date - r.due_date between 61 and 90)                         as bucket_90,
  sum(r.due_amount) filter (where current_date - r.due_date > 90)                                      as bucket_90_plus
from customers c
join reminder_schedule r on r.customer_id = c.id and r.status in ('scheduled', 'sent')
group by c.business_id, c.id, c.name, c.phone, c.outstanding_balance;

-- Incoming money with no matching PoP submission (customer paid, nobody claimed it).
create or replace view v_unreconciled_transactions
with (security_invoker = on) as
select business_id, id, stitch_transaction_id, amount, currency, reference,
       description, transaction_date
from bank_transactions
where reconciled = false;

-- Submissions never confirmed by money arriving (claimed, never paid).
create or replace view v_unmatched_submissions
with (security_invoker = on) as
select s.business_id, s.id, s.customer_id, c.name as customer_name,
       s.extracted_data ->> 'amount'           as claimed_amount,
       s.extracted_data ->> 'reference_number' as claimed_reference,
       s.verdict, s.created_at
from pop_submissions s
left join customers c on c.id = s.customer_id
where s.verdict in ('PENDING', 'SUSPICIOUS');
