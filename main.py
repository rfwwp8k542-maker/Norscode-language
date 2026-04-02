import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

from compiler.cgen import CGenerator
from compiler.lexer import Lexer
from compiler.loader import ModuleLoader
from compiler.parser import Parser
from compiler.semantic import SemanticAnalyzer


IR_OPS_WITH_ARG = {"PUSH", "LABEL", "JMP", "JZ", "CALL", "STORE", "LOAD"}
IR_OPS_NO_ARG = {
    "ADD",
    "SUB",
    "MUL",
    "DIV",
    "MOD",
    "EQ",
    "GT",
    "LT",
    "AND",
    "OR",
    "NOT",
    "DUP",
    "POP",
    "SWAP",
    "OVER",
    "PRINT",
    "HALT",
    "RET",
}
IR_ALL_OPS = IR_OPS_WITH_ARG | IR_OPS_NO_ARG
IR_SNAPSHOT_FIXTURE = Path("tests/ir_snapshot_cases.json")
PROJECT_CONFIG_NAME = "norcode.toml"
LEGACY_PROJECT_CONFIG_NAME = "norsklang.toml"
PROJECT_CONFIG_NAMES = (PROJECT_CONFIG_NAME, LEGACY_PROJECT_CONFIG_NAME)
PYPROJECT_NAME = "pyproject.toml"
CHANGELOG_NAME = "CHANGELOG.md"
LOCKFILE_NAME = "norcode.lock"
LEGACY_LOCKFILE_NAME = "norsklang.lock"
LOCKFILE_NAMES = (LOCKFILE_NAME, LEGACY_LOCKFILE_NAME)
REMOTE_REGISTRY_CACHE = ".norcode/registry/remote_index.json"
LEGACY_REMOTE_REGISTRY_CACHE = ".norsklang/registry/remote_index.json"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_LEGACY_WARNINGS_EMITTED: set[str] = set()


def _warn_legacy_once(key: str, message: str):
    if key in _LEGACY_WARNINGS_EMITTED:
        return
    _LEGACY_WARNINGS_EMITTED.add(key)
    print(message, file=sys.stderr)


def _find_existing_project_config_in_dir(base: Path) -> Path | None:
    for name in PROJECT_CONFIG_NAMES:
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def _project_config_display_names() -> str:
    return " / ".join(PROJECT_CONFIG_NAMES)


def _find_project_config(start_dir: Path | None = None) -> Path:
    base = (start_dir or Path.cwd()).resolve()
    for candidate_dir in (base, *base.parents):
        candidate = _find_existing_project_config_in_dir(candidate_dir)
        if candidate is not None:
            if candidate.name == LEGACY_PROJECT_CONFIG_NAME:
                _warn_legacy_once(
                    "legacy-config",
                    "Merk: bruker legacy konfig 'norsklang.toml'. Bytt til 'norcode.toml'.",
                )
            return candidate
    raise RuntimeError(
        f"Fant ikke {_project_config_display_names()} i denne mappen eller overliggende mapper"
    )


def _parse_toml_string(raw: str) -> str | None:
    value = raw.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return None


def _parse_project_name_from_toml(path: Path) -> str | None:
    current_section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            continue
        if current_section == "project" and "=" in stripped:
            key, value = stripped.split("=", 1)
            if key.strip() == "name":
                return _parse_toml_string(value)
    return None


