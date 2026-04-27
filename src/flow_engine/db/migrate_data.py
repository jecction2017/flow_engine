from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from flow_engine.db.models import (
    Base,
    FeDictModule,
    FeEnvProfile,
    FeFlow,
    FeFlowDraft,
    FeFlowVersion,
    FeLookupNs,
    FeLookupRow,
    FeUserScript,
)
from flow_engine.db.session import db_session, get_engine


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return data


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def _upsert_profile(profile_code: str, *, is_default: bool) -> None:
    with db_session() as s:
        row = s.execute(
            select(FeEnvProfile).where(FeEnvProfile.profile_code == profile_code)
        ).scalar_one_or_none()
        if row is None:
            row = FeEnvProfile(
                profile_code=profile_code,
                display_name=profile_code,
                is_default=1 if is_default else 0,
                deleted_at=None,
            )
            s.add(row)
        else:
            row.display_name = row.display_name or profile_code
            row.is_default = 1 if is_default else 0
            row.deleted_at = None


def migrate_profiles(data_dir: Path) -> dict[str, int]:
    cfg_path = data_dir / "profiles" / "config.yaml"
    if not cfg_path.exists():
        _upsert_profile("default", is_default=True)
        return {"profiles": 1}

    cfg = _read_yaml(cfg_path)
    profiles = cfg.get("profiles") or ["default"]
    if not isinstance(profiles, list):
        raise ValueError("data/profiles/config.yaml: profiles must be a list")
    default_profile = str(cfg.get("default_profile") or "default")

    for pid in profiles:
        _upsert_profile(str(pid), is_default=(str(pid) == default_profile))
    if default_profile not in {str(x) for x in profiles}:
        _upsert_profile(default_profile, is_default=True)
    return {"profiles": len({str(x) for x in profiles} | {default_profile})}


def migrate_dict(data_dir: Path) -> dict[str, int]:
    root = data_dir / "dict"
    if not root.exists():
        return {"dict_modules": 0}

    count = 0
    with db_session() as s:
        # base modules -> layer=base, profile_code=default
        base_root = root / "base"
        if base_root.exists():
            for f in base_root.rglob("*.yaml"):
                rel = f.relative_to(base_root).as_posix()
                module_code = rel[:-5].replace("/", ".")
                text = f.read_text(encoding="utf-8")
                row = s.execute(
                    select(FeDictModule)
                    .where(FeDictModule.layer == "base")
                    .where(FeDictModule.profile_code == "default")
                    .where(FeDictModule.module_code == module_code)
                ).scalar_one_or_none()
                if row is None:
                    s.add(
                        FeDictModule(
                            layer="base",
                            profile_code="default",
                            module_code=module_code,
                            yaml_text=text,
                            deleted_at=None,
                        )
                    )
                else:
                    row.yaml_text = text
                    row.deleted_at = None
                count += 1

        # profile modules -> layer=profile, profile_code=<profile>
        profiles_root = root / "profiles"
        if profiles_root.exists():
            for pf in profiles_root.iterdir():
                if not pf.is_dir():
                    continue
                profile_code = pf.name
                for f in pf.rglob("*.yaml"):
                    rel = f.relative_to(pf).as_posix()
                    module_code = rel[:-5].replace("/", ".")
                    text = f.read_text(encoding="utf-8")
                    row = s.execute(
                        select(FeDictModule)
                        .where(FeDictModule.layer == "profile")
                        .where(FeDictModule.profile_code == profile_code)
                        .where(FeDictModule.module_code == module_code)
                    ).scalar_one_or_none()
                    if row is None:
                        s.add(
                            FeDictModule(
                                layer="profile",
                                profile_code=profile_code,
                                module_code=module_code,
                                yaml_text=text,
                                deleted_at=None,
                            )
                        )
                    else:
                        row.yaml_text = text
                        row.deleted_at = None
                    count += 1
    return {"dict_modules": count}


def _parse_version_file_name(name: str) -> int | None:
    if not name.startswith("v") or not name.endswith(".yaml"):
        return None
    raw = name[1:-5]
    return int(raw) if raw.isdigit() else None


