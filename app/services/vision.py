"""Claude Vision extraction: screenshot -> structured PoPExtraction.

Uses the Anthropic Python SDK with structured outputs (messages.parse), so the
response is schema-validated JSON — no hand-rolled parsing.
"""

import base64
import logging

import anthropic

from app.config import get_settings
from app.models.schemas import PoPExtraction

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You analyse proof-of-payment (PoP) screenshots sent over WhatsApp to South African
businesses. Customers sometimes send edited or fake bank notifications to get goods
released before money arrives.

Extract the payment details exactly as shown — do not infer or correct values.
Then inspect the image for signs of tampering: font or kerning mismatches around
amounts/dates, misaligned text, compression artifacts localised to edited regions,
layouts that don't match the named bank's real notifications, or missing elements
a genuine notification would have. Common SA banks: FNB, Standard Bank, ABSA,
Nedbank, Capitec, TymeBank, Discovery Bank.

Be conservative with tamper flags: a blurry photo of a real screen is not tampering.
Report only ONE structured JSON object."""

_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def analyse_pop_image(image_bytes: bytes, media_type: str = "image/jpeg") -> PoPExtraction:
    """Send the screenshot to Claude Vision and return the structured extraction."""
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    if media_type not in _MEDIA_TYPES:
        media_type = "image/jpeg"

    response = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
                        },
                    },
                    {
                        "type": "text",
                        "text": "Analyse this proof-of-payment screenshot and return the structured extraction.",
                    },
                ],
            }
        ],
        output_format=PoPExtraction,
    )

    extraction = response.parsed_output
    if extraction is None:
        raise ValueError("Claude Vision returned no parseable output")

    logger.info(
        "vision extraction complete",
        extra={
            "amount": extraction.amount,
            "bank": extraction.bank_name,
            "tamper_flags": [f.value for f in extraction.tamper_flags],
            "confidence": extraction.confidence,
        },
    )
    return extraction
