"""Read/write flow definitions as YAML files on disk."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")


def _flows_dir() -> Path:
    raw = os.environ.get("FLOW_ENGINE_FLOWS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "flows").resolve()


def validate_flow_id(flow_id: str) -> str:
    if not flow_id or not _SAFE_ID.match(flow_id):
        raise ValueError(
            "Invalid flow id: use letters, digits, underscore or hyphen (max 128 chars).",
        )
    return flow_id


@dataclass
class FlowFileInfo:
    id: str
    name: str
    path: str
    updated_at: float | None


class FlowYamlStore:
    """Persists one flow per ``{flow_id}.yaml`` file."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _flows_dir()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, flow_id: str) -> Path:
        fid = validate_flow_id(flow_id)
        return self.directory / f"{fid}.yaml"

    def exists(self, flow_id: str) -> bool:
        return self._path(flow_id).is_file()

    def path_for(self, flow_id: str) -> Path:
        """Resolved ``.yaml`` path for a valid id."""
        return self._path(flow_id)

    def list_flows(self) -> list[FlowFileInfo]:
        out: list[FlowFileInfo] = []
        if not self.directory.is_dir():
            return out
        for p in sorted(self.directory.glob("*.yaml")):
            fid = p.stem
            try:
                validate_flow_id(fid)
            except ValueError:
                continue
            stat = p.stat()
            name = fid
            try:
                with p.open(encoding="utf-8") as f:
                    head = yaml.safe_load(f) or {}
                if isinstance(head, dict) and head.get("name"):
                    name = str(head["name"])
            except OSError:
                pass
            out.append(
                FlowFileInfo(
                    id=fid,
                    name=name,
                    path=str(p),
                    updated_at=stat.st_mtime,
                ),
            )
        return out

    def read_raw(self, flow_id: str) -> dict[str, Any]:
        path = self._path(flow_id)
        if not path.is_file():
            raise FileNotFoundError(flow_id)
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError("YAML root must be a mapping")
        return data

    def write_raw(self, flow_id: str, data: dict[str, Any]) -> None:
        path = self._path(flow_id)
        text = yaml.safe_dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        path.write_text(text, encoding="utf-8")

    def delete(self, flow_id: str) -> None:
        path = self._path(flow_id)
        if path.is_file():
            path.unlink()
