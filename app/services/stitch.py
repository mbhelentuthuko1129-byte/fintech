"""Stitch API integration (South African open banking).

Phase 1 scope: client-credentials auth + pulling recent incoming transactions
for a business's linked account so the decision engine can match against them.
Account linking itself (user-consent OAuth flow) is a Console/onboarding task —
we store the resulting account linkage status on the `businesses` row.

If Stitch isn't configured or the business isn't linked, callers get
`bank_data_available=False` and the pipeline degrades to PENDING verdicts.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings
from app.models.schemas import BankTransaction

logger = logging.getLogger(__name__)

_TRANSACTIONS_QUERY = """
query GetAccountTransactions($accountId: ID!, $from: Date!) {
  node(id: $accountId) {
    ... on BankAccount {
      transactions(filter: { date: { gte: $from } }) {
        edges {
          node {
            id
            amount { quantity currency }
            reference
            description
            date
          }
        }
      }
    }
  }
}
"""


def is_configured() -> bool:
    s = get_settings()
    return bool(s.stitch_client_id and s.stitch_client_secret)


def _get_access_token() -> str:
    s = get_settings()
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            s.stitch_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": s.stitch_client_id,
                "client_secret": s.stitch_client_secret,
                "scope": "client_bankaccountdata",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def fetch_recent_incoming_transactions(
    stitch_account_id: str, lookback_days: int = 7
) -> list[BankTransaction]:
    """Pull recent transactions for the linked account; credits only."""
    token = _get_access_token()
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            get_settings().stitch_api_url,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": _TRANSACTIONS_QUERY,
                "variables": {"accountId": stitch_account_id, "from": since},
            },
        )
        resp.raise_for_status()
        payload = resp.json()

    if payload.get("errors"):
        logger.error("stitch query failed", extra={"errors": payload["errors"]})
        raise RuntimeError(f"Stitch query failed: {payload['errors']}")

    edges = (((payload.get("data") or {}).get("node") or {}).get("transactions") or {}).get("edges", [])
    transactions: list[BankTransaction] = []
    for edge in edges:
        node = edge["node"]
        amount = float(node["amount"]["quantity"])
        if amount <= 0:  # only incoming money can verify a PoP
            continue
        transactions.append(
            BankTransaction(
                id=node["id"],
                amount=amount,
                currency=node["amount"].get("currency", "ZAR"),
                reference=node.get("reference"),
                description=node.get("description"),
                date=datetime.fromisoformat(node["date"]),
            )
        )
    return transactions
