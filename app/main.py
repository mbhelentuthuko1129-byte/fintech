"""FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.config import get_settings
from app.logging_config import configure_logging
from app.routes import internal, webhook

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="WhatsApp PoP Verification",
    description="Detects fake/edited proof-of-payment screenshots for SA SMEs over WhatsApp.",
    version="0.1.0",
)

app.include_router(webhook.router)
app.include_router(internal.router)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "env": settings.app_env}
