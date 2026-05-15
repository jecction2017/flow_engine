"""Pluggable secret crypto backends."""

from __future__ import annotations

from typing import Any, Protocol


class SecretCryptoBackend(Protocol):
    """Encrypt/decrypt using backend-specific ``secret_data`` JSON."""

    secret_type: str

    def encrypt(self, plaintext: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return ``secret_data`` blob to store in ``fe_secret``."""
        ...

    def decrypt(self, secret_data: dict[str, Any], *, context: dict[str, Any] | None = None) -> str:
        """Decrypt ``secret_data`` to plaintext."""
        ...
