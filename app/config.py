"""Application configuration loaded from environment variables.

All secrets come from the environment — nothing is hardcoded. See .env.example
for the full list of variables and what they're for.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"

    # --- WhatsApp Cloud API (Meta) ---
    whatsapp_verify_token: str = ""  # token you choose; Meta echoes it on webhook setup
    whatsapp_app_secret: str = ""  # used to verify X-Hub-Signature-256 on inbound webhooks
    whatsapp_access_token: str = ""  # system-user token for Graph API calls
    whatsapp_api_version: str = "v21.0"
    whatsapp_graph_base_url: str = "https://graph.facebook.com"

    # --- Anthropic (Claude Vision) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # --- Stitch (SA open banking) ---
    stitch_client_id: str = ""
    stitch_client_secret: str = ""
    stitch_token_url: str = "https://secure.stitch.money/connect/token"
    stitch_api_url: str = "https://api.stitch.money/graphql"

    # --- Supabase ---
    supabase_url: str = ""
    supabase_service_role_key: str = ""  # backend uses service role; RLS protects other clients
    supabase_storage_bucket: str = "pop-images"
    supabase_invoice_bucket: str = "invoices"

    # --- Internal automation (n8n) ---
    internal_api_key: str = ""  # shared secret for /internal/* endpoints called by n8n

    # --- Decision engine tuning ---
    match_time_window_hours: int = 72  # EFT can lag; how far around the claimed time to match
    amount_tolerance_cents: int = 0  # exact amount match by default
    min_extraction_confidence: float = 0.5

    # --- Payment reminders (Phase 2) ---
    reminder_cadence_days: int = 3  # days between follow-ups once a debt is overdue
    reminder_max_sends: int = 3  # stop nagging after this many reminders


@lru_cache
def get_settings() -> Settings:
    return Settings()
