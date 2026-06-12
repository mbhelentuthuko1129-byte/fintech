"""Phase 2 payment reminders.

n8n calls /internal/send-reminders daily; we scan reminder_schedule for rows
that are due and send a WhatsApp reminder to the customer on a cadence
(first on due_date, then every REMINDER_CADENCE_DAYS, capped at
REMINDER_MAX_SENDS). Rows are created by the owner via Retool — or, in
Phase 3+, automatically from orders/invoices.

Due-selection and message formatting are pure; sending is orchestrated below.
"""

import logging
from datetime import date, datetime
from typing import Any

from app.config import get_settings
from app.services import db, whatsapp

logger = logging.getLogger(__name__)


def is_reminder_due(
    *,
    status: str,
    due_date: date,
    send_count: int,
    last_sent_at: datetime | None,
    today: date,
    cadence_days: int = 3,
    max_sends: int = 3,
) -> bool:
    """A reminder is due when the debt is open, due_date has arrived, we
    haven't exhausted the cap, and the cadence has elapsed since last send."""
    if status not in ("scheduled", "sent"):
        return False
    if due_date > today:
        return False
    if send_count >= max_sends:
        return False
    if last_sent_at is not None and (today - last_sent_at.date()).days < cadence_days:
        return False
    return True


def format_reminder_message(
    business_name: str,
    customer_name: str | None,
    amount: float,
    due_date: date,
    reference: str | None,
    send_count: int,
) -> str:
    greeting = f"Hi {customer_name}," if customer_name else "Hi,"
    days_overdue = (date.today() - due_date).days
    if send_count == 0:
        opener = f"friendly reminder from *{business_name}*:"
    else:
        opener = f"reminder from *{business_name}* (follow-up {send_count + 1}):"

    lines = [f"{greeting} {opener}", "", f"Amount due: ZAR {amount:,.2f}"]
    if reference:
        lines.append(f"Reference: {reference}")
    if days_overdue > 0:
        lines.append(f"Due date: {due_date:%d %b %Y} ({days_overdue} days overdue)")
    else:
        lines.append(f"Due date: {due_date:%d %b %Y}")
    lines += [
        "",
        "Please use the reference when paying so we can match your payment automatically. "
        "If you've already paid, you can ignore this message — or send us your proof of payment here.",
    ]
    return "\n".join(lines)


# --- orchestration --------------------------------------------------------------


def send_due_reminders() -> dict[str, int]:
    """Send all due reminders. Called by n8n on a daily schedule."""
    settings = get_settings()
    today = date.today()
    summary = {"scanned": 0, "sent": 0, "errors": 0}

    for row in db.get_open_reminders():
        summary["scanned"] += 1
        last_sent = _parse_ts(row.get("last_sent_at"))
        if not is_reminder_due(
            status=row["status"],
            due_date=date.fromisoformat(row["due_date"]),
            send_count=row.get("send_count", 0),
            last_sent_at=last_sent,
            today=today,
            cadence_days=settings.reminder_cadence_days,
            max_sends=settings.reminder_max_sends,
        ):
            continue

        customer = row["customers"]
        business = row["businesses"]
        message = format_reminder_message(
            business_name=business.get("name", "the business"),
            customer_name=customer.get("name"),
            amount=float(row["due_amount"]),
            due_date=date.fromisoformat(row["due_date"]),
            reference=row.get("reference"),
            send_count=row.get("send_count", 0),
        )
        try:
            whatsapp.send_text(business["whatsapp_phone_number_id"], customer["phone"], message)
            db.record_reminder_sent(row["id"], row.get("send_count", 0) + 1)
            summary["sent"] += 1
        except Exception:
            summary["errors"] += 1
            logger.exception("failed to send reminder", extra={"reminder_id": row.get("id")})

    logger.info("reminder run complete", extra=summary)
    return summary


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
