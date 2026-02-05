"""
Credential encryption utilities for sensitive data stored in user preferences.

Uses Fernet symmetric encryption with a key derived from the SECRET_KEY setting.
Encrypted values are stored as base64 strings prefixed with 'enc:' to distinguish
from plaintext values (for backward compatibility during migration).
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_ENCRYPTED_PREFIX = "enc:"


def _get_fernet_key() -> bytes:
    """Derive a Fernet-compatible key from the application SECRET_KEY."""
    from app.core.config import settings
    secret = settings.SECRET_KEY
    if not secret:
        raise RuntimeError(
            "SECRET_KEY must be set for credential encryption. "
            "Set it in your environment or .env file."
        )
    # Fernet requires a 32-byte url-safe base64-encoded key
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string. Returns prefixed base64 ciphertext."""
    if not plaintext:
        return ""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError(
            "cryptography package is required for credential encryption. "
            "Install it with: pip install cryptography"
        )
    try:
        f = Fernet(_get_fernet_key())
        encrypted = f.encrypt(plaintext.encode())
        return _ENCRYPTED_PREFIX + encrypted.decode()
    except Exception as e:
        logger.error(f"[CredentialEncryption] encrypt error: {type(e).__name__}")
        raise


def decrypt_credential(value: str) -> str:
    """Decrypt a credential string. Handles both encrypted (prefixed) and plaintext values."""
    if not value:
        return ""
    if not value.startswith(_ENCRYPTED_PREFIX):
        # Plaintext (legacy or fallback) — return as-is
        return value
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError(
            "cryptography package is required for credential decryption. "
            "Install it with: pip install cryptography"
        )
    try:
        f = Fernet(_get_fernet_key())
        encrypted_bytes = value[len(_ENCRYPTED_PREFIX):].encode()
        return f.decrypt(encrypted_bytes).decode()
    except Exception as e:
        logger.error(f"[CredentialEncryption] decrypt error: {type(e).__name__}")
        raise ValueError("Failed to decrypt credential. Key may have changed.")


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted (has the enc: prefix)."""
    return bool(value) and value.startswith(_ENCRYPTED_PREFIX)