def migrate_flows(data_dir: Path) -> dict[str, int]:
    flows_root = data_dir / "flows"
    if not flows_root.exists():
        return {"flows": 0, "flow_versions": 0, "flow_drafts": 0}

    flow_count = 0
    ver_count = 0
    draft_count = 0

    for meta_path in flows_root.glob("*/meta.json"):
        flow_dir = meta_path.parent
        flow_code = flow_dir.name
        meta = _read_json(meta_path)

        latest_ver = int(meta.get("latest_version") or 0)
        has_draft = bool(meta.get("has_draft"))

        draft_path = flow_dir / "draft.yaml"
        draft_body: dict[str, Any] | None = None
        display_name = flow_code
        if draft_path.exists():
            draft_body = _read_yaml(draft_path)
            display_name = str(draft_body.get("display_name") or draft_body.get("name") or flow_code)

        versions_meta = {}
        for item in meta.get("versions", []):
            if isinstance(item, dict) and "version" in item:
                versions_meta[int(item["version"])] = item

        with db_session() as s:
            flow_row = s.execute(
                select(FeFlow).where(FeFlow.flow_code == flow_code)
            ).scalar_one_or_none()
            if flow_row is None:
                flow_row = FeFlow(
                    flow_code=flow_code,
                    display_name=display_name,
                    latest_ver_no=latest_ver,
                    has_draft=1 if has_draft and draft_body is not None else 0,
                    deleted_at=None,
                )
                s.add(flow_row)
            else:
                flow_row.display_name = display_name
                flow_row.latest_ver_no = latest_ver
                flow_row.has_draft = 1 if has_draft and draft_body is not None else 0
                flow_row.deleted_at = None

            if draft_body is not None:
                draft_text = json.dumps(draft_body, ensure_ascii=False)
                draft_row = s.execute(
                    select(FeFlowDraft).where(FeFlowDraft.flow_code == flow_code)
                ).scalar_one_or_none()
                if draft_row is None:
                    s.add(
                        FeFlowDraft(
                            flow_code=flow_code,
                            body=draft_text,
                            deleted_at=None,
                        )
                    )
                else:
                    draft_row.body = draft_text
                    draft_row.deleted_at = None
                draft_count += 1

            versions_dir = flow_dir / "versions"
            if versions_dir.exists():
                for vf in versions_dir.glob("v*.yaml"):
                    ver_no = _parse_version_file_name(vf.name)
                    if ver_no is None:
                        continue
                    body = _read_yaml(vf)
                    body_text = json.dumps(body, ensure_ascii=False)
                    vm = versions_meta.get(ver_no, {})
                    row = s.execute(
                        select(FeFlowVersion)
                        .where(FeFlowVersion.flow_code == flow_code)
                        .where(FeFlowVersion.ver_no == ver_no)
                    ).scalar_one_or_none()
                    if row is None:
                        s.add(
                            FeFlowVersion(
                                flow_code=flow_code,
                                ver_no=ver_no,
                                body=body_text,
                                display_name=str(vm.get("display_name") or body.get("display_name") or body.get("name") or flow_code),
                                description=str(vm.get("description") or ""),
                                deleted_at=None,
                            )
                        )
                    else:
                        row.body = body_text
                        row.display_name = str(vm.get("display_name") or body.get("display_name") or body.get("name") or flow_code)
                        row.description = str(vm.get("description") or "")
                        row.deleted_at = None
                    ver_count += 1
        flow_count += 1

    return {"flows": flow_count, "flow_versions": ver_count, "flow_drafts": draft_count}


def migrate_lookup(data_dir: Path) -> dict[str, int]:
    root = data_dir / "lookup" / "profiles"
    if not root.exists():
        return {"lookup_tables": 0, "lookup_rows": 0}

    table_count = 0
    row_count = 0
    with db_session() as s:
        for profile_dir in root.iterdir():
            if not profile_dir.is_dir():
                continue
            profile_code = profile_dir.name
            for jf in profile_dir.glob("*.json"):
                ns_code = jf.stem
                payload = _read_json(jf)
                schema = payload.get("schema") or {"type": "object", "properties": {}}
                rows = payload.get("rows") or []
                if not isinstance(schema, dict):
                    raise ValueError(f"lookup schema must be object: {jf}")
                if not isinstance(rows, list):
                    raise ValueError(f"lookup rows must be list: {jf}")

                ns = s.execute(
                    select(FeLookupNs)
                    .where(FeLookupNs.profile_code == profile_code)
                    .where(FeLookupNs.ns_code == ns_code)
                ).scalar_one_or_none()
                if ns is None:
                    ns = FeLookupNs(
                        profile_code=profile_code,
                        ns_code=ns_code,
                        schema_json=schema,
                        deleted_at=None,
                    )
                    s.add(ns)
                else:
                    ns.schema_json = schema
                    ns.deleted_at = None

                # hard replace active rows for deterministic migration
                old_rows = s.execute(
                    select(FeLookupRow)
                    .where(FeLookupRow.profile_code == profile_code)
                    .where(FeLookupRow.ns_code == ns_code)
                ).scalars().all()
                for old in old_rows:
                    s.delete(old)

                for row in rows:
                    if not isinstance(row, dict):
                        raise ValueError(f"lookup row must be object: {jf}")
                    s.add(
                        FeLookupRow(
                            profile_code=profile_code,
                            ns_code=ns_code,
                            row_data=row,
                            deleted_at=None,
                        )
                    )
                    row_count += 1
                table_count += 1
    return {"lookup_tables": table_count, "lookup_rows": row_count}


def migrate_user_scripts(data_dir: Path) -> dict[str, int]:
    root = data_dir / "starlark_user"
    if not root.exists():
        return {"user_scripts": 0}

    count = 0
    with db_session() as s:
        for tenant_dir in root.iterdir():
            if not tenant_dir.is_dir():
                continue
            tenant = tenant_dir.name
            for sf in tenant_dir.rglob("*.star"):
                rel_path = sf.relative_to(tenant_dir).as_posix()
                content = sf.read_text(encoding="utf-8")
                row = s.execute(
                    select(FeUserScript)
                    .where(FeUserScript.tenant == tenant)
                    .where(FeUserScript.rel_path == rel_path)
                ).scalar_one_or_none()
                if row is None:
                    s.add(
                        FeUserScript(
                            tenant=tenant,
                            rel_path=rel_path,
                            content=content,
                            deleted_at=None,
                        )
                    )
                else:
                    row.content = content
                    row.deleted_at = None
                count += 1
    return {"user_scripts": count}


def migrate_all_data(data_dir: str | Path) -> dict[str, int]:
    data_path = Path(data_dir).resolve()
    if not data_path.exists():
        raise FileNotFoundError(f"data directory not found: {data_path}")

    # Ensure schema exists before migration.
    Base.metadata.create_all(bind=get_engine())

    stats: dict[str, int] = {}
    for fn in (
        migrate_profiles,
        migrate_dict,
        migrate_flows,
        migrate_lookup,
        migrate_user_scripts,
    ):
        stats.update(fn(data_path))
    return stats
