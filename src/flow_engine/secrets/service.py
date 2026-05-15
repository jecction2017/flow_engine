"""Secret resolution and encrypt/decrypt orchestration."""

from __future__ import annotations

import copy
from typing import Any

from flow_engine.secrets.errors import SecretError
from flow_engine.secrets.reference import is_secret_reference, parse_secret_reference
from flow_engine.secrets.registry import get_backend
from flow_engine.stores.secret_store import SecretStoreError


def encrypt_plaintext(
    secret_type: str,
    plaintext: str,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Encrypt plaintext; returns ``secret_data`` JSON for storage in fe_secret."""
    backend = get_backend(secret_type)
    return backend.encrypt(plaintext, context=context)


def decrypt_with_type(
    secret_type: str,
    secret_data: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> str:
    backend = get_backend(secret_type)
    if not isinstance(secret_data, dict):
        raise SecretError("secret_data must be a JSON object")
    return backend.decrypt(secret_data, context=context)


def decrypt_secret_by_name(
    secret_name: str,
    *,
    profile: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    from flow_engine.stores.profile_store import active_profile
    from flow_engine.stores.secret_store import store as secret_store

    pid = profile if profile is not None else active_profile()
    rec = secret_store().get_secret(secret_name, profile=pid)
    return decrypt_with_type(rec.secret_type, rec.secret_data, context=context)


def resolve_secret_value(
    value: Any,
    *,
    profile: str | None = None,
    context: dict[str, Any] | None = None,
) -> Any:
    """If ``value`` is ``secret://name``, decrypt; otherwise return unchanged."""
    if not is_secret_reference(value):
        return value
    name = parse_secret_reference(str(value))
    return decrypt_secret_by_name(name, profile=profile, context=context)


def resolve_secret_references(
    tree: Any,
    *,
    profile: str | None = None,
    context: dict[str, Any] | None = None,
) -> Any:
    """Deep-copy tree and replace all ``secret://`` string leaves with plaintext.

    For Python integration modules only — not used by flow runtime, HTTP, or Starlark.
    """
    if isinstance(tree, dict):
        return {
            k: resolve_secret_references(v, profile=profile, context=context)
            for k, v in tree.items()
        }
    if isinstance(tree, list):
        return [
            resolve_secret_references(item, profile=profile, context=context)
            for item in tree
        ]
    if is_secret_reference(tree):
        return resolve_secret_value(tree, profile=profile, context=context)
    return tree
