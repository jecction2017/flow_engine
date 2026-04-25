"""Global runtime profile configuration (dev/sit/prod, etc.)."""

from __future__ import annotations

import copy
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

import yaml

from flow_engine._repo_root import repo_root
from flow_engine.engine.exceptions import FlowEngineError

DEFAULT_PROFILE_ID = "default"
PROFILE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ProfileConfigError(FlowEngineError):
    """Invalid profile id or broken profile config file."""


def validate_profile_id(profile_id: str) -> str:
    pid = (profile_id or "").strip()
    if not PROFILE_ID_PATTERN.fullmatch(pid):
        raise ProfileConfigError(
            f"Invalid profile_id {profile_id!r}; expected ^[a-z][a-z0-9_-]{{0,63}}$"
        )
    return pid


def _profile_dir() -> Path:
    raw = os.environ.get("FLOW_ENGINE_PROFILE_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (repo_root() / "data" / "profiles").resolve()


class GlobalProfileStore:
    """Persists global profile list + default profile in YAML."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _profile_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config_path = self.directory / "config.yaml"
        self._ensure_default_config()

    def _ensure_default_config(self) -> None:
        if not self.config_path.is_file():
            self._write_config({"default_profile": DEFAULT_PROFILE_ID, "profiles": [DEFAULT_PROFILE_ID]})
        self._sync_backing_dirs()

    def _read_config(self) -> dict[str, Any]:
        raw = self.config_path.read_text(encoding="utf-8")
        loaded = yaml.safe_load(raw) if raw.strip() else {}
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ProfileConfigError("profile config root must be a mapping")

        default_profile = validate_profile_id(str(loaded.get("default_profile") or DEFAULT_PROFILE_ID))
        profiles_raw = loaded.get("profiles")
        if profiles_raw is None:
            profiles = [default_profile]
        elif isinstance(profiles_raw, list):
            profiles = [validate_profile_id(str(x)) for x in profiles_raw]
        else:
            raise ProfileConfigError("profiles must be a list")

        uniq_profiles = sorted(set(profiles + [default_profile]))
        return {"default_profile": default_profile, "profiles": uniq_profiles}

    def _write_config(self, data: dict[str, Any]) -> None:
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
        self.config_path.write_text(text, encoding="utf-8", newline="\n")

    def _sync_backing_dirs(self) -> None:
        cfg = self._read_config()
        from flow_engine.lookup.lookup_store import get_lookup_store
        from flow_engine.stores import data_dict

        dict_store = data_dict.store()
        lookup_store = get_lookup_store()
        for profile in cfg["profiles"]:
            dict_store.create_profile(profile)
            lookup_store.create_profile(profile)

    def list_profiles(self) -> list[str]:
        return copy.deepcopy(self._read_config()["profiles"])

    def get_default_profile(self) -> str:
        return self._read_config()["default_profile"]

    def create_profile(self, profile_id: str) -> str:
        pid = validate_profile_id(profile_id)
        cfg = self._read_config()
        if pid not in cfg["profiles"]:
            cfg["profiles"] = sorted(cfg["profiles"] + [pid])
            self._write_config(cfg)
        self._sync_backing_dirs()
        return pid

    def set_default_profile(self, profile_id: str) -> str:
        pid = validate_profile_id(profile_id)
        cfg = self._read_config()
        if pid not in cfg["profiles"]:
            cfg["profiles"] = sorted(cfg["profiles"] + [pid])
        cfg["default_profile"] = pid
        self._write_config(cfg)
        self._sync_backing_dirs()
        return pid

    def resolve_profile(self, explicit_profile: str | None = None) -> str:
        if explicit_profile:
            pid = validate_profile_id(explicit_profile)
            if pid not in self.list_profiles():
                raise ProfileConfigError(f"Profile not found: {pid}")
            return pid
        return self.get_default_profile()


_store_cache: tuple[str, GlobalProfileStore] | None = None
_active_profile: ContextVar[str | None] = ContextVar("flow_engine_active_profile", default=None)


def invalidate_profile_store_cache() -> None:
    global _store_cache
    _store_cache = None


def store() -> GlobalProfileStore:
    global _store_cache
    key = str(_profile_dir())
    if _store_cache is None or _store_cache[0] != key:
        _store_cache = (key, GlobalProfileStore())
    return _store_cache[1]


def active_profile() -> str:
    cur = _active_profile.get()
    return store().resolve_profile(cur)


@contextmanager
def profile_scope(profile_id: str | None) -> Iterator[str]:
    resolved = store().resolve_profile(profile_id)
    token = _active_profile.set(resolved)
    try:
        yield resolved
    finally:
        _active_profile.reset(token)
