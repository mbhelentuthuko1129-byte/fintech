"""WhatsApp Cloud API webhook: verification handshake (GET) and inbound
message events (POST). Image processing runs as a background task so we
ACK Meta within their timeout."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from app.config import get_settings
from app.services.pipeline import process_image_message
from app.services.whatsapp import verify_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["whatsapp"])


@router.get("")
def verify(
    mode: str = Query(default="", alias="hub.mode"),
    token: str = Query(default="", alias="hub.verify_token"),
    challenge: str = Query(default="", alias="hub.challenge"),
):
    settings = get_settings()
    if mode == "subscribe" and token and token == settings.whatsapp_verify_token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
async def receive(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not verify_webhook_signature(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id", "")
            contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            for message in value.get("messages", []):
                if message.get("type") != "image":
                    continue
                sender = message.get("from", "")
                background.add_task(
                    process_image_message,
                    phone_number_id=phone_number_id,
                    sender_wa_id=sender,
                    sender_name=contacts.get(sender),
                    media_id=message["image"]["id"],
                    message_id=message.get("id", ""),
                )

    # Always 200 quickly; Meta retries aggressively on non-2xx.
    return {"status": "received"}
