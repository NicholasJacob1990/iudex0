"""
Webhook validation utilities for Microsoft Graph change notifications.
Uses HMAC-SHA256 to prevent webhook spoofing.
"""

import hashlib
import hmac

from app.core.config import settings


def validate_client_state(received_state: str) -> bool:
    """Validate clientState from Graph change notifications."""
    if not settings.GRAPH_WEBHOOK_SECRET:
        return False

    expected = generate_client_state(settings.GRAPH_WEBHOOK_SECRET)
    return hmac.compare_digest(received_state, expected)


def generate_client_state(secret: str) -> str:
    """Generate clientState for subscription registration."""
    return hmac.new(
        secret.encode("utf-8"),
        msg=b"graph-notification",
        digestmod=hashlib.sha256,
    ).hexdigest()
