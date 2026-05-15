"""Local Fernet (AES-128-CBC + HMAC) using ``FLOW_SECRET_MASTER_KEY``."""

from __future__ import annotations

import base64
import os
from typing import Any

from flow_engine.secrets.errors import SecretError

_SECRET_DATA_VERSION = 1


def _master_key_bytes() -> bytes:
    raw = (os.environ.get("FLOW_SECRET_MASTER_KEY") or "").strip()
    if not raw:
        raise SecretError(
            "FLOW_SECRET_MASTER_KEY is not set; required for local_fernet encrypt/decrypt"
        )
    try:
        key = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as e:
        raise SecretError("FLOW_SECRET_MASTER_KEY must be url-safe base64") from e
    if len(key) != 32:
        raise SecretError(
            f"FLOW_SECRET_MASTER_KEY must decode to 32 bytes (Fernet key), got {len(key)}"
        )
    return key


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise SecretError(
            "cryptography package is required for local_fernet; "
            "install flow-engine[mysql] or cryptography"
        ) from e
    return Fernet(base64.urlsafe_b64encode(_master_key_bytes()))


class LocalFernetBackend:
    """Symmetric encryption with a deployment-wide master key from env."""

    secret_type = "local_fernet"

    def encrypt(self, plaintext: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        token = _fernet().encrypt(plaintext.encode("utf-8"))
        return {
            "version": _SECRET_DATA_VERSION,
            "ciphertext": token.decode("ascii"),
        }

    def decrypt(self, secret_data: dict[str, Any], *, context: dict[str, Any] | None = None) -> str:
        del context
        if not isinstance(secret_data, dict):
            raise SecretError("secret_data must be a JSON object")
        version = secret_data.get("version")
        if version != _SECRET_DATA_VERSION:
            raise SecretError(f"Unsupported local_fernet secret_data version: {version!r}")
        ciphertext = secret_data.get("ciphertext")
        if not isinstance(ciphertext, str) or not ciphertext.strip():
            raise SecretError("local_fernet secret_data requires non-empty 'ciphertext'")
        try:
            plain = _fernet().decrypt(ciphertext.encode("ascii"))
        except Exception as e:
            raise SecretError("local_fernet decrypt failed") from e
        return plain.decode("utf-8")