def _resolve_package_dir(package_path: str) -> tuple[Path, Path]:
    path = Path(package_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()

    if path.is_file():
        if path.name not in PROJECT_CONFIG_NAMES:
            raise RuntimeError(f"Sti peker til fil, men ikke {_project_config_display_names()}: {path}")
        package_dir = path.parent
        package_config = path
    else:
        package_dir = path
        package_config = _find_existing_project_config_in_dir(package_dir) or (package_dir / PROJECT_CONFIG_NAME)

    if not package_dir.exists():
        raise RuntimeError(f"Fant ikke pakkesti: {package_dir}")
    if not package_dir.is_dir():
        raise RuntimeError(f"Pakkesti må være mappe: {package_dir}")
    if not package_config.exists():
        raise RuntimeError(f"Fant ikke pakkekonfig: {package_config}")

    return package_dir, package_config


def _load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Kunne ikke lese TOML {path}: {exc}") from exc


def _load_security_policy(config_path: Path) -> dict:
    data = _load_toml(config_path)
    sec = data.get("security", {})
    if not isinstance(sec, dict):
        sec = {}

    def to_set(key: str) -> set[str]:
        raw = sec.get(key, [])
        if isinstance(raw, list):
            return {str(x).strip().lower() for x in raw if isinstance(x, str) and str(x).strip()}
        return set()

    return {
        "trusted_git_hosts": to_set("trusted_git_hosts"),
        "trusted_url_hosts": to_set("trusted_url_hosts"),
        "trusted_registry_sha256": (
            str(sec.get("trusted_registry_sha256")).strip().lower()
            if isinstance(sec.get("trusted_registry_sha256"), str) and str(sec.get("trusted_registry_sha256")).strip()
            else None
        ),
    }


def _verify_registry_integrity(config_path: Path, registry_file: Path):
    policy = _load_security_policy(config_path)
    expected = policy.get("trusted_registry_sha256")
    if expected is None:
        return

    if not _is_valid_sha256(expected):
        raise RuntimeError("Ugyldig [security].trusted_registry_sha256 i norcode.toml")

    if not registry_file.exists():
        raise RuntimeError(f"Registry-fil mangler, men trusted_registry_sha256 er satt: {registry_file}")

    actual = _hash_file(registry_file).lower()
    if actual != expected:
        raise RuntimeError(
            f"Registry-integritet feilet: expected {expected}, actual {actual} ({registry_file})"
        )


def _extract_git_host(git_url: str) -> str | None:
    raw = git_url.strip()
    if not raw:
        return None
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.hostname:
        return parsed.hostname.lower()
    if "@" in raw and ":" in raw and "://" not in raw:
        after_at = raw.split("@", 1)[1]
        host = after_at.split(":", 1)[0].strip().lower()
        return host or None
    return None


def _extract_url_host(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        return "file"
    if parsed.hostname:
        return parsed.hostname.lower()
    return None


def _host_matches(host: str, allowlist: set[str]) -> bool:
    if host in allowlist:
        return True
    for allowed in allowlist:
        if allowed.startswith("*.") and host.endswith(allowed[1:]):
            return True
    return False


def _enforce_trusted_source(kind: str, source: str, security_policy: dict, allow_untrusted: bool = False):
    if allow_untrusted:
        return

    if kind == "git":
        allowlist = security_policy.get("trusted_git_hosts", set())
        if not allowlist:
            return
        host = _extract_git_host(source)
        if host is None:
            local_path = Path(source).expanduser()
            if local_path.exists():
                return
            raise RuntimeError(f"Git-kilde kan ikke verifiseres mot trusted hosts: {source}")
        if not _host_matches(host, allowlist):
            raise RuntimeError(f"Git-host ikke tillatt av security policy: {host}")
        return

    if kind == "url":
        allowlist = security_policy.get("trusted_url_hosts", set())
        if not allowlist:
            return
        host = _extract_url_host(source)
        if host is None:
            raise RuntimeError(f"URL-kilde kan ikke verifiseres mot trusted hosts: {source}")
        if host == "file":
            return
        if not _host_matches(host, allowlist):
            raise RuntimeError(f"URL-host ikke tillatt av security policy: {host}")
        return


def _normalize_registry_path(raw_path: str, relative_to: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (relative_to / path).resolve()


def _semver_key(version: str) -> tuple[int, int, int]:
    if not SEMVER_RE.match(version):
        return (-1, -1, -1)
    a, b, c = version.split(".")
    return int(a), int(b), int(c)


def _parse_registry_entry(name: str, value: object) -> dict | None:
    if isinstance(value, str):
        return {"kind": "path", "path": value, "description": None, "version": None, "name": name}

    if not isinstance(value, dict):
        return None

    description = value.get("description")
    version = value.get("version")
    if isinstance(value.get("path"), str):
        return {
            "kind": "path",
            "path": value["path"],
            "description": description,
            "version": version if isinstance(version, str) else None,
            "name": name,
        }
    if isinstance(value.get("git"), str):
        return {
            "kind": "git",
            "git": value["git"],
            "ref": value.get("ref") if isinstance(value.get("ref"), str) else None,
            "description": description,
            "version": version if isinstance(version, str) else None,
            "name": name,
        }
    if isinstance(value.get("url"), str):
        return {
            "kind": "url",
            "url": value["url"],
            "description": description,
            "version": version if isinstance(version, str) else None,
            "name": name,
        }
    return None


def _select_remote_version(package_name: str, package_obj: dict) -> dict | None:
    versions = package_obj.get("versions")
    if not isinstance(versions, dict) or not versions:
        return _parse_registry_entry(package_name, package_obj)

    latest = package_obj.get("latest")
    selected_version = latest if isinstance(latest, str) and latest in versions else None
    if selected_version is None:
        candidates = sorted((v for v in versions.keys() if isinstance(v, str)), key=_semver_key, reverse=True)
        selected_version = candidates[0] if candidates else None
    if selected_version is None:
        return None

    entry = _parse_registry_entry(package_name, versions[selected_version])
    if entry is None:
        return None
    entry["version"] = selected_version
    return entry


def _load_registry_source_text(source: str, project_dir: Path, security_policy: dict, allow_untrusted: bool) -> tuple[str, str]:
    if "://" in source:
        parsed = urllib.parse.urlparse(source)
        scheme = parsed.scheme.lower()
        if scheme in ("http", "https", "file"):
            _enforce_trusted_source("url", source, security_policy, allow_untrusted=allow_untrusted)
            with urllib.request.urlopen(source) as resp:
                text = resp.read().decode("utf-8")
            return source, text
        raise RuntimeError(f"Ukjent registry source scheme: {scheme}")

    source_path = Path(source).expanduser()
    if not source_path.is_absolute():
        source_path = (project_dir / source_path).resolve()
    if not source_path.exists():
        raise RuntimeError(f"Fant ikke registry source-fil: {source_path}")
    return str(source_path), source_path.read_text(encoding="utf-8")


def _parse_remote_registry_text(source_name: str, text: str) -> dict[str, dict]:
    data = None
    try:
        data = json.loads(text)
    except Exception:
        try:
            data = tomllib.loads(text)
        except Exception as exc:
            raise RuntimeError(f"Ugyldig registry-format i {source_name}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Ugyldig registry-rot i {source_name}: forventet objekt/tabell")

    raw_packages = data.get("packages", {})
    if not isinstance(raw_packages, dict):
        raise RuntimeError(f"Ugyldig packages-seksjon i {source_name}")

    out: dict[str, dict] = {}
    for pkg_name, pkg_obj in raw_packages.items():
        if not isinstance(pkg_name, str):
            continue
        entry = _select_remote_version(pkg_name, pkg_obj)
        if entry is None:
            continue
        entry["source"] = source_name
        out[pkg_name] = entry
    return out


def _remote_registry_cache_path(project_dir: Path) -> Path:
    primary = (project_dir / REMOTE_REGISTRY_CACHE).resolve()
    legacy = (project_dir / LEGACY_REMOTE_REGISTRY_CACHE).resolve()
    if primary.exists() or not legacy.exists():
        return primary
    _warn_legacy_once(
        "legacy-registry-cache",
        "Merk: bruker legacy cache '.norsklang/'. Migrer til '.norcode/'.",
    )
    return legacy


def _load_remote_registry_cache(project_dir: Path) -> dict[str, dict]:
    cache_path = _remote_registry_cache_path(project_dir)
    if not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    entries = payload.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    out = {}
    for name, obj in entries.items():
        if isinstance(name, str) and isinstance(obj, dict):
            out[name] = obj
    return out


def registry_sync(
    source_override: str | None = None,
    allow_untrusted: bool = False,
    require_all: bool = False,
    fallback_to_cache: bool = True,
):
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    security_policy = _load_security_policy(config_path)
    project_toml = _load_toml(config_path)
    registry_section = project_toml.get("registry", {}) if isinstance(project_toml.get("registry", {}), dict) else {}
    configured_sources = registry_section.get("sources", [])

    sources: list[str]
    if source_override:
        sources = [source_override]
    elif isinstance(configured_sources, list):
        sources = [s for s in configured_sources if isinstance(s, str) and s.strip()]
    else:
        sources = []

    if not sources:
        raise RuntimeError("Ingen registry-kilder satt. Bruk [registry].sources eller --source")

    merged: dict[str, dict] = {}
    used_sources: list[str] = []
    failed_sources: list[dict] = []
    for src in sources:
        try:
            source_name, text = _load_registry_source_text(src, project_dir, security_policy, allow_untrusted=allow_untrusted)
            entries = _parse_remote_registry_text(source_name, text)
        except Exception as exc:
            failed_sources.append({"source": src, "error": str(exc)})
            if require_all:
                raise RuntimeError(f"Registry-sync feilet for {src}: {exc}") from exc
            continue

        for name, entry in entries.items():
            prev = merged.get(name)
            if prev is None:
                merged[name] = entry
                continue
            prev_v = prev.get("version")
            cur_v = entry.get("version")
            if isinstance(cur_v, str) and isinstance(prev_v, str):
                if _semver_key(cur_v) > _semver_key(prev_v):
                    merged[name] = entry
            else:
                merged[name] = entry
        used_sources.append(source_name)

    cache_path = _remote_registry_cache_path(project_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    stale_fallback_used = False
    if not merged and failed_sources and fallback_to_cache and cache_path.exists():
        merged = _load_remote_registry_cache(project_dir)
        stale_fallback_used = True

    if not merged and failed_sources:
        raise RuntimeError("Registry-sync feilet: ingen vellykkede kilder og ingen brukbar cache")

    payload = {
        "version": 1,
        "synced_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": used_sources,
        "entries": merged,
        "failed_sources": failed_sources,
        "stale_fallback_used": stale_fallback_used,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "cache": str(cache_path),
        "sources": used_sources,
        "count": len(merged),
        "failed_sources": failed_sources,
        "stale_fallback_used": stale_fallback_used,
    }


def registry_mirror(output_file: str | None = None):
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    entries = _read_registry_entries(config_path)
    mirror_path = (Path(output_file).expanduser() if output_file else project_dir / "build" / "registry_mirror.json")
    if not mirror_path.is_absolute():
        mirror_path = (project_dir / mirror_path).resolve()
    mirror_path.parent.mkdir(parents=True, exist_ok=True)

    packages = {}
    for name, meta in sorted(entries.items(), key=lambda item: item[0]):
        row = {"description": meta.get("description")}
        if isinstance(meta.get("version"), str):
            row["version"] = meta["version"]
        if isinstance(meta.get("source"), str):
            row["source"] = meta["source"]

        kind = meta.get("kind")
        if kind == "path":
            p = meta.get("path")
            if isinstance(p, Path):
                row["path"] = str(p)
            elif isinstance(p, str):
                row["path"] = p
        elif kind == "git":
            row["git"] = meta.get("git")
            if isinstance(meta.get("ref"), str):
                row["ref"] = meta["ref"]
        elif kind == "url":
            row["url"] = meta.get("url")
        packages[name] = row

    payload = {
        "format_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "packages": packages,
    }
    mirror_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "output": str(mirror_path),
        "count": len(packages),
    }


def _extract_package_map(raw: object) -> dict[str, dict]:
    if not isinstance(raw, dict):
        return {}

    out: dict[str, dict] = {}
    for name, value in raw.items():
        if isinstance(value, str):
            out[name] = {"path": value, "description": None, "git": None, "url": None, "ref": None}
        elif isinstance(value, dict):
            raw_path = value.get("path")
            raw_git = value.get("git")
            raw_url = value.get("url")
            if isinstance(raw_path, str) or isinstance(raw_git, str) or isinstance(raw_url, str):
                out[name] = {
                    "path": raw_path if isinstance(raw_path, str) else None,
                    "git": raw_git if isinstance(raw_git, str) else None,
                    "url": raw_url if isinstance(raw_url, str) else None,
                    "ref": value.get("ref") if isinstance(value.get("ref"), str) else None,
                    "description": value.get("description"),
                }
    return out


def _read_registry_entries(project_config_path: Path) -> dict[str, dict]:
    project_dir = project_config_path.parent.resolve()
    entries: dict[str, dict] = {}

    # 1) Inline registry in project config: [registry.packages]
    project_toml = _load_toml(project_config_path)
    inline_registry = project_toml.get("registry", {})
    inline_packages = _extract_package_map(inline_registry.get("packages"))
    for name, meta in inline_packages.items():
        if isinstance(meta.get("path"), str):
            entries[name] = {
                "kind": "path",
                "path": _normalize_registry_path(meta["path"], project_dir),
                "description": meta.get("description"),
                "source": str(project_config_path),
            }
        elif isinstance(meta.get("git"), str):
            entries[name] = {
                "kind": "git",
                "git": meta["git"],
                "ref": meta.get("ref"),
                "description": meta.get("description"),
                "source": str(project_config_path),
            }
        elif isinstance(meta.get("url"), str):
            entries[name] = {
                "kind": "url",
                "url": meta["url"],
                "description": meta.get("description"),
                "source": str(project_config_path),
            }

    # 2) External registry file: packages/registry.toml
    registry_file = project_dir / "packages" / "registry.toml"
    if registry_file.exists():
        _verify_registry_integrity(project_config_path, registry_file)
        registry_toml = _load_toml(registry_file)
        top_packages = _extract_package_map(registry_toml.get("packages"))
        for name, meta in top_packages.items():
            if isinstance(meta.get("path"), str):
                entries[name] = {
                    "kind": "path",
                    "path": _normalize_registry_path(meta["path"], registry_file.parent),
                    "description": meta.get("description"),
                    "source": str(registry_file),
                }
            elif isinstance(meta.get("git"), str):
                entries[name] = {
                    "kind": "git",
                    "git": meta["git"],
                    "ref": meta.get("ref"),
                    "description": meta.get("description"),
                    "source": str(registry_file),
                }
            elif isinstance(meta.get("url"), str):
                entries[name] = {
                    "kind": "url",
                    "url": meta["url"],
                    "description": meta.get("description"),
                    "source": str(registry_file),
                }

        nested_registry = registry_toml.get("registry", {})
        nested_packages = _extract_package_map(nested_registry.get("packages"))
        for name, meta in nested_packages.items():
            if isinstance(meta.get("path"), str):
                entries[name] = {
                    "kind": "path",
                    "path": _normalize_registry_path(meta["path"], registry_file.parent),
                    "description": meta.get("description"),
                    "source": str(registry_file),
                }
            elif isinstance(meta.get("git"), str):
                entries[name] = {
                    "kind": "git",
                    "git": meta["git"],
                    "ref": meta.get("ref"),
                    "description": meta.get("description"),
                    "source": str(registry_file),
                }
            elif isinstance(meta.get("url"), str):
                entries[name] = {
                    "kind": "url",
                    "url": meta["url"],
                    "description": meta.get("description"),
                    "source": str(registry_file),
                }

    # 3) Synkronisert remote cache (overskriver ikke lokale entries)
    remote_entries = _load_remote_registry_cache(project_dir)
    for name, meta in remote_entries.items():
        if name in entries:
            continue
        if not isinstance(meta, dict):
            continue
        kind = meta.get("kind")
        if kind == "path" and isinstance(meta.get("path"), str):
            entries[name] = {
                "kind": "path",
                "path": _normalize_registry_path(meta["path"], project_dir),
                "description": meta.get("description"),
                "source": meta.get("source", "remote-cache"),
                "version": meta.get("version"),
            }
        elif kind == "git" and isinstance(meta.get("git"), str):
            entries[name] = {
                "kind": "git",
                "git": meta["git"],
                "ref": meta.get("ref"),
                "description": meta.get("description"),
                "source": meta.get("source", "remote-cache"),
                "version": meta.get("version"),
            }
        elif kind == "url" and isinstance(meta.get("url"), str):
            entries[name] = {
                "kind": "url",
                "url": meta["url"],
                "description": meta.get("description"),
                "source": meta.get("source", "remote-cache"),
                "version": meta.get("version"),
            }

    return entries


def _to_project_relative_path(target_dir: Path, project_dir: Path) -> str:
    relative = os.path.relpath(target_dir, project_dir).replace("\\", "/")
    if relative == ".":
        return "."
    if not relative.startswith("."):
        return f"./{relative}"
    return relative


def _upsert_dependency(config_path: Path, dep_name: str, dep_value: str) -> bool:
    lines = config_path.read_text(encoding="utf-8").splitlines()
    rendered_line = f'{dep_name} = "{dep_value}"'

    dep_start = None
    dep_end = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[dependencies]":
            dep_start = idx
            continue
        if dep_start is not None and stripped.startswith("[") and stripped.endswith("]"):
            dep_end = idx
            break

    changed = False
    if dep_start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append("[dependencies]")
        lines.append(rendered_line)
        changed = True
    else:
        existing_idx = None
        for idx in range(dep_start + 1, dep_end):
            stripped = lines[idx].strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _value = stripped.split("=", 1)
            if key.strip() == dep_name:
                existing_idx = idx
                break

        if existing_idx is not None:
            if lines[existing_idx].strip() != rendered_line:
                lines[existing_idx] = rendered_line
                changed = True
        else:
            lines.insert(dep_end, rendered_line)
            changed = True

    if changed:
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def _upsert_section_string_value(config_path: Path, section: str, key: str, value: str) -> bool:
    lines = config_path.read_text(encoding="utf-8").splitlines()
    rendered = f'{key} = "{value}"'
    section_header = f"[{section}]"

    sec_start = None
    sec_end = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == section_header:
            sec_start = idx
            continue
        if sec_start is not None and stripped.startswith("[") and stripped.endswith("]"):
            sec_end = idx
            break

    changed = False
    if sec_start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(section_header)
        lines.append(rendered)
        changed = True
    else:
        existing_idx = None
        for idx in range(sec_start + 1, sec_end):
            stripped = lines[idx].strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            cur_key, _cur_val = stripped.split("=", 1)
            if cur_key.strip() == key:
                existing_idx = idx
                break
        if existing_idx is not None:
            if lines[existing_idx].strip() != rendered:
                lines[existing_idx] = rendered
                changed = True
        else:
            lines.insert(sec_end, rendered)
            changed = True

    if changed:
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def registry_sign(write_config: bool = False):
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    registry_path = (project_dir / "packages" / "registry.toml").resolve()
    if not registry_path.exists():
        raise RuntimeError(f"Fant ikke registry-fil: {registry_path}")

    digest = _hash_file(registry_path).lower()
    changed = False
    if write_config:
        changed = _upsert_section_string_value(
            config_path,
            section="security",
            key="trusted_registry_sha256",
            value=digest,
        )

    return {
        "registry": str(registry_path),
        "sha256": digest,
        "config": str(config_path),
        "written_to_config": write_config,
        "config_changed": changed,
    }


def list_registry_packages():
    config_path = _find_project_config()
    entries = _read_registry_entries(config_path)
    return config_path, entries


def _render_git_dependency(git_url: str, ref: str | None) -> str:
    if ref:
        return f"git+{git_url}@{ref}"
    return f"git+{git_url}"


def _render_url_dependency(url: str) -> str:
    return f"url+{url}"


def _parse_dependencies_from_toml(path: Path) -> dict[str, str]:
    data = _load_toml(path)
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        return {}
    out = {}
    for name, value in deps.items():
        if isinstance(name, str) and isinstance(value, str):
            out[name] = value
    return out


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _is_valid_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", value))


def _hash_directory(path: Path) -> str:
    h = hashlib.sha256()
    files = [p for p in sorted(path.rglob("*")) if p.is_file() and ".git" not in p.parts]
    for f in files:
        rel = str(f.relative_to(path)).replace("\\", "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        with f.open("rb") as fd:
            while True:
                chunk = fd.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()


def _parse_git_dependency(value: str) -> tuple[str, str | None]:
    raw = value[len("git+") :]
    if "@" in raw:
        url, ref = raw.rsplit("@", 1)
        return url, ref
    return raw, None


def _resolve_path_dependency(project_dir: Path, value: str) -> Path:
    dep_path = Path(value).expanduser()
    if dep_path.is_absolute():
        return dep_path.resolve()
    return (project_dir / dep_path).resolve()


def generate_lockfile(check_only: bool = False):
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    deps = _parse_dependencies_from_toml(config_path)
    project_toml = _load_toml(config_path)
    project_meta = project_toml.get("project", {}) if isinstance(project_toml.get("project", {}), dict) else {}

    lock = {
        "lock_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project": {
            "name": project_meta.get("name", project_dir.name),
            "version": project_meta.get("version"),
            "entry": project_meta.get("entry"),
        },
        "dependencies": {},
    }

    for dep_name, dep_value in sorted(deps.items(), key=lambda item: item[0]):
        entry = {"specifier": dep_value}
        if dep_value.startswith("git+"):
            git_url, git_ref = _parse_git_dependency(dep_value)
            entry["kind"] = "git"
            entry["resolved"] = {
                "url": git_url,
                "ref": git_ref,
                "pinned": bool(git_ref),
            }
        elif dep_value.startswith("url+"):
            url = dep_value[len("url+") :]
            entry["kind"] = "url"
            entry["resolved"] = {
                "url": url,
                "pinned": True,
            }
        else:
            dep_path = _resolve_path_dependency(project_dir, dep_value)
            entry["kind"] = "path"
            resolved = {
                "path": str(dep_path),
                "exists": dep_path.exists(),
            }
            if dep_path.exists() and dep_path.is_dir():
                resolved["digest_sha256"] = _hash_directory(dep_path)
                dep_cfg = _find_existing_project_config_in_dir(dep_path)
                if dep_cfg is not None and dep_cfg.exists():
                    dep_toml = _load_toml(dep_cfg)
                    proj = dep_toml.get("project", {})
                    if isinstance(proj, dict):
                        resolved["project_name"] = proj.get("name")
                        resolved["project_version"] = proj.get("version")
                        resolved["entry"] = proj.get("entry")
            elif dep_path.exists() and dep_path.is_file():
                resolved["digest_sha256"] = _hash_file(dep_path)
            entry["resolved"] = resolved

        lock["dependencies"][dep_name] = entry

    lock_path = project_dir / LOCKFILE_NAME
    payload = json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if check_only:
        if not lock_path.exists():
            return lock_path, False, "mangler"
        try:
            current_obj = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            return lock_path, False, "utdatert"

        expected_obj = dict(lock)
        current_obj = dict(current_obj) if isinstance(current_obj, dict) else {}
        expected_obj.pop("generated_at", None)
        current_obj.pop("generated_at", None)
        ok = current_obj == expected_obj
        return lock_path, ok, "ok" if ok else "utdatert"

    lock_path.write_text(payload, encoding="utf-8")
    return lock_path, True, "skrevet"


def _cache_base_dir(project_dir: Path) -> Path:
    primary = (project_dir / ".norcode" / "cache").resolve()
    legacy = (project_dir / ".norsklang" / "cache").resolve()
    if primary.exists() or not legacy.exists():
        return primary
    _warn_legacy_once(
        "legacy-cache",
        "Merk: bruker legacy cache '.norsklang/cache'. Migrer til '.norcode/cache'.",
    )
    return legacy


def _safe_extract_tar(archive_path: Path, dest_dir: Path):
    with tarfile.open(archive_path) as tar:
        for member in tar.getmembers():
            member_path = (dest_dir / member.name).resolve()
            if not str(member_path).startswith(str(dest_dir.resolve())):
                raise RuntimeError(f"Utrygg tar-oppføring blokkert: {member.name}")
        tar.extractall(path=dest_dir)


def _safe_extract_zip(archive_path: Path, dest_dir: Path):
    with zipfile.ZipFile(archive_path) as zf:
        for name in zf.namelist():
            target = (dest_dir / name).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise RuntimeError(f"Utrygg zip-oppføring blokkert: {name}")
        zf.extractall(path=dest_dir)


def _find_cached_package_root(base_dir: Path) -> Path:
    direct = _find_existing_project_config_in_dir(base_dir)
    if direct is not None:
        return base_dir

    candidates = []
    for cfg_name in PROJECT_CONFIG_NAMES:
        candidates.extend(base_dir.glob(f"**/{cfg_name}"))
    candidates = sorted(candidates)
    if not candidates:
        raise RuntimeError(f"Fant ikke {_project_config_display_names()} i cache: {base_dir}")
    if len(candidates) > 1:
        # Velg nærmeste kandidat (kortest sti) for forutsigbarhet.
        candidates.sort(key=lambda p: len(p.relative_to(base_dir).parts))
    return candidates[0].parent


def _fetch_git_to_cache(project_dir: Path, package_name: str, git_url: str, git_ref: str | None, refresh: bool) -> Path:
    cache_dir = _cache_base_dir(project_dir) / "git"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = f"{git_url}@{git_ref or 'HEAD'}"
    short = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    target = cache_dir / f"{package_name}-{short}"

    if target.exists() and refresh:
        shutil.rmtree(target)

    if not target.exists():
        subprocess.run(["git", "clone", git_url, str(target)], check=True)
    if git_ref:
        subprocess.run(["git", "-C", str(target), "fetch", "--all", "--tags"], check=True)
        subprocess.run(["git", "-C", str(target), "checkout", git_ref], check=True)

    return _find_cached_package_root(target)


def _fetch_url_to_cache(
    project_dir: Path,
    package_name: str,
    source_url: str,
    refresh: bool,
    expected_sha256: str | None = None,
) -> Path:
    cache_dir = _cache_base_dir(project_dir) / "url"
    cache_dir.mkdir(parents=True, exist_ok=True)
    short = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12]
    target = cache_dir / f"{package_name}-{short}"

    if target.exists() and refresh:
        shutil.rmtree(target)

    archives_dir = target / "archives"
    extract_dir = target / "src"
    if not target.exists():
        archives_dir.mkdir(parents=True, exist_ok=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(source_url.split("?")[0]).name or "package.tar.gz"
        archive_path = archives_dir / filename
        urllib.request.urlretrieve(source_url, archive_path)
        archive_digest = _hash_file(archive_path)
        if expected_sha256 is not None and archive_digest.lower() != expected_sha256.lower():
            raise RuntimeError(
                f"SHA256 mismatch for {source_url}: expected {expected_sha256.lower()} got {archive_digest.lower()}"
            )

        lower_name = filename.lower()
        if lower_name.endswith(".zip"):
            _safe_extract_zip(archive_path, extract_dir)
        elif lower_name.endswith((".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            _safe_extract_tar(archive_path, extract_dir)
        else:
            raise RuntimeError(f"Ukjent arkivformat for URL-kilde: {filename}")

    return _find_cached_package_root(extract_dir)


def add_dependency(
    package: str,
    package_path: str | None = None,
    dep_name_override: str | None = None,
    git_url: str | None = None,
    git_ref: str | None = None,
    tarball_url: str | None = None,
    fetch: bool = False,
    refresh: bool = False,
    pin: bool = False,
    expected_sha256: str | None = None,
    allow_untrusted: bool = False,
):
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    registry_entries = _read_registry_entries(config_path)
    security_policy = _load_security_policy(config_path)

    if git_url and tarball_url:
        raise RuntimeError("Bruk enten --git eller --url, ikke begge")
    if (git_url or tarball_url) and package_path:
        raise RuntimeError("Ikke kombiner path-argument med --git/--url")
    if git_ref and not git_url:
        raise RuntimeError("--ref krever --git")
    if pin and git_url and not git_ref:
        raise RuntimeError("--pin krever --ref når --git brukes")
    if expected_sha256 is not None and not _is_valid_sha256(expected_sha256):
        raise RuntimeError("--sha256 må være 64 hex-tegn")
    if expected_sha256 is not None and not fetch:
        raise RuntimeError("--sha256 krever --fetch")

    path_like = any(sep in package for sep in ("/", "\\")) or package.startswith(".")
    dep_kind = "path"
    dep_value = ""
    package_name = package

    if git_url:
        dep_name = dep_name_override or package
        _enforce_trusted_source("git", git_url, security_policy, allow_untrusted=allow_untrusted)
        dep_kind = "git"
        dep_value = _render_git_dependency(git_url, git_ref)
        package_name = dep_name
        if fetch:
            cached_root = _fetch_git_to_cache(project_dir, dep_name, git_url, git_ref, refresh=refresh)
            dep_kind = "path"
            dep_value = _to_project_relative_path(cached_root, project_dir)
            cached_cfg = _find_existing_project_config_in_dir(cached_root) or (cached_root / PROJECT_CONFIG_NAME)
            package_name = _parse_project_name_from_toml(cached_cfg) or cached_root.name
    elif tarball_url:
        dep_name = dep_name_override or package
        _enforce_trusted_source("url", tarball_url, security_policy, allow_untrusted=allow_untrusted)
        dep_kind = "url"
        dep_value = _render_url_dependency(tarball_url)
        package_name = dep_name
        if fetch:
            cached_root = _fetch_url_to_cache(
                project_dir,
                dep_name,
                tarball_url,
                refresh=refresh,
                expected_sha256=expected_sha256,
            )
            dep_kind = "path"
            dep_value = _to_project_relative_path(cached_root, project_dir)
            cached_cfg = _find_existing_project_config_in_dir(cached_root) or (cached_root / PROJECT_CONFIG_NAME)
            package_name = _parse_project_name_from_toml(cached_cfg) or cached_root.name
    if package_path:
        dep_name = dep_name_override or package
        resolved_dir, pkg_config = _resolve_package_dir(package_path)
        dep_kind = "path"
        dep_value = _to_project_relative_path(resolved_dir, project_dir)
        package_name = _parse_project_name_from_toml(pkg_config) or resolved_dir.name
    elif not git_url and not tarball_url and path_like:
        resolved_dir, pkg_config = _resolve_package_dir(package)
        dep_name = dep_name_override or _parse_project_name_from_toml(pkg_config) or resolved_dir.name
        dep_kind = "path"
        dep_value = _to_project_relative_path(resolved_dir, project_dir)
        package_name = _parse_project_name_from_toml(pkg_config) or resolved_dir.name
    elif not git_url and not tarball_url:
        dep_name = dep_name_override or package
        registry_hit = registry_entries.get(package)
        if registry_hit is not None:
            if registry_hit.get("kind") == "path":
                resolved_dir, pkg_config = _resolve_package_dir(str(registry_hit["path"]))
                dep_kind = "path"
                dep_value = _to_project_relative_path(resolved_dir, project_dir)
                package_name = _parse_project_name_from_toml(pkg_config) or resolved_dir.name
            elif registry_hit.get("kind") == "git":
                if pin and not registry_hit.get("ref"):
                    raise RuntimeError(f"Registry-pakke '{package}' mangler låst git-ref (bruk pakke med ref eller uten --pin)")
                _enforce_trusted_source("git", registry_hit["git"], security_policy, allow_untrusted=allow_untrusted)
                dep_kind = "git"
                dep_value = _render_git_dependency(registry_hit["git"], registry_hit.get("ref"))
                package_name = dep_name
                if fetch:
                    cached_root = _fetch_git_to_cache(
                        project_dir,
                        dep_name,
                        registry_hit["git"],
                        registry_hit.get("ref"),
                        refresh=refresh,
                    )
                    dep_kind = "path"
                    dep_value = _to_project_relative_path(cached_root, project_dir)
                    cached_cfg = _find_existing_project_config_in_dir(cached_root) or (cached_root / PROJECT_CONFIG_NAME)
                    package_name = _parse_project_name_from_toml(cached_cfg) or cached_root.name
            elif registry_hit.get("kind") == "url":
                _enforce_trusted_source("url", registry_hit["url"], security_policy, allow_untrusted=allow_untrusted)
                dep_kind = "url"
                dep_value = _render_url_dependency(registry_hit["url"])
                package_name = dep_name
                if fetch:
                    cached_root = _fetch_url_to_cache(
                        project_dir,
                        dep_name,
                        registry_hit["url"],
                        refresh=refresh,
                        expected_sha256=expected_sha256,
                    )
                    dep_kind = "path"
                    dep_value = _to_project_relative_path(cached_root, project_dir)
                    cached_cfg = _find_existing_project_config_in_dir(cached_root) or (cached_root / PROJECT_CONFIG_NAME)
                    package_name = _parse_project_name_from_toml(cached_cfg) or cached_root.name
            else:
                raise RuntimeError(f"Ukjent registry-kind for {package}: {registry_hit.get('kind')}")
        else:
            default_dir = project_dir / "packages" / package
            resolved_dir, pkg_config = _resolve_package_dir(str(default_dir))
            dep_kind = "path"
            dep_value = _to_project_relative_path(resolved_dir, project_dir)
            package_name = _parse_project_name_from_toml(pkg_config) or resolved_dir.name

    if not dep_name:
        raise RuntimeError("Kunne ikke finne avhengighetsnavn (bruk --name)")

    if not dep_value:
        raise RuntimeError("Kunne ikke finne dependency-verdi")

    changed = _upsert_dependency(config_path, dep_name, dep_value)
    return config_path, dep_name, dep_value, package_name, dep_kind, changed


def verify_lockfile():
    cwd = Path.cwd().resolve()
    lock_path = (cwd / LOCKFILE_NAME).resolve()
    for candidate_name in LOCKFILE_NAMES:
        candidate = (cwd / candidate_name).resolve()
        if candidate.exists():
            lock_path = candidate
            break
    if lock_path.name == LEGACY_LOCKFILE_NAME:
        _warn_legacy_once(
            "legacy-lockfile",
            "Merk: bruker legacy lockfile 'norsklang.lock'. Bytt til 'norcode.lock'.",
        )
    if not lock_path.exists():
        return lock_path, False, [{"name": "*", "status": "mangler lockfile"}]

    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return lock_path, False, [{"name": "*", "status": f"ugyldig lockfile: {exc}"}]

    deps = lock.get("dependencies", {})
    if not isinstance(deps, dict):
        return lock_path, False, [{"name": "*", "status": "ugyldig dependencies i lockfile"}]

    results = []
    ok = True
    for name, entry in sorted(deps.items(), key=lambda item: item[0]):
        if not isinstance(entry, dict):
            results.append({"name": name, "status": "ugyldig entry"})
            ok = False
            continue

        kind = entry.get("kind")
        resolved = entry.get("resolved", {})
        if kind == "path":
            path_str = resolved.get("path") if isinstance(resolved, dict) else None
            expected_digest = resolved.get("digest_sha256") if isinstance(resolved, dict) else None
            if not isinstance(path_str, str):
                results.append({"name": name, "status": "mangler path i lock"})
                ok = False
                continue

            path = Path(path_str)
            if not path.exists():
                results.append({"name": name, "status": f"mangler path: {path}"})
                ok = False
                continue

            if isinstance(expected_digest, str):
                actual = _hash_directory(path) if path.is_dir() else _hash_file(path)
                if actual != expected_digest:
                    results.append({"name": name, "status": "digest mismatch"})
                    ok = False
                    continue
            results.append({"name": name, "status": "ok"})
        elif kind == "git":
            ref = resolved.get("ref") if isinstance(resolved, dict) else None
            pinned = bool(ref)
            results.append({"name": name, "status": "ok" if pinned else "advarsel: upinnet git-ref"})
        elif kind == "url":
            results.append({"name": name, "status": "ok"})
        else:
            results.append({"name": name, "status": f"ukjent kind: {kind}"})
            ok = False

    return lock_path, ok, results


def migrate_names(apply_changes: bool = False, cleanup_legacy: bool = False) -> dict:
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    actions: list[dict] = []

    def record_file_migration(legacy_name: str, primary_name: str) -> tuple[Path, Path, str]:
        legacy = (project_dir / legacy_name).resolve()
        primary = (project_dir / primary_name).resolve()
        if not legacy.exists():
            actions.append(
                {
                    "kind": "file",
                    "legacy": str(legacy),
                    "primary": str(primary),
                    "status": "skipped",
                    "reason": "legacy mangler",
                }
            )
            return legacy, primary, "skipped"
        if primary.exists():
            actions.append(
                {
                    "kind": "file",
                    "legacy": str(legacy),
                    "primary": str(primary),
                    "status": "skipped",
                    "reason": "primary finnes allerede",
                }
            )
            return legacy, primary, "skipped"
        if apply_changes:
            shutil.copy2(legacy, primary)
            status = "copied"
        else:
            status = "planned"
        actions.append(
            {
                "kind": "file",
                "legacy": str(legacy),
                "primary": str(primary),
                "status": status,
            }
        )
        return legacy, primary, status

    def record_dir_migration(legacy_name: str, primary_name: str) -> tuple[Path, Path, str]:
        legacy = (project_dir / legacy_name).resolve()
        primary = (project_dir / primary_name).resolve()
        if not legacy.exists():
            actions.append(
                {
                    "kind": "dir",
                    "legacy": str(legacy),
                    "primary": str(primary),
                    "status": "skipped",
                    "reason": "legacy mangler",
                }
            )
            return legacy, primary, "skipped"
        if primary.exists():
            actions.append(
                {
                    "kind": "dir",
                    "legacy": str(legacy),
                    "primary": str(primary),
                    "status": "skipped",
                    "reason": "primary finnes allerede",
                }
            )
            return legacy, primary, "skipped"
        if apply_changes:
            shutil.copytree(legacy, primary)
            status = "copied"
        else:
            status = "planned"
        actions.append(
            {
                "kind": "dir",
                "legacy": str(legacy),
                "primary": str(primary),
                "status": status,
            }
        )
        return legacy, primary, status

    migrated_resources = [
        ("file", *record_file_migration(LEGACY_PROJECT_CONFIG_NAME, PROJECT_CONFIG_NAME)),
        ("file", *record_file_migration(LEGACY_LOCKFILE_NAME, LOCKFILE_NAME)),
        ("dir", *record_dir_migration(".norsklang", ".norcode")),
    ]

    if cleanup_legacy:
        for kind, legacy, primary, status in migrated_resources:
            if not legacy.exists():
                continue
            primary_ready = primary.exists() or status == "copied"
            if not primary_ready:
                actions.append(
                    {
                        "kind": f"cleanup-{kind}",
                        "legacy": str(legacy),
                        "primary": str(primary),
                        "status": "skipped",
                        "reason": "primary mangler",
                    }
                )
                continue
            if kind == "dir":
                if not legacy.is_dir() or not primary.is_dir():
                    actions.append(
                        {
                            "kind": f"cleanup-{kind}",
                            "legacy": str(legacy),
                            "primary": str(primary),
                            "status": "skipped",
                            "reason": "type mismatch",
                        }
                    )
                    continue
                if _hash_directory(legacy) != _hash_directory(primary):
                    actions.append(
                        {
                            "kind": f"cleanup-{kind}",
                            "legacy": str(legacy),
                            "primary": str(primary),
                            "status": "skipped",
                            "reason": "primary avviker",
                        }
                    )
                    continue
            else:
                if not legacy.is_file() or not primary.is_file():
                    actions.append(
                        {
                            "kind": f"cleanup-{kind}",
                            "legacy": str(legacy),
                            "primary": str(primary),
                            "status": "skipped",
                            "reason": "type mismatch",
                        }
                    )
                    continue
                if _hash_file(legacy) != _hash_file(primary):
                    actions.append(
                        {
                            "kind": f"cleanup-{kind}",
                            "legacy": str(legacy),
                            "primary": str(primary),
                            "status": "skipped",
                            "reason": "primary avviker",
                        }
                    )
                    continue
            if apply_changes:
                if kind == "dir":
                    shutil.rmtree(legacy)
                else:
                    legacy.unlink()
                cleanup_status = "removed"
            else:
                cleanup_status = "planned-remove"
            actions.append(
                {
                    "kind": f"cleanup-{kind}",
                    "legacy": str(legacy),
                    "primary": str(primary),
                    "status": cleanup_status,
                }
            )

    copied = sum(1 for a in actions if a["status"] == "copied")
    planned = sum(1 for a in actions if a["status"] == "planned")
    skipped = sum(1 for a in actions if a["status"] == "skipped")
    removed = sum(1 for a in actions if a["status"] == "removed")
    planned_remove = sum(1 for a in actions if a["status"] == "planned-remove")
    return {
        "project_dir": str(project_dir),
        "applied": apply_changes,
        "cleanup": cleanup_legacy,
        "copied": copied,
        "planned": planned,
        "removed": removed,
        "planned_remove": planned_remove,
        "needs_migration": (planned + planned_remove) > 0,
        "skipped": skipped,
        "actions": actions,
    }


def _resolve_dependency_from_registry(
    dep_name: str,
    registry_hit: dict,
    project_dir: Path,
    fetch: bool,
    refresh: bool,
    pin: bool,
    security_policy: dict,
    allow_untrusted: bool,
) -> tuple[str, str]:
    kind = registry_hit.get("kind")
    if kind == "path":
        resolved_dir, _pkg_config = _resolve_package_dir(str(registry_hit["path"]))
        dep_value = _to_project_relative_path(resolved_dir, project_dir)
        return "path", dep_value

    if kind == "git":
        if pin and not registry_hit.get("ref"):
            raise RuntimeError(f"Registry-pakke '{dep_name}' mangler låst git-ref (bruk pakke med ref eller uten --pin)")
        _enforce_trusted_source("git", registry_hit["git"], security_policy, allow_untrusted=allow_untrusted)
        if fetch:
            cached_root = _fetch_git_to_cache(
                project_dir,
                dep_name,
                registry_hit["git"],
                registry_hit.get("ref"),
                refresh=refresh,
            )
            return "path", _to_project_relative_path(cached_root, project_dir)
        return "git", _render_git_dependency(registry_hit["git"], registry_hit.get("ref"))

    if kind == "url":
        _enforce_trusted_source("url", registry_hit["url"], security_policy, allow_untrusted=allow_untrusted)
        if fetch:
            cached_root = _fetch_url_to_cache(project_dir, dep_name, registry_hit["url"], refresh=refresh)
            return "path", _to_project_relative_path(cached_root, project_dir)
        return "url", _render_url_dependency(registry_hit["url"])

    raise RuntimeError(f"Ukjent registry-kind for {dep_name}: {kind}")


def update_dependencies(
    package: str | None = None,
    check_only: bool = False,
    pin: bool = False,
    fetch: bool = False,
    refresh: bool = False,
    with_lock: bool = False,
    allow_untrusted: bool = False,
):
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    deps = _parse_dependencies_from_toml(config_path)
    registry_entries = _read_registry_entries(config_path)
    security_policy = _load_security_policy(config_path)

    if package is not None:
        if package not in deps:
            raise RuntimeError(f"Dependency finnes ikke i {_project_config_display_names()}: {package}")
        targets = [package]
    else:
        targets = sorted(deps.keys())

    updated = 0
    unchanged = 0
    skipped = 0
    items = []

    for dep_name in targets:
        current = deps[dep_name]
        hit = registry_entries.get(dep_name)
        if hit is None:
            skipped += 1
            items.append(
                {
                    "name": dep_name,
                    "status": "skipped",
                    "reason": "ikke i registry",
                    "current": current,
                }
            )
            continue

        new_kind, desired = _resolve_dependency_from_registry(
            dep_name=dep_name,
            registry_hit=hit,
            project_dir=project_dir,
            fetch=fetch,
            refresh=refresh,
            pin=pin,
            security_policy=security_policy,
            allow_untrusted=allow_untrusted,
        )

        if current == desired:
            unchanged += 1
            items.append(
                {
                    "name": dep_name,
                    "status": "unchanged",
                    "kind": new_kind,
                    "value": desired,
                }
            )
            continue

        if not check_only:
            _upsert_dependency(config_path, dep_name, desired)
        updated += 1
        items.append(
            {
                "name": dep_name,
                "status": "updated",
                "kind": new_kind,
                "from": current,
                "to": desired,
            }
        )

    lock_info = None
    if with_lock and not check_only:
        lock_path, _ok, status = generate_lockfile(check_only=False)
        lock_info = {"path": str(lock_path), "status": status}

    return {
        "config": str(config_path),
        "check_only": check_only,
        "target": package or "*",
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "items": items,
        "lock": lock_info,
    }


def _find_pyproject(start_dir: Path | None = None) -> Path:
    base = (start_dir or Path.cwd()).resolve()
    for candidate_dir in (base, *base.parents):
        candidate = candidate_dir / PYPROJECT_NAME
        if candidate.exists():
            return candidate
    raise RuntimeError(f"Fant ikke {PYPROJECT_NAME} i denne mappen eller overliggende mapper")


def _parse_project_version_from_pyproject(path: Path) -> str:
    current_section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            continue
        if current_section == "project" and "=" in stripped:
            key, value = stripped.split("=", 1)
            if key.strip() == "version":
                parsed = _parse_toml_string(value)
                if parsed:
                    return parsed
    raise RuntimeError(f"Fant ikke [project].version i {path}")


def _set_project_version_in_pyproject(path: Path, new_version: str, dry_run: bool = False) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines()
    current_section = ""
    changed = False

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            continue
        if current_section == "project" and "=" in stripped:
            key, _value = stripped.split("=", 1)
            if key.strip() == "version":
                rendered = f'version = "{new_version}"'
                if stripped != rendered:
                    lines[idx] = rendered
                    changed = True
                break

    if changed and not dry_run:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def _next_semver(version: str, bump: str) -> str:
    if not SEMVER_RE.match(version):
        raise RuntimeError(f"Ugyldig semver i pyproject: {version}")
    major, minor, patch = (int(part) for part in version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _upsert_changelog_release(changelog_path: Path, version: str, release_date: str, dry_run: bool = False) -> bool:
    if not changelog_path.exists():
        baseline = (
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            f"## [{version}] - {release_date}\n\n"
            "### Endret\n"
            f"- Versjonsbump til `{version}`.\n"
        )
        if not dry_run:
            changelog_path.write_text(baseline, encoding="utf-8")
        return True

    lines = changelog_path.read_text(encoding="utf-8").splitlines()
    if any(line.startswith(f"## [{version}]") for line in lines):
        return False

    unreleased_idx = next((i for i, line in enumerate(lines) if line.strip().lower() == "## [unreleased]"), None)
    if unreleased_idx is not None:
        insert_at = len(lines)
        for i in range(unreleased_idx + 1, len(lines)):
            if lines[i].startswith("## "):
                insert_at = i
                break
    else:
        insert_at = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))

    new_block = [
        "",
        f"## [{version}] - {release_date}",
        "",
        "### Endret",
        f"- Versjonsbump til `{version}`.",
    ]
    updated = lines[:insert_at] + new_block + lines[insert_at:]
    if not dry_run:
        changelog_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    return True


def prepare_release(version: str | None = None, bump: str = "patch", dry_run: bool = False, release_date: str | None = None):
    pyproject_path = _find_pyproject()
    old_version = _parse_project_version_from_pyproject(pyproject_path)

    if version is not None:
        if not SEMVER_RE.match(version):
            raise RuntimeError(f"Ugyldig versjon: {version} (forventer MAJOR.MINOR.PATCH)")
        new_version = version
    else:
        new_version = _next_semver(old_version, bump)

    if new_version == old_version:
        raise RuntimeError(f"Versjon er allerede {old_version}")

    today = release_date or dt.date.today().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        raise RuntimeError(f"Ugyldig datoformat: {today} (forventer YYYY-MM-DD)")

    pyproject_changed = _set_project_version_in_pyproject(pyproject_path, new_version, dry_run=dry_run)
    changelog_path = pyproject_path.parent / CHANGELOG_NAME
    changelog_changed = _upsert_changelog_release(changelog_path, new_version, today, dry_run=dry_run)

    return {
        "pyproject": str(pyproject_path),
        "changelog": str(changelog_path),
        "old_version": old_version,
        "new_version": new_version,
        "release_date": today,
        "dry_run": dry_run,
        "changed_pyproject": pyproject_changed,
        "changed_changelog": changelog_changed,
    }


def _resolve_source_path(source_file: str) -> Path:
    path = Path(source_file).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"Fant ikke kildefil: {path}")
    return path


def load_program(source_file: str):
    source_path = _resolve_source_path(source_file)
    loader = ModuleLoader(source_path.parent)
    loaded = loader.load_entry_file(source_path.name)

    if isinstance(loaded, tuple):
        program, alias_map = loaded
    else:
        program, alias_map = loaded, {}

    return source_path, program, alias_map


def lex_source(source_text: str):
    lexer = Lexer(source_text)
    tokens = []
    while True:
        tok = lexer.next_token()
        tokens.append(tok)
        if tok.typ == "EOF":
            break
    return tokens


def parse_source(source_text: str):
    parser = Parser(Lexer(source_text))
    return parser.parse()


def _ast_to_data(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_ast_to_data(item) for item in value]
    if hasattr(value, "__dict__"):
        data = {"node": value.__class__.__name__}
        for key, item in value.__dict__.items():
            data[key] = _ast_to_data(item)
        return data
    return repr(value)


def debug_source(source_file: str, show_tokens: bool, show_ast: bool, show_symbols: bool):
    source_path = _resolve_source_path(source_file)
    source_text = source_path.read_text(encoding="utf-8")
    parsed_program = parse_source(source_text)

    payload = {
        "source": str(source_path),
        "imports": [
            {"module": imp.module_name, "alias": imp.alias}
            for imp in getattr(parsed_program, "imports", [])
        ],
        "functions": [
            {"name": fn.name, "params": len(getattr(fn, "params", []))}
            for fn in getattr(parsed_program, "functions", [])
        ],
    }

    if show_tokens:
        payload["tokens"] = [
            {"type": tok.typ, "value": tok.value, "line": tok.line, "column": tok.column}
            for tok in lex_source(source_text)
        ]

    if show_ast:
        payload["ast"] = _ast_to_data(parsed_program)

    if show_symbols:
        _src, _program, alias_map, analyzer = check_program(source_file)
        payload["aliases"] = alias_map
        symbols = []
        for name, meta in sorted(analyzer.functions.items(), key=lambda item: item[0]):
            module_name = getattr(meta, "module_name", None) or "__main__"
            symbols.append(
                {
                    "name": name,
                    "module": module_name,
                    "params": list(getattr(meta, "params", [])),
                    "return_type": getattr(meta, "return_type", None),
                    "builtin": bool(getattr(meta, "builtin", False)),
                }
            )
        payload["symbols"] = symbols

    return payload


def check_program(source_file: str):
    source_path, program, alias_map = load_program(source_file)
    analyzer = SemanticAnalyzer(alias_map=alias_map)
    analyzer.analyze(program)
    return source_path, program, alias_map, analyzer


def build_program(source_file: str):
    source_path, program, alias_map, analyzer = check_program(source_file)

    cgen = CGenerator(analyzer.functions, alias_map=alias_map)
    code = cgen.generate(program)

    c_path = source_path.with_suffix(".c")
    exe_path = source_path.with_suffix("")

    c_path.write_text(code, encoding="utf-8")
    subprocess.run(["clang", str(c_path), "-o", str(exe_path)], check=True)

    return source_path, c_path, exe_path, alias_map, analyzer


def disasm_program(source_file: str):
    source_path, program, alias_map, analyzer = check_program(source_file)
    cgen = CGenerator(analyzer.functions, alias_map=alias_map)
    code = cgen.generate(program)
    return source_path, code


def tokenize_simple(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    in_comment = False

    for ch in text:
        if in_comment:
            if ch == "\n":
                in_comment = False
            continue

        if ch == "#":
            if current:
                tokens.append("".join(current))
                current.clear()
            in_comment = True
            continue

        if ch.isalnum() or ch in "_-":
            current.append(ch)
            continue

        if current:
            tokens.append("".join(current))
            current.clear()

    if current:
        tokens.append("".join(current))

    return tokens


def parse_ir_tokens(tokens: list[str], strict: bool = False) -> list[str]:
    def is_selfhost_int_token(value: str) -> bool:
        try:
            return str(int(value)) == value
        except ValueError:
            return False

    def parse_selfhost_int(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    lines: list[str] = []
    i = 0
    pc = 0
    while i < len(tokens):
        op = tokens[i]
        if strict and op not in IR_ALL_OPS:
            raise RuntimeError(f"/* feil: ukjent opcode {op} ved token {i} */")
        if op in IR_OPS_WITH_ARG:
            if i + 1 >= len(tokens):
                raise RuntimeError(f"/* feil: op mangler verdi ved token {i} */")
            arg_token = tokens[i + 1]
            if strict:
                if not is_selfhost_int_token(arg_token):
                    raise RuntimeError(f"/* feil: ugyldig heltallsargument {arg_token} ved token {i + 1} */")
                arg_value = int(arg_token)
            else:
                arg_value = parse_selfhost_int(arg_token)
            lines.append(f"{pc}: {op} {arg_value}")
            i += 2
        else:
            lines.append(f"{pc}: {op}")
            i += 1
        pc += 1
    return lines


def _escape_no_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_selfhost_disasm(tokens: list[str], strict: bool = False) -> list[str]:
    build_dir = Path("build").resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    suffix = uuid.uuid4().hex[:8]
    source_path = build_dir / f"ir_disasm_{suffix}.no"
    c_path = source_path.with_suffix(".c")
    exe_path = source_path.with_suffix("")

    token_list = ", ".join(f'"{_escape_no_string(tok)}"' for tok in tokens)
    fn_name = "disasm_fra_tokens_strict" if strict else "disasm_fra_tokens"
    source = (
        "bruk selfhost.compiler som sh\n\n"
        "funksjon start() -> heltall {\n"
        f"    la tokens: liste_tekst = [{token_list}]\n"
        f"    skriv(sh.{fn_name}(tokens))\n"
        "    returner 0\n"
        "}\n"
    )

    try:
        source_path.write_text(source, encoding="utf-8")
        _src, _c, built_exe, _alias_map, _analyzer = build_program(str(source_path))
        result = subprocess.run(
            [str(built_exe.resolve())],
            capture_output=True,
            text=True,
            check=True,
        )
        text = result.stdout.rstrip("\n")
        return [] if not text else text.splitlines()
    finally:
        for path in (source_path, c_path, exe_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def ir_disasm_source(source_file: str, strict: bool = False, engine: str = "python"):
    source_path = _resolve_source_path(source_file)
    source = source_path.read_text(encoding="utf-8")
    tokens = tokenize_simple(source)
    if engine == "selfhost":
        disasm_lines = _run_selfhost_disasm(tokens, strict=strict)
        if strict and disasm_lines and disasm_lines[0].startswith("/* feil:"):
            raise RuntimeError(disasm_lines[0])
    else:
        disasm_lines = parse_ir_tokens(tokens, strict=strict)
    return source_path, disasm_lines


def ir_disasm_source_captured(source_file: str, strict: bool, engine: str):
    try:
        source_path, lines = ir_disasm_source(source_file, strict=strict, engine=engine)
        return source_path, True, lines, ""
    except Exception as exc:
        source_path = _resolve_source_path(source_file)
        return source_path, False, [], str(exc)


def run_program(source_file: str):
    source_path, c_path, exe_path, _alias_map, _analyzer = build_program(source_file)
    print(f"Generert C-fil: {c_path}")
    print("Kompilert med: clang")
    print(f"Kjører: {exe_path}")
    subprocess.run([str(exe_path.resolve())], check=True)
    return source_path


def discover_tests() -> list[Path]:
    tests_dir = Path("tests").resolve()
    if not tests_dir.exists():
        return []
    return sorted(p.resolve() for p in tests_dir.glob("test_*.no"))


def run_test_file(source_file: str):
    started = time.perf_counter()
    source_path, c_path, exe_path, _alias_map, _analyzer = build_program(source_file)

    result = subprocess.run(
        [str(exe_path.resolve())],
        capture_output=True,
        text=True,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)

    return {
        "source": str(source_path),
        "c_file": str(c_path),
        "exe_file": str(exe_path),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "success": result.returncode == 0,
        "duration_ms": duration_ms,
    }


def print_test_result(result, verbose: bool = False):
    status = "OK" if result["success"] else "FEIL"
    duration_ms = result.get("duration_ms")
    if isinstance(duration_ms, int):
        print(f"{status}: {result['source']} ({duration_ms} ms)")
    else:
        print(f"{status}: {result['source']}")

    if verbose or not result["success"]:
        if result["stdout"]:
            print("STDOUT:")
            print(result["stdout"], end="" if result["stdout"].endswith("\n") else "\n")
        if result["stderr"]:
            print("STDERR:")
            print(result["stderr"], end="" if result["stderr"].endswith("\n") else "\n")


def run_ir_snapshot_checks():
    started = time.perf_counter()
    fixture_path = IR_SNAPSHOT_FIXTURE.resolve()
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        cases = [(item["name"], item["source"]) for item in fixture.get("non_strict", [])]
        strict_cases = fixture.get("strict", [])
    except Exception as exc:
        return {
            "source": "IR snapshot parity (python vs selfhost)",
            "c_file": "",
            "exe_file": "",
            "returncode": 1,
            "stdout": "",
            "stderr": f"Kunne ikke lese fixture {fixture_path}: {exc}\n",
            "success": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

    mismatch_lines: list[str] = []

    for name, src in cases:
        tokens = tokenize_simple(src)
        py_lines = parse_ir_tokens(tokens, strict=False)
        sh_lines = _run_selfhost_disasm(tokens, strict=False)
        if py_lines != sh_lines:
            mismatch_lines.append(f"[{name}] non-strict mismatch")
            mismatch_lines.append("--- python")
            mismatch_lines.append("+++ selfhost")
            mismatch_lines.extend(
                difflib.unified_diff(py_lines, sh_lines, fromfile="python", tofile="selfhost", lineterm="")
            )

    for item in strict_cases:
        name = item.get("name", "strict_case")
        src = item.get("source", "")
        expected_error = item.get("expected_error")
        expected_lines = item.get("expected_lines")

        tokens = tokenize_simple(src)
        py_ok = True
        py_lines: list[str] = []
        py_err = ""
        try:
            py_lines = parse_ir_tokens(tokens, strict=True)
        except Exception as exc:
            py_ok = False
            py_err = str(exc)

        sh_ok = True
        sh_lines: list[str] = []
        sh_err = ""
        try:
            sh_lines = _run_selfhost_disasm(tokens, strict=True)
            if sh_lines and sh_lines[0].startswith("/* feil:"):
                sh_ok = False
                sh_err = sh_lines[0]
                sh_lines = []
        except Exception as exc:
            sh_ok = False
            sh_err = str(exc)

        if py_ok != sh_ok or py_lines != sh_lines or py_err != sh_err:
            mismatch_lines.append(f"[{name}] strict mismatch")
            mismatch_lines.append(f"python: {'OK ' + repr(py_lines) if py_ok else py_err}")
            mismatch_lines.append(f"selfhost: {'OK ' + repr(sh_lines) if sh_ok else sh_err}")

        if expected_error is not None:
            if py_ok:
                mismatch_lines.append(f"[{name}] strict expected error but got success")
                mismatch_lines.append(f"python: OK {repr(py_lines)}")
            elif py_err != expected_error:
                mismatch_lines.append(f"[{name}] strict expected error mismatch")
                mismatch_lines.append(f"expected: {expected_error}")
                mismatch_lines.append(f"actual:   {py_err}")

        if expected_lines is not None:
            if not py_ok:
                mismatch_lines.append(f"[{name}] strict expected lines but got error")
                mismatch_lines.append(f"python error: {py_err}")
            elif py_lines != expected_lines:
                mismatch_lines.append(f"[{name}] strict expected lines mismatch")
                mismatch_lines.extend(
                    difflib.unified_diff(expected_lines, py_lines, fromfile="expected", tofile="actual", lineterm="")
                )

    success = len(mismatch_lines) == 0
    return {
        "source": "IR snapshot parity (python vs selfhost)",
        "c_file": "",
        "exe_file": "",
        "returncode": 0 if success else 1,
        "stdout": "",
        "stderr": "" if success else "\n".join(mismatch_lines) + "\n",
        "success": success,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def update_ir_snapshots(check_only: bool = False):
    fixture_path = IR_SNAPSHOT_FIXTURE.resolve()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    strict_cases = fixture.get("strict", [])

    updated = 0
    for item in strict_cases:
        src = item.get("source", "")
        tokens = tokenize_simple(src)
        try:
            lines = parse_ir_tokens(tokens, strict=True)
            if item.get("expected_lines") != lines:
                updated += 1
            item["expected_lines"] = lines
            item.pop("expected_error", None)
        except Exception as exc:
            err = str(exc)
            if item.get("expected_error") != err:
                updated += 1
            item["expected_error"] = err
            item.pop("expected_lines", None)

    if not check_only:
        fixture_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return fixture_path, updated, len(strict_cases)


def run_all_tests(verbose: bool = False, quiet: bool = False):
    tests = discover_tests()
    if not tests:
        raise RuntimeError("Fant ingen tester i tests/")

    results = []
    for test_file in tests:
        result = run_test_file(str(test_file))
        results.append(result)
        if not quiet:
            print_test_result(result, verbose=verbose)

    snapshot_result = run_ir_snapshot_checks()
    results.append(snapshot_result)
    if not quiet:
        print_test_result(snapshot_result, verbose=verbose)

    total = len(results)
    passed = sum(1 for r in results if r["success"])
    failed = total - passed

    if not quiet:
        print()
        print(f"Tester kjørt: {total}")
        print(f"Bestått: {passed}")
        print(f"Feilet: {failed}")

    return results


def summarize_test_results(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.get("success"))
    failed = total - passed
    duration_ms = sum(r.get("duration_ms", 0) for r in results if isinstance(r.get("duration_ms"), int))
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "duration_ms": duration_ms,
        "ok": failed == 0,
    }


def check_workflow_action_versions(workflows_dir: Path | None = None) -> dict:
    base = workflows_dir or Path(".github/workflows")
    minimum_action_majors = {
        "actions/checkout": 6,
        "actions/setup-python": 6,
    }
    payload = {
        "ok": True,
        "scanned_files": 0,
        "issue_count": 0,
        "issues": [],
        "policy": {
            "minimum_action_majors": minimum_action_majors,
            "require_node24_env": True,
            "forbid_unsecure_node_opt_out": True,
        },
    }
    if not base.exists():
        return payload

    workflow_files = sorted([*base.glob("*.yml"), *base.glob("*.yaml")])
    payload["scanned_files"] = len(workflow_files)
    for workflow_path in workflow_files:
        try:
            lines = workflow_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        has_node24_env = False
        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            lower_line = line.lower().replace(" ", "")
            if "force_javascript_actions_to_node24:" in lower_line and "true" in lower_line:
                has_node24_env = True
            for match in re.finditer(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@v(\d+)", line):
                action_name = match.group(1)
                major = int(match.group(2))
                minimum_major = minimum_action_majors.get(action_name)
                if minimum_major is not None and major < minimum_major:
                    payload["issues"].append(
                        {
                            "file": str(workflow_path),
                            "line": line_no,
                            "found": f"{action_name}@v{major}",
                            "expected": f"{action_name}@v{minimum_major}",
                        }
                    )
            if (
                "actions_allow_use_unsecure_node_version" in lower_line
                and "true" in lower_line
            ):
                payload["issues"].append(
                    {
                        "file": str(workflow_path),
                        "line": line_no,
                        "found": "ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true",
                        "expected": "fjern opt-out og bruk Node 24-kompatible action-versjoner",
                    }
                )
        if not has_node24_env:
            payload["issues"].append(
                {
                    "file": str(workflow_path),
                    "line": 1,
                    "found": "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 mangler/ikke true",
                    "expected": 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"',
                }
            )

    payload["issue_count"] = len(payload["issues"])
    payload["ok"] = payload["issue_count"] == 0
    return payload


def run_ci_pipeline(json_output: bool = False, check_names: bool = False):
    total_steps = 5 if check_names else 4
    payload = {
        "steps": {"total": total_steps, "name_check_enabled": check_names},
        "snapshot_check": {"ok": False, "updated": None},
        "parity_check": {"ok": False},
        "test_check": {"ok": False, "passed": 0, "failed": 0, "total": 0},
        "workflow_action_check": {
            "ok": False,
            "scanned_files": 0,
            "issue_count": 0,
            "issues": [],
            "policy": {
                "minimum_action_majors": {
                    "actions/checkout": 6,
                    "actions/setup-python": 6,
                },
                "require_node24_env": True,
                "forbid_unsecure_node_opt_out": True,
            },
        },
        "name_migration_check": {"enabled": check_names, "ok": True, "needs_migration": False},
    }

    if not json_output:
        print(f"[1/{total_steps}] Snapshot check")
    _fixture_path, updated, _total = update_ir_snapshots(check_only=True)
    payload["snapshot_check"]["updated"] = updated
    if updated > 0:
        raise RuntimeError(f"Snapshots er utdaterte ({updated} avvik). Kjør: norcode update-snapshots")
    payload["snapshot_check"]["ok"] = True
    if not json_output:
        print("OK")

    if not json_output:
        print(f"[2/{total_steps}] Engine parity check")
    _, py_ok, py_lines, py_err = ir_disasm_source_captured("tests/ir_sample.nlir", strict=False, engine="python")
    _, sh_ok, sh_lines, sh_err = ir_disasm_source_captured("tests/ir_sample.nlir", strict=False, engine="selfhost")
    if py_ok != sh_ok:
        raise RuntimeError(f"Parity mismatch (status): python={py_ok} selfhost={sh_ok} {py_err or sh_err}")
    if py_ok and py_lines != sh_lines:
        raise RuntimeError("Parity mismatch: python/selfhost disasm avviker for tests/ir_sample.nlir")

    _, py_s_ok, py_s_lines, py_s_err = ir_disasm_source_captured("tests/ir_sample.nlir", strict=True, engine="python")
    _, sh_s_ok, sh_s_lines, sh_s_err = ir_disasm_source_captured("tests/ir_sample.nlir", strict=True, engine="selfhost")
    if py_s_ok != sh_s_ok or py_s_lines != sh_s_lines or py_s_err != sh_s_err:
        raise RuntimeError("Parity mismatch i strict-modus for tests/ir_sample.nlir")
    payload["parity_check"]["ok"] = True
    if not json_output:
        print("OK")

    if not json_output:
        print(f"[3/{total_steps}] Full test")
    results = run_all_tests(verbose=False, quiet=json_output)
    failed = sum(1 for r in results if not r["success"])
    total = len(results)
    passed = total - failed
    payload["test_check"]["ok"] = failed == 0
    payload["test_check"]["passed"] = passed
    payload["test_check"]["failed"] = failed
    payload["test_check"]["total"] = total
    if failed != 0:
        raise RuntimeError("Testfeil i CI-pipeline")
    if not json_output:
        print("OK")

    if not json_output:
        print(f"[4/{total_steps}] Workflow action version check")
    workflow_check = check_workflow_action_versions()
    payload["workflow_action_check"] = workflow_check
    if not workflow_check["ok"]:
        issue = workflow_check["issues"][0]
        raise RuntimeError(
            "Deprecated GitHub Action oppdaget: "
            f"{issue['found']} i {issue['file']}:{issue['line']} "
            f"(oppdater til {issue['expected']})"
        )
    if not json_output:
        print("OK")

    if check_names:
        if not json_output:
            print(f"[5/{total_steps}] Name migration check")
        migration = migrate_names(apply_changes=False, cleanup_legacy=True)
        payload["name_migration_check"]["needs_migration"] = migration["needs_migration"]
        payload["name_migration_check"]["ok"] = not migration["needs_migration"]
        payload["name_migration_check"]["summary"] = {
            "planned": migration["planned"],
            "planned_remove": migration["planned_remove"],
            "skipped": migration["skipped"],
        }
        if migration["needs_migration"]:
            raise RuntimeError("Navnemigrering gjenstår (kjør: norcode migrate-names --apply --cleanup)")
        if not json_output:
            print("OK")

    return payload


def main():
    parser = argparse.ArgumentParser(prog="norcode", description="NorCode CLI")
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="Bygg og kjør en .no-fil")
    run.add_argument("file")

    check = sub.add_parser("check", help="Parser og valider en .no-fil uten å bygge")
    check.add_argument("file")

    build = sub.add_parser("build", help="Generer C og bygg kjørbar fil")
    build.add_argument("file")

    add = sub.add_parser("add", help="Legg til pakkeavhengighet i norcode.toml")
    add.add_argument("package", nargs="?", help="Pakkenavn eller pakkesti")
    add.add_argument("path", nargs="?", help="Valgfri pakkesti (hvis package er navn)")
    add.add_argument("--name", help="Overstyr dependency-navn")
    add.add_argument("--list", action="store_true", help="Vis tilgjengelige pakker i registry")
    add.add_argument("--git", help="Direkte Git-kilde (f.eks. https://github.com/org/repo.git)")
    add.add_argument("--ref", help="Git ref (tag/branch/commit) brukt sammen med --git")
    add.add_argument("--url", help="Direkte URL-kilde (f.eks. tarball/zip)")
    add.add_argument("--fetch", action="store_true", help="Last ned/cach ekstern Git/URL-kilde til lokal mappe")
    add.add_argument("--refresh", action="store_true", help="Tving ny nedlasting ved --fetch")
    add.add_argument("--pin", action="store_true", help="Krev låst versjon/ref for ekstern kilde")
    add.add_argument("--sha256", help="Forventet SHA256 for URL-arkiv ved --fetch")
    add.add_argument("--allow-untrusted", action="store_true", help="Overstyr trusted host-policy for denne kommandoen")

    debug = sub.add_parser("debug", help="Vis debug-info (tokens/AST/symboler) for en .no-fil")
    debug.add_argument("file")
    debug.add_argument("--tokens", action="store_true", help="Vis lexer-tokens")
    debug.add_argument("--ast", action="store_true", help="Vis AST")
    debug.add_argument("--symbols", action="store_true", help="Vis semantiske symboler/funksjoner")
    debug.add_argument("--json", action="store_true", help="Skriv debug-output som JSON")

    disasm = sub.add_parser("disasm", help="Vis generert C-kode for en .no-fil")
    disasm.add_argument("file")

    ir_disasm = sub.add_parser("ir-disasm", help="Vis IR-disassembly fra tekstfil")
    ir_disasm.add_argument("file")
    ir_disasm.add_argument("--json", action="store_true", help="Skriv output som JSON")
    ir_disasm.add_argument("--strict", action="store_true", help="Feil ved ukjente opcodes/ugyldige argumenter")
    ir_disasm.add_argument("--engine", choices=["python", "selfhost"], default="python", help="Velg disasm-motor")
    ir_disasm.add_argument("--diff", action="store_true", help="Sammenlign python og selfhost disasm")
    ir_disasm.add_argument("--fail-on-warning", action="store_true", help="Feil hvis strict-resultat avviker mellom motorene")
    ir_disasm.add_argument("--save-diff", help="Lagre diff-output til fil ved --diff")

    update_snapshots = sub.add_parser("update-snapshots", help="Regenerer IR snapshot-forventninger")
    update_snapshots.add_argument("--check", action="store_true", help="Feil hvis snapshots er utdaterte (skriv ikke)")

    ci = sub.add_parser("ci", help="Kjør lokal CI-sekvens (snapshot, parity, test)")
    ci.add_argument("--json", action="store_true", help="Skriv CI-resultat som JSON")
    ci.add_argument("--check-names", action="store_true", help="Inkluder sjekk for navnemigrering (legacy -> NorCode)")

    lock = sub.add_parser("lock", help="Generer dependency lockfile (norcode.lock)")
    lock.add_argument("--check", action="store_true", help="Feil hvis lockfile er manglende/utdatert")
    lock.add_argument("--verify", action="store_true", help="Verifiser path-digests i eksisterende lockfile")
    lock.add_argument("--json", action="store_true", help="Skriv lock-resultat som JSON")

    update = sub.add_parser("update", help="Oppdater dependencies fra registry")
    update.add_argument("package", nargs="?", help="Valgfri dependency å oppdatere")
    update.add_argument("--check", action="store_true", help="Feil hvis en dependency ville blitt oppdatert")
    update.add_argument("--json", action="store_true", help="Skriv update-resultat som JSON")
    update.add_argument("--pin", action="store_true", help="Krev låst ref for registry git-kilder")
    update.add_argument("--fetch", action="store_true", help="Materialiser registry git/url-kilder til lokal cache")
    update.add_argument("--refresh", action="store_true", help="Tving ny nedlasting ved --fetch")
    update.add_argument("--lock", action="store_true", help="Regenerer lockfile etter oppdatering")
    update.add_argument("--allow-untrusted", action="store_true", help="Overstyr trusted host-policy for denne kommandoen")

    registry_sign_cmd = sub.add_parser("registry-sign", help="Beregn/pinn SHA256 for packages/registry.toml")
    registry_sign_cmd.add_argument("--write-config", action="store_true", help="Skriv hash til [security].trusted_registry_sha256")
    registry_sign_cmd.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    registry_sync_cmd = sub.add_parser("registry-sync", help="Synkroniser remote registry-indeks til lokal cache")
    registry_sync_cmd.add_argument("--source", help="Overstyr registry source for denne kjøringen")
    registry_sync_cmd.add_argument("--allow-untrusted", action="store_true", help="Overstyr trusted host-policy for denne kommandoen")
    registry_sync_cmd.add_argument("--require-all", action="store_true", help="Feil hvis en eneste source feiler")
    registry_sync_cmd.add_argument("--no-fallback", action="store_true", help="Ikke bruk eksisterende cache ved source-feil")
    registry_sync_cmd.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    registry_mirror_cmd = sub.add_parser("registry-mirror", help="Bygg distribuerbar registry-speilfil fra lokale+remote entries")
    registry_mirror_cmd.add_argument("--output", help="Output-fil for mirror (default: build/registry_mirror.json)")
    registry_mirror_cmd.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    migrate_names_cmd = sub.add_parser("migrate-names", help="Migrer legacy navn (norsklang*) til NorCode-navn")
    migrate_names_cmd.add_argument("--apply", action="store_true", help="Utfør migrering (default er dry-run)")
    migrate_names_cmd.add_argument("--cleanup", action="store_true", help="Fjern legacy-filer etter vellykket migrering")
    migrate_names_cmd.add_argument("--check", action="store_true", help="Feil hvis migrering/cleanup fortsatt gjenstår")
    migrate_names_cmd.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    release = sub.add_parser("release", help="Forbered release (versjonsbump + changelog)")
    release.add_argument("--bump", choices=["major", "minor", "patch"], default="patch", help="Type semver-bump")
    release.add_argument("--version", help="Sett eksakt versjon (overstyrer --bump)")
    release.add_argument("--date", help="Release-dato (YYYY-MM-DD)")
    release.add_argument("--dry-run", action="store_true", help="Vis endringer uten å skrive filer")
    release.add_argument("--json", action="store_true", help="Skriv release-resultat som JSON")

    test = sub.add_parser("test", help="Kjør én testfil eller alle i tests/")
    test.add_argument("file", nargs="?", help="Valgfri testfil")
    test.add_argument("--verbose", action="store_true", help="Vis output også for tester som består")
    test.add_argument("--json", action="store_true", help="Skriv testresultat som JSON")

    args = parser.parse_args()

    try:
        if args.cmd == "run":
            run_program(args.file)

        elif args.cmd == "check":
            source_path, _program, alias_map, analyzer = check_program(args.file)
            print(f"Kilde: {source_path}")
            print(f"Aliaser: {alias_map}")
            print("Semantikk: OK")
            print(f"Funksjoner: {list(analyzer.functions.keys())}")

        elif args.cmd == "build":
            _source_path, c_path, exe_path, _alias_map, _analyzer = build_program(args.file)
            print(f"Generert C-fil: {c_path}")
            print("Kompilert med: clang")
            print(f"Kjørbar fil: {exe_path}")

        elif args.cmd == "add":
            if args.list:
                config_path, entries = list_registry_packages()
                print(f"Prosjektkonfig: {config_path}")
                if not entries:
                    print("Registry: ingen pakker funnet")
                else:
                    print(f"Registry: {len(entries)} pakker")
                    for name, meta in sorted(entries.items(), key=lambda item: item[0]):
                        desc = meta.get("description")
                        desc_text = f" - {desc}" if isinstance(desc, str) and desc.strip() else ""
                        version_text = f" @ {meta.get('version')}" if isinstance(meta.get("version"), str) else ""
                        source_text = f" [{meta.get('source')}]" if isinstance(meta.get("source"), str) else ""
                        if meta.get("kind") == "path":
                            target = str(meta["path"])
                        elif meta.get("kind") == "git":
                            target = _render_git_dependency(meta["git"], meta.get("ref"))
                        elif meta.get("kind") == "url":
                            target = _render_url_dependency(meta["url"])
                        else:
                            target = "<ukjent>"
                        print(f"  {name}{version_text} => {target}{source_text}{desc_text}")
                return

            if not args.package:
                raise RuntimeError("Mangler pakkenavn. Bruk: add <pakke> eller add --list")

            config_path, dep_name, dep_value, package_name, dep_kind, changed = add_dependency(
                args.package,
                package_path=args.path,
                dep_name_override=args.name,
                git_url=args.git,
                git_ref=args.ref,
                tarball_url=args.url,
                fetch=args.fetch,
                refresh=args.refresh,
                pin=args.pin,
                expected_sha256=args.sha256,
                allow_untrusted=args.allow_untrusted,
            )
            print(f"Konfig: {config_path}")
            print(f"Pakke: {package_name}")
            print(f"Kilde: {dep_kind}")
            print(f"Dependency: {dep_name} = \"{dep_value}\"")
            print("Status: oppdatert" if changed else "Status: uendret")

        elif args.cmd == "debug":
            show_tokens = args.tokens
            show_ast = args.ast
            show_symbols = args.symbols
            if not (show_tokens or show_ast or show_symbols):
                show_symbols = True

            payload = debug_source(args.file, show_tokens=show_tokens, show_ast=show_ast, show_symbols=show_symbols)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Kilde: {payload['source']}")
                print(f"Imports: {len(payload.get('imports', []))}")
                for imp in payload.get("imports", []):
                    alias_text = f" som {imp['alias']}" if imp.get("alias") else ""
                    print(f"  bruk {imp['module']}{alias_text}")

                print(f"Funksjoner: {len(payload.get('functions', []))}")
                for fn in payload.get("functions", []):
                    print(f"  {fn['name']} (params: {fn['params']})")

                if "tokens" in payload:
                    print("Tokens:")
                    for tok in payload["tokens"]:
                        print(f"  {tok['line']}:{tok['column']} {tok['type']} {repr(tok['value'])}")

                if "symbols" in payload:
                    print("Symboler:")
                    for sym in payload["symbols"]:
                        print(
                            f"  {sym['name']} -> modul={sym['module']} "
                            f"params={sym['params']} return={sym['return_type']}"
                        )
                    if payload.get("aliases"):
                        print("Aliaser:")
                        for alias, module_name in payload["aliases"].items():
                            print(f"  {alias} => {module_name}")

                if "ast" in payload:
                    print("AST:")
                    print(json.dumps(payload["ast"], ensure_ascii=False, indent=2))

        elif args.cmd == "disasm":
            source_path, code = disasm_program(args.file)
            print(f"Kilde: {source_path}")
            print("Generert C:")
            print(code)

        elif args.cmd == "ir-disasm":
            if args.diff:
                source_path, py_ok, py_lines, py_err = ir_disasm_source_captured(args.file, strict=args.strict, engine="python")
                _source_path2, sh_ok, sh_lines, sh_err = ir_disasm_source_captured(args.file, strict=args.strict, engine="selfhost")

                diff_lines: list[str] = []
                diff_text = ""

                if py_ok != sh_ok:
                    if args.json:
                        payload = {
                            "source": str(source_path),
                            "strict": args.strict,
                            "match": False,
                            "python_ok": py_ok,
                            "python_error": py_err,
                            "selfhost_ok": sh_ok,
                            "selfhost_error": sh_err,
                        }
                        if args.save_diff:
                            diff_text = (
                                "MISMATCH (ulik feilstatus)\n"
                                f"python: {'OK' if py_ok else py_err}\n"
                                f"selfhost: {'OK' if sh_ok else sh_err}\n"
                            )
                            Path(args.save_diff).expanduser().write_text(diff_text, encoding="utf-8")
                            payload["saved_diff"] = str(Path(args.save_diff).expanduser().resolve())
                        print(json.dumps(payload, ensure_ascii=False, indent=2))
                    else:
                        print(f"Kilde: {source_path}")
                        print("Motor: diff (python vs selfhost)")
                        print("IR disasm: MISMATCH (ulik feilstatus)")
                        print(f"python: {'OK' if py_ok else py_err}")
                        print(f"selfhost: {'OK' if sh_ok else sh_err}")
                        if args.save_diff:
                            diff_text = (
                                "MISMATCH (ulik feilstatus)\n"
                                f"python: {'OK' if py_ok else py_err}\n"
                                f"selfhost: {'OK' if sh_ok else sh_err}\n"
                            )
                            save_path = Path(args.save_diff).expanduser()
                            save_path.write_text(diff_text, encoding="utf-8")
                            print(f"Diff lagret: {save_path.resolve()}")
                    sys.exit(1)

                if not py_ok and not sh_ok:
                    if py_err != sh_err:
                        if args.json:
                            payload = {
                                "source": str(source_path),
                                "strict": args.strict,
                                "match": False,
                                "python_error": py_err,
                                "selfhost_error": sh_err,
                            }
                            if args.save_diff:
                                diff_text = (
                                    "MISMATCH (ulik feilmelding)\n"
                                    f"python: {py_err}\n"
                                    f"selfhost: {sh_err}\n"
                                )
                                Path(args.save_diff).expanduser().write_text(diff_text, encoding="utf-8")
                                payload["saved_diff"] = str(Path(args.save_diff).expanduser().resolve())
                            print(json.dumps(payload, ensure_ascii=False, indent=2))
                        else:
                            print(f"Kilde: {source_path}")
                            print("Motor: diff (python vs selfhost)")
                            print("IR disasm: MISMATCH (ulik feilmelding)")
                            print(f"python: {py_err}")
                            print(f"selfhost: {sh_err}")
                            if args.save_diff:
                                diff_text = (
                                    "MISMATCH (ulik feilmelding)\n"
                                    f"python: {py_err}\n"
                                    f"selfhost: {sh_err}\n"
                                )
                                save_path = Path(args.save_diff).expanduser()
                                save_path.write_text(diff_text, encoding="utf-8")
                                print(f"Diff lagret: {save_path.resolve()}")
                        sys.exit(1)
                    raise RuntimeError(py_err)

                if args.json:
                    payload = {
                        "source": str(source_path),
                        "strict": args.strict,
                        "match": py_lines == sh_lines,
                        "python_lines": py_lines,
                        "selfhost_lines": sh_lines,
                    }
                    if args.fail_on_warning:
                        _src_w1, py_strict_ok, py_strict_lines, py_strict_err = ir_disasm_source_captured(args.file, strict=True, engine="python")
                        _src_w2, sh_strict_ok, sh_strict_lines, sh_strict_err = ir_disasm_source_captured(args.file, strict=True, engine="selfhost")
                        payload["strict_warning_match"] = (
                            py_strict_ok == sh_strict_ok
                            and py_strict_lines == sh_strict_lines
                            and py_strict_err == sh_strict_err
                        )
                        payload["python_strict_ok"] = py_strict_ok
                        payload["python_strict_error"] = py_strict_err
                        payload["selfhost_strict_ok"] = sh_strict_ok
                        payload["selfhost_strict_error"] = sh_strict_err
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Kilde: {source_path}")
                    print("Motor: diff (python vs selfhost)")
                    if py_lines == sh_lines:
                        print("IR disasm: MATCH")
                        for line in py_lines:
                            print(line)
                    else:
                        print("IR disasm: MISMATCH")
                        diff_lines = list(difflib.unified_diff(
                            py_lines,
                            sh_lines,
                            fromfile="python",
                            tofile="selfhost",
                            lineterm="",
                        ))
                        for line in diff_lines:
                            print(line)
                        if args.save_diff:
                            save_path = Path(args.save_diff).expanduser()
                            save_path.write_text("\n".join(diff_lines) + "\n", encoding="utf-8")
                            print(f"Diff lagret: {save_path.resolve()}")
                        sys.exit(1)

                    if args.fail_on_warning:
                        _src_w1, py_strict_ok, py_strict_lines, py_strict_err = ir_disasm_source_captured(args.file, strict=True, engine="python")
                        _src_w2, sh_strict_ok, sh_strict_lines, sh_strict_err = ir_disasm_source_captured(args.file, strict=True, engine="selfhost")
                        warning_match = (
                            py_strict_ok == sh_strict_ok
                            and py_strict_lines == sh_strict_lines
                            and py_strict_err == sh_strict_err
                        )
                        if warning_match:
                            print("Warning check: MATCH")
                        else:
                            print("Warning check: MISMATCH")
                            print(f"python strict: {'OK' if py_strict_ok else py_strict_err}")
                            print(f"selfhost strict: {'OK' if sh_strict_ok else sh_strict_err}")
                            if args.save_diff:
                                diff_text = (
                                    "Warning check mismatch\n"
                                    f"python strict: {'OK' if py_strict_ok else py_strict_err}\n"
                                    f"selfhost strict: {'OK' if sh_strict_ok else sh_strict_err}\n"
                                )
                                save_path = Path(args.save_diff).expanduser()
                                save_path.write_text(diff_text, encoding="utf-8")
                                print(f"Diff lagret: {save_path.resolve()}")
                            sys.exit(1)
            else:
                source_path, lines = ir_disasm_source(args.file, strict=args.strict, engine=args.engine)
                if args.json:
                    payload = {
                        "source": str(source_path),
                        "engine": args.engine,
                        "lines": lines,
                    }
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Kilde: {source_path}")
                    print(f"Motor: {args.engine}")
                    print("IR disasm:")
                    for line in lines:
                        print(line)

        elif args.cmd == "update-snapshots":
            fixture_path, updated, total = update_ir_snapshots(check_only=args.check)
            print(f"Oppdatert snapshot-fixture: {fixture_path}")
            print(f"Strict-cases: {total}")
            if args.check:
                print(f"Avvik funnet: {updated}")
                if updated > 0:
                    sys.exit(1)
            else:
                print(f"Endringer skrevet: {updated}")

        elif args.cmd == "ci":
            payload = run_ci_pipeline(json_output=args.json, check_names=args.check_names)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))

        elif args.cmd == "lock":
            if args.verify:
                lock_path, ok, results = verify_lockfile()
                if args.json:
                    print(json.dumps({"lockfile": str(lock_path), "ok": ok, "verify": True, "results": results}, ensure_ascii=False, indent=2))
                else:
                    print(f"Lockfile: {lock_path}")
                    print("Verify:")
                    for row in results:
                        print(f"  {row['name']}: {row['status']}")
                if not ok:
                    sys.exit(1)
            else:
                lock_path, ok, status = generate_lockfile(check_only=args.check)
                if args.json:
                    print(json.dumps({"lockfile": str(lock_path), "ok": ok, "status": status, "check": args.check}, ensure_ascii=False, indent=2))
                else:
                    print(f"Lockfile: {lock_path}")
                    print(f"Status: {status}")
                if args.check and not ok:
                    sys.exit(1)

        elif args.cmd == "update":
            payload = update_dependencies(
                package=args.package,
                check_only=args.check,
                pin=args.pin,
                fetch=args.fetch,
                refresh=args.refresh,
                with_lock=args.lock,
                allow_untrusted=args.allow_untrusted,
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Konfig: {payload['config']}")
                print(f"Target: {payload['target']}")
                print(f"Updated: {payload['updated']}")
                print(f"Unchanged: {payload['unchanged']}")
                print(f"Skipped: {payload['skipped']}")
                for item in payload["items"]:
                    name = item["name"]
                    status = item["status"]
                    if status == "updated":
                        print(f"  {name}: oppdatert -> {item['to']}")
                    elif status == "unchanged":
                        print(f"  {name}: uendret")
                    else:
                        print(f"  {name}: hoppet over ({item.get('reason', 'ukjent')})")
                if payload.get("lock"):
                    print(f"Lockfile: {payload['lock']['path']} ({payload['lock']['status']})")
            if args.check and payload["updated"] > 0:
                sys.exit(1)

        elif args.cmd == "registry-sign":
            payload = registry_sign(write_config=args.write_config)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Registry: {payload['registry']}")
                print(f"SHA256: {payload['sha256']}")
                if payload["written_to_config"]:
                    print(f"Konfig: {payload['config']}")
                    print("Status: oppdatert" if payload["config_changed"] else "Status: uendret")

        elif args.cmd == "registry-sync":
            payload = registry_sync(
                source_override=args.source,
                allow_untrusted=args.allow_untrusted,
                require_all=args.require_all,
                fallback_to_cache=not args.no_fallback,
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Cache: {payload['cache']}")
                print(f"Kilder: {len(payload['sources'])}")
                for src in payload["sources"]:
                    print(f"  - {src}")
                print(f"Pakker i cache: {payload['count']}")
                if payload.get("failed_sources"):
                    print("Feilede kilder:")
                    for row in payload["failed_sources"]:
                        print(f"  - {row['source']}: {row['error']}")
                if payload.get("stale_fallback_used"):
                    print("Fallback: bruker eksisterende cache")

        elif args.cmd == "registry-mirror":
            payload = registry_mirror(output_file=args.output)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Mirror: {payload['output']}")
                print(f"Pakker: {payload['count']}")

        elif args.cmd == "migrate-names":
            payload = migrate_names(apply_changes=args.apply, cleanup_legacy=args.cleanup)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                mode = "apply+cleanup" if args.apply and args.cleanup else ("apply" if args.apply else ("dry-run+cleanup" if args.cleanup else "dry-run"))
                print(f"Prosjekt: {payload['project_dir']}")
                print(f"Modus: {mode}")
                for action in payload["actions"]:
                    reason = action.get("reason")
                    if reason:
                        print(
                            f"  {action['kind']}: {action['legacy']} -> {action['primary']} "
                            f"[{action['status']}: {reason}]"
                        )
                    else:
                        print(
                            f"  {action['kind']}: {action['legacy']} -> {action['primary']} "
                            f"[{action['status']}]"
                        )
                print(
                    "Oppsummert: "
                    f"copied={payload['copied']} planned={payload['planned']} "
                    f"removed={payload['removed']} planned_remove={payload['planned_remove']} "
                    f"skipped={payload['skipped']}"
                )
            if args.check and payload["needs_migration"]:
                sys.exit(1)

        elif args.cmd == "release":
            payload = prepare_release(
                version=args.version,
                bump=args.bump,
                dry_run=args.dry_run,
                release_date=args.date,
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                mode = "DRY-RUN" if payload["dry_run"] else "SKREVET"
                print(f"Release: {mode}")
                print(f"Versjon: {payload['old_version']} -> {payload['new_version']}")
                print(f"Dato: {payload['release_date']}")
                print(f"Pyproject: {'oppdatert' if payload['changed_pyproject'] else 'uendret'} ({payload['pyproject']})")
                print(f"Changelog: {'oppdatert' if payload['changed_changelog'] else 'uendret'} ({payload['changelog']})")

        elif args.cmd == "test":
            if args.file:
                result = run_test_file(args.file)
                if args.json:
                    payload = {
                        "mode": "single",
                        "results": [result],
                        "summary": summarize_test_results([result]),
                    }
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print_test_result(result, verbose=args.verbose)
                if not result["success"]:
                    sys.exit(1)
            else:
                results = run_all_tests(verbose=args.verbose, quiet=args.json)
                if args.json:
                    payload = {
                        "mode": "all",
                        "results": results,
                        "summary": summarize_test_results(results),
                    }
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                if any(not r["success"] for r in results):
                    sys.exit(1)

        else:
            parser.print_help()
            sys.exit(1)

    except Exception as e:
        print(f"Feil: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
