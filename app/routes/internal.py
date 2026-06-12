"""Internal endpoints for automation (n8n). Protected by a shared API key."""

import logging

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.services.pipeline import recheck_pending_submissions
from app.services.reconciliation import reconcile_all_businesses
from app.services.reminders import send_due_reminders

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _check_key(x_internal_api_key: str | None) -> None:
    settings = get_settings()
    if not settings.internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/recheck-pending")
def recheck_pending(x_internal_api_key: str | None = Header(default=None)):
    """Re-match PENDING submissions against fresh Stitch data.
    Superseded by /internal/reconcile for nightly runs, but kept for ad-hoc
    re-checks of the pending queue only."""
    _check_key(x_internal_api_key)
    return recheck_pending_submissions()


@router.post("/reconcile")
def reconcile(x_internal_api_key: str | None = Header(default=None)):
    """Nightly full reconciliation (n8n): sync Stitch transactions for every
    linked business, match them against open submissions, flip confirmed
    PENDINGs to VERIFIED, settle reminders, and send the owner a digest of
    unmatched money and unmatched claims."""
    _check_key(x_internal_api_key)
    return reconcile_all_businesses()


@router.post("/send-reminders")
def send_reminders(x_internal_api_key: str | None = Header(default=None)):
    """Daily payment-reminder dispatch (n8n): scans reminder_schedule and
    sends WhatsApp reminders to customers on the configured cadence."""
    _check_key(x_internal_api_key)
    return send_due_reminders()
