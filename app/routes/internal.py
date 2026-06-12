"""Internal endpoints for automation (n8n). Protected by a shared API key."""

import logging

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.services.pipeline import recheck_pending_submissions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _check_key(x_internal_api_key: str | None) -> None:
    settings = get_settings()
    if not settings.internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/recheck-pending")
def recheck_pending(x_internal_api_key: str | None = Header(default=None)):
    """Nightly reconciliation hook: re-match PENDING submissions against fresh
    Stitch data. n8n calls this on a schedule."""
    _check_key(x_internal_api_key)
    return recheck_pending_submissions()
