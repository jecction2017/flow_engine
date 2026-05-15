"""Secret reference resolution and pluggable crypto backends."""

from flow_engine.secrets.errors import SecretError
from flow_engine.secrets.reference import is_secret_reference, parse_secret_reference

__all__ = [
    "SecretError",
    "is_secret_reference",
    "parse_secret_reference",
]


def __getattr__(name: str):  # noqa: ANN001
    if name in {
        "decrypt_secret_by_name",
        "decrypt_with_type",
        "encrypt_plaintext",
        "resolve_secret_value",
    }:
        from flow_engine.secrets import service as _svc

        return getattr(_svc, name)
    raise AttributeError(name)
