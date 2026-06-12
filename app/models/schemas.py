"""Pydantic models shared across the pipeline.

PoPExtraction doubles as the structured-output schema sent to Claude Vision,
so its fields and descriptions are written for the model as much as for us.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    PENDING = "PENDING"
    SUSPICIOUS = "SUSPICIOUS"
    FAKE = "FAKE"


class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class TamperFlag(str, Enum):
    FONT_MISMATCH = "font_mismatch"
    ALIGNMENT_IRREGULARITY = "alignment_irregularity"
    RESOLUTION_ARTIFACT = "resolution_artifact"
    INCONSISTENT_METADATA = "inconsistent_metadata"
    EDITED_TEXT_REGION = "edited_text_region"
    SCREENSHOT_OF_SCREENSHOT = "screenshot_of_screenshot"
    MISSING_EXPECTED_ELEMENT = "missing_expected_element"
    OTHER = "other"


class PoPExtraction(BaseModel):
    """Structured data extracted from a proof-of-payment screenshot."""

    is_payment_proof: bool = Field(
        description="True if the image is a payment notification/receipt/EFT proof, false otherwise."
    )
    amount: float | None = Field(
        default=None, description="Payment amount as a number, e.g. 1500.00. Null if not visible."
    )
    currency: str | None = Field(
        default=None, description="ISO currency code, e.g. ZAR. Null if not visible."
    )
    reference_number: str | None = Field(
        default=None, description="Payment/transaction reference exactly as shown. Null if absent."
    )
    bank_name: str | None = Field(
        default=None, description="Bank or app the screenshot is from, e.g. FNB, Capitec."
    )
    sender_name: str | None = Field(default=None, description="Payer/sender name if shown.")
    recipient_name: str | None = Field(default=None, description="Recipient/beneficiary name if shown.")
    date_time: str | None = Field(
        default=None,
        description="Payment date/time exactly as shown on the screenshot, ISO 8601 if unambiguous.",
    )
    tamper_flags: list[TamperFlag] = Field(
        default_factory=list,
        description=(
            "Visual tampering signals: font mismatches, misaligned text, resolution artifacts "
            "around numbers, inconsistent spacing, elements a real notification would have but "
            "this one lacks. Empty list if nothing suspicious."
        ),
    )
    tamper_notes: str | None = Field(
        default=None, description="One short sentence explaining any tamper flags raised."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence (0-1) that the extracted fields are correct and legible.",
    )


class BankTransaction(BaseModel):
    """A transaction synced from Stitch, normalised for matching."""

    id: str
    amount: float
    currency: str = "ZAR"
    reference: str | None = None
    description: str | None = None
    date: datetime


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str | None = None


class DecisionResult(BaseModel):
    verdict: Verdict
    confidence: float
    matched_transaction_id: str | None = None
    checks: list[CheckResult] = Field(default_factory=list)

    @property
    def reasons(self) -> list[str]:
        return [c.detail or c.name for c in self.checks if not c.passed]
