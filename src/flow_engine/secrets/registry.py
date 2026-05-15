"""Registry of ``SecretCryptoBackend`` implementations by ``secret_type``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flow_engine.secrets.errors import SecretError

if TYPE_CHECKING:
    from flow_engine.secrets.protocol import SecretCryptoBackend

_backends: dict[str, SecretCryptoBackend] = {}
_bootstrapped = False


def register_backend(backend: SecretCryptoBackend) -> None:
    key = (backend.secret_type or "").strip().lower()
    if not key:
        raise SecretError("secret_type must be non-empty")
    _backends[key] = backend


def get_backend(secret_type: str) -> SecretCryptoBackend:
    _ensure_bootstrapped()
    key = (secret_type or "").strip().lower()
    backend = _backends.get(key)
    if backend is None:
        known = ", ".join(sorted(_backends)) or "(none)"
        raise SecretError(f"Unknown secret_type {secret_type!r}; registered: {known}")
    return backend


def list_secret_types() -> list[str]:
    _ensure_bootstrapped()
    return sorted(_backends)


def _ensure_bootstrapped() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    from flow_engine.secrets.backends.local_fernet import LocalFernetBackend

    register_backend(LocalFernetBackend())
    _bootstrapped = True


def reset_registry_for_tests() -> None:
    """Clear registry (tests only)."""
    global _bootstrapped
    _backends.clear()
    _bootstrapped = False
