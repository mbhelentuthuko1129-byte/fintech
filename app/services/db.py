"""Supabase persistence layer.

The backend uses the service-role key, which bypasses RLS — required for the
cross-tenant duplicate-hash check. RLS policies (see supabase/schema.sql)
protect every other client (Retool dashboard, future tenant-scoped APIs).
"""

import hashlib
import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.config import get_settings
from app.models.schemas import BankTransaction
from app.services.hashing import is_phash_duplicate

logger = logging.getLogger(__name__)


@lru_cache
def get_client() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def hash_phone(phone: str) -> str:
    """Phone numbers of submitting customers are stored hashed on submissions
    for privacy; the customers table keeps the real number per-tenant."""
    return hashlib.sha256(phone.encode()).hexdigest()


# --- businesses ---------------------------------------------------------------


def get_business_by_phone_number_id(phone_number_id: str) -> dict[str, Any] | None:
    resp = (
        get_client()
        .table("businesses")
        .select("*")
        .eq("whatsapp_phone_number_id", phone_number_id)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


# --- customers ----------------------------------------------------------------


def upsert_customer(business_id: str, phone: str, name: str | None) -> dict[str, Any]:
    client = get_client()
    existing = (
        client.table("customers")
        .select("*")
        .eq("business_id", business_id)
        .eq("phone", phone)
        .limit(1)
        .execute()
    )
    if existing.data:
        customer = existing.data[0]
        if name and not customer.get("name"):
            client.table("customers").update({"name": name}).eq("id", customer["id"]).execute()
            customer["name"] = name
        return customer
    resp = (
        client.table("customers")
        .insert({"business_id": business_id, "phone": phone, "name": name})
        .execute()
    )
    return resp.data[0]


# --- pop_submissions ----------------------------------------------------------


def submission_exists(whatsapp_message_id: str) -> bool:
    """Idempotency check: Meta retries webhook deliveries."""
    if not whatsapp_message_id:
        return False
    resp = (
        get_client()
        .table("pop_submissions")
        .select("id")
        .eq("whatsapp_message_id", whatsapp_message_id)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def find_duplicate_submission(sha256: str, phash: str) -> dict[str, Any] | None:
    """Cross-tenant duplicate check: exact byte match first, then perceptual
    near-match against recent submissions."""
    client = get_client()
    exact = client.table("pop_submissions").select("id, business_id, verdict").eq("image_sha256", sha256).limit(1).execute()
    if exact.data:
        return exact.data[0]

    # pHash near-match: compare in app code. Bounded to the most recent
    # submissions; replace with a Hamming-distance SQL function if volume grows.
    recent = (
        client.table("pop_submissions")
        .select("id, business_id, verdict, image_phash")
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
    )
    for row in recent.data or []:
        if row.get("image_phash") and is_phash_duplicate(phash, row["image_phash"]):
            return row
    return None


def insert_submission(record: dict[str, Any]) -> dict[str, Any]:
    resp = get_client().table("pop_submissions").insert(record).execute()
    return resp.data[0]


def update_submission(submission_id: str, fields: dict[str, Any]) -> None:
    get_client().table("pop_submissions").update(fields).eq("id", submission_id).execute()


def get_pending_submissions(limit: int = 200) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("pop_submissions")
        .select("*, businesses!inner(id, whatsapp_phone_number_id, owner_whatsapp_number, stitch_account_id, stitch_linked)")
        .eq("verdict", "PENDING")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def get_open_submissions(business_id: str, limit: int = 500) -> list[dict[str, Any]]:
    """Submissions not yet settled by money arriving (reconciliation input)."""
    resp = (
        get_client()
        .table("pop_submissions")
        .select("id, customer_id, extracted_data, verdict, created_at")
        .eq("business_id", business_id)
        .in_("verdict", ["PENDING", "SUSPICIOUS"])
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return resp.data or []


# --- bank_transactions --------------------------------------------------------


def sync_bank_transactions(business_id: str, transactions: list[BankTransaction]) -> None:
    if not transactions:
        return
    rows = [
        {
            "business_id": business_id,
            "stitch_transaction_id": tx.id,
            "amount": tx.amount,
            "currency": tx.currency,
            "reference": tx.reference,
            "description": tx.description,
            "transaction_date": tx.date.isoformat(),
        }
        for tx in transactions
    ]
    get_client().table("bank_transactions").upsert(
        rows, on_conflict="business_id,stitch_transaction_id"
    ).execute()


def get_unreconciled_transactions(business_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("bank_transactions")
        .select("*")
        .eq("business_id", business_id)
        .eq("reconciled", False)
        .order("transaction_date", desc=False)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def mark_transaction_reconciled(business_id: str, stitch_transaction_id: str, submission_id: str) -> None:
    get_client().table("bank_transactions").update(
        {"reconciled": True, "matched_submission_id": submission_id, "reconciled_at": "now()"}
    ).eq("business_id", business_id).eq("stitch_transaction_id", stitch_transaction_id).execute()


def get_stitch_linked_businesses() -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("businesses")
        .select("*")
        .eq("stitch_linked", True)
        .not_.is_("stitch_account_id", "null")
        .execute()
    )
    return resp.data or []


# --- reminder_schedule ----------------------------------------------------------


def get_open_reminders(limit: int = 1000) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("reminder_schedule")
        .select("*, customers!inner(id, name, phone), businesses!inner(id, name, whatsapp_phone_number_id)")
        .in_("status", ["scheduled", "sent"])
        .order("due_date", desc=False)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def record_reminder_sent(reminder_id: str, new_send_count: int) -> None:
    get_client().table("reminder_schedule").update(
        {"status": "sent", "send_count": new_send_count, "last_sent_at": "now()"}
    ).eq("id", reminder_id).execute()


def mark_reminders_paid(business_id: str, customer_id: str, amount: float) -> None:
    """A verified payment settles open reminders for that customer at the
    same amount. The reminder_schedule trigger refreshes outstanding_balance."""
    get_client().table("reminder_schedule").update({"status": "paid"}).eq(
        "business_id", business_id
    ).eq("customer_id", customer_id).eq("due_amount", amount).in_(
        "status", ["scheduled", "sent"]
    ).execute()


# --- verification_log ---------------------------------------------------------


def insert_verification_log(
    submission_id: str, business_id: str, verdict: str, confidence: float, checks: list[dict[str, Any]]
) -> None:
    get_client().table("verification_log").insert(
        {
            "submission_id": submission_id,
            "business_id": business_id,
            "verdict": verdict,
            "confidence": confidence,
            "checks": checks,
        }
    ).execute()


# --- usage_counters -----------------------------------------------------------


def get_usage_count(business_id: str) -> int:
    """Current month's verification count (tier enforcement)."""
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    resp = (
        get_client()
        .table("usage_counters")
        .select("verification_count")
        .eq("business_id", business_id)
        .eq("period", period)
        .limit(1)
        .execute()
    )
    return resp.data[0]["verification_count"] if resp.data else 0


def increment_usage(business_id: str) -> int:
    """Bump this month's verification counter and return the new count.
    Tier limits aren't enforced yet (no billing), but the data is ready."""
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    client = get_client()
    existing = (
        client.table("usage_counters")
        .select("*")
        .eq("business_id", business_id)
        .eq("period", period)
        .limit(1)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        new_count = row["verification_count"] + 1
        client.table("usage_counters").update({"verification_count": new_count}).eq("id", row["id"]).execute()
        return new_count
    client.table("usage_counters").insert(
        {"business_id": business_id, "period": period, "verification_count": 1}
    ).execute()
    return 1


# --- storage ------------------------------------------------------------------


def upload_image(path: str, image_bytes: bytes, content_type: str) -> str:
    s = get_settings()
    get_client().storage.from_(s.supabase_storage_bucket).upload(
        path, image_bytes, {"content-type": content_type}
    )
    return path
