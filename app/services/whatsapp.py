"""WhatsApp Cloud API (Meta) integration: webhook signature verification,
media download, and sending replies."""

import hashlib
import hmac
import logging

import httpx

from app.config import get_settings
from app.models.schemas import DecisionResult, PoPExtraction, Verdict

logger = logging.getLogger(__name__)


def verify_webhook_signature(payload: bytes, signature_header: str | None) -> bool:
    """Verify Meta's X-Hub-Signature-256 header (HMAC-SHA256 of the raw body
    keyed with the app secret)."""
    settings = get_settings()
    if not settings.whatsapp_app_secret:
        logger.error("WHATSAPP_APP_SECRET not configured; rejecting webhook")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.whatsapp_app_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def _graph_url(path: str) -> str:
    s = get_settings()
    return f"{s.whatsapp_graph_base_url}/{s.whatsapp_api_version}/{path}"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().whatsapp_access_token}"}


def download_media(media_id: str) -> tuple[bytes, str]:
    """Resolve a media ID to its content. Returns (bytes, mime_type)."""
    with httpx.Client(timeout=30) as client:
        meta = client.get(_graph_url(media_id), headers=_auth_headers())
        meta.raise_for_status()
        info = meta.json()
        content = client.get(info["url"], headers=_auth_headers())
        content.raise_for_status()
        return content.content, info.get("mime_type", "image/jpeg")


def send_text(phone_number_id: str, to: str, body: str) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(_graph_url(f"{phone_number_id}/messages"), headers=_auth_headers(), json=payload)
        if resp.status_code >= 400:
            logger.error("failed to send WhatsApp message", extra={"status": resp.status_code, "body": resp.text})
        resp.raise_for_status()


_VERDICT_EMOJI = {
    Verdict.VERIFIED: "✅",
    Verdict.PENDING: "⏳",
    Verdict.SUSPICIOUS: "⚠️",
    Verdict.FAKE: "🚫",
}

_VERDICT_ADVICE = {
    Verdict.VERIFIED: "Payment matched on your bank account. Safe to release.",
    Verdict.PENDING: "No matching transaction yet (EFT can take time). We'll re-check automatically and notify you.",
    Verdict.SUSPICIOUS: "Details don't check out. Do NOT release goods until the money reflects.",
    Verdict.FAKE: "This looks like a reused or forged screenshot. Do NOT release goods.",
}


def format_verdict_message(extraction: PoPExtraction, decision: DecisionResult) -> str:
    """Human-readable verdict for the business owner."""
    lines = [f"{_VERDICT_EMOJI[decision.verdict]} *PoP check: {decision.verdict.value}*", ""]
    if extraction.amount is not None:
        currency = extraction.currency or "ZAR"
        lines.append(f"Amount: {currency} {extraction.amount:,.2f}")
    if extraction.reference_number:
        lines.append(f"Reference: {extraction.reference_number}")
    if extraction.bank_name:
        lines.append(f"Bank: {extraction.bank_name}")
    if extraction.sender_name:
        lines.append(f"From: {extraction.sender_name}")
    if extraction.date_time:
        lines.append(f"Dated: {extraction.date_time}")
    reasons = decision.reasons
    if reasons:
        lines.append("")
        lines.append("Why: " + "; ".join(reasons))
    lines.append("")
    lines.append(_VERDICT_ADVICE[decision.verdict])
    return "\n".join(lines)
