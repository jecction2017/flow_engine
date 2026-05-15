"""Parse secret references in dictionary values.

Format: ``secret://<name>`` (YAML-safe, no custom tag).

Example in dictionary YAML::

    pwd: secret://es_password
"""

from __future__ import annotations

import re

from flow_engine.secrets.errors import SecretError

# secret://name — not a YAML tag; safe unquoted in mapping values
SECRET_REFERENCE_RE = re.compile(
    r"^secret://([a-z][a-z0-9_-]{0,63})$",
    re.IGNORECASE,
)


def is_secret_reference(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return SECRET_REFERENCE_RE.fullmatch(value.strip()) is not None


def parse_secret_reference(value: str) -> str:
    """Return secret name from a reference string."""
    text = value.strip()
    m = SECRET_REFERENCE_RE.fullmatch(text)
    if m is None:
        raise SecretError(
            f"Invalid secret reference {value!r}; expected 'secret://<name>' "
            "(name: ^[a-z][a-z0-9_-]{{0,63}}$)"
        )
    return m.group(1).lower()
