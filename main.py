import argparse
import datetime as dt
import difflib
import hashlib
import json
import locale
import os
import re
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
import platform
try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib  # type: ignore
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

from compiler.cgen import CGenerator
from compiler.bytecode_backend import build_command as build_bytecode_command
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
SELFHOST_PARSER_M1_FIXTURE = Path("tests/selfhost_parser_m1_cases.json")
SELFHOST_PARSER_M2_FIXTURE = Path("tests/selfhost_parser_m2_cases.json")
SELFHOST_PARSER_EXTENDED_FIXTURE = Path("tests/selfhost_parser_core_cases.json")
WORKFLOW_ACTION_POLICY = {
    "minimum_action_majors": {
        "actions/checkout": 6,
        "actions/setup-python": 6,
    },
    "require_node24_env": True,
    "forbid_unsecure_node_opt_out": True,
    "required_norscode_ci_flags": [
        "--check-names",
        "--require-selfhost-ready",
    ],
}
PROJECT_CONFIG_NAME = "norscode.toml"
LEGACY_PROJECT_CONFIG_NAME = "norsklang.toml"
PROJECT_CONFIG_NAMES = (PROJECT_CONFIG_NAME, LEGACY_PROJECT_CONFIG_NAME)
PYPROJECT_NAME = "pyproject.toml"
CHANGELOG_NAME = "CHANGELOG.md"
LOCKFILE_NAME = "norscode.lock"
LEGACY_LOCKFILE_NAME = "norsklang.lock"
LOCKFILE_NAMES = (LOCKFILE_NAME, LEGACY_LOCKFILE_NAME)
REMOTE_REGISTRY_CACHE = ".norscode/registry/remote_index.json"
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
                    "Merk: bruker legacy konfig 'norsklang.toml'. Bytt til 'norscode.toml'.",
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
        raise RuntimeError("Ugyldig felt [security].trusted_registry_sha256 i norscode.toml")

    if not registry_file.exists():
        raise RuntimeError(f"Registerfil mangler, men trusted_registry_sha256 er satt: {registry_file}")

    actual = _hash_file(registry_file).lower()
    if actual != expected:
        raise RuntimeError(
            f"Registerintegritet feilet: forventet {expected}, faktisk {actual} ({registry_file})"
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
            raise RuntimeError(f"Git-kilde kan ikke verifiseres mot tillatte verter: {source}")
        if not _host_matches(host, allowlist):
            raise RuntimeError(f"Git-vert ikke tillatt av sikkerhetspolicy: {host}")
        return

    if kind == "url":
        allowlist = security_policy.get("trusted_url_hosts", set())
        if not allowlist:
            return
        host = _extract_url_host(source)
        if host is None:
            raise RuntimeError(f"URL-kilde kan ikke verifiseres mot tillatte verter: {source}")
        if host == "file":
            return
        if not _host_matches(host, allowlist):
            raise RuntimeError(f"URL-vert ikke tillatt av sikkerhetspolicy: {host}")
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
        raise RuntimeError(f"Ukjent registerkildeskjema: {scheme}")

    source_path = Path(source).expanduser()
    if not source_path.is_absolute():
        source_path = (project_dir / source_path).resolve()
    if not source_path.exists():
        raise RuntimeError(f"Fant ikke registerkildefil: {source_path}")
    return str(source_path), source_path.read_text(encoding="utf-8")


def _parse_remote_registry_text(source_name: str, text: str) -> dict[str, dict]:
    data = None
    try:
        data = json.loads(text)
    except Exception:
        try:
            data = tomllib.loads(text)
        except Exception as exc:
            raise RuntimeError(f"Ugyldig registerformat i {source_name}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Ugyldig registerrot i {source_name}: forventet objekt/tabell")

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
                        "legacy-register-lager",
        "Merk: bruker legacy-lager '.norsklang/'. Migrer til '.norscode/'.",
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

    sources = _resolve_registry_sync_sources(source_override, configured_sources)

    if not sources:
        raise RuntimeError("Ingen registerkilder satt. Bruk [registry].sources eller --source")

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
                raise RuntimeError(f"Registersynk feilet for {src}: {exc}") from exc
            continue

        _merge_registry_entries(merged, entries)
        used_sources.append(source_name)

    cache_path = _remote_registry_cache_path(project_dir)
    stale_fallback_used, merged = _apply_registry_sync_fallback(
        project_dir=project_dir,
        merged=merged,
        failed_sources=failed_sources,
        fallback_to_cache=fallback_to_cache,
        cache_path=cache_path,
    )

    if not merged and failed_sources:
        raise RuntimeError("Registersynk feilet: ingen vellykkede kilder og ingen brukbart lager")

    payload = {
        "version": 1,
        "synced_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": used_sources,
        "entries": merged,
        "failed_sources": failed_sources,
        "stale_fallback_used": stale_fallback_used,
    }
    _write_registry_sync_cache(cache_path, payload)
    return {
        "cache": str(cache_path),
        "sources": used_sources,
        "count": len(merged),
        "failed_sources": failed_sources,
        "stale_fallback_used": stale_fallback_used,
    }


def _resolve_registry_sync_sources(source_override: str | None, configured_sources: object) -> list[str]:
    if source_override:
        return [source_override]
    if isinstance(configured_sources, list):
        return [s for s in configured_sources if isinstance(s, str) and s.strip()]
    return []


def _merge_registry_entries(merged: dict[str, dict], entries: dict[str, dict]):
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


def _apply_registry_sync_fallback(
    project_dir: Path,
    merged: dict[str, dict],
    failed_sources: list[dict],
    fallback_to_cache: bool,
    cache_path: Path,
) -> tuple[bool, dict[str, dict]]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    stale_fallback_used = False
    if not merged and failed_sources and fallback_to_cache and cache_path.exists():
        merged = _load_remote_registry_cache(project_dir)
        stale_fallback_used = True
    return stale_fallback_used, merged


def _write_registry_sync_cache(cache_path: Path, payload: dict):
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def registry_mirror(output_file: str | None = None):
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    entries = _read_registry_entries(config_path)
    mirror_path = (Path(output_file).expanduser() if output_file else project_dir / "build" / "registerspeiling.json")
    if not mirror_path.is_absolute():
        mirror_path = (project_dir / mirror_path).resolve()
    mirror_path.parent.mkdir(parents=True, exist_ok=True)

    packages = {}
    for name, meta in sorted(entries.items(), key=lambda item: item[0]):
        packages[name] = _build_registry_mirror_package_row(meta)

    payload = {
        "format_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "packages": packages,
    }
    _write_registry_mirror_payload(mirror_path, payload)
    return {
        "output": str(mirror_path),
        "count": len(packages),
    }


def _build_registry_mirror_package_row(meta: dict) -> dict:
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
    return row


def _write_registry_mirror_payload(mirror_path: Path, payload: dict):
    mirror_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_ci_step_order(
    parity_suite: str,
    run_m2_sync_check: bool,
    require_selfhost_ready: bool,
    check_names: bool,
) -> list[str]:
    step_order = ["snapshot_check", "parser_fixture_check", "parity_check"]
    if parity_suite == "m1":
        step_order.append("parser_core_m1_check")
    elif parity_suite == "m2":
        step_order.append("parser_core_m2_check")
    else:
        step_order.append("parser_core_m1_check")
        step_order.append("parser_core_m2_check")
        step_order.append("parser_core_extended_check")
    step_order.append("parser_suite_consistency_check")
    if run_m2_sync_check:
        step_order.append("selfhost_m2_sync_check")
    if require_selfhost_ready:
        step_order.append("selfhost_progress_check")
    step_order.extend(["test_check", "workflow_action_check"])
    if check_names:
        step_order.append("name_migration_check")
    return step_order


def _build_ci_payload_base(
    started_at_utc: str,
    started_at_epoch_ms: int,
    source_revision: str | None,
    source_branch: str | None,
    source_tag: str | None,
    source_remote: str | None,
    source_remote_protocol: str | None,
    source_remote_host: str | None,
    source_remote_provider: str,
    source_repo_slug: str | None,
    source_repo_owner: str | None,
    source_repo_name: str | None,
    source_dirty: bool | None,
    py_major_minor: str,
    json_output: bool,
    check_names: bool,
    parity_suite: str,
    require_selfhost_ready: bool,
    run_m2_sync_check: bool,
    total_steps: int,
    step_order: list[str],
) -> dict:
    return {
        "schema_version": 1,
        "run_id": uuid.uuid4().hex,
        "ok": False,
        "source_revision": source_revision,
        "source_revision_short": to_short_git_revision(source_revision),
        "source_branch": source_branch,
        "source_tag": source_tag,
        "source_ref": source_tag or source_branch,
        "source_ref_type": "tag" if source_tag else ("branch" if source_branch else "unknown"),
        "source_remote": source_remote,
        "source_remote_protocol": source_remote_protocol,
        "source_remote_is_https": source_remote_protocol == "https",
        "source_remote_is_ssh": source_remote_protocol == "ssh",
        "source_remote_host": source_remote_host,
        "source_remote_is_github": is_github_host(source_remote_host),
        "source_remote_is_gitlab": is_gitlab_host(source_remote_host),
        "source_remote_is_bitbucket": is_bitbucket_host(source_remote_host),
        "source_remote_provider": source_remote_provider,
        "source_remote_is_unknown": source_remote_provider == "unknown",
        "source_repo_slug": source_repo_slug,
        "source_repo_owner": source_repo_owner,
        "source_repo_name": source_repo_name,
        "source_repo_url": get_source_repo_url(source_remote_host, source_repo_slug),
        "source_branch_url": get_source_ref_url(source_remote_host, source_repo_slug, source_branch),
        "source_tag_url": get_source_ref_url(source_remote_host, source_repo_slug, source_tag),
        "source_ref_url": get_source_ref_url(source_remote_host, source_repo_slug, source_tag or source_branch),
        "source_revision_url": get_source_revision_url(source_remote_host, source_repo_slug, source_revision),
        "source_is_tagged": source_tag is not None,
        "source_is_main": source_branch == "main",
        "source_dirty": source_dirty,
        "source_clean": (not source_dirty) if source_dirty is not None else None,
        "invocation": {
            "cmd": "norscode ci",
            "argv0": sys.argv[0] if sys.argv else None,
            "raw": " ".join(shlex.quote(arg) for arg in sys.argv),
            "json_output": json_output,
            "check_names": check_names,
            "parity_suite": parity_suite,
            "require_selfhost_ready": require_selfhost_ready,
            "argv": sys.argv[1:],
        },
        "runtime": {
            "python_version": platform.python_version(),
            "python_major_minor": py_major_minor,
            "python_api_version": sys.api_version,
            "python_hexversion": sys.hexversion,
            "python_implementation": platform.python_implementation(),
            "python_compiler": platform.python_compiler(),
            "python_build": " ".join(platform.python_build()),
            "python_cache_tag": sys.implementation.cache_tag,
            "python_executable": sys.executable,
            "python_prefix": sys.prefix,
            "python_base_prefix": sys.base_prefix,
            "python_is_venv": sys.prefix != sys.base_prefix,
            "byteorder": sys.byteorder,
            "locale": locale.setlocale(locale.LC_CTYPE, None),
            "encoding": locale.getpreferredencoding(False),
            "path_entries": len(os.getenv("PATH", "").split(os.pathsep)) if os.getenv("PATH") else 0,
            "path_separator": os.pathsep,
            "env_var_count": len(os.environ),
            "stdin_isatty": sys.stdin.isatty(),
            "stdout_isatty": sys.stdout.isatty(),
            "stderr_isatty": sys.stderr.isatty(),
            "shell": os.getenv("SHELL"),
            "term": os.getenv("TERM"),
            "virtual_env": os.getenv("VIRTUAL_ENV"),
            "virtual_env_name": Path(os.getenv("VIRTUAL_ENV")).name if os.getenv("VIRTUAL_ENV") else None,
            "is_ci": bool(os.getenv("CI")),
            "is_github_actions": bool(os.getenv("GITHUB_ACTIONS")),
            "github_actions_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_actions_run_number": os.getenv("GITHUB_RUN_NUMBER"),
            "github_actions_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
            "github_actions_workflow": os.getenv("GITHUB_WORKFLOW"),
            "github_actions_job": os.getenv("GITHUB_JOB"),
            "github_actions_ref": os.getenv("GITHUB_REF"),
            "github_actions_sha": os.getenv("GITHUB_SHA"),
            "github_actions_actor": os.getenv("GITHUB_ACTOR"),
            "github_actions_event_name": os.getenv("GITHUB_EVENT_NAME"),
            "os": platform.system(),
            "arch": platform.machine(),
            "platform": platform.platform(),
            "hostname": platform.node(),
            "user": os.getenv("USER") or os.getenv("USERNAME"),
            "uid": os.getuid() if hasattr(os, "getuid") else None,
            "gid": os.getgid() if hasattr(os, "getgid") else None,
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "process_group_id": os.getpgrp() if hasattr(os, "getpgrp") else None,
            "home": os.path.expanduser("~"),
            "tmpdir": tempfile.gettempdir(),
            "cwd": str(Path.cwd()),
            "cwd_has_spaces": " " in str(Path.cwd()),
            "timezone": dt.datetime.now().astimezone().tzname(),
        },
        "steps": {
            "total": total_steps,
            "name_check_enabled": check_names,
            "parity_suite": parity_suite,
            "require_selfhost_ready": require_selfhost_ready,
            "order": step_order,
        },
        "started_at_utc": started_at_utc,
        "started_at_epoch_ms": started_at_epoch_ms,
        "finished_at_utc": None,
        "finished_at_epoch_ms": None,
        "timings_ms": {},
        "timings_s": {},
        "timings_ratio": {},
        "snapshot_check": {"ok": False, "updated": None},
        "parser_fixture_check": {"ok": False, "updated": None, "cases": 0, "suite": parity_suite},
        "parity_check": {"ok": False},
        "parser_core_m1_check": {"ok": False, "case_count": 0, "error_cases": 0},
        "parser_core_m2_check": {"ok": False, "case_count": 0, "error_cases": 0},
        "parser_core_extended_check": {"ok": False, "case_count": 0, "error_cases": 0},
        "parser_suite_consistency_check": {"ok": False, "checked_cases": 0, "mismatch_count": 0},
        "selfhost_m2_sync_check": {"enabled": run_m2_sync_check, "ok": True, "updated": 0, "missing_m1_from_core_count": 0},
        "selfhost_progress_check": {"enabled": require_selfhost_ready, "ok": True, "ready": None, "coverage_total_pct": None},
        "test_check": {"ok": False, "passed": 0, "failed": 0, "total": 0},
        "workflow_action_check": {
            "ok": False,
            "scanned_dir": ".github/workflows",
            "scanned_files": 0,
            "files": [],
            "file_extensions": [".yml", ".yaml"],
            "issue_count": 0,
            "issue_types": {},
            "issues": [],
            "policy": WORKFLOW_ACTION_POLICY,
        },
        "name_migration_check": {"enabled": check_names, "ok": True, "needs_migration": False},
    }


def _run_ci_snapshot_check(payload: dict, total_steps: int, json_output: bool):
    if not json_output:
        print(f"[1/{total_steps}] Snapshot check")
    started = time.perf_counter()
    _fixture_path, updated, _total = update_ir_snapshots(check_only=True)
    payload["timings_ms"]["snapshot_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["snapshot_check"] = round(payload["timings_ms"]["snapshot_check"] / 1000.0, 3)
    payload["snapshot_check"]["updated"] = updated
    if updated > 0:
        raise RuntimeError(f"Snapshots er utdaterte ({updated} avvik). Kjør: norscode update-snapshots")
    payload["snapshot_check"]["ok"] = True
    if not json_output:
        print("OK")


def _run_ci_parser_fixture_check(payload: dict, total_steps: int, json_output: bool, parity_suite: str):
    if not json_output:
        print(f"[2/{total_steps}] Selfhost parity fixture check")
    started = time.perf_counter()
    fixture_suite = parity_suite if parity_suite in {"m1", "m2"} else "all"
    fixture_check = update_selfhost_parser_fixtures(check_only=True, suite=fixture_suite)
    payload["timings_ms"]["parser_fixture_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["parser_fixture_check"] = round(payload["timings_ms"]["parser_fixture_check"] / 1000.0, 3)
    payload["parser_fixture_check"]["ok"] = fixture_check["updated"] == 0
    payload["parser_fixture_check"]["updated"] = int(fixture_check["updated"])
    payload["parser_fixture_check"]["cases"] = int(fixture_check["cases"])
    payload["parser_fixture_check"]["suite"] = str(fixture_check["suite"])
    if fixture_check["updated"] > 0:
        raise RuntimeError(
            f"Selfhost parity-fixtures er utdaterte ({fixture_check['updated']} avvik). "
            f"Kjør: norscode update-selfhost-parity-fixtures --suite {fixture_suite}"
        )
    if not json_output:
        print(
            f"OK ({payload['parser_fixture_check']['cases']} cases, "
            f"suite={payload['parser_fixture_check']['suite']})"
        )


def _run_ci_parity_check(payload: dict, total_steps: int, json_output: bool):
    if not json_output:
        print(f"[3/{total_steps}] Engine parity check")
    started = time.perf_counter()
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
    payload["timings_ms"]["parity_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["parity_check"] = round(payload["timings_ms"]["parity_check"] / 1000.0, 3)
    payload["parity_check"]["ok"] = True
    if not json_output:
        print("OK")


def _run_ci_parser_suite_consistency_check(
    payload: dict,
    total_steps: int,
    json_output: bool,
    parity_suite: str,
) -> int:
    consistency_step = 7 if parity_suite == "all" else 5
    if not json_output:
        print(f"[{consistency_step}/{total_steps}] Parser suite consistency")
    started = time.perf_counter()
    if parity_suite == "m1":
        consistency = run_selfhost_parser_suite_consistency_check(
            SELFHOST_PARSER_M1_FIXTURE,
            SELFHOST_PARSER_EXTENDED_FIXTURE,
        )
    elif parity_suite == "m2":
        consistency = run_selfhost_parser_suite_subset_consistency_check(
            SELFHOST_PARSER_M2_FIXTURE,
            SELFHOST_PARSER_EXTENDED_FIXTURE,
            "m2",
        )
    else:
        consistency = run_selfhost_parser_suite_all_consistency_check(
            SELFHOST_PARSER_M1_FIXTURE,
            SELFHOST_PARSER_M2_FIXTURE,
            SELFHOST_PARSER_EXTENDED_FIXTURE,
        )
    payload["timings_ms"]["parser_suite_consistency_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["parser_suite_consistency_check"] = round(
        payload["timings_ms"]["parser_suite_consistency_check"] / 1000.0, 3
    )
    payload["parser_suite_consistency_check"]["ok"] = bool(consistency.get("success"))
    payload["parser_suite_consistency_check"]["checked_cases"] = int(consistency.get("checked_cases", 0) or 0)
    payload["parser_suite_consistency_check"]["mismatch_count"] = int(consistency.get("mismatch_count", 0) or 0)
    if not consistency.get("success"):
        raise RuntimeError(
            "Parser suite consistency-feil:\n"
            + (consistency.get("stderr", "").rstrip() or "ukjent feil")
        )
    if not json_output:
        print(f"OK ({payload['parser_suite_consistency_check']['checked_cases']} cases)")
    return consistency_step


def _run_ci_selfhost_m2_sync_check(
    payload: dict,
    total_steps: int,
    json_output: bool,
    consistency_step: int,
) -> int:
    sync_step = consistency_step + 1
    if not json_output:
        print(f"[{sync_step}/{total_steps}] Selfhost M2 sync check")
    started = time.perf_counter()
    m2_sync = sync_selfhost_parser_m2_fixture(check_only=True)
    payload["timings_ms"]["selfhost_m2_sync_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["selfhost_m2_sync_check"] = round(
        payload["timings_ms"]["selfhost_m2_sync_check"] / 1000.0, 3
    )
    payload["selfhost_m2_sync_check"]["enabled"] = True
    payload["selfhost_m2_sync_check"]["updated"] = int(m2_sync.get("updated", 0) or 0)
    payload["selfhost_m2_sync_check"]["missing_m1_from_core_count"] = int(
        m2_sync.get("missing_m1_from_core_count", 0) or 0
    )
    payload["selfhost_m2_sync_check"]["ok"] = (
        payload["selfhost_m2_sync_check"]["updated"] == 0
        and payload["selfhost_m2_sync_check"]["missing_m1_from_core_count"] == 0
    )
    payload["selfhost_m2_sync_check"]["result"] = m2_sync
    if not payload["selfhost_m2_sync_check"]["ok"]:
        raise RuntimeError(
            "Selfhost M2 sync-feil: M2-fixture er ute av synk med core minus M1. "
            "Kjør: norscode sync-selfhost-parity-m2"
        )
    if not json_output:
        print("OK")
    return 1


def _run_ci_selfhost_progress_check(
    payload: dict,
    total_steps: int,
    json_output: bool,
    progress_step: int,
):
    if not json_output:
        print(f"[{progress_step}/{total_steps}] Selfhost parity progress check")
    started = time.perf_counter()
    progress = run_selfhost_parity_progress()
    payload["timings_ms"]["selfhost_progress_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["selfhost_progress_check"] = round(
        payload["timings_ms"]["selfhost_progress_check"] / 1000.0, 3
    )
    payload["selfhost_progress_check"]["enabled"] = True
    payload["selfhost_progress_check"]["ok"] = bool(progress.get("ok"))
    payload["selfhost_progress_check"]["ready"] = bool(progress.get("ready"))
    payload["selfhost_progress_check"]["coverage_total_pct"] = (
        progress.get("coverage", {}).get("total_pct") if isinstance(progress.get("coverage"), dict) else None
    )
    payload["selfhost_progress_check"]["result"] = progress
    if not progress.get("ok"):
        raise RuntimeError(
            "Selfhost parity progress-feil:\n"
            + (str(progress.get("stderr", "")).rstrip() or "ukjent feil")
        )
    if not progress.get("ready"):
        coverage_pct = (
            progress.get("coverage", {}).get("total_pct")
            if isinstance(progress.get("coverage"), dict)
            else None
        )
        raise RuntimeError(
            "Selfhost parity progress er ikke klar for full coverage"
            + (f" (dekning={coverage_pct}%)" if coverage_pct is not None else "")
        )
    if not json_output:
        print(
            "OK "
            f"(ready=ja, total_dekning={payload['selfhost_progress_check']['coverage_total_pct']}%)"
        )


def _run_ci_test_check(
    payload: dict,
    total_steps: int,
    json_output: bool,
    test_step: int,
):
    if not json_output:
        print(f"[{test_step}/{total_steps}] Full test")
    started = time.perf_counter()
    results = run_all_tests(verbose=False, quiet=json_output)
    payload["timings_ms"]["test_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["test_check"] = round(payload["timings_ms"]["test_check"] / 1000.0, 3)
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


def _run_ci_workflow_action_check(
    payload: dict,
    total_steps: int,
    json_output: bool,
    workflow_step: int,
):
    if not json_output:
        print(f"[{workflow_step}/{total_steps}] Workflow action version check")
    started = time.perf_counter()
    workflow_check = check_workflow_action_versions()
    payload["timings_ms"]["workflow_action_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["workflow_action_check"] = round(payload["timings_ms"]["workflow_action_check"] / 1000.0, 3)
    payload["workflow_action_check"] = workflow_check
    if not workflow_check["ok"]:
        issue = workflow_check["issues"][0]
        issue_type = issue.get("type", "unknown")
        raise RuntimeError(
            f"Workflow policy-brudd ({issue_type}) oppdaget: "
            f"{issue['found']} i {issue['file']}:{issue['line']} "
            f"(forventet: {issue['expected']})"
        )
    if not json_output:
        print(f"OK ({workflow_check['scanned_files']} filer)")


def _run_ci_name_migration_check(
    payload: dict,
    total_steps: int,
    json_output: bool,
    name_step: int,
):
    if not json_output:
        print(f"[{name_step}/{total_steps}] Name migration check")
    started = time.perf_counter()
    migration = migrate_names(apply_changes=False, cleanup_legacy=True)
    payload["timings_ms"]["name_migration_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["name_migration_check"] = round(payload["timings_ms"]["name_migration_check"] / 1000.0, 3)
    payload["name_migration_check"]["needs_migration"] = migration["needs_migration"]
    payload["name_migration_check"]["ok"] = not migration["needs_migration"]
    payload["name_migration_check"]["summary"] = {
        "planned": migration["planned"],
        "planned_remove": migration["planned_remove"],
        "skipped": migration["skipped"],
    }
    if migration["needs_migration"]:
        raise RuntimeError("Navnemigrering gjenstår (kjør: norscode migrate-names --apply --cleanup)")
    if not json_output:
        print("OK")


def _finalize_ci_payload(payload: dict, pipeline_started: float):
    return _finalize_ci_payload(payload, pipeline_started)


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

    # 2) Ekstern registerfil: packages/registry.toml
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
    registry_path, digest = _read_registry_sign_digest(project_dir)
    changed = _write_registry_sign_config(config_path, digest, write_config=write_config)

    return {
        "registry": str(registry_path),
        "sha256": digest,
        "config": str(config_path),
        "written_to_config": write_config,
        "config_changed": changed,
    }


def _read_registry_sign_digest(project_dir: Path) -> tuple[Path, str]:
    registry_path = (project_dir / "packages" / "registry.toml").resolve()
    if not registry_path.exists():
        raise RuntimeError(f"Fant ikke registerfil: {registry_path}")
    return registry_path, _hash_file(registry_path).lower()


def _write_registry_sign_config(config_path: Path, digest: str, write_config: bool = False) -> bool:
    if not write_config:
        return False
    return _upsert_section_string_value(
        config_path,
        section="security",
        key="trusted_registry_sha256",
        value=digest,
    )


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


def _build_lock_project_entry(project_dir: Path, project_meta: dict) -> dict:
    return {
        "name": project_meta.get("name", project_dir.name),
        "version": project_meta.get("version"),
        "entry": project_meta.get("entry"),
    }


def _build_lock_dependency_entry(project_dir: Path, dep_value: str) -> dict:
    entry = {"specifier": dep_value}
    if dep_value.startswith("git+"):
        git_url, git_ref = _parse_git_dependency(dep_value)
        entry["kind"] = "git"
        entry["resolved"] = {
            "url": git_url,
            "ref": git_ref,
            "pinned": bool(git_ref),
        }
        return entry

    if dep_value.startswith("url+"):
        url = dep_value[len("url+") :]
        entry["kind"] = "url"
        entry["resolved"] = {
            "url": url,
            "pinned": True,
        }
        return entry

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
    return entry


def _build_lock_document(project_dir: Path, deps: dict, project_meta: dict) -> dict:
    lock = {
        "lock_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project": _build_lock_project_entry(project_dir, project_meta),
        "dependencies": {},
    }

    for dep_name, dep_value in sorted(deps.items(), key=lambda item: item[0]):
        lock["dependencies"][dep_name] = _build_lock_dependency_entry(project_dir, dep_value)

    return lock


def generate_lockfile(check_only: bool = False):
    config_path = _find_project_config()
    project_dir = config_path.parent.resolve()
    deps = _parse_dependencies_from_toml(config_path)
    project_toml = _load_toml(config_path)
    project_meta = project_toml.get("project", {}) if isinstance(project_toml.get("project", {}), dict) else {}
    lock = _build_lock_document(project_dir, deps, project_meta)

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


def _verify_lock_path_dependency(name: str, resolved: dict) -> tuple[bool, dict]:
    path_str = resolved.get("path") if isinstance(resolved, dict) else None
    expected_digest = resolved.get("digest_sha256") if isinstance(resolved, dict) else None
    if not isinstance(path_str, str):
        return False, {"name": name, "status": "mangler path i lock"}

    path = Path(path_str)
    if not path.exists():
        return False, {"name": name, "status": f"mangler path: {path}"}

    if isinstance(expected_digest, str):
        actual = _hash_directory(path) if path.is_dir() else _hash_file(path)
        if actual != expected_digest:
            return False, {"name": name, "status": "digest mismatch"}

    return True, {"name": name, "status": "ok"}


def _verify_lock_dependency_entry(name: str, entry: dict) -> tuple[bool, dict]:
    if not isinstance(entry, dict):
        return False, {"name": name, "status": "ugyldig entry"}

    kind = entry.get("kind")
    resolved = entry.get("resolved", {})
    if kind == "path":
        return _verify_lock_path_dependency(name, resolved)
    if kind == "git":
        ref = resolved.get("ref") if isinstance(resolved, dict) else None
        pinned = bool(ref)
        return True, {"name": name, "status": "ok" if pinned else "advarsel: upinnet git-ref"}
    if kind == "url":
        return True, {"name": name, "status": "ok"}
    return False, {"name": name, "status": f"ukjent kind: {kind}"}


def _cache_base_dir(project_dir: Path) -> Path:
    primary = (project_dir / ".norscode" / "cache").resolve()
    legacy = (project_dir / ".norsklang" / "cache").resolve()
    if primary.exists() or not legacy.exists():
        return primary
    _warn_legacy_once(
        "legacy-cache",
        "Merk: bruker legacy-lager '.norsklang/cache'. Migrer til '.norscode/cache'.",
    )
    return legacy


def _safe_extract_tar(archive_path: Path, dest_dir: Path):
    base_dir = dest_dir.resolve()

    def _is_safe_member(member_name: str) -> bool:
        if not member_name:
            return False
        if member_name.startswith(("/", "\\")):
            return False
        normalized = Path(member_name.replace("\\", "/"))
        if ".." in normalized.parts:
            return False
        target = (dest_dir / normalized).resolve()
        return target.is_relative_to(base_dir)

    with tarfile.open(archive_path) as tar:
        for member in tar.getmembers():
            if not _is_safe_member(member.name):
                raise RuntimeError(f"Utrygg tar-oppføring blokkert: {member.name}")
        tar.extractall(path=dest_dir)


def _safe_extract_zip(archive_path: Path, dest_dir: Path):
    base_dir = dest_dir.resolve()

    def _is_safe_member(member_name: str) -> bool:
        if not member_name:
            return False
        if member_name.startswith(("/", "\\")):
            return False
        normalized = Path(member_name.replace("\\", "/"))
        if ".." in normalized.parts:
            return False
        target = (dest_dir / normalized).resolve()
        return target.is_relative_to(base_dir)

    with zipfile.ZipFile(archive_path) as zf:
        for name in zf.namelist():
            if not _is_safe_member(name):
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
        raise RuntimeError(f"Fant ikke {_project_config_display_names()} i lageret: {base_dir}")
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
        dep_kind, dep_value, package_name = _resolve_add_dependency_from_explicit_source(
            package=package,
            dep_name=dep_name,
            project_dir=project_dir,
            git_url=git_url,
            git_ref=git_ref,
            tarball_url=None,
            fetch=fetch,
            refresh=refresh,
            expected_sha256=expected_sha256,
            security_policy=security_policy,
            allow_untrusted=allow_untrusted,
        )
    elif tarball_url:
        dep_name = dep_name_override or package
        dep_kind, dep_value, package_name = _resolve_add_dependency_from_explicit_source(
            package=package,
            dep_name=dep_name,
            project_dir=project_dir,
            git_url=None,
            git_ref=git_ref,
            tarball_url=tarball_url,
            fetch=fetch,
            refresh=refresh,
            expected_sha256=expected_sha256,
            security_policy=security_policy,
            allow_untrusted=allow_untrusted,
        )
    if package_path:
        dep_name, dep_kind, dep_value, package_name = _resolve_add_dependency_from_path_source(
            package=package,
            package_path=package_path,
            dep_name_override=dep_name_override,
            project_dir=project_dir,
        )
    elif not git_url and not tarball_url and path_like:
        dep_name, dep_kind, dep_value, package_name = _resolve_add_dependency_from_path_source(
            package=package,
            package_path=None,
            dep_name_override=dep_name_override,
            project_dir=project_dir,
        )
    elif not git_url and not tarball_url:
        dep_name = dep_name_override or package
        registry_hit = registry_entries.get(package)
        if registry_hit is not None:
            dep_kind, dep_value, package_name = _resolve_add_dependency_from_registry(
                package=package,
                dep_name=dep_name,
                registry_hit=registry_hit,
                project_dir=project_dir,
                fetch=fetch,
                refresh=refresh,
                pin=pin,
                expected_sha256=expected_sha256,
                security_policy=security_policy,
                allow_untrusted=allow_untrusted,
            )
        else:
            dep_name, dep_kind, dep_value, package_name = _resolve_add_dependency_from_path_source(
                package=str(project_dir / "packages" / package),
                package_path=None,
                dep_name_override=dep_name,
                project_dir=project_dir,
            )

    if not dep_name:
        raise RuntimeError("Kunne ikke finne avhengighetsnavn (bruk --name)")

    if not dep_value:
        raise RuntimeError("Kunne ikke finne dependency-verdi")

    changed = _upsert_dependency(config_path, dep_name, dep_value)
    return config_path, dep_name, dep_value, package_name, dep_kind, changed


def _resolve_add_dependency_from_registry(
    package: str,
    dep_name: str,
    registry_hit: dict,
    project_dir: Path,
    fetch: bool,
    refresh: bool,
    pin: bool,
    expected_sha256: str | None,
    security_policy: dict,
    allow_untrusted: bool,
) -> tuple[str, str, str]:
    if registry_hit.get("kind") == "path":
        resolved_dir, pkg_config = _resolve_package_dir(str(registry_hit["path"]))
        dep_kind = "path"
        dep_value = _to_project_relative_path(resolved_dir, project_dir)
        package_name = _parse_project_name_from_toml(pkg_config) or resolved_dir.name
    elif registry_hit.get("kind") == "git":
        if pin and not registry_hit.get("ref"):
            raise RuntimeError(f"Registerpakke '{package}' mangler låst git-ref (bruk pakke med ref eller uten --pin)")
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

    return dep_kind, dep_value, package_name


def _resolve_add_dependency_from_explicit_source(
    package: str,
    dep_name: str,
    project_dir: Path,
    git_url: str | None,
    git_ref: str | None,
    tarball_url: str | None,
    fetch: bool,
    refresh: bool,
    expected_sha256: str | None,
    security_policy: dict,
    allow_untrusted: bool,
) -> tuple[str, str, str]:
    if git_url:
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
        return dep_kind, dep_value, package_name

    if tarball_url:
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
        return dep_kind, dep_value, package_name

    raise RuntimeError("Mangler eksplisitt kilde for add-resolution")


def _resolve_add_dependency_from_path_source(
    package: str,
    package_path: str | None,
    dep_name_override: str | None,
    project_dir: Path,
) -> tuple[str, str, str, str]:
    if package_path:
        resolved_dir, pkg_config = _resolve_package_dir(package_path)
        dep_name = dep_name_override or package
        dep_kind = "path"
        dep_value = _to_project_relative_path(resolved_dir, project_dir)
        package_name = _parse_project_name_from_toml(pkg_config) or resolved_dir.name
        return dep_name, dep_kind, dep_value, package_name

    resolved_dir, pkg_config = _resolve_package_dir(package)
    dep_name = dep_name_override or _parse_project_name_from_toml(pkg_config) or resolved_dir.name
    dep_kind = "path"
    dep_value = _to_project_relative_path(resolved_dir, project_dir)
    package_name = _parse_project_name_from_toml(pkg_config) or resolved_dir.name
    return dep_name, dep_kind, dep_value, package_name


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
            "Merk: bruker legacy lockfile 'norsklang.lock'. Bytt til 'norscode.lock'.",
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
        entry_ok, result = _verify_lock_dependency_entry(name, entry)
        results.append(result)
        if not entry_ok:
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
        ("dir", *record_dir_migration(".norsklang", ".norscode")),
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
            raise RuntimeError(f"Registerpakke '{dep_name}' mangler låst git-ref (bruk pakke med ref eller uten --pin)")
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


def _plan_dependency_update(
    dep_name: str,
    current: str,
    registry_entries: dict,
    project_dir: Path,
    fetch: bool,
    refresh: bool,
    pin: bool,
    security_policy: dict,
    allow_untrusted: bool,
) -> tuple[str, dict]:
    hit = registry_entries.get(dep_name)
    if hit is None:
        return (
            "skipped",
            {
                "name": dep_name,
                "status": "skipped",
                "reason": "ikke i registry",
                "current": current,
            },
        )

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
        return (
            "unchanged",
            {
                "name": dep_name,
                "status": "unchanged",
                "kind": new_kind,
                "value": desired,
            },
        )

    return (
        "updated",
        {
            "name": dep_name,
            "status": "updated",
            "kind": new_kind,
            "from": current,
            "to": desired,
        },
    )


def _maybe_generate_lock_after_update(with_lock: bool, check_only: bool) -> dict | None:
    if not with_lock or check_only:
        return None
    lock_path, _ok, status = generate_lockfile(check_only=False)
    return {"path": str(lock_path), "status": status}


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
        status, item = _plan_dependency_update(
            dep_name=dep_name,
            current=current,
            registry_entries=registry_entries,
            project_dir=project_dir,
            fetch=fetch,
            refresh=refresh,
            pin=pin,
            security_policy=security_policy,
            allow_untrusted=allow_untrusted,
        )

        if status == "skipped":
            skipped += 1
            items.append(item)
            continue

        if status == "unchanged":
            unchanged += 1
            items.append(item)
            continue

        if not check_only:
            _upsert_dependency(config_path, dep_name, item["to"])
        updated += 1
        items.append(item)

    lock_info = _maybe_generate_lock_after_update(with_lock=with_lock, check_only=check_only)

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


def _run_selfhost_parser_disasm_cases(cases: list[str], mode: str) -> list[list[str]]:
    if mode not in {"expression", "script"}:
        raise RuntimeError(f"Ugyldig parsermodus: {mode}")

    build_dir = Path("build").resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    suffix = uuid.uuid4().hex[:8]
    source_path = build_dir / f"parser_core_{suffix}.no"
    c_path = source_path.with_suffix(".c")
    exe_path = source_path.with_suffix("")

    fn_name = "disasm_uttrykk" if mode == "expression" else "disasm_skript"
    lines = [
        "bruk selfhost.compiler som sh",
        "",
        "funksjon start() -> heltall {",
    ]
    for i, source in enumerate(cases):
        marker = f"__NORCODE_CASE_{i}__"
        lines.append(f'    skriv("{marker}")')
        lines.append(f'    skriv(sh.{fn_name}("{_escape_no_string(source)}"))')
    lines.extend(
        [
            "    returner 0",
            "}",
            "",
        ]
    )
    source = "\n".join(lines)

    try:
        source_path.write_text(source, encoding="utf-8")
        _src, _c, built_exe, _alias_map, _analyzer = build_program(str(source_path))
        result = subprocess.run(
            [str(built_exe.resolve())],
            capture_output=True,
            text=True,
            check=True,
        )
        out_lines = result.stdout.splitlines()
        parsed: list[list[str]] = [[] for _ in cases]
        current = -1
        for line in out_lines:
            if line.startswith("__NORCODE_CASE_") and line.endswith("__"):
                mid = line[len("__NORCODE_CASE_") : -2]
                try:
                    idx = int(mid)
                except ValueError:
                    continue
                if idx < 0 or idx >= len(cases):
                    continue
                current = idx
                continue
            if current >= 0:
                parsed[current].append(line)
        for idx in range(len(parsed)):
            while parsed[idx] and parsed[idx][-1] == "":
                parsed[idx].pop()
        return parsed
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


def get_current_git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        revision = result.stdout.strip()
        return revision or None
    except Exception:
        return None


def get_current_git_branch() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        return branch or None
    except Exception:
        return None


def get_current_git_dirty_state() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except Exception:
        return None


def to_short_git_revision(revision: str | None) -> str | None:
    if not revision:
        return None
    return revision[:7]


def get_current_git_exact_tag() -> str | None:
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
            check=True,
        )
        tag = result.stdout.strip()
        return tag or None
    except Exception:
        return None


def get_current_git_origin_url() -> str | None:
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        return url or None
    except Exception:
        return None


def get_git_remote_host(remote_url: str | None) -> str | None:
    if not remote_url:
        return None
    parsed = urllib.parse.urlparse(remote_url)
    if parsed.hostname:
        return parsed.hostname
    if "@" in remote_url and ":" in remote_url:
        rhs = remote_url.split("@", 1)[1]
        host = rhs.split(":", 1)[0].strip()
        return host or None
    return None


def get_git_remote_repo_slug(remote_url: str | None) -> str | None:
    if not remote_url:
        return None
    parsed = urllib.parse.urlparse(remote_url)
    path = ""
    if parsed.scheme and parsed.netloc:
        path = parsed.path
    elif "@" in remote_url and ":" in remote_url:
        path = remote_url.split(":", 1)[1]
    cleaned = path.strip().lstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    parts = [p for p in cleaned.split("/") if p]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return None


def get_git_remote_protocol(remote_url: str | None) -> str:
    if not remote_url:
        return "unknown"
    parsed = urllib.parse.urlparse(remote_url)
    if parsed.scheme:
        return parsed.scheme.lower()
    if "@" in remote_url and ":" in remote_url:
        return "ssh"
    return "unknown"


def split_repo_slug(slug: str | None) -> tuple[str | None, str | None]:
    if not slug or "/" not in slug:
        return None, None
    owner, name = slug.split("/", 1)
    owner = owner.strip() or None
    name = name.strip() or None
    return owner, name


def is_github_host(host: str | None) -> bool:
    return bool(host and host.lower() == "github.com")


def is_gitlab_host(host: str | None) -> bool:
    return bool(host and host.lower() == "gitlab.com")


def is_bitbucket_host(host: str | None) -> bool:
    return bool(host and host.lower() == "bitbucket.org")


def get_git_remote_provider(host: str | None) -> str:
    if not host:
        return "unknown"
    normalized = host.lower()
    if normalized == "github.com":
        return "github"
    if normalized == "gitlab.com":
        return "gitlab"
    if normalized == "bitbucket.org":
        return "bitbucket"
    return "unknown"


def get_source_revision_url(remote_host: str | None, repo_slug: str | None, revision: str | None) -> str | None:
    if not remote_host or not repo_slug or not revision:
        return None
    return f"https://{remote_host}/{repo_slug}/commit/{revision}"


def get_source_ref_url(remote_host: str | None, repo_slug: str | None, source_ref: str | None) -> str | None:
    if not remote_host or not repo_slug or not source_ref:
        return None
    return f"https://{remote_host}/{repo_slug}/tree/{source_ref}"


def get_source_repo_url(remote_host: str | None, repo_slug: str | None) -> str | None:
    if not remote_host or not repo_slug:
        return None
    return f"https://{remote_host}/{repo_slug}"


def _runtime_binary_candidates() -> list[Path]:
    project_dir = Path(__file__).resolve().parent
    runtime_dir = project_dir / "runtime"
    return [
        runtime_dir / "target" / "debug" / "norscode-runtime",
        runtime_dir / "target" / "release" / "norscode-runtime",
        runtime_dir / "target" / "debug" / "norscode-runtime.exe",
        runtime_dir / "target" / "release" / "norscode-runtime.exe",
    ]


def resolve_runtime_binary(explicit_path: str | None = None) -> Path:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.exists():
            raise RuntimeError(f"Fant ikke runtime-binær: {path}")
        return path

    for candidate in _runtime_binary_candidates():
        if candidate.exists():
            return candidate.resolve()

    expected = ", ".join(str(path) for path in _runtime_binary_candidates())
    raise RuntimeError(
        "Fant ingen prebygd runtime-binær. "
        f"Forventet en av: {expected}. "
        "Bruk Python-tilbakefall bare eksplisitt ved behov."
    )


def run_native_runtime(command: str, bytecode_file: str, runtime_binary: str | None = None):
    runtime_path = resolve_runtime_binary(runtime_binary)
    source_path = _resolve_source_path(bytecode_file)
    subprocess.run([str(runtime_path), command, str(source_path)], check=True)
    return source_path, runtime_path


def run_native_runtime_captured(command: str, bytecode_file: str, runtime_binary: str | None = None):
    runtime_path = resolve_runtime_binary(runtime_binary)
    source_path = _resolve_source_path(bytecode_file)
    result = subprocess.run(
        [str(runtime_path), command, str(source_path)],
        capture_output=True,
        text=True,
    )
    return source_path, runtime_path, result


def run_native_lock_command_captured(
    action: str,
    runtime_binary: str | None = None,
):
    runtime_path = resolve_runtime_binary(runtime_binary)
    result = subprocess.run(
        [str(runtime_path), "lock", action],
        capture_output=True,
        text=True,
    )
    return runtime_path, result


def run_native_update_command_captured(
    package: str | None = None,
    check_only: bool = False,
    pin: bool = False,
    fetch: bool = False,
    refresh: bool = False,
    allow_untrusted: bool = False,
    runtime_binary: str | None = None,
):
    runtime_path = resolve_runtime_binary(runtime_binary)
    cmd = [str(runtime_path), "update"]
    if package:
        cmd.append(package)
    if check_only:
        cmd.append("--check")
    if pin:
        cmd.append("--pin")
    if fetch:
        cmd.append("--fetch")
    if refresh:
        cmd.append("--refresh")
    if allow_untrusted:
        cmd.append("--allow-untrusted")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    return runtime_path, result


def run_native_registry_sync_command_captured(
    source: str | None = None,
    allow_untrusted: bool = False,
    require_all: bool = False,
    no_fallback: bool = False,
    runtime_binary: str | None = None,
):
    runtime_path = resolve_runtime_binary(runtime_binary)
    cmd = [str(runtime_path), "registry-sync"]
    if source:
        cmd.extend(["--source", source])
    if allow_untrusted:
        cmd.append("--allow-untrusted")
    if require_all:
        cmd.append("--require-all")
    if no_fallback:
        cmd.append("--no-fallback")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    return runtime_path, result


def run_native_registry_sign_command_captured(
    action: str | None = None,
    runtime_binary: str | None = None,
):
    runtime_path = resolve_runtime_binary(runtime_binary)
    cmd = [str(runtime_path), "registry-sign"]
    if action:
        cmd.append(action)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    return runtime_path, result


def run_native_registry_mirror_command_captured(
    action: str | None = None,
    output: str | None = None,
    runtime_binary: str | None = None,
):
    runtime_path = resolve_runtime_binary(runtime_binary)
    cmd = [str(runtime_path), "registry-mirror"]
    if action:
        cmd.append(action)
    if output:
        cmd.extend(["--output", output])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    return runtime_path, result


def run_native_ci_command_captured(
    check_names: bool = False,
    parity_suite: str = "all",
    require_selfhost_ready: bool = False,
    snapshot_check: bool = False,
    parser_fixture_check: bool = False,
    parity_check: bool = False,
    selfhost_m2_sync_check: bool = False,
    selfhost_progress_check: bool = False,
    test_check: bool = False,
    workflow_action_check: bool = False,
    name_migration_check: bool = False,
    runtime_binary: str | None = None,
):
    runtime_path = resolve_runtime_binary(runtime_binary)
    cmd = [str(runtime_path), "ci", "--parity-suite", parity_suite]
    if check_names:
        cmd.append("--check-names")
    if require_selfhost_ready:
        cmd.append("--require-selfhost-ready")
    if snapshot_check:
        cmd.append("--snapshot-check")
    if parser_fixture_check:
        cmd.append("--parser-fixture-check")
    if parity_check:
        cmd.append("--parity-check")
    if selfhost_m2_sync_check:
        cmd.append("--selfhost-m2-sync-check")
    if selfhost_progress_check:
        cmd.append("--selfhost-progress-check")
    if test_check:
        cmd.append("--test-check")
    if workflow_action_check:
        cmd.append("--workflow-action-check")
    if name_migration_check:
        cmd.append("--name-migration-check")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    return runtime_path, result


def run_native_add_command_captured(
    name: str | None = None,
    package: str | None = None,
    path: str | None = None,
    ref: str | None = None,
    pin: bool = False,
    fetch: bool = False,
    refresh: bool = False,
    sha256: str | None = None,
    allow_untrusted: bool = False,
    runtime_binary: str | None = None,
):
    runtime_path = resolve_runtime_binary(runtime_binary)
    cmd = [str(runtime_path), "add"]
    if name:
        cmd.extend(["--name", name])
    if ref:
        cmd.extend(["--ref", ref])
    if pin:
        cmd.append("--pin")
    if fetch:
        cmd.append("--fetch")
    if refresh:
        cmd.append("--refresh")
    if sha256:
        cmd.extend(["--sha256", sha256])
    if allow_untrusted:
        cmd.append("--allow-untrusted")
    if package:
        cmd.append(package)
    if path:
        cmd.append(path)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    return runtime_path, result


def _parse_native_lock_stdout(stdout: str) -> dict:
    payload: dict[str, object] = {}
    issues: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "issue":
            issues.append(value)
            continue
        if value == "true":
            payload[key] = True
        elif value == "false":
            payload[key] = False
        else:
            try:
                payload[key] = int(value)
            except ValueError:
                payload[key] = value
    if issues:
        payload["issues"] = issues
    return payload


def _parse_native_update_stdout(stdout: str) -> dict:
    payload: dict[str, object] = {}
    packages: list[str] = []
    items: list[dict[str, str]] = []
    item_reasons: dict[str, str] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "package":
            packages.append(value)
            continue
        if key == "item":
            name, _, status = value.partition("=")
            items.append({"name": name, "status": status})
            continue
        if key == "item_reason":
            name, _, reason = value.partition("=")
            item_reasons[name] = reason
            continue
        if value == "true":
            payload[key] = True
        elif value == "false":
            payload[key] = False
        else:
            try:
                payload[key] = int(value)
            except ValueError:
                payload[key] = value
    if packages:
        payload["packages"] = packages
    if items:
        for item in items:
            reason = item_reasons.get(item["name"])
            if reason:
                item["reason"] = reason
        payload["items"] = items
    return payload


def _parse_native_add_stdout(stdout: str) -> dict:
    payload: dict[str, object] = {}
    dependencies: list[str] = []
    items: list[dict[str, str]] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "dependency":
            dependencies.append(value)
            continue
        if key == "item":
            name, _, kind = value.partition("=")
            items.append({"name": name, "kind": kind})
            continue
        if value == "true":
            payload[key] = True
        elif value == "false":
            payload[key] = False
        else:
            try:
                payload[key] = int(value)
            except ValueError:
                payload[key] = value
    if dependencies:
        payload["dependencies"] = dependencies
    if items:
        payload["items"] = items
    return payload


def _parse_native_registry_sync_stdout(stdout: str) -> dict:
    payload: dict[str, object] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value == "true":
            payload[key] = True
        elif value == "false":
            payload[key] = False
        else:
            try:
                payload[key] = int(value)
            except ValueError:
                payload[key] = value
    return payload


def _parse_native_registry_sign_stdout(stdout: str) -> dict:
    payload: dict[str, object] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value == "true":
            payload[key] = True
        elif value == "false":
            payload[key] = False
        else:
            try:
                payload[key] = int(value)
            except ValueError:
                payload[key] = value
    return payload


def build_bytecode_file(source_file: str, output: str | None = None) -> Path:
    return build_bytecode_command(source_file=source_file, output=output)


def run_native_source(
    command: str,
    source_file: str,
    runtime_binary: str | None = None,
    keep_bytecode: bool = False,
    output: str | None = None,
):
    source_path = _resolve_source_path(source_file)
    if keep_bytecode or output:
        bytecode_path = build_bytecode_file(str(source_path), output=output)
        runtime_source_path, runtime_path = run_native_runtime(
            command,
            str(bytecode_path),
            runtime_binary=runtime_binary,
        )
        return source_path, bytecode_path, runtime_source_path, runtime_path

    with tempfile.TemporaryDirectory(prefix="norscode-native-") as tmpdir:
        bytecode_path = Path(tmpdir) / f"{source_path.stem}.ncb.json"
        build_bytecode_file(str(source_path), output=str(bytecode_path))
        runtime_source_path, runtime_path = run_native_runtime(
            command,
            str(bytecode_path),
            runtime_binary=runtime_binary,
        )
        return source_path, None, runtime_source_path, runtime_path


def discover_tests() -> list[Path]:
    tests_dir = Path("tests").resolve()
    if not tests_dir.exists():
        return []
    return sorted(p.resolve() for p in tests_dir.glob("test_*.no"))


def discover_tests_in_dir(target_dir: Path) -> list[Path]:
    if not target_dir.exists() or not target_dir.is_dir():
        return []
    return sorted(p.resolve() for p in target_dir.rglob("test_*.no"))


def run_native_test_file(
    source_file: str,
    runtime_binary: str | None = None,
):
    started = time.perf_counter()
    source_path = _resolve_source_path(source_file)

    with tempfile.TemporaryDirectory(prefix="norscode-native-test-") as tmpdir:
        bytecode_path = Path(tmpdir) / f"{source_path.stem}.ncb.json"
        build_bytecode_file(str(source_path), output=str(bytecode_path))
        runtime_source_path, runtime_path, result = run_native_runtime_captured(
            "run",
            str(bytecode_path),
            runtime_binary=runtime_binary,
        )
        bytecode_path = None

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "source": str(source_path),
        "bytecode_file": str(bytecode_path) if bytecode_path is not None else "",
        "runtime_bytecode_file": str(runtime_source_path),
        "runtime_binary": str(runtime_path),
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


def run_selfhost_parser_core_checks(fixture_path: Path, label: str):
    started = time.perf_counter()
    fixture_path = fixture_path.resolve()
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "source": label,
            "c_file": "",
            "exe_file": "",
            "returncode": 1,
            "stdout": "",
            "stderr": f"Kunne ikke lese fixture {fixture_path}: {exc}\n",
            "success": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "case_count": 0,
            "expression_cases": 0,
            "script_cases": 0,
            "line_cases": 0,
            "error_cases": 0,
        }

    expression_cases = fixture.get("expressions", [])
    script_cases = fixture.get("scripts", [])
    expression_count = len(expression_cases)
    script_count = len(script_cases)
    line_case_count = 0
    error_case_count = 0
    mismatch_lines: list[str] = []

    def _validate_and_collect(cases: list[dict], mode: str):
        nonlocal line_case_count, error_case_count
        if not cases:
            return
        seen_names: set[str] = set()
        for idx, item in enumerate(cases):
            has_expected_lines = "expected_lines" in item
            has_expected_error = "expected_error" in item
            if "source" not in item:
                mismatch_lines.append(f"[{mode}#{idx}] mangler source i fixture")
                return
            case_name = str(item.get("name") or f"{mode}_{idx}")
            if case_name in seen_names:
                mismatch_lines.append(f"[{mode}#{idx}] duplikat casenavn: {case_name}")
                return
            seen_names.add(case_name)
            if has_expected_lines == has_expected_error:
                mismatch_lines.append(
                    f"[{mode}#{idx}] må ha nøyaktig ett av feltene expected_lines eller expected_error"
                )
                return
            if has_expected_error:
                error_case_count += 1
            else:
                line_case_count += 1
        sources = [str(item["source"]) for item in cases]
        actual_lists = _run_selfhost_parser_disasm_cases(sources, mode=mode)
        if len(actual_lists) != len(cases):
            mismatch_lines.append(f"[{mode}] intern feil: antall resultater avviker")
            return
        for idx, item in enumerate(cases):
            name = str(item.get("name") or f"{mode}_{idx}")
            actual_lines = actual_lists[idx]
            expected_error = item.get("expected_error")
            if expected_error is not None:
                actual_error = actual_lines[0] if actual_lines else ""
                if actual_error != str(expected_error):
                    mismatch_lines.append(f"[{name}] error mismatch")
                    mismatch_lines.append(f"expected: {expected_error}")
                    mismatch_lines.append(f"actual:   {actual_error}")
                continue

            expected_lines = [str(line) for line in item.get("expected_lines", [])]
            if expected_lines != actual_lines:
                mismatch_lines.append(f"[{name}] mismatch")
                mismatch_lines.extend(
                    difflib.unified_diff(
                        expected_lines,
                        actual_lines,
                        fromfile=f"{name}/expected",
                        tofile=f"{name}/actual",
                        lineterm="",
                    )
                )

    try:
        _validate_and_collect(expression_cases, "expression")
        _validate_and_collect(script_cases, "script")
    except Exception as exc:
        mismatch_lines.append(f"Kjøring feilet: {exc}")

    success = len(mismatch_lines) == 0
    return {
        "source": label,
        "c_file": "",
        "exe_file": "",
        "returncode": 0 if success else 1,
        "stdout": "",
        "stderr": "" if success else "\n".join(mismatch_lines) + "\n",
        "success": success,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "case_count": expression_count + script_count,
        "expression_cases": expression_count,
        "script_cases": script_count,
        "line_cases": line_case_count,
        "error_cases": error_case_count,
    }


def run_selfhost_parser_parity(suite: str = "all") -> dict:
    suites = _selfhost_parity_suite_targets(suite)
    started = time.perf_counter()
    results: list[dict] = []
    for fixture_path, label in suites:
        results.append(run_selfhost_parser_core_checks(fixture_path, label))

    ok = all(item.get("success") for item in results)
    return {
        "suite": suite,
        "ok": ok,
        "case_count": sum(int(item.get("case_count", 0) or 0) for item in results),
        "expression_cases": sum(int(item.get("expression_cases", 0) or 0) for item in results),
        "script_cases": sum(int(item.get("script_cases", 0) or 0) for item in results),
        "line_cases": sum(int(item.get("line_cases", 0) or 0) for item in results),
        "error_cases": sum(int(item.get("error_cases", 0) or 0) for item in results),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "results": results,
    }


def _count_selfhost_parity_cases(fixture: dict) -> dict:
    expression_cases = fixture.get("expressions", [])
    script_cases = fixture.get("scripts", [])
    all_cases = [*expression_cases, *script_cases]
    error_cases = sum(1 for item in all_cases if "expected_error" in item)
    line_cases = len(all_cases) - error_cases
    return {
        "case_count": len(all_cases),
        "expression_cases": len(expression_cases),
        "script_cases": len(script_cases),
        "line_cases": line_cases,
        "error_cases": error_cases,
    }


def run_selfhost_parity_progress() -> dict:
    started = time.perf_counter()
    mismatch_lines: list[str] = []
    m1_fixture = _load_selfhost_parity_fixture(SELFHOST_PARSER_M1_FIXTURE, mismatch_lines)
    m2_fixture = _load_selfhost_parity_fixture(SELFHOST_PARSER_M2_FIXTURE, mismatch_lines)
    ext_fixture = _load_selfhost_parity_fixture(SELFHOST_PARSER_EXTENDED_FIXTURE, mismatch_lines)
    if m1_fixture is None or m2_fixture is None or ext_fixture is None:
        return {
            "ok": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "stderr": "\n".join(mismatch_lines) + "\n",
        }

    m1_maps, _ = _selfhost_parity_fixture_case_maps(m1_fixture, "m1", mismatch_lines)
    m2_maps, _ = _selfhost_parity_fixture_case_maps(m2_fixture, "m2", mismatch_lines)
    ext_maps, _ = _selfhost_parity_fixture_case_maps(ext_fixture, "extended", mismatch_lines)

    overlap_expr = sorted(set(m1_maps["expressions"].keys()) & set(m2_maps["expressions"].keys()))
    overlap_scripts = sorted(set(m1_maps["scripts"].keys()) & set(m2_maps["scripts"].keys()))
    overlap_total = len(overlap_expr) + len(overlap_scripts)

    union_expr = set(m1_maps["expressions"].keys()) | set(m2_maps["expressions"].keys())
    union_scripts = set(m1_maps["scripts"].keys()) | set(m2_maps["scripts"].keys())
    ext_expr = set(ext_maps["expressions"].keys())
    ext_scripts = set(ext_maps["scripts"].keys())
    union_total = len(union_expr) + len(union_scripts)
    ext_total = len(ext_expr) + len(ext_scripts)

    missing_expr = sorted(ext_expr - union_expr)
    missing_scripts = sorted(ext_scripts - union_scripts)
    missing_total = len(missing_expr) + len(missing_scripts)

    extra_expr = sorted(union_expr - ext_expr)
    extra_scripts = sorted(union_scripts - ext_scripts)
    extra_total = len(extra_expr) + len(extra_scripts)

    consistency = run_selfhost_parser_suite_all_consistency_check(
        SELFHOST_PARSER_M1_FIXTURE,
        SELFHOST_PARSER_M2_FIXTURE,
        SELFHOST_PARSER_EXTENDED_FIXTURE,
    )

    def _pct(part: int, total: int) -> float:
        if total <= 0:
            return 100.0
        return round((part / total) * 100.0, 2)

    coverage_expr = _pct(len(union_expr), len(ext_expr))
    coverage_scripts = _pct(len(union_scripts), len(ext_scripts))
    coverage_total = _pct(union_total, ext_total)
    m1_total = len(m1_maps["expressions"]) + len(m1_maps["scripts"])
    m2_total = len(m2_maps["expressions"]) + len(m2_maps["scripts"])
    coverage_m1 = _pct(m1_total, ext_total)
    coverage_m2 = _pct(m2_total, ext_total)

    ready = (
        consistency.get("success")
        and missing_total == 0
        and extra_total == 0
        and overlap_total == 0
    )
    ok = ready and not mismatch_lines
    return {
        "ok": ok,
        "ready": bool(ready),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "m1": {
            **_count_selfhost_parity_cases(m1_fixture),
            "coverage_total_pct": coverage_m1,
        },
        "m2": {
            **_count_selfhost_parity_cases(m2_fixture),
            "coverage_total_pct": coverage_m2,
        },
        "extended": _count_selfhost_parity_cases(ext_fixture),
        "coverage": {
            "expression_pct": coverage_expr,
            "script_pct": coverage_scripts,
            "total_pct": coverage_total,
            "union_case_count": union_total,
            "extended_case_count": ext_total,
            "missing_in_m1_m2_count": missing_total,
            "extra_in_m1_m2_count": extra_total,
            "overlap_count": overlap_total,
            "missing_in_m1_m2_examples": (missing_expr + missing_scripts)[:10],
            "extra_in_m1_m2_examples": (extra_expr + extra_scripts)[:10],
            "overlap_examples": (overlap_expr + overlap_scripts)[:10],
        },
        "consistency": {
            "ok": bool(consistency.get("success")),
            "checked_cases": int(consistency.get("checked_cases", 0) or 0),
            "mismatch_count": int(consistency.get("mismatch_count", 0) or 0),
        },
        "stderr": "" if ok else (consistency.get("stderr", "") or "\n".join(mismatch_lines) + "\n"),
    }


def _load_selfhost_parity_fixture(path: Path, mismatch_lines: list[str]) -> dict | None:
    try:
        return json.loads(path.resolve().read_text(encoding="utf-8"))
    except Exception as exc:
        mismatch_lines.append(f"Kunne ikke lese fixture {path.resolve()}: {exc}")
        return None


def _normalize_selfhost_parity_case(item: dict) -> dict:
    normalized = {"source": str(item.get("source", ""))}
    has_lines = "expected_lines" in item
    has_error = "expected_error" in item
    if has_lines == has_error:
        normalized["invalid"] = True
        return normalized
    if has_error:
        normalized["expected_error"] = str(item.get("expected_error", ""))
    else:
        normalized["expected_lines"] = [str(line) for line in item.get("expected_lines", [])]
    return normalized


def _selfhost_parity_fixture_case_maps(
    fixture: dict,
    fixture_tag: str,
    mismatch_lines: list[str],
) -> tuple[dict[str, dict[str, dict]], int]:
    maps: dict[str, dict[str, dict]] = {"expressions": {}, "scripts": {}}
    checked = 0
    for mode in ("expressions", "scripts"):
        cases = fixture.get(mode, [])
        mode_map = maps[mode]
        for idx, item in enumerate(cases):
            if "name" not in item:
                mismatch_lines.append(f"[{fixture_tag}/{mode}#{idx}] mangler navn")
                continue
            name = str(item["name"])
            if name in mode_map:
                mismatch_lines.append(f"[{fixture_tag}/{mode}#{idx}] duplikat navn: {name}")
                continue
            mode_map[name] = _normalize_selfhost_parity_case(item)
            checked += 1
    return maps, checked


def run_selfhost_parser_suite_subset_consistency_check(
    subset_fixture: Path,
    extended_fixture: Path,
    subset_tag: str,
) -> dict:
    started = time.perf_counter()
    mismatch_lines: list[str] = []

    subset = _load_selfhost_parity_fixture(subset_fixture, mismatch_lines)
    extended = _load_selfhost_parity_fixture(extended_fixture, mismatch_lines)
    if subset is None or extended is None:
        return {
            "success": False,
            "checked_cases": 0,
            "mismatch_count": len(mismatch_lines),
            "stderr": "\n".join(mismatch_lines) + "\n",
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "scope": subset_tag,
        }

    subset_maps, checked = _selfhost_parity_fixture_case_maps(subset, subset_tag, mismatch_lines)
    ext_maps, _ = _selfhost_parity_fixture_case_maps(extended, "extended", mismatch_lines)

    for mode in ("expressions", "scripts"):
        for name, subset_norm in subset_maps[mode].items():
            ext_norm = ext_maps[mode].get(name)
            if ext_norm is None:
                mismatch_lines.append(f"[{subset_tag}/{mode}/{name}] finnes ikke i utvidet fixture")
                continue
            if subset_norm.get("invalid") or ext_norm.get("invalid"):
                mismatch_lines.append(f"[{subset_tag}/{mode}/{name}] ugyldig expected_* format")
                continue
            if subset_norm != ext_norm:
                mismatch_lines.append(f"[{subset_tag}/{mode}/{name}] avviker mot utvidet")
                mismatch_lines.extend(
                    difflib.unified_diff(
                        json.dumps(subset_norm, ensure_ascii=False, indent=2).splitlines(),
                        json.dumps(ext_norm, ensure_ascii=False, indent=2).splitlines(),
                        fromfile=f"{subset_tag}/{name}",
                        tofile=f"extended/{name}",
                        lineterm="",
                    )
                )

    success = len(mismatch_lines) == 0
    return {
        "success": success,
        "checked_cases": checked,
        "mismatch_count": len(mismatch_lines),
        "stderr": "" if success else "\n".join(mismatch_lines) + "\n",
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "scope": subset_tag,
    }


def run_selfhost_parser_suite_all_consistency_check(
    m1_fixture: Path,
    m2_fixture: Path,
    extended_fixture: Path,
) -> dict:
    started = time.perf_counter()
    mismatch_lines: list[str] = []

    m1 = run_selfhost_parser_suite_subset_consistency_check(m1_fixture, extended_fixture, "m1")
    m2 = run_selfhost_parser_suite_subset_consistency_check(m2_fixture, extended_fixture, "m2")

    m1_fixture_obj = _load_selfhost_parity_fixture(m1_fixture, mismatch_lines)
    m2_fixture_obj = _load_selfhost_parity_fixture(m2_fixture, mismatch_lines)
    ext_fixture_obj = _load_selfhost_parity_fixture(extended_fixture, mismatch_lines)

    coverage_checked = 0
    if m1_fixture_obj is not None and m2_fixture_obj is not None and ext_fixture_obj is not None:
        m1_maps, _ = _selfhost_parity_fixture_case_maps(m1_fixture_obj, "m1", mismatch_lines)
        m2_maps, _ = _selfhost_parity_fixture_case_maps(m2_fixture_obj, "m2", mismatch_lines)
        ext_maps, _ = _selfhost_parity_fixture_case_maps(ext_fixture_obj, "extended", mismatch_lines)

        for mode in ("expressions", "scripts"):
            union_names = set(m1_maps[mode].keys()) | set(m2_maps[mode].keys())
            coverage_checked += len(union_names)

            overlap = set(m1_maps[mode].keys()) & set(m2_maps[mode].keys())
            for name in sorted(overlap):
                if m1_maps[mode][name] != m2_maps[mode][name]:
                    mismatch_lines.append(f"[all/{mode}/{name}] finnes i både m1 og m2 med ulikt innhold")

            for name in sorted(union_names):
                union_case = m1_maps[mode].get(name) or m2_maps[mode].get(name)
                ext_case = ext_maps[mode].get(name)
                if ext_case is None:
                    mismatch_lines.append(f"[all/{mode}/{name}] finnes i m1/m2 men ikke i utvidet fixture")
                    continue
                if union_case.get("invalid") or ext_case.get("invalid"):
                    mismatch_lines.append(f"[all/{mode}/{name}] ugyldig expected_* format")
                    continue
                if union_case != ext_case:
                    mismatch_lines.append(f"[all/{mode}/{name}] avviker mellom m1/m2-union og utvidet")

            extra_in_extended = set(ext_maps[mode].keys()) - union_names
            for name in sorted(extra_in_extended):
                mismatch_lines.append(f"[all/{mode}/{name}] finnes i utvidet fixture, men mangler i m1+m2")

    all_success = m1.get("success") and m2.get("success") and not mismatch_lines
    total_mismatch = int(m1.get("mismatch_count", 0) or 0) + int(m2.get("mismatch_count", 0) or 0) + len(mismatch_lines)

    details: list[str] = []
    if not m1.get("success") and m1.get("stderr"):
        details.append("[m1]\n" + str(m1.get("stderr", "")).rstrip())
    if not m2.get("success") and m2.get("stderr"):
        details.append("[m2]\n" + str(m2.get("stderr", "")).rstrip())
    if mismatch_lines:
        details.append("[all]\n" + "\n".join(mismatch_lines))

    return {
        "success": bool(all_success),
        "checked_cases": int(m1.get("checked_cases", 0) or 0)
        + int(m2.get("checked_cases", 0) or 0)
        + coverage_checked,
        "mismatch_count": total_mismatch,
        "stderr": "" if all_success else ("\n\n".join(details).rstrip() + "\n"),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "scope": "all",
        "checks": {
            "m1": m1,
            "m2": m2,
            "coverage_checked_cases": coverage_checked,
            "coverage_mismatch_count": len(mismatch_lines),
        },
    }


def run_selfhost_parser_suite_consistency_check(m1_fixture: Path, extended_fixture: Path) -> dict:
    return run_selfhost_parser_suite_subset_consistency_check(m1_fixture, extended_fixture, "m1")


def _selfhost_parity_suite_targets(suite: str) -> list[tuple[Path, str]]:
    suites = {
        "m1": [(SELFHOST_PARSER_M1_FIXTURE, "Selfhost parser parity (M1)")],
        "m2": [(SELFHOST_PARSER_M2_FIXTURE, "Selfhost parser parity (M2)")],
        "extended": [(SELFHOST_PARSER_EXTENDED_FIXTURE, "Selfhost parser parity (utvidet)")],
        "all": [
            (SELFHOST_PARSER_M1_FIXTURE, "Selfhost parser parity (M1)"),
            (SELFHOST_PARSER_M2_FIXTURE, "Selfhost parser parity (M2)"),
            (SELFHOST_PARSER_EXTENDED_FIXTURE, "Selfhost parser parity (utvidet)"),
        ],
    }
    if suite not in suites:
        raise RuntimeError(f"Ugyldig suite: {suite}")
    return suites[suite]


def update_selfhost_parser_fixtures(check_only: bool = False, suite: str = "all", sync_m2: bool = True) -> dict:
    targets = _selfhost_parity_suite_targets(suite)
    summaries: list[dict] = []
    total_updated = 0
    total_cases = 0
    m2_sync_payload = None

    if sync_m2 and suite in {"m2", "all"}:
        m2_sync_payload = sync_selfhost_parser_m2_fixture(check_only=check_only)
        total_updated += int(m2_sync_payload.get("updated", 0) or 0)
        total_updated += int(m2_sync_payload.get("missing_m1_from_core_count", 0) or 0)

    for fixture_path, label in targets:
        fixture_abs = fixture_path.resolve()
        fixture = json.loads(fixture_abs.read_text(encoding="utf-8"))
        updated = 0
        case_count = 0

        for mode, key in (("expression", "expressions"), ("script", "scripts")):
            cases = fixture.get(key, [])
            if not cases:
                continue
            sources = [str(item.get("source", "")) for item in cases]
            actual_lists = _run_selfhost_parser_disasm_cases(sources, mode=mode)
            if len(actual_lists) != len(cases):
                raise RuntimeError(f"Intern feil ved oppdatering av {fixture_abs} ({mode}): antall resultater avviker")

            for idx, item in enumerate(cases):
                case_count += 1
                actual_lines = actual_lists[idx]
                old_lines = item.get("expected_lines")
                old_error = item.get("expected_error")

                if actual_lines and actual_lines[0].startswith("/* feil:"):
                    new_error = actual_lines[0]
                    if old_error != new_error or old_lines is not None:
                        updated += 1
                    item["expected_error"] = new_error
                    item.pop("expected_lines", None)
                else:
                    if old_lines != actual_lines or old_error is not None:
                        updated += 1
                    item["expected_lines"] = actual_lines
                    item.pop("expected_error", None)

        total_updated += updated
        total_cases += case_count
        summaries.append(
            {
                "fixture": str(fixture_abs),
                "label": label,
                "cases": case_count,
                "updated": updated,
            }
        )
        if not check_only:
            fixture_abs.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "suite": suite,
        "check_only": check_only,
        "sync_m2": sync_m2,
        "m2_sync": m2_sync_payload,
        "updated": total_updated,
        "cases": total_cases,
        "fixtures": summaries,
    }


def sync_selfhost_parser_m2_fixture(check_only: bool = False) -> dict:
    m1_path = SELFHOST_PARSER_M1_FIXTURE.resolve()
    core_path = SELFHOST_PARSER_EXTENDED_FIXTURE.resolve()
    m2_path = SELFHOST_PARSER_M2_FIXTURE.resolve()

    m1 = json.loads(m1_path.read_text(encoding="utf-8"))
    core = json.loads(core_path.read_text(encoding="utf-8"))
    current_m2 = json.loads(m2_path.read_text(encoding="utf-8")) if m2_path.exists() else {"expressions": [], "scripts": []}

    target_m2: dict[str, list[dict]] = {"expressions": [], "scripts": []}
    missing_from_core: dict[str, list[str]] = {"expressions": [], "scripts": []}

    for mode in ("expressions", "scripts"):
        m1_cases = m1.get(mode, [])
        core_cases = core.get(mode, [])
        m1_names = {str(item.get("name", "")) for item in m1_cases if "name" in item}
        core_names = {str(item.get("name", "")) for item in core_cases if "name" in item}
        target_m2[mode] = [item for item in core_cases if str(item.get("name", "")) not in m1_names]
        missing_from_core[mode] = sorted(name for name in m1_names if name and name not in core_names)

    updated = 1 if current_m2 != target_m2 else 0
    if not check_only and updated:
        m2_path.write_text(json.dumps(target_m2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    missing_count = len(missing_from_core["expressions"]) + len(missing_from_core["scripts"])
    ok = updated == 0 and missing_count == 0

    return {
        "check_only": check_only,
        "ok": ok,
        "updated": updated,
        "fixture": str(m2_path),
        "m1_fixture": str(m1_path),
        "core_fixture": str(core_path),
        "m1_cases": len(m1.get("expressions", [])) + len(m1.get("scripts", [])),
        "core_cases": len(core.get("expressions", [])) + len(core.get("scripts", [])),
        "m2_cases": len(target_m2.get("expressions", [])) + len(target_m2.get("scripts", [])),
        "missing_m1_from_core_count": missing_count,
        "missing_m1_from_core": missing_from_core,
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


def run_test_collection(
    test_files: list[Path],
    verbose: bool = False,
    quiet: bool = False,
    runtime_binary: str | None = None,
) -> list[dict]:
    results = []
    for test_file in test_files:
        result = run_native_test_file(str(test_file), runtime_binary=runtime_binary)
        results.append(result)
        if not quiet:
            print_test_result(result, verbose=verbose)
    return results


def run_all_tests(verbose: bool = False, quiet: bool = False, runtime_binary: str | None = None):
    tests = discover_tests()
    if not tests:
        raise RuntimeError("Fant ingen tester i tests/")

    results = run_test_collection(tests, verbose=verbose, quiet=quiet, runtime_binary=runtime_binary)

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
    minimum_action_majors = WORKFLOW_ACTION_POLICY["minimum_action_majors"]
    required_norscode_ci_flags = [str(flag) for flag in WORKFLOW_ACTION_POLICY.get("required_norscode_ci_flags", [])]
    payload = {
        "ok": True,
        "scanned_dir": str(base),
        "scanned_files": 0,
        "files": [],
        "file_extensions": [".yml", ".yaml"],
        "issue_count": 0,
        "issue_types": {},
        "issues": [],
        "policy": WORKFLOW_ACTION_POLICY,
    }
    if not base.exists():
        return payload

    workflow_files = sorted([*base.glob("*.yml"), *base.glob("*.yaml")])
    payload["scanned_files"] = len(workflow_files)
    payload["files"] = [str(path) for path in workflow_files]
    for workflow_path in workflow_files:
        try:
            lines = workflow_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        has_node24_env = False
        saw_norscode_ci_command = False
        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if re.search(
                r'^\s*FORCE_JAVASCRIPT_ACTIONS_TO_NODE24\s*:\s*("true"|true)\s*$',
                line,
                re.IGNORECASE,
            ):
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
                            "type": "deprecated_action_major",
                            "rule": "action_min_major",
                            "found": f"{action_name}@v{major}",
                            "expected": f"{action_name}@v{minimum_major}",
                        }
                    )
            if re.search(
                r'^\s*ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION\s*:\s*("true"|true)\s*$',
                line,
                re.IGNORECASE,
            ):
                payload["issues"].append(
                    {
                        "file": str(workflow_path),
                        "line": line_no,
                        "type": "unsecure_node_opt_out",
                        "rule": "forbid_unsecure_opt_out",
                        "found": "ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true",
                        "expected": "fjern opt-out og bruk Node 24-kompatible action-versjoner",
                    }
                )
            run_match = re.search(r"^\s*run\s*:\s*(.+)$", raw_line)
            if run_match:
                run_cmd = run_match.group(1).strip()
                if "norscode ci" in run_cmd:
                    saw_norscode_ci_command = True
                    for flag in required_norscode_ci_flags:
                        if flag not in run_cmd:
                            payload["issues"].append(
                                {
                                    "file": str(workflow_path),
                                    "line": line_no,
                                    "type": "missing_norscode_ci_flag",
                                    "rule": "require_norscode_ci_flag",
                                    "found": run_cmd,
                                    "expected": f"run-linje med norscode ci må inkludere {flag}",
                                }
                            )
        if not has_node24_env:
            payload["issues"].append(
                {
                    "file": str(workflow_path),
                    "line": 1,
                    "type": "missing_node24_env",
                    "rule": "require_node24_env",
                    "found": "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 mangler/ikke true",
                    "expected": 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"',
                }
            )
        if required_norscode_ci_flags and not saw_norscode_ci_command:
            payload["issues"].append(
                {
                    "file": str(workflow_path),
                    "line": 1,
                    "type": "missing_norscode_ci_command",
                    "rule": "require_norscode_ci_command",
                    "found": "mangler run-linje med 'norscode ci'",
                    "expected": "legg til run: norscode ci --check-names --require-selfhost-ready",
                }
            )

    payload["issues"] = sorted(
        payload["issues"],
        key=lambda issue: (
            str(issue.get("file", "")),
            int(issue.get("line", 0)),
            str(issue.get("type", "")),
        ),
    )
    payload["issue_count"] = len(payload["issues"])
    issue_types: dict[str, int] = {}
    for issue in payload["issues"]:
        issue_type = str(issue.get("type", "unknown"))
        issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
    payload["issue_types"] = issue_types
    payload["ok"] = payload["issue_count"] == 0
    return payload


def run_ci_pipeline(
    json_output: bool = False,
    check_names: bool = False,
    parity_suite: str = "all",
    require_selfhost_ready: bool = False,
):
    if parity_suite not in {"m1", "m2", "all"}:
        raise RuntimeError(f"Ugyldig parity-suite for CI: {parity_suite}")
    run_m2_sync_check = parity_suite in {"m2", "all"}
    pipeline_started = time.perf_counter()
    started_at_utc = dt.datetime.now(dt.UTC).isoformat()
    started_at_epoch_ms = int(time.time() * 1000)
    source_revision = get_current_git_revision()
    source_branch = get_current_git_branch()
    source_tag = get_current_git_exact_tag()
    source_remote = get_current_git_origin_url()
    source_remote_protocol = get_git_remote_protocol(source_remote)
    source_remote_host = get_git_remote_host(source_remote)
    source_remote_provider = get_git_remote_provider(source_remote_host)
    source_repo_slug = get_git_remote_repo_slug(source_remote)
    source_repo_owner, source_repo_name = split_repo_slug(source_repo_slug)
    source_dirty = get_current_git_dirty_state()
    py_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    step_order = _build_ci_step_order(
        parity_suite=parity_suite,
        run_m2_sync_check=run_m2_sync_check,
        require_selfhost_ready=require_selfhost_ready,
        check_names=check_names,
    )
    total_steps = len(step_order)
    payload = _build_ci_payload_base(
        started_at_utc=started_at_utc,
        started_at_epoch_ms=started_at_epoch_ms,
        source_revision=source_revision,
        source_branch=source_branch,
        source_tag=source_tag,
        source_remote=source_remote,
        source_remote_protocol=source_remote_protocol,
        source_remote_host=source_remote_host,
        source_remote_provider=source_remote_provider,
        source_repo_slug=source_repo_slug,
        source_repo_owner=source_repo_owner,
        source_repo_name=source_repo_name,
        source_dirty=source_dirty,
        py_major_minor=py_major_minor,
        json_output=json_output,
        check_names=check_names,
        parity_suite=parity_suite,
        require_selfhost_ready=require_selfhost_ready,
        run_m2_sync_check=run_m2_sync_check,
        total_steps=total_steps,
        step_order=step_order,
    )

    if not json_output:
        print(f"[1/{total_steps}] Snapshot check")
    started = time.perf_counter()
    _fixture_path, updated, _total = update_ir_snapshots(check_only=True)
    payload["timings_ms"]["snapshot_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["snapshot_check"] = round(payload["timings_ms"]["snapshot_check"] / 1000.0, 3)
    payload["snapshot_check"]["updated"] = updated
    if updated > 0:
        raise RuntimeError(f"Snapshots er utdaterte ({updated} avvik). Kjør: norscode update-snapshots")
    payload["snapshot_check"]["ok"] = True
    if not json_output:
        print("OK")

    if not json_output:
        print(f"[2/{total_steps}] Selfhost parity fixture check")
    started = time.perf_counter()
    fixture_suite = parity_suite if parity_suite in {"m1", "m2"} else "all"
    fixture_check = update_selfhost_parser_fixtures(check_only=True, suite=fixture_suite)
    payload["timings_ms"]["parser_fixture_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["parser_fixture_check"] = round(payload["timings_ms"]["parser_fixture_check"] / 1000.0, 3)
    payload["parser_fixture_check"]["ok"] = fixture_check["updated"] == 0
    payload["parser_fixture_check"]["updated"] = int(fixture_check["updated"])
    payload["parser_fixture_check"]["cases"] = int(fixture_check["cases"])
    payload["parser_fixture_check"]["suite"] = str(fixture_check["suite"])
    if fixture_check["updated"] > 0:
        raise RuntimeError(
            f"Selfhost parity-fixtures er utdaterte ({fixture_check['updated']} avvik). "
            f"Kjør: norscode update-selfhost-parity-fixtures --suite {fixture_suite}"
        )
    if not json_output:
        print(
            f"OK ({payload['parser_fixture_check']['cases']} cases, "
            f"suite={payload['parser_fixture_check']['suite']})"
        )

    if not json_output:
        print(f"[3/{total_steps}] Engine parity check")
    started = time.perf_counter()
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
    payload["timings_ms"]["parity_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["parity_check"] = round(payload["timings_ms"]["parity_check"] / 1000.0, 3)
    payload["parity_check"]["ok"] = True
    if not json_output:
        print("OK")

    if parity_suite in {"m1", "all"}:
        if not json_output:
            print(f"[4/{total_steps}] Selfhost parser parity (M1)")
        started = time.perf_counter()
        parser_core_m1_result = run_selfhost_parser_core_checks(
            SELFHOST_PARSER_M1_FIXTURE, "Selfhost parser parity (M1)"
        )
        payload["timings_ms"]["parser_core_m1_check"] = int((time.perf_counter() - started) * 1000)
        payload["timings_s"]["parser_core_m1_check"] = round(
            payload["timings_ms"]["parser_core_m1_check"] / 1000.0, 3
        )
        payload["parser_core_m1_check"]["ok"] = parser_core_m1_result["success"]
        payload["parser_core_m1_check"]["case_count"] = int(parser_core_m1_result.get("case_count", 0) or 0)
        payload["parser_core_m1_check"]["error_cases"] = int(parser_core_m1_result.get("error_cases", 0) or 0)
        if not parser_core_m1_result["success"]:
            raise RuntimeError(
                "Selfhost parser parity-feil (M1):\n"
                + (parser_core_m1_result.get("stderr", "").rstrip() or "ukjent feil")
            )
        if not json_output:
            print(
                f"OK ({payload['parser_core_m1_check']['case_count']} cases, "
                f"{payload['parser_core_m1_check']['error_cases']} feil-cases)"
            )
    else:
        payload["parser_core_m1_check"]["ok"] = True
        payload["parser_core_m1_check"]["case_count"] = 0
        payload["parser_core_m1_check"]["error_cases"] = 0

    if parity_suite in {"m2", "all"}:
        if not json_output:
            m2_step = 5 if parity_suite == "all" else 4
            print(f"[{m2_step}/{total_steps}] Selfhost parser parity (M2)")
        started = time.perf_counter()
        parser_core_m2_result = run_selfhost_parser_core_checks(
            SELFHOST_PARSER_M2_FIXTURE, "Selfhost parser parity (M2)"
        )
        payload["timings_ms"]["parser_core_m2_check"] = int((time.perf_counter() - started) * 1000)
        payload["timings_s"]["parser_core_m2_check"] = round(
            payload["timings_ms"]["parser_core_m2_check"] / 1000.0, 3
        )
        payload["parser_core_m2_check"]["ok"] = parser_core_m2_result["success"]
        payload["parser_core_m2_check"]["case_count"] = int(parser_core_m2_result.get("case_count", 0) or 0)
        payload["parser_core_m2_check"]["error_cases"] = int(parser_core_m2_result.get("error_cases", 0) or 0)
        if not parser_core_m2_result["success"]:
            raise RuntimeError(
                "Selfhost parser parity-feil (M2):\n"
                + (parser_core_m2_result.get("stderr", "").rstrip() or "ukjent feil")
            )
        if not json_output:
            print(
                f"OK ({payload['parser_core_m2_check']['case_count']} cases, "
                f"{payload['parser_core_m2_check']['error_cases']} feil-cases)"
            )
    else:
        payload["parser_core_m2_check"]["ok"] = True
        payload["parser_core_m2_check"]["case_count"] = 0
        payload["parser_core_m2_check"]["error_cases"] = 0

    if parity_suite == "all":
        if not json_output:
            print(f"[6/{total_steps}] Selfhost parser parity (utvidet)")
        started = time.perf_counter()
        parser_core_extended_result = run_selfhost_parser_core_checks(
            SELFHOST_PARSER_EXTENDED_FIXTURE, "Selfhost parser parity (utvidet)"
        )
        payload["timings_ms"]["parser_core_extended_check"] = int((time.perf_counter() - started) * 1000)
        payload["timings_s"]["parser_core_extended_check"] = round(
            payload["timings_ms"]["parser_core_extended_check"] / 1000.0, 3
        )
        payload["parser_core_extended_check"]["ok"] = parser_core_extended_result["success"]
        payload["parser_core_extended_check"]["case_count"] = int(
            parser_core_extended_result.get("case_count", 0) or 0
        )
        payload["parser_core_extended_check"]["error_cases"] = int(
            parser_core_extended_result.get("error_cases", 0) or 0
        )
        if not parser_core_extended_result["success"]:
            raise RuntimeError(
                "Selfhost parser parity-feil (utvidet):\n"
                + (parser_core_extended_result.get("stderr", "").rstrip() or "ukjent feil")
            )
        if not json_output:
            print(
                f"OK ({payload['parser_core_extended_check']['case_count']} cases, "
                f"{payload['parser_core_extended_check']['error_cases']} feil-cases)"
            )
    else:
        payload["parser_core_extended_check"]["ok"] = True
        payload["parser_core_extended_check"]["case_count"] = 0
        payload["parser_core_extended_check"]["error_cases"] = 0

    consistency_step = 7 if parity_suite == "all" else 5
    if not json_output:
        print(f"[{consistency_step}/{total_steps}] Parser suite consistency")
    started = time.perf_counter()
    if parity_suite == "m1":
        consistency = run_selfhost_parser_suite_consistency_check(
            SELFHOST_PARSER_M1_FIXTURE,
            SELFHOST_PARSER_EXTENDED_FIXTURE,
        )
    elif parity_suite == "m2":
        consistency = run_selfhost_parser_suite_subset_consistency_check(
            SELFHOST_PARSER_M2_FIXTURE,
            SELFHOST_PARSER_EXTENDED_FIXTURE,
            "m2",
        )
    else:
        consistency = run_selfhost_parser_suite_all_consistency_check(
            SELFHOST_PARSER_M1_FIXTURE,
            SELFHOST_PARSER_M2_FIXTURE,
            SELFHOST_PARSER_EXTENDED_FIXTURE,
        )
    payload["timings_ms"]["parser_suite_consistency_check"] = int((time.perf_counter() - started) * 1000)
    payload["timings_s"]["parser_suite_consistency_check"] = round(
        payload["timings_ms"]["parser_suite_consistency_check"] / 1000.0, 3
    )
    payload["parser_suite_consistency_check"]["ok"] = bool(consistency.get("success"))
    payload["parser_suite_consistency_check"]["checked_cases"] = int(consistency.get("checked_cases", 0) or 0)
    payload["parser_suite_consistency_check"]["mismatch_count"] = int(consistency.get("mismatch_count", 0) or 0)
    if not consistency.get("success"):
        raise RuntimeError(
            "Parser suite consistency-feil:\n"
            + (consistency.get("stderr", "").rstrip() or "ukjent feil")
        )
    if not json_output:
        print(f"OK ({payload['parser_suite_consistency_check']['checked_cases']} cases)")

    post_consistency_offset = 0
    if run_m2_sync_check:
        post_consistency_offset += _run_ci_selfhost_m2_sync_check(
            payload=payload,
            total_steps=total_steps,
            json_output=json_output,
            consistency_step=consistency_step,
        )

    progress_step = consistency_step + 1 + post_consistency_offset
    if require_selfhost_ready:
        _run_ci_selfhost_progress_check(
            payload=payload,
            total_steps=total_steps,
            json_output=json_output,
            progress_step=progress_step,
        )

    test_step = progress_step + (1 if require_selfhost_ready else 0)
    _run_ci_test_check(
        payload=payload,
        total_steps=total_steps,
        json_output=json_output,
        test_step=test_step,
    )

    workflow_step = test_step + 1
    _run_ci_workflow_action_check(
        payload=payload,
        total_steps=total_steps,
        json_output=json_output,
        workflow_step=workflow_step,
    )

    if check_names:
        name_step = workflow_step + 1
        _run_ci_name_migration_check(
            payload=payload,
            total_steps=total_steps,
            json_output=json_output,
            name_step=name_step,
        )

    payload["timings_ms"]["total"] = int((time.perf_counter() - pipeline_started) * 1000)
    step_keys = [k for k in payload["timings_ms"].keys() if k not in ("total", "wallclock_total")]
    payload["timings_ms"]["step_sum"] = sum(
        payload["timings_ms"][k] for k in step_keys if isinstance(payload["timings_ms"].get(k), int)
    )
    payload["timings_ms"]["overhead"] = payload["timings_ms"]["total"] - payload["timings_ms"]["step_sum"]
    payload["timings_s"]["total"] = round(payload["timings_ms"]["total"] / 1000.0, 3)
    payload["timings_s"]["step_sum"] = round(payload["timings_ms"]["step_sum"] / 1000.0, 3)
    payload["timings_s"]["overhead"] = round(payload["timings_ms"]["overhead"] / 1000.0, 3)
    total_ms = payload["timings_ms"]["total"]
    if total_ms > 0:
        payload["timings_ratio"]["step_coverage"] = round(payload["timings_ms"]["step_sum"] / total_ms, 4)
        payload["timings_ratio"]["overhead_share"] = round(payload["timings_ms"]["overhead"] / total_ms, 4)
        payload["timings_ratio"]["step_coverage_pct"] = round(payload["timings_ratio"]["step_coverage"] * 100.0, 2)
        payload["timings_ratio"]["overhead_share_pct"] = round(payload["timings_ratio"]["overhead_share"] * 100.0, 2)
    else:
        payload["timings_ratio"]["step_coverage"] = 0.0
        payload["timings_ratio"]["overhead_share"] = 0.0
        payload["timings_ratio"]["step_coverage_pct"] = 0.0
        payload["timings_ratio"]["overhead_share_pct"] = 0.0
    payload["timings_ratio"]["ratio_sum"] = round(
        payload["timings_ratio"]["step_coverage"] + payload["timings_ratio"]["overhead_share"], 4
    )
    payload["timings_ratio"]["ratio_delta"] = round(abs(1.0 - payload["timings_ratio"]["ratio_sum"]), 6)
    payload["timings_ratio"]["percent_sum"] = round(
        payload["timings_ratio"]["step_coverage_pct"] + payload["timings_ratio"]["overhead_share_pct"], 2
    )
    payload["timings_ratio"]["percent_delta"] = round(abs(100.0 - payload["timings_ratio"]["percent_sum"]), 4)
    payload["timings_ratio"]["overhead_policy"] = {
        "low_max": 0.02,
        "medium_max": 0.05,
        "unit": "share",
    }
    overhead_share = payload["timings_ratio"]["overhead_share"]
    if overhead_share <= payload["timings_ratio"]["overhead_policy"]["low_max"]:
        payload["timings_ratio"]["overhead_level"] = "low"
    elif overhead_share <= payload["timings_ratio"]["overhead_policy"]["medium_max"]:
        payload["timings_ratio"]["overhead_level"] = "medium"
    else:
        payload["timings_ratio"]["overhead_level"] = "high"
    payload["timings_ratio"]["overhead_within_medium"] = (
        overhead_share <= payload["timings_ratio"]["overhead_policy"]["medium_max"]
    )
    payload["finished_at_utc"] = dt.datetime.now(dt.UTC).isoformat()
    payload["finished_at_epoch_ms"] = int(time.time() * 1000)
    payload["timings_ms"]["wallclock_total"] = payload["finished_at_epoch_ms"] - payload["started_at_epoch_ms"]
    payload["timings_s"]["wallclock_total"] = round(payload["timings_ms"]["wallclock_total"] / 1000.0, 3)
    payload["ok"] = True
    return payload


def main():
    runtime_note = "Standard (anbefalt): bruk den prebygde binæren via `norscode` eller `bin/nc`."
    mode_note = (
        "Standardmodi: `run` og `test` er binær-først, "
        "`build` er bytecode-først, `check` kombinerer semantikk og binær validering."
    )
    project_note = (
        "Prosjektkommandoer som `lock`, `add`, `update` og `registry-*` er fortsatt tilgjengelige "
        "i toppnivå-CLI-en mens den binær-først migreringen fortsetter."
    )
    legacy_note = "Legacy-fallback: `python3 -m norscode` er fortsatt tilgjengelig ved behov."
    parser = argparse.ArgumentParser(
        prog="norscode",
        description="NorCode CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"{runtime_note}\n"
            f"{mode_note}\n"
            f"{project_note}\n"
            f"{legacy_note}\n\n"
            "Kommandolinjeopplevelsen under er binær-først, med tilbakefall i legacy-sporet ved behov."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version="NorCode CLI 0.1.0 (binær-først anbefalt)",
    )
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="Kjør en .no-fil via prebygd runtime-binær (standard)")
    run.add_argument("file")
    run.add_argument("--runtime-binary", help="Valgfri sti til prebygd runtime-binær")
    run.add_argument("--keep-bytecode", action="store_true", help="Behold generert bytecode-fil")
    run.add_argument("--output", help="Valgfri utdata-fil for bytecode ved --keep-bytecode")

    check = sub.add_parser("check", help="Parser og valider en .no-fil med semantikk + prebygd runtime-binær")
    check.add_argument("file")
    check.add_argument("--runtime-binary", help="Valgfri sti til prebygd runtime-binær")

    build = sub.add_parser("build", help="Bygg .no til bytecode som standard")
    build.add_argument("file")
    build.add_argument("--output", help="Valgfri utdata-fil for bytecode")

    bytecode_build = sub.add_parser(
        "bytecode-build",
        help="Utviklerkommando: bygg .no-fil til .ncb.json bytecode",
    )
    bytecode_build.add_argument("file", help="Kildefil (.no)")
    bytecode_build.add_argument("--output", help="Valgfri utdata-fil for bytecode")

    add = sub.add_parser("add", help="Legg til pakkeavhengighet i norscode.toml")
    add.add_argument("package", nargs="?", help="Pakkenavn eller pakkesti")
    add.add_argument("path", nargs="?", help="Valgfri pakkesti (hvis package er navn)")
    add.add_argument("--name", help="Overstyr dependency-navn")
    add.add_argument("--list", action="store_true", help="Vis tilgjengelige pakker i registeret")
    add.add_argument("--git", help="Direkte Git-kilde (f.eks. https://github.com/org/repo.git)")
    add.add_argument("--ref", help="Git ref (tag/branch/commit) brukt sammen med --git")
    add.add_argument("--url", help="Direkte URL-kilde (f.eks. tarball/zip)")
    add.add_argument("--fetch", action="store_true", help="Last ned/cach ekstern Git/URL-kilde til lokal mappe")
    add.add_argument("--refresh", action="store_true", help="Tving ny nedlasting ved --fetch")
    add.add_argument("--pin", action="store_true", help="Krev låst versjon/ref for ekstern kilde")
    add.add_argument("--sha256", help="Forventet SHA256 for URL-arkiv ved --fetch")
    add.add_argument("--allow-untrusted", action="store_true", help="Overstyr policy for tillatte verter for denne kommandoen")
    add.add_argument(
        "--legacy-python",
        action="store_true",
        help="Bruk eksplisitt Python-tilbakefall i stedet for binærsporet for add",
    )
    add.add_argument(
        "--native-runtime",
        action="store_true",
        help="Valgfritt kompatibilitetsflagg: add bruker binærsporet i enkle standardflyter",
    )
    add.add_argument(
        "--runtime-binary",
        help="Valgfri eksplisitt sti til runtime-binær for add i de enkle standardflytene",
    )

    debug = sub.add_parser("debug", help="Prosjektkommando: vis debug-info (tokens/AST/symboler) for en .no-fil")
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
    ir_disasm.add_argument(
        "--engine",
        choices=["python", "selfhost"],
        default="selfhost",
        help="Velg disasm-motor (selfhost er standard; python er fallback/parity)",
    )
    ir_disasm.add_argument("--diff", action="store_true", help="Sammenlign python og selfhost disasm")
    ir_disasm.add_argument("--fail-on-warning", action="store_true", help="Feil hvis strict-resultat avviker mellom motorene")
    ir_disasm.add_argument("--save-diff", help="Lagre diff-output til fil ved --diff")

    update_snapshots = sub.add_parser("update-snapshots", help="Regenerer IR snapshot-forventninger")
    update_snapshots.add_argument("--check", action="store_true", help="Feil hvis snapshots er utdaterte (skriv ikke)")
    update_snapshots.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    update_selfhost_parity = sub.add_parser(
        "update-selfhost-parity-fixtures",
        help="Regenerer selfhost parser parity-forventninger",
    )
    update_selfhost_parity.add_argument("--suite", choices=["m1", "m2", "extended", "all"], default="all", help="Velg fixtures å oppdatere")
    update_selfhost_parity.add_argument("--check", action="store_true", help="Feil hvis parity-fixtures er utdaterte (skriv ikke)")
    update_selfhost_parity.add_argument("--no-sync-m2", action="store_true", help="Hopp over automatisk M2-sync (core minus M1)")
    update_selfhost_parity.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    sync_selfhost_parity_m2 = sub.add_parser(
        "sync-selfhost-parity-m2",
        help="Synkroniser M2-fixture som core minus M1",
    )
    sync_selfhost_parity_m2.add_argument("--check", action="store_true", help="Feil hvis M2-fixture er ute av synk")
    sync_selfhost_parity_m2.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    ci = sub.add_parser("ci", help="Prosjektkommando: kjør lokal CI-sekvens (snapshot, parity, test)")
    ci.add_argument("--json", action="store_true", help="Skriv CI-resultat som JSON")
    ci.add_argument("--check-names", action="store_true", help="Inkluder sjekk for navnemigrering (legacy -> NorCode)")
    ci.add_argument("--parity-suite", choices=["m1", "m2", "all"], default="all", help="Velg parity-scope i CI")
    ci.add_argument(
        "--snapshot-check",
        action="store_true",
        help="Bruk første binære CI-check-runner for IR snapshot-fixture",
    )
    ci.add_argument(
        "--parser-fixture-check",
        action="store_true",
        help="Bruk binær CI-check-runner for selfhost parity-fixturefiler",
    )
    ci.add_argument(
        "--parity-check",
        action="store_true",
        help="Bruk binær CI-check-runner for parity-prøvefilen tests/ir_sample.nlir",
    )
    ci.add_argument(
        "--selfhost-m2-sync-check",
        action="store_true",
        help="Bruk binær CI-check-runner for M1/M2/core fixturegrunnlag til selfhost M2-sync",
    )
    ci.add_argument(
        "--selfhost-progress-check",
        action="store_true",
        help="Bruk binær CI-check-runner for første selfhost progress-baseline",
    )
    ci.add_argument(
        "--test-check",
        action="store_true",
        help="Bruk binær CI-check-runner for testgrunnlaget i tests/",
    )
    ci.add_argument(
        "--workflow-action-check",
        action="store_true",
        help="Bruk binær CI-check-runner for workflow-grunnlaget i .github/workflows",
    )
    ci.add_argument(
        "--name-migration-check",
        action="store_true",
        help="Bruk binær CI-check-runner for legacy navn/migreringsrester",
    )
    ci.add_argument(
        "--require-selfhost-ready",
        action="store_true",
        help="Feil hvis selfhost parity progress ikke er fullført/ready",
    )
    ci.add_argument(
        "--native-runtime",
        action="store_true",
        help="Bruk binær CI-forhåndsvisning og én binær check-runner om gangen",
    )
    ci.add_argument(
        "--runtime-binary",
        help="Valgfri eksplisitt sti til runtime-binær for ci-preview eller én binær check-runner sammen med --native-runtime",
    )

    selfhost_parity = sub.add_parser("selfhost-parity", help="Kjør selfhost parser parity-suiter")
    selfhost_parity.add_argument("--suite", choices=["m1", "m2", "extended", "all"], default="all", help="Velg parity-suite")
    selfhost_parity.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    selfhost_parity_progress = sub.add_parser(
        "selfhost-parity-progress",
        help="Vis fremdrift for M1/M2 dekning mot utvidet parity-suite",
    )
    selfhost_parity_progress.add_argument("--json", action="store_true", help="Skriv resultat som JSON")
    selfhost_parity_progress.add_argument(
        "--require-ready",
        action="store_true",
        help="Feil hvis progress ikke er ready",
    )
    selfhost_parity_progress.add_argument(
        "--min-coverage",
        type=float,
        help="Krev minimum total dekningsprosent (0-100)",
    )

    selfhost_parity_consistency = sub.add_parser(
        "selfhost-parity-consistency",
        help="Sjekk consistency mellom parity-suiter og utvidet suite",
    )
    selfhost_parity_consistency.add_argument(
        "--scope",
        choices=["m1", "m2", "all"],
        default="m1",
        help="Velg hvilke consistency-sjekker som kjøres",
    )
    selfhost_parity_consistency.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    lock = sub.add_parser("lock", help="Prosjektkommando: generer dependency lockfile (norscode.lock)")
    lock.add_argument("--check", action="store_true", help="Feil hvis lockfile er manglende/utdatert")
    lock.add_argument("--verify", action="store_true", help="Verifiser path-digests i eksisterende lockfile")
    lock.add_argument("--json", action="store_true", help="Skriv lock-resultat som JSON")
    lock.add_argument(
        "--legacy-python",
        action="store_true",
        help="Bruk eksplisitt Python-tilbakefall i stedet for binærsporet for lock",
    )
    lock.add_argument(
        "--native-runtime",
        action="store_true",
        help="Valgfritt kompatibilitetsflagg: lock bruker binærsporet som standard",
    )
    lock.add_argument(
        "--runtime-binary",
        help="Valgfri eksplisitt sti til runtime-binær for lock i standardflytene",
    )

    update = sub.add_parser("update", help="Prosjektkommando: oppdater avhengigheter fra registry")
    update.add_argument("package", nargs="?", help="Valgfri dependency å oppdatere")
    update.add_argument("--check", action="store_true", help="Feil hvis en dependency ville blitt oppdatert")
    update.add_argument("--json", action="store_true", help="Skriv update-resultat som JSON")
    update.add_argument("--pin", action="store_true", help="Krev låst ref for registry git-kilder")
    update.add_argument("--fetch", action="store_true", help="Materialiser registry git- og url-kilder til lokalt lager")
    update.add_argument("--refresh", action="store_true", help="Tving ny nedlasting ved --fetch")
    update.add_argument("--lock", action="store_true", help="Regenerer lockfile etter oppdatering")
    update.add_argument("--allow-untrusted", action="store_true", help="Overstyr policy for tillatte verter for denne kommandoen")
    update.add_argument(
        "--legacy-python",
        action="store_true",
        help="Bruk eksplisitt Python-tilbakefall i stedet for binærsporet for update",
    )
    update.add_argument(
        "--native-runtime",
        action="store_true",
        help="Valgfritt kompatibilitetsflagg: update bruker binærsporet i enkle standardflyter",
    )
    update.add_argument(
        "--runtime-binary",
        help="Valgfri eksplisitt sti til runtime-binær for update i de enkle standardflytene",
    )

    registry_sign_cmd = sub.add_parser(
        "registry-sign",
        help="Prosjektkommando: beregn og pinn SHA256 for packages/registry.toml",
    )
    registry_sign_cmd.add_argument("--write-config", action="store_true", help="Skriv hash til feltet [security].trusted_registry_sha256")
    registry_sign_cmd.add_argument(
        "--write-digest",
        action="store_true",
        help="Skriv digest-sidevogn til packages/registry.toml.sha256",
    )
    registry_sign_cmd.add_argument("--json", action="store_true", help="Skriv resultat som JSON-form")
    registry_sign_cmd.add_argument(
        "--legacy-python",
        action="store_true",
        help="Utgått flagg: registersignering bruker nå binærsporet",
    )
    registry_sign_cmd.add_argument(
        "--native-runtime",
        action="store_true",
        help="Valgfritt kompatibilitetsflagg: registersignering bruker allerede binærsporet som standard",
    )
    registry_sign_cmd.add_argument(
        "--runtime-binary",
        help="Valgfri eksplisitt sti til runtime-binær for registersignering, som allerede bruker binærsporet som standard",
    )

    registry_sync_cmd = sub.add_parser(
        "registry-sync",
        help="Prosjektkommando: synkroniser ekstern registerindeks til lokalt lager",
    )
    registry_sync_cmd.add_argument("--source", help="Overstyr registerkilde for denne kjøringen")
    registry_sync_cmd.add_argument("--allow-untrusted", action="store_true", help="Overstyr policy for tillatte verter for denne kommandoen")
    registry_sync_cmd.add_argument("--require-all", action="store_true", help="Feil hvis en eneste kilde feiler")
    registry_sync_cmd.add_argument("--no-fallback", action="store_true", help="Ikke bruk eksisterende lager ved kildefeil")
    registry_sync_cmd.add_argument("--json", action="store_true", help="Skriv resultat som JSON-form")
    registry_sync_cmd.add_argument(
        "--legacy-python",
        action="store_true",
        help="Bruk eksplisitt Python-tilbakefall i stedet for binærsporet for registersynk",
    )
    registry_sync_cmd.add_argument(
        "--native-runtime",
        action="store_true",
        help="Valgfritt kompatibilitetsflagg: registersynk bruker binærsporet i de enkle standardflytene",
    )
    registry_sync_cmd.add_argument(
        "--runtime-binary",
        help="Valgfri eksplisitt sti til runtime-binær for registersynk i de enkle standardflytene",
    )

    registry_mirror_cmd = sub.add_parser(
        "registry-mirror",
        help="Prosjektkommando: bygg distribuerbar registerspeilfil fra lokale og eksterne oppføringer",
    )
    registry_mirror_cmd.add_argument("--output", help="Utdata-fil for registerspeiling (standard: build/registerspeiling.json)")
    registry_mirror_cmd.add_argument(
        "--write-default",
        action="store_true",
        help="Skriv speilutdata til standard build/registerspeiling.json",
    )
    registry_mirror_cmd.add_argument("--json", action="store_true", help="Skriv resultat som JSON-form")
    registry_mirror_cmd.add_argument(
        "--legacy-python",
        action="store_true",
        help="Utgått flagg: registerspeiling bruker nå binærsporet",
    )
    registry_mirror_cmd.add_argument(
        "--native-runtime",
        action="store_true",
        help="Valgfritt kompatibilitetsflagg: registerspeiling bruker allerede binærsporet som standard",
    )
    registry_mirror_cmd.add_argument(
        "--runtime-binary",
        help="Valgfri eksplisitt sti til runtime-binær for registerspeiling, som allerede bruker binærsporet som standard",
    )

    migrate_names_cmd = sub.add_parser(
        "migrate-names",
        help="Prosjektkommando: migrer legacynavn (norsklang*) til NorCode-navn",
    )
    migrate_names_cmd.add_argument("--apply", action="store_true", help="Utfør migrering (standard er tørrkjøring)")
    migrate_names_cmd.add_argument("--cleanup", action="store_true", help="Fjern legacyfiler etter vellykket migrering")
    migrate_names_cmd.add_argument("--check", action="store_true", help="Feil hvis migrering eller opprydding fortsatt gjenstår")
    migrate_names_cmd.add_argument("--json", action="store_true", help="Skriv resultat som JSON")

    release = sub.add_parser("release", help="Prosjektkommando: forbered release (versjonsbump + changelog)")
    release.add_argument("--bump", choices=["major", "minor", "patch"], default="patch", help="Type semver-bump")
    release.add_argument("--version", help="Sett eksakt versjon (overstyrer --bump)")
    release.add_argument("--date", help="Release-dato (YYYY-MM-DD)")
    release.add_argument("--dry-run", action="store_true", help="Vis endringer uten å skrive filer")
    release.add_argument("--json", action="store_true", help="Skriv release-resultat som JSON")

    test = sub.add_parser("test", help="Kjør tester via prebygd runtime-binær som standard")
    test.add_argument("file", nargs="?", help="Valgfri testfil eller testmappe")
    test.add_argument("--verbose", action="store_true", help="Vis output også for tester som består")
    test.add_argument("--json", action="store_true", help="Skriv testresultat som JSON")
    test.add_argument("--runtime-binary", help="Valgfri sti til prebygd runtime-binær")

    args = parser.parse_args()

    try:
        if args.cmd == "run":
            source_path, bytecode_path, _runtime_source_path, runtime_path = run_native_source(
                "run",
                args.file,
                runtime_binary=args.runtime_binary,
                keep_bytecode=args.keep_bytecode,
                output=args.output,
            )
            print(f"Kilde: {source_path}")
            if bytecode_path is not None:
                print(f"Bytecode-fil: {bytecode_path}")
            print(f"Runtime-binær: {runtime_path}")

        elif args.cmd == "check":
            source_path, _program, alias_map, analyzer = check_program(args.file)
            print(f"Kilde: {source_path}")
            print(f"Aliaser: {alias_map}")
            print("Semantikk: OK")
            print(f"Funksjoner: {list(analyzer.functions.keys())}")
            _native_source_path, bytecode_path, _runtime_source_path, runtime_path = run_native_source(
                "check",
                args.file,
                runtime_binary=args.runtime_binary,
            )
            if bytecode_path is not None:
                print(f"Bytecode-fil: {bytecode_path}")
            print(f"Runtime-binær: {runtime_path}")
            print("Native runtime: OK")

        elif args.cmd == "build":
            out_path = build_bytecode_file(args.file, output=args.output)
            print(f"Bytecode-fil: {out_path}")

        elif args.cmd == "bytecode-build":
            out_path = build_bytecode_file(args.file, output=args.output)
            print(f"Bytecode-fil: {out_path}")

        elif args.cmd == "add":
            if args.native_runtime and args.legacy_python:
                raise RuntimeError("add støtter ikke --native-runtime og --legacy-python samtidig")
            if args.runtime_binary and args.legacy_python:
                raise RuntimeError("add støtter ikke --runtime-binary sammen med --legacy-python")
            if args.list and (
                args.package
                or args.path
                or args.git
                or args.url
                or args.name
                or args.ref
                or args.fetch
                or args.refresh
                or args.pin
                or args.sha256
                or args.allow_untrusted
            ):
                raise RuntimeError("add støtter ikke mål- eller hente-flagg sammen med --list")
            if args.name and not (args.package or args.git or args.url):
                raise RuntimeError("add støtter bare --name sammen med et eksplisitt mål")
            if args.git and isinstance(args.package, str) and (
                args.package.startswith("git+") or args.package.startswith("url+")
            ):
                raise RuntimeError("add støtter ikke direkte git+...- eller url+...-mål sammen med --git")
            if args.url and isinstance(args.package, str) and (
                args.package.startswith("git+") or args.package.startswith("url+")
            ):
                raise RuntimeError("add støtter ikke direkte git+...- eller url+...-mål sammen med --url")
            if (
                args.ref
                and isinstance(args.package, str)
                and args.package.startswith("git+")
                and "@" in args.package
            ):
                raise RuntimeError("add støtter ikke --ref sammen med direkte git+...-mål som allerede inneholder @ref")
            if args.ref and (args.url or (isinstance(args.package, str) and args.package.startswith("url+"))):
                raise RuntimeError("add støtter ikke --ref sammen med --url eller direkte url+...-mål")
            if args.path and args.fetch:
                raise RuntimeError("add støtter ikke --fetch sammen med posisjonell sti")
            if args.path and args.refresh:
                raise RuntimeError("add støtter ikke --refresh sammen med posisjonell sti")
            if args.path and args.allow_untrusted:
                raise RuntimeError("add støtter ikke --allow-untrusted sammen med posisjonell sti")
            if args.path and args.sha256:
                raise RuntimeError("add støtter ikke --sha256 sammen med posisjonell sti")
            if args.path and args.pin:
                raise RuntimeError("add støtter ikke --pin sammen med posisjonell sti")
            if args.path and args.ref:
                raise RuntimeError("add støtter ikke --ref sammen med posisjonell sti")
            if args.path and isinstance(args.package, str) and (
                args.package.startswith("git+") or args.package.startswith("url+")
            ):
                raise RuntimeError("add støtter ikke posisjonell sti sammen med direkte git+...- eller url+...-mål")
            if args.git and args.url:
                raise RuntimeError("add støtter ikke --git og --url samtidig")
            if args.path and (args.git or args.url):
                raise RuntimeError("add støtter ikke posisjonell sti sammen med --git eller --url")
            if args.fetch and not (
                args.git
                or args.url
                or (isinstance(args.package, str) and (args.package.startswith("git+") or args.package.startswith("url+")))
            ):
                raise RuntimeError("add støtter bare --fetch sammen med git+... eller url+...-mål")
            if args.pin and not (
                args.git
                or args.url
                or (isinstance(args.package, str) and (args.package.startswith("git+") or args.package.startswith("url+")))
            ):
                raise RuntimeError("add støtter bare --pin sammen med git+... eller url+...-mål")
            if args.pin and not args.fetch:
                raise RuntimeError("add støtter bare --pin sammen med --fetch")
            if args.ref and not (args.git or (isinstance(args.package, str) and args.package.startswith("git+"))):
                raise RuntimeError("add støtter bare --ref sammen med --git eller direkte git+...-mål")
            if args.sha256 and not (args.url or (isinstance(args.package, str) and args.package.startswith("url+"))):
                raise RuntimeError("add støtter bare --sha256 sammen med --url eller direkte url+...-mål")
            if args.sha256 and not args.fetch:
                raise RuntimeError("add støtter bare --sha256 sammen med --fetch")
            if args.refresh and not args.fetch:
                raise RuntimeError("add støtter bare --refresh sammen med --fetch")
            if args.allow_untrusted and not args.fetch:
                raise RuntimeError("add støtter bare --allow-untrusted sammen med --fetch")
            native_add_package = args.package
            if args.git:
                native_add_package = f"git+{args.git}"
            if args.url:
                native_add_package = f"url+{args.url}"
            add_target_kind = "none"
            if args.path:
                add_target_kind = "path"
            elif native_add_package and native_add_package.startswith("git+"):
                add_target_kind = "git"
            elif native_add_package and native_add_package.startswith("url+"):
                add_target_kind = "url"
            elif native_add_package:
                add_target_kind = "package"
            fetch_profile = "none"
            if args.fetch:
                fetch_profile = "refresh" if args.refresh else "fetch"
            trust_profile = "default" if not args.allow_untrusted else "allow-untrusted"
            pin_profile = "pinned" if args.pin else "floating"
            ref_profile = "explicit-ref" if args.ref else "default-ref"
            checksum_profile = "explicit-sha256" if args.sha256 else "no-sha256"
            name_profile = "explicit-name" if args.name else "derived-name"
            active_flags: list[str] = []
            if args.fetch:
                active_flags.append("fetch")
            if args.refresh:
                active_flags.append("refresh")
            if args.allow_untrusted:
                active_flags.append("allow-untrusted")
            if args.pin:
                active_flags.append("pin")
            if args.ref:
                active_flags.append("ref")
            if args.sha256:
                active_flags.append("sha256")
            if args.name:
                active_flags.append("name")
            if args.check:
                active_flags.append("check")
            target_source = (
                "git"
                if args.git
                else ("url" if args.url else ("path" if args.path else ("package" if args.package else "none")))
            )
            target_input_mode = (
                "flag-git"
                if args.git
                else (
                    "flag-url"
                    if args.url
                    else (
                        "direct-git"
                        if (isinstance(args.package, str) and args.package.startswith("git+"))
                        else (
                            "direct-url"
                            if (isinstance(args.package, str) and args.package.startswith("url+"))
                            else (
                                "path"
                                if args.path
                                else ("package" if args.package else "none")
                            )
                        )
                    )
                )
            )
            path_mode = "positional-path" if args.path else "no-path"
            runtime_profile = "explicit-runtime" if args.runtime_binary else "default-runtime"
            runtime_selection = "forced-native" if args.native_runtime else "default-native"
            preview_mode = not bool(native_add_package or args.path)
            add_action = "preview" if preview_mode else "add-target"
            add_scope = (
                "preview"
                if preview_mode
                else ("local" if add_target_kind == "path" else ("remote" if add_target_kind in {"git", "url"} else "package"))
            )
            local_add = bool(add_target_kind == "path")
            package_add = bool(add_target_kind == "package")
            remote_add = bool(add_target_kind in {"git", "url"})
            remote_fetch = bool(args.fetch and add_target_kind in {"git", "url"})
            check_mode = "check" if args.check else "write"
            use_native_add = (
                not args.legacy_python
                and (
                    args.native_runtime
                    or (
                        not args.list
                        and bool(native_add_package)
                    )
                )
            )
            if use_native_add:
                if args.list:
                    raise RuntimeError(
                        "add i binærsporet støtter foreløpig direkte sti, git+ og url-input samt --git og --url, men ikke --list-visning"
                    )
                if (
                    args.pin
                    and native_add_package
                    and native_add_package.startswith("git+")
                    and not args.ref
                    and "@" not in native_add_package
                ):
                    raise RuntimeError("--pin krever --ref for direkte git+... eller --git i add i binærsporet")
                runtime_path, result = run_native_add_command_captured(
                    name=args.name,
                    package=native_add_package,
                    path=args.path,
                    ref=args.ref,
                    pin=args.pin,
                    fetch=args.fetch,
                    refresh=args.refresh,
                    sha256=args.sha256,
                    allow_untrusted=args.allow_untrusted,
                    runtime_binary=args.runtime_binary,
                )
                parsed_stdout = _parse_native_add_stdout(result.stdout)
                if args.json:
                    payload = {
                        "native_runtime": True,
                        "runtime_binary": str(runtime_path),
                        "requested_runtime_binary": args.runtime_binary,
                        "target": native_add_package or args.path or "all",
                        "target_kind": add_target_kind,
                        "target_source": target_source,
                        "target_input_mode": target_input_mode,
                        "path_mode": path_mode,
                        "add_action": add_action,
                        "add_scope": add_scope,
                        "local_add": local_add,
                        "package_add": package_add,
                        "remote_add": remote_add,
                        "remote_fetch": remote_fetch,
                        "check": args.check,
                        "check_mode": check_mode,
                        "active_flags": active_flags,
                        "name": args.name,
                        "path": args.path,
                        "package": native_add_package,
                        "git": args.git,
                        "url": args.url,
                        "ref": args.ref,
                        "sha256": args.sha256,
                        "fetch": args.fetch,
                        "fetch_mode": bool(args.fetch),
                        "refresh": args.refresh,
                        "pin": args.pin,
                        "allow_untrusted": args.allow_untrusted,
                        "fetch_profile": fetch_profile,
                        "trust_profile": trust_profile,
                        "pin_profile": pin_profile,
                        "ref_profile": ref_profile,
                        "checksum_profile": checksum_profile,
                        "name_profile": name_profile,
                        "runtime_profile": runtime_profile,
                        "runtime_selection": runtime_selection,
                        "preview": preview_mode,
                        "ok": result.returncode == 0,
                        "result": parsed_stdout,
                        "stderr": result.stderr,
                    }
                    if isinstance(parsed_stdout, dict):
                        if "registry" in parsed_stdout:
                            payload["registry"] = parsed_stdout["registry"]
                        if "sha256" in parsed_stdout:
                            payload["sha256"] = parsed_stdout["sha256"]
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Kjøretid: {runtime_path}")
                    print("Handling: add")
                    print(f"Måltype: {add_target_kind}")
                    print(f"Målkilde: {target_source}")
                    print(f"Målinngang: {target_input_mode}")
                    print(f"Stimodus: {path_mode}")
                    print(f"Handlingstype: {add_action}")
                    print(f"Omfang: {add_scope}")
                    print(f"Lokal add: {local_add}")
                    print(f"Pakke-add: {package_add}")
                    print(f"Remote add: {remote_add}")
                    print(f"Ekstern henting: {remote_fetch}")
                    print(f"Sjekk: {args.check}")
                    print(f"Sjekkmodus: {check_mode}")
                    print(f"Native runtime: {args.native_runtime}")
                    print(f"Kjøretidsprofil: {runtime_profile}")
                    print(f"Kjøretidsvalg: {runtime_selection}")
                    print(f"Fetch: {args.fetch}")
                    print(f"Oppfrisking: {args.refresh}")
                    print(f"Pin: {args.pin}")
                    print(f"Tillat utrygg: {args.allow_untrusted}")
                    if active_flags:
                        print(f"Aktive flagg: {', '.join(active_flags)}")
                    if args.runtime_binary:
                        print(f"Forespurt kjøretid: {args.runtime_binary}")
                    print(f"Forhåndsvisning: {preview_mode}")
                    print(f"Hentemodus: {bool(args.fetch)}")
                    print(f"Henteprofil: {fetch_profile}")
                    if args.fetch:
                        print("Henting: aktiv")
                    print(f"Tillitprofil: {trust_profile}")
                    print(f"Pinprofil: {pin_profile}")
                    print(f"Refprofil: {ref_profile}")
                    if args.ref:
                        print(f"Ref: {args.ref}")
                    print(f"Checksumprofil: {checksum_profile}")
                    if args.sha256:
                        print(f"SHA256: {args.sha256}")
                    print(f"Navneprofil: {name_profile}")
                    if args.name:
                        print(f"Navn: {args.name}")
                    if args.git:
                        print(f"Git: {args.git}")
                    if args.url:
                        print(f"URL: {args.url}")
                    add_target = native_add_package or args.path
                    if add_target:
                        print(f"Mål: {add_target}")
                    if not args.native_runtime:
                        print("Merk: enkel add bruker nå binærsporet som standard.")
                    if args.fetch or args.refresh or args.sha256 or args.allow_untrusted:
                        print("Merk: add kjører nå også med valgte add-flagg.")
                    elif native_add_package:
                        print("Merk: add kan nå skrive enkle direkte sti-, git+- og url-avhengigheter samt --git og --url.")
                    if parsed_stdout.get("status") == "unchanged":
                        print("Status: uendret")
                    elif parsed_stdout.get("status") == "updated":
                        print("Status: oppdatert")
                    if result.stderr.strip():
                        print(result.stderr.rstrip(), file=sys.stderr)
                if result.returncode != 0:
                    sys.exit(result.returncode)
                return
            if args.list:
                config_path, entries = list_registry_packages()
                print(f"Prosjektkonfig: {config_path}")
                if not entries:
                    print("Register: ingen pakker funnet")
                else:
                    print(f"Register: {len(entries)} pakker")
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
            payload = {
                "fixture": str(Path(fixture_path).resolve()),
                "check_only": bool(args.check),
                "updated": int(updated),
                "strict_cases": int(total),
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Oppdatert snapshot-fixture: {fixture_path}")
                print(f"Strict-cases: {total}")
                if args.check:
                    print(f"Avvik funnet: {updated}")
                else:
                    print(f"Endringer skrevet: {updated}")
            if args.check and updated > 0:
                sys.exit(1)

        elif args.cmd == "update-selfhost-parity-fixtures":
            payload = update_selfhost_parser_fixtures(
                check_only=args.check,
                suite=args.suite,
                sync_m2=(not args.no_sync_m2),
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Suite: {payload['suite']}")
                print(f"Cases: {payload['cases']}")
                print(f"Avvik: {payload['updated']}")
                if payload.get("m2_sync") is not None:
                    m2_sync = payload["m2_sync"]
                    print(
                        f"- M2 sync: {m2_sync.get('m2_cases', 0)} cases, "
                        f"{m2_sync.get('updated', 0)} oppdateringer ({m2_sync.get('fixture')})"
                    )
                for row in payload["fixtures"]:
                    print(
                        f"- {row['label']}: {row['cases']} cases, "
                        f"{row['updated']} oppdateringer ({row['fixture']})"
                    )
                if args.check:
                    print("Status: check-only")
                else:
                    print("Status: skrevet")
            if args.check and payload["updated"] > 0:
                sys.exit(1)

        elif args.cmd == "sync-selfhost-parity-m2":
            payload = sync_selfhost_parser_m2_fixture(check_only=args.check)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"OK: {'ja' if payload.get('ok') else 'nei'}")
                print(f"M2 fixture: {payload['fixture']}")
                print(f"M1 cases: {payload['m1_cases']}")
                print(f"Core cases: {payload['core_cases']}")
                print(f"M2 cases (beregnet): {payload['m2_cases']}")
                print(f"Avvik: {payload['updated']}")
                print(f"M1-mangler i core: {payload['missing_m1_from_core_count']}")
                if args.check:
                    print("Status: check-only")
                else:
                    print("Status: synkronisert")
            if args.check and not payload.get("ok"):
                sys.exit(1)

        elif args.cmd == "ci":
            ci_available_check_specs = [
                ("snapshot_check", "--snapshot-check", args.snapshot_check),
                ("parser_fixture_check", "--parser-fixture-check", args.parser_fixture_check),
                ("parity_check", "--parity-check", args.parity_check),
                ("selfhost_m2_sync_check", "--selfhost-m2-sync-check", args.selfhost_m2_sync_check),
                ("selfhost_progress_check", "--selfhost-progress-check", args.selfhost_progress_check),
                ("test_check", "--test-check", args.test_check),
                ("workflow_action_check", "--workflow-action-check", args.workflow_action_check),
                ("name_migration_check", "--name-migration-check", args.name_migration_check),
            ]
            ci_selected_entries = [
                (name, flag) for name, flag, enabled in ci_available_check_specs if enabled
            ]
            ci_selected_lookup = {
                name for name, _ in ci_selected_entries
            }
            ci_selected_names = [name for name, _ in ci_selected_entries]
            ci_selected_count = len(ci_selected_names)
            ci_has_selection = ci_selected_count > 0
            ci_has_multiple_selection = ci_selected_count > 1
            ci_check_status = {
                name: name in ci_selected_lookup
                for name, _, _ in ci_available_check_specs
            }
            ci_cli_flags = [flag for _, flag in ci_selected_entries]
            if ci_selected_count == 1:
                ci_selected_cli_flag_text = ci_cli_flags[0]
            elif ci_selected_count > 1:
                ci_selected_cli_flag_text = (
                    ", ".join(ci_cli_flags[:-1])
                    + f" og {ci_cli_flags[-1]}"
                )
            else:
                ci_selected_cli_flag_text = ""
            ci_errors = {
                "selected_requires_native_runtime": (
                    f"ci {ci_selected_cli_flag_text} krever --native-runtime for binær check-runner"
                ),
                "multiple_selected_checks": (
                    "ci støtter foreløpig bare én binær check-runner om gangen"
                ),
                "runtime_binary_requires_native_runtime": (
                    "ci støtter bare --runtime-binary sammen med --native-runtime"
                ),
            }
            ci_selected = (
                ci_selected_names[0] if ci_has_selection else None
            )
            ci_mode = (
                ci_selected if ci_has_selection else "preview"
            )
            ci_is_preview_mode = not ci_has_selection
            ci_is_check_runner_mode = ci_has_selection
            ci_status = {
                "mode": ci_mode,
                "preview_mode": ci_is_preview_mode,
                "check_runner_mode": ci_is_check_runner_mode,
                "selected_check": ci_selected,
                "selected_checks": ci_selected_names,
                "selected_check_count": ci_selected_count,
            }
            ci_config = {
                "check_names": args.check_names,
                "parity_suite": args.parity_suite,
                "require_selfhost_ready": args.require_selfhost_ready,
            }
            ci_runtime_binary = args.runtime_binary
            ci_uses_native_runtime = args.native_runtime
            ci_has_runtime_binary = ci_runtime_binary is not None
            ci_json_requested = args.json
            ci_runtime = {
                "native_runtime": ci_uses_native_runtime,
                "runtime_binary": ci_runtime_binary,
            }
            ci_check_config = {
                **ci_config,
                **ci_check_status,
            }
            ci_mode_messages = {
                "preview": (
                    "Merk: ci er foreløpig forhåndsvisning av prosjekt og konfig samt valgt CI-omfang, ikke full kjøring."
                ),
                "snapshot_check": (
                    "Merk: ci kjører foreløpig en smal snapshot-fixture-sjekk, ikke full CI-sekvens."
                ),
                "parser_fixture_check": (
                    "Merk: ci kjører foreløpig en smal parser-fixture-sjekk, ikke full CI-sekvens."
                ),
                "parity_check": (
                    "Merk: ci kjører foreløpig en smal parity-prøvefilsjekk, ikke full engine-parity."
                ),
                "selfhost_m2_sync_check": (
                    "Merk: ci kjører foreløpig en smal fixturegrunnlag-sjekk for selfhost M2-sync, ikke full sync-diff."
                ),
                "selfhost_progress_check": (
                    "Merk: ci kjører foreløpig en smal selfhost progress-baseline, ikke full progress-analyse."
                ),
                "test_check": (
                    "Merk: ci kjører foreløpig en smal sjekk av testgrunnlaget, ikke full testkjøring."
                ),
                "workflow_action_check": (
                    "Merk: ci kjører foreløpig en smal arbeidsflyt-grunnsjekk, ikke full handlingspolicy-validering."
                ),
                "name_migration_check": (
                    "Merk: ci kjører foreløpig en smal navnemigreringssjekk, ikke full migrate-names-paritet."
                ),
            }
            ci_mode_message = ci_mode_messages[ci_mode]
            if ci_has_multiple_selection:
                raise RuntimeError(ci_errors["multiple_selected_checks"])
            if ci_has_runtime_binary and not ci_uses_native_runtime:
                raise RuntimeError(
                    ci_errors["runtime_binary_requires_native_runtime"]
                )
            if ci_uses_native_runtime:
                ci_native_runtime, ci_native_process = run_native_ci_command_captured(
                    **ci_check_config,
                    runtime_binary=ci_runtime_binary,
                )
                ci_native_runtime_output = str(ci_native_runtime)
                ci_native_exit_code = ci_native_process.returncode
                ci_native_ok = ci_native_exit_code == 0
                ci_native_stdout = ci_native_process.stdout
                ci_native_stderr = ci_native_process.stderr
                ci_native_result = _parse_native_registry_sign_stdout(
                    ci_native_stdout
                )
                ci_native_json_payload = {
                    **ci_runtime,
                    "runtime_binary": ci_native_runtime_output,
                    "ok": ci_native_ok,
                    "result": ci_native_result,
                    "stderr": ci_native_stderr,
                    **ci_status,
                    **ci_check_config,
                }
                ci_native_text_output = {
                    "lines": [
                        f"Kjøretid: {ci_native_runtime_output}",
                        "Handling: ci",
                        ci_mode_message,
                    ],
                    "stdout": (
                        ci_native_stdout.rstrip()
                        if ci_native_stdout.strip()
                        else None
                    ),
                    "stderr": (
                        ci_native_stderr.rstrip()
                        if ci_native_stderr.strip()
                        else None
                    ),
                }
                if ci_json_requested:
                    print(json.dumps(ci_native_json_payload, ensure_ascii=False, indent=2))
                else:
                    for line in ci_native_text_output["lines"]:
                        print(line)
                    if ci_native_text_output["stdout"]:
                        print(ci_native_text_output["stdout"])
                    if ci_native_text_output["stderr"]:
                        print(ci_native_text_output["stderr"], file=sys.stderr)
                if not ci_native_ok:
                    sys.exit(ci_native_exit_code)
            else:
                if ci_has_selection:
                    raise RuntimeError(
                        ci_errors["selected_requires_native_runtime"]
                    )
                ci_fallback_payload = run_ci_pipeline(
                    json_output=ci_json_requested,
                    **ci_config,
                )
                if ci_json_requested:
                    print(json.dumps(ci_fallback_payload, ensure_ascii=False, indent=2))

        elif args.cmd == "selfhost-parity":
            payload = run_selfhost_parser_parity(suite=args.suite)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Suite: {payload['suite']}")
                print(f"OK: {'ja' if payload['ok'] else 'nei'}")
                print(f"Cases: {payload['case_count']}")
                print(
                    f"Fordeling: uttrykk={payload['expression_cases']} "
                    f"skript={payload['script_cases']} "
                    f"linje={payload['line_cases']} feil={payload['error_cases']}"
                )
                print(f"Tid: {payload['duration_ms']} ms")
                for item in payload["results"]:
                    status = "OK" if item.get("success") else "FEIL"
                    print(
                        f"- {status}: {item['source']} "
                        f"({item.get('case_count', 0)} cases, "
                        f"{item.get('error_cases', 0)} feil)"
                    )
                    if not item.get("success") and item.get("stderr"):
                        print(item["stderr"].rstrip())
            if not payload["ok"]:
                sys.exit(1)

        elif args.cmd == "selfhost-parity-progress":
            payload = run_selfhost_parity_progress()
            coverage = payload.get("coverage", {}) if isinstance(payload.get("coverage"), dict) else {}
            total_coverage = coverage.get("total_pct")
            if args.min_coverage is not None:
                threshold = float(args.min_coverage)
                if threshold < 0 or threshold > 100:
                    raise RuntimeError("--min-coverage må være mellom 0 og 100")
                payload["min_coverage_required"] = threshold
                payload["min_coverage_ok"] = (
                    isinstance(total_coverage, (int, float)) and float(total_coverage) >= threshold
                )
            else:
                payload["min_coverage_required"] = None
                payload["min_coverage_ok"] = True
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"OK: {'ja' if payload.get('ok') else 'nei'}")
                print(f"Klar for full coverage: {'ja' if payload.get('ready') else 'nei'}")
                print(
                    "Dekning: "
                    f"uttrykk={coverage.get('expression_pct', 0)}% "
                    f"skript={coverage.get('script_pct', 0)}% "
                    f"total={coverage.get('total_pct', 0)}%"
                )
                if args.min_coverage is not None:
                    print(
                        "Coverage-gate: "
                        f"min={payload.get('min_coverage_required')}% "
                        f"status={'OK' if payload.get('min_coverage_ok') else 'FEIL'}"
                    )
                print(
                    "Cases: "
                    f"m1={payload.get('m1', {}).get('case_count', 0)} "
                    f"m2={payload.get('m2', {}).get('case_count', 0)} "
                    f"utvidet={payload.get('extended', {}).get('case_count', 0)}"
                )
                print(
                    "Avvik: "
                    f"missing={coverage.get('missing_in_m1_m2_count', 0)} "
                    f"extra={coverage.get('extra_in_m1_m2_count', 0)} "
                    f"overlap={coverage.get('overlap_count', 0)}"
                )
                consistency = payload.get("consistency", {})
                print(
                    "Consistency(all): "
                    f"{'OK' if consistency.get('ok') else 'FEIL'} "
                    f"({consistency.get('checked_cases', 0)} cases, "
                    f"{consistency.get('mismatch_count', 0)} avvik)"
                )
                print(f"Tid: {payload.get('duration_ms', 0)} ms")
                if payload.get("stderr") and not payload.get("ok"):
                    print(str(payload.get("stderr", "")).rstrip())
            if not payload.get("ok"):
                sys.exit(1)
            if args.require_ready and not payload.get("ready"):
                if not args.json:
                    print("Gate-feil: progress er ikke ready")
                sys.exit(1)
            if not payload.get("min_coverage_ok"):
                if not args.json:
                    print(
                        "Gate-feil: total dekningsprosent under minimum "
                        f"({coverage.get('total_pct', 0)} < {payload.get('min_coverage_required')})"
                    )
                sys.exit(1)

        elif args.cmd == "selfhost-parity-consistency":
            if args.scope == "m1":
                payload = run_selfhost_parser_suite_consistency_check(
                    SELFHOST_PARSER_M1_FIXTURE,
                    SELFHOST_PARSER_EXTENDED_FIXTURE,
                )
            elif args.scope == "m2":
                payload = run_selfhost_parser_suite_subset_consistency_check(
                    SELFHOST_PARSER_M2_FIXTURE,
                    SELFHOST_PARSER_EXTENDED_FIXTURE,
                    "m2",
                )
            else:
                payload = run_selfhost_parser_suite_all_consistency_check(
                    SELFHOST_PARSER_M1_FIXTURE,
                    SELFHOST_PARSER_M2_FIXTURE,
                    SELFHOST_PARSER_EXTENDED_FIXTURE,
                )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Scope: {payload.get('scope', 'm1')}")
                print(f"OK: {'ja' if payload.get('success') else 'nei'}")
                print(f"Sjekkede cases: {payload.get('checked_cases', 0)}")
                print(f"Avvik: {payload.get('mismatch_count', 0)}")
                print(f"Tid: {payload.get('duration_ms', 0)} ms")
                checks = payload.get("checks")
                if isinstance(checks, dict):
                    m1 = checks.get("m1", {})
                    m2 = checks.get("m2", {})
                    print(
                        f"- m1: {'OK' if m1.get('success') else 'FEIL'} "
                        f"({m1.get('checked_cases', 0)} cases, {m1.get('mismatch_count', 0)} avvik)"
                    )
                    print(
                        f"- m2: {'OK' if m2.get('success') else 'FEIL'} "
                        f"({m2.get('checked_cases', 0)} cases, {m2.get('mismatch_count', 0)} avvik)"
                    )
                    print(
                        f"- coverage: {checks.get('coverage_checked_cases', 0)} cases, "
                        f"{checks.get('coverage_mismatch_count', 0)} avvik"
                    )
                if not payload.get("success") and payload.get("stderr"):
                    print(payload["stderr"].rstrip())
            if not payload.get("success"):
                sys.exit(1)

        elif args.cmd == "lock":
            if args.native_runtime and args.legacy_python:
                raise RuntimeError("lock støtter ikke --native-runtime og --legacy-python samtidig")
            if args.runtime_binary and args.legacy_python:
                raise RuntimeError("lock støtter ikke --runtime-binary sammen med --legacy-python")
            if args.check and args.verify:
                raise RuntimeError("lock støtter ikke --check og --verify samtidig")
            use_native_lock = not args.legacy_python
            if use_native_lock:
                action = "verify" if args.verify else "check" if args.check else "write"
                runtime_path, result = run_native_lock_command_captured(
                    action,
                    runtime_binary=args.runtime_binary,
                )
                parsed_stdout = _parse_native_lock_stdout(result.stdout)
                if args.json:
                    payload = {
                        "native_runtime": True,
                        "legacy_python": False,
                        "execution_path": "runtime",
                        "action_source": "runtime",
                        "runtime_selection": "default-native" if not args.native_runtime else "forced-native",
                        "runtime_binary": str(runtime_path),
                        "requested_runtime_binary": args.runtime_binary,
                        "runtime_profile": (
                            "explicit-runtime" if args.runtime_binary else "default-runtime"
                        ),
                        "runtime_override": bool(args.runtime_binary),
                        "action": action,
                        "lock_mode": action,
                        "mode": action,
                        "ok": result.returncode == 0,
                        "read_only": action != "write",
                        "write": action == "write",
                        "preview": action != "write",
                        "check": action == "check",
                        "verify": action == "verify",
                        "has_lockfile": False,
                        "lockfile": None,
                        "lockfile_source": "none",
                        "has_status": action in {"write", "check", "verify"},
                        "status": None,
                        "status_source": "none",
                        "has_status_result": action in {"write", "check", "verify"},
                        "has_issues": False,
                        "issue_count": 0,
                        "issues": [],
                        "issues_source": None,
                        "has_results": action == "verify",
                        "results_source": "none",
                        "result_count": 0,
                        "results": [],
                        "result": parsed_stdout,
                        "stderr": result.stderr,
                    }
                    if isinstance(parsed_stdout, dict):
                        payload["has_lockfile"] = bool(parsed_stdout.get("lock_path"))
                        if "lock_path" in parsed_stdout:
                            payload["lockfile"] = parsed_stdout["lock_path"]
                            payload["lockfile_source"] = "runtime"
                        payload["has_status"] = "status" in parsed_stdout or payload["has_status"]
                        payload["has_status_result"] = "status" in parsed_stdout or payload["has_status_result"]
                        if action == "verify":
                            payload["has_results"] = True
                            payload["result_count"] = len(parsed_stdout.get("issues") or [])
                            payload["results_source"] = "runtime" if "issues" in parsed_stdout else "cli-fallback"
                        else:
                            payload["has_results"] = False
                            payload["result_count"] = 0
                            payload["results_source"] = "none"
                        if "status" in parsed_stdout:
                            payload["status"] = parsed_stdout["status"]
                            payload["status_source"] = "runtime"
                        elif action in {"write", "check", "verify"}:
                            payload["status"] = "ok" if result.returncode == 0 else "failed"
                            payload["status_source"] = "cli-fallback"
                        payload["has_issues"] = bool(parsed_stdout.get("issues"))
                        payload["issue_count"] = len(parsed_stdout.get("issues") or [])
                        if "issues" in parsed_stdout:
                            payload["issues"] = parsed_stdout["issues"]
                            payload["issues_source"] = "runtime"
                            if action == "verify":
                                payload["results"] = parsed_stdout["issues"]
                        else:
                            payload["issues_source"] = "none"
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Kjøretid: {runtime_path}")
                    print("Native runtime: True")
                    print("Legacy Python: False")
                    print("Kjørevei: runtime")
                    print("Handlingskilde: runtime")
                    print(
                        f"Kjøretidsvalg: {'default-native' if not args.native_runtime else 'forced-native'}"
                    )
                    print(
                        f"Kjøretidsprofil: {'explicit-runtime' if args.runtime_binary else 'default-runtime'}"
                    )
                    print(f"Runtime-overstyring: {bool(args.runtime_binary)}")
                    if args.runtime_binary:
                        print(f"Forespurt runtime-binær: {args.runtime_binary}")
                    print(f"Handling: {action}")
                    print(f"Modus: {action}")
                    print(f"Låsmodus: {action}")
                    print(f"Har lockfil: {bool(parsed_stdout.get('lock_path'))}")
                    print(f"OK: {result.returncode == 0}")
                    print(f"Lesemodus: {action != 'write'}")
                    print(f"Skriving: {action == 'write'}")
                    print(f"Sjekk: {action == 'check'}")
                    print(f"Verifiser: {action == 'verify'}")
                    print(f"Har problemer: {bool(parsed_stdout.get('issues'))}")
                    print(f"Problemantall: {len(parsed_stdout.get('issues') or [])}")
                    if parsed_stdout.get("issues"):
                        print("Problemerkilde: runtime")
                    else:
                        print("Problemerkilde: ingen")
                    print(f"Har status: {'status' in parsed_stdout or action in {'write', 'check', 'verify'}}")
                    print(f"Har statusresultat: {'status' in parsed_stdout or action in {'write', 'check', 'verify'}}")
                    if action == "verify":
                        print(f"Resultatantall: {len(parsed_stdout.get('issues') or [])}")
                        print(
                            f"Resultatkilde: {'runtime' if 'issues' in parsed_stdout else 'cli-fallback'}"
                        )
                        print("Har verifiseringsresultater: True")
                    else:
                        print("Resultatantall: 0")
                        print("Resultatkilde: ingen")
                        print("Har verifiseringsresultater: False")
                    print(f"Har resultater: {action == 'verify'}")
                    print(f"Forhåndsvisning: {action != 'write'}")
                    if parsed_stdout.get("lock_path"):
                        print(f"Lockfil: {parsed_stdout['lock_path']}")
                        print("Lockfilkilde: runtime")
                    else:
                        print("Lockfil: ingen")
                        print("Lockfilkilde: ingen")
                    if parsed_stdout.get("status"):
                        print(f"Status: {parsed_stdout['status']}")
                        print("Statuskilde: runtime")
                    elif action in {"write", "check", "verify"}:
                        print(f"Status: {'ok' if result.returncode == 0 else 'failed'}")
                        print("Statuskilde: cli-fallback")
                    else:
                        print("Status: ingen")
                        print("Statuskilde: ingen")
                    if parsed_stdout.get("issues"):
                        print("Problemer:")
                        for issue in parsed_stdout["issues"]:
                            print(f"  - {issue}")
                    if not args.check and not args.verify and not args.native_runtime:
                        print("Merk: lock bruker nå binærsporet som standard.")
                    if args.verify and not args.native_runtime:
                        print("Merk: lock --verify bruker nå binærsporet som standard.")
                    if args.check and not args.native_runtime:
                        print("Merk: lock --check bruker nå binærsporet som standard.")
                    if result.stderr.strip():
                        print(result.stderr.rstrip(), file=sys.stderr)
                if result.returncode != 0:
                    sys.exit(result.returncode)
            elif args.verify:
                lock_path, ok, results = verify_lockfile()
                if args.json:
                    print(
                        json.dumps(
                            {
                                "native_runtime": False,
                                "legacy_python": True,
                                "execution_path": "legacy-python",
                                "action_source": "legacy-python",
                                "runtime_selection": "legacy-python",
                                "requested_runtime_binary": args.runtime_binary,
                                "runtime_profile": (
                                    "explicit-runtime" if args.runtime_binary else "default-runtime"
                                ),
                                "runtime_override": bool(args.runtime_binary),
                                "action": "verify",
                                "lock_mode": "verify",
                                "mode": "verify",
                                "ok": ok,
                                "has_lockfile": True,
                                "lockfile_source": "legacy-python",
                                "has_status": True,
                                "has_status_result": True,
                                "has_results": True,
                                "result_count": len(results),
                                "results_source": "legacy-python",
                                "has_issues": not ok,
                                "issue_count": sum(1 for row in results if row.get("status") != "ok"),
                                "issues": [row["name"] for row in results if row.get("status") != "ok"],
                                "issues_source": "legacy-python" if not ok else "none",
                                "status_source": "legacy-python",
                                "read_only": True,
                                "write": False,
                                "preview": True,
                                "status": "ok" if ok else "failed",
                                "lockfile": str(lock_path),
                                "check": False,
                                "verify": True,
                                "results": results,
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print("Merk: lock --legacy-python bruker eksplisitt Python-tilbakefall.")
                    print("Native runtime: False")
                    print("Legacy Python: True")
                    print("Kjørevei: legacy-python")
                    print("Handlingskilde: legacy-python")
                    print("Kjøretidsvalg: legacy-python")
                    print(
                        f"Kjøretidsprofil: {'explicit-runtime' if args.runtime_binary else 'default-runtime'}"
                    )
                    print(f"Runtime-overstyring: {bool(args.runtime_binary)}")
                    if args.runtime_binary:
                        print(f"Forespurt runtime-binær: {args.runtime_binary}")
                    print("Handling: verify")
                    print("Modus: verify")
                    print("Låsmodus: verify")
                    print("Har lockfil: True")
                    print(f"OK: {ok}")
                    print("Har statusresultat: True")
                    print("Har verifiseringsresultater: True")
                    print(f"Resultatantall: {len(results)}")
                    print("Resultatkilde: legacy-python")
                    print("Har resultater: True")
                    print(f"Har problemer: {not ok}")
                    print(f"Problemantall: {sum(1 for row in results if row.get('status') != 'ok')}")
                    if results:
                        print("Problemerkilde: legacy-python")
                    else:
                        print("Problemerkilde: ingen")
                    print("Har status: True")
                    print(f"Status: {'ok' if ok else 'failed'}")
                    print("Statuskilde: legacy-python")
                    print("Lesemodus: True")
                    print("Skriving: False")
                    print("Sjekk: False")
                    print("Verifiser: True")
                    print("Forhåndsvisning: True")
                    print(f"Lockfil: {lock_path}")
                    print("Lockfilkilde: legacy-python")
                    print("Verifisering:")
                    for row in results:
                        print(f"  {row['name']}: {row['status']}")
                if not ok:
                    sys.exit(1)
            else:
                lock_path, ok, status = generate_lockfile(check_only=args.check)
                if args.json:
                    print(
                        json.dumps(
                            {
                                "native_runtime": False,
                                "legacy_python": True,
                                "execution_path": "legacy-python",
                                "action_source": "legacy-python",
                                "runtime_selection": "legacy-python",
                                "requested_runtime_binary": args.runtime_binary,
                                "runtime_profile": (
                                    "explicit-runtime" if args.runtime_binary else "default-runtime"
                                ),
                                "runtime_override": bool(args.runtime_binary),
                                "action": "check" if args.check else "write",
                                "lock_mode": "check" if args.check else "write",
                                "mode": "check" if args.check else "write",
                                "ok": ok,
                                "has_lockfile": True,
                                "lockfile_source": "legacy-python",
                                "has_status": True,
                                "has_status_result": True,
                                "has_results": False,
                                "result_count": 0,
                                "results_source": "none",
                                "results": [],
                                "has_issues": args.check and not ok,
                                "issue_count": 0 if ok else 1,
                                "issues": [] if ok else ["lock-check-failed"],
                                "issues_source": "legacy-python" if (args.check and not ok) else "none",
                                "status_source": "legacy-python",
                                "read_only": args.check,
                                "write": not args.check,
                                "preview": args.check,
                                "lockfile": str(lock_path),
                                "status": status,
                                "check": args.check,
                                "verify": False,
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print("Merk: lock --legacy-python bruker eksplisitt Python-tilbakefall.")
                    print("Native runtime: False")
                    print("Legacy Python: True")
                    print("Kjørevei: legacy-python")
                    print("Handlingskilde: legacy-python")
                    print("Kjøretidsvalg: legacy-python")
                    print(
                        f"Kjøretidsprofil: {'explicit-runtime' if args.runtime_binary else 'default-runtime'}"
                    )
                    print(f"Runtime-overstyring: {bool(args.runtime_binary)}")
                    if args.runtime_binary:
                        print(f"Forespurt runtime-binær: {args.runtime_binary}")
                    print(f"Handling: {'check' if args.check else 'write'}")
                    print(f"Modus: {'check' if args.check else 'write'}")
                    print(f"Låsmodus: {'check' if args.check else 'write'}")
                    print("Har lockfil: True")
                    print(f"OK: {ok}")
                    print("Har statusresultat: True")
                    print("Resultatantall: 0")
                    print(f"Har problemer: {args.check and not ok}")
                    print(f"Problemantall: {0 if ok else 1}")
                    if args.check and not ok:
                        print("Problemerkilde: legacy-python")
                    else:
                        print("Problemerkilde: ingen")
                    print("Har status: True")
                    print(f"Sjekk: {args.check}")
                    print("Verifiser: False")
                    print("Resultatkilde: ingen")
                    print("Har verifiseringsresultater: False")
                    print("Har resultater: False")
                    print("Statuskilde: legacy-python")
                    print(f"Lesemodus: {args.check}")
                    print(f"Skriving: {not args.check}")
                    print(f"Forhåndsvisning: {args.check}")
                    print(f"Lockfil: {lock_path}")
                    print("Lockfilkilde: legacy-python")
                    print(f"Status: {status}")
                    if args.check and not ok:
                        print("Problemer:")
                        print("  - lock-check-failed")
                if args.check and not ok:
                    sys.exit(1)

        elif args.cmd == "update":
            if args.native_runtime and args.legacy_python:
                raise RuntimeError("update støtter ikke --native-runtime og --legacy-python samtidig")
            if args.runtime_binary and args.legacy_python:
                raise RuntimeError("update støtter ikke --runtime-binary sammen med --legacy-python")
            if args.check and args.lock:
                raise RuntimeError("update støtter ikke --check og --lock samtidig")
            if args.refresh and not args.fetch:
                raise RuntimeError("update støtter bare --refresh sammen med --fetch")
            if args.allow_untrusted and not args.fetch:
                raise RuntimeError("update støtter bare --allow-untrusted sammen med --fetch")
            if args.pin and not args.fetch:
                raise RuntimeError("update støtter bare --pin sammen med --fetch")
            update_active_flags: list[str] = []
            if args.fetch:
                update_active_flags.append("fetch")
            if args.refresh:
                update_active_flags.append("refresh")
            if args.pin:
                update_active_flags.append("pin")
            if args.allow_untrusted:
                update_active_flags.append("allow-untrusted")
            if args.lock:
                update_active_flags.append("lock")
            if args.check:
                update_active_flags.append("check")
            use_native_update = (
                not args.legacy_python
                and (
                    args.native_runtime
                    or not args.package
                    or args.check
                )
            )
            if use_native_update:
                runtime_path, result = run_native_update_command_captured(
                    package=args.package,
                    check_only=args.check,
                    pin=args.pin,
                    fetch=args.fetch,
                    refresh=args.refresh,
                    allow_untrusted=args.allow_untrusted,
                    runtime_binary=args.runtime_binary,
                )
                parsed_stdout = _parse_native_update_stdout(result.stdout)
                lock_result = None
                lock_runtime_path = None
                if result.returncode == 0 and args.lock:
                    lock_runtime_path, lock_process = run_native_lock_command_captured(
                        "write",
                        runtime_binary=args.runtime_binary,
                    )
                    lock_result = {
                        "runtime_binary": str(lock_runtime_path),
                        "ok": lock_process.returncode == 0,
                        "result": _parse_native_lock_stdout(lock_process.stdout),
                        "stderr": lock_process.stderr,
                    }
                    if lock_process.returncode != 0:
                        result = lock_process
                if args.json:
                    payload = {
                        "native_runtime": True,
                        "runtime_binary": str(runtime_path),
                        "check": args.check,
                        "lock": args.lock,
                        "fetch": args.fetch,
                        "refresh": args.refresh,
                        "pin": args.pin,
                        "allow_untrusted": args.allow_untrusted,
                        "active_flags": update_active_flags,
                        "requested_runtime_binary": args.runtime_binary,
                        "runtime_profile": (
                            "explicit-runtime" if args.runtime_binary else "default-runtime"
                        ),
                        "runtime_selection": (
                            "forced-native" if args.native_runtime else "default-native"
                        ),
                        "package": args.package,
                        "target": args.package or "all",
                        "target_kind": "package" if args.package else "all",
                        "target_input_mode": "package" if args.package else "all",
                        "target_mode": "package" if args.package else "all",
                        "fetch_profile": (
                            "refresh"
                            if args.refresh
                            else ("fetch" if args.fetch else "none")
                        ),
                        "trust_profile": (
                            "allow-untrusted" if args.allow_untrusted else "default"
                        ),
                        "pin_profile": "pinned" if args.pin else "default",
                        "update_scope": "package" if args.package else "all",
                        "preview": args.check,
                        "lock_profile": "with-lock" if args.lock else "no-lock",
                        "lock_ran": lock_result is not None,
                        "remote_fetch": args.fetch,
                        "local_update": not args.package,
                        "package_update": bool(args.package),
                        "check_mode": "check" if args.check else "write",
                        "update_action": "check" if args.check else "update",
                        "ok": result.returncode == 0,
                        "result": parsed_stdout,
                        "stderr": result.stderr,
                    }
                    if lock_result is not None:
                        payload["lock_result"] = lock_result
                        payload["lock_ok"] = lock_result.get("ok")
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Kjøretid: {runtime_path}")
                    print("Handling: update")
                    print("Native runtime: True")
                    print(f"Lock: {args.lock}")
                    print(f"Fetch: {args.fetch}")
                    print(f"Oppfrisking: {args.refresh}")
                    print(f"Pin: {args.pin}")
                    print(f"Tillat utrygg: {args.allow_untrusted}")
                    print(f"Aktive flagg: {', '.join(update_active_flags) if update_active_flags else 'ingen'}")
                    print(
                        f"Kjøretidsprofil: {'explicit-runtime' if args.runtime_binary else 'default-runtime'}"
                    )
                    print(
                        f"Kjøretidsvalg: {'forced-native' if args.native_runtime else 'default-native'}"
                    )
                    if args.runtime_binary:
                        print(f"Forespurt runtime-binær: {args.runtime_binary}")
                    if args.package:
                        print(f"Pakke: {args.package}")
                    print(f"Måltype: {'package' if (args.package or 'all') != 'all' else 'all'}")
                    print(f"Målinngang: {'package' if args.package else 'all'}")
                    print(f"Målmodus: {'package' if args.package else 'all'}")
                    print(
                        f"Henteprofil: {'refresh' if args.refresh else ('fetch' if args.fetch else 'none')}"
                    )
                    print(
                        f"Tillitprofil: {'allow-untrusted' if args.allow_untrusted else 'default'}"
                    )
                    print(f"Pinprofil: {'pinned' if args.pin else 'default'}")
                    print(f"Omfang: {'package' if (args.package or 'all') != 'all' else 'all'}")
                    print(f"Forhåndsvisning: {args.check}")
                    print(f"Lockprofil: {'with-lock' if args.lock else 'no-lock'}")
                    print(f"Lock kjørt: {lock_result is not None}")
                    print(f"Ekstern henting: {args.fetch}")
                    print(f"Lokal update: {not args.package}")
                    print(f"Pakke-update: {bool(args.package)}")
                    print(f"Handlingstype: {'check' if args.check else 'update'}")
                    print(f"Sjekkmodus: {'check' if args.check else 'write'}")
                    print(f"Mål: {args.package or 'all'}")
                    if not args.check and not args.native_runtime:
                        print("Merk: enkel update bruker nå binærsporet som standard.")
                    if args.check and not args.native_runtime:
                        print("Merk: enkel update --check bruker nå binærsporet som standard.")
                    if args.lock:
                        print("Merk: update --lock bruker nå binærsporet sammen med binær lock-flyt i den enkle standardflyten.")
                    if args.pin or args.fetch or args.refresh or args.allow_untrusted:
                        print("Merk: update kjører nå også med valgte update-flagg.")
                    else:
                        print("Merk: update dekker foreløpig direkte upinnet git+ og direkte url-avhengigheter først.")
                    if lock_result is not None and lock_result["result"]:
                        print("Lock:")
                        for key, value in lock_result["result"].items():
                            print(f"  {key}={value}")
                    if result.stderr.strip():
                        print(result.stderr.rstrip(), file=sys.stderr)
                if result.returncode != 0:
                    sys.exit(result.returncode)
            else:
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
                    print(json.dumps({
                        **payload,
                        "native_runtime": False,
                        "runtime_binary": None,
                        "check": args.check,
                        "lock": args.lock,
                        "fetch": args.fetch,
                        "refresh": args.refresh,
                        "pin": args.pin,
                        "allow_untrusted": args.allow_untrusted,
                        "package": args.package,
                        "active_flags": update_active_flags,
                        "requested_runtime_binary": args.runtime_binary,
                        "runtime_profile": (
                            "explicit-runtime" if args.runtime_binary else "default-runtime"
                        ),
                        "runtime_selection": (
                            "forced-native" if args.native_runtime else "default-native"
                        ),
                        "target": payload["target"],
                        "target_kind": "package" if payload["target"] != "all" else "all",
                        "target_input_mode": "package" if payload["target"] != "all" else "all",
                        "target_mode": "package" if payload["target"] != "all" else "all",
                        "fetch_profile": (
                            "refresh"
                            if args.refresh
                            else ("fetch" if args.fetch else "none")
                        ),
                        "trust_profile": (
                            "allow-untrusted" if args.allow_untrusted else "default"
                        ),
                        "pin_profile": "pinned" if args.pin else "default",
                        "update_scope": "package" if args.package else "all",
                        "preview": args.check,
                        "lock_profile": "with-lock" if args.lock else "no-lock",
                        "lock_ran": bool(payload.get("lock")),
                        "remote_fetch": args.fetch,
                        "local_update": payload["target"] == "all",
                        "package_update": payload["target"] != "all",
                        "check_mode": "check" if args.check else "write",
                        "update_action": "check" if args.check else "update",
                    }, ensure_ascii=False, indent=2))
                else:
                    print(f"Konfig: {payload['config']}")
                    print("Handling: update")
                    print("Native runtime: False")
                    print(f"Lock: {args.lock}")
                    print(f"Fetch: {args.fetch}")
                    print(f"Oppfrisking: {args.refresh}")
                    print(f"Pin: {args.pin}")
                    print(f"Tillat utrygg: {args.allow_untrusted}")
                    print(f"Aktive flagg: {', '.join(update_active_flags) if update_active_flags else 'ingen'}")
                    print(
                        f"Kjøretidsprofil: {'explicit-runtime' if args.runtime_binary else 'default-runtime'}"
                    )
                    print(
                        f"Kjøretidsvalg: {'forced-native' if args.native_runtime else 'default-native'}"
                    )
                    if args.runtime_binary:
                        print(f"Forespurt runtime-binær: {args.runtime_binary}")
                    if args.package:
                        print(f"Pakke: {args.package}")
                    print(f"Målinngang: {'package' if payload['target'] != 'all' else 'all'}")
                    print(f"Måltype: {'package' if payload['target'] != 'all' else 'all'}")
                    print(f"Målmodus: {'package' if payload['target'] != 'all' else 'all'}")
                    print(
                        f"Henteprofil: {'refresh' if args.refresh else ('fetch' if args.fetch else 'none')}"
                    )
                    print(
                        f"Tillitprofil: {'allow-untrusted' if args.allow_untrusted else 'default'}"
                    )
                    print(f"Pinprofil: {'pinned' if args.pin else 'default'}")
                    print(f"Omfang: {'package' if (args.package or 'all') != 'all' else 'all'}")
                    print(f"Forhåndsvisning: {args.check}")
                    print(f"Lockprofil: {'with-lock' if args.lock else 'no-lock'}")
                    print(f"Lock kjørt: {bool(payload.get('lock'))}")
                    print(f"Ekstern henting: {args.fetch}")
                    print(f"Lokal update: {not args.package}")
                    print(f"Pakke-update: {bool(args.package)}")
                    print(f"Handlingstype: {'check' if args.check else 'update'}")
                    print(f"Sjekkmodus: {'check' if args.check else 'write'}")
                    print(f"Mål: {payload['target']}")
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
                        print(f"Lockfil: {payload['lock']['path']} ({payload['lock']['status']})")
                if args.check and payload["updated"] > 0:
                    sys.exit(1)

        elif args.cmd == "registry-sign":
            if args.legacy_python:
                raise RuntimeError("registersignering støtter ikke lenger --legacy-python; kommandoen bruker nå binærsporet")
            if args.write_digest and args.write_config:
                raise RuntimeError("registersignering støtter ikke --write-digest og --write-config samtidig")
            action = "write-config" if args.write_config else ("write-digest" if args.write_digest else None)
            sign_target = (
                "config"
                if args.write_config
                else ("digest-sidecar" if args.write_digest else "preview")
            )
            runtime_path, result = run_native_registry_sign_command_captured(
                action=action,
                runtime_binary=args.runtime_binary,
            )
            parsed_stdout = _parse_native_registry_sign_stdout(result.stdout)
            if args.json:
                payload = {
                    "native_runtime": True,
                    "runtime_binary": str(runtime_path),
                    "write_digest": args.write_digest,
                    "write_config": args.write_config,
                    "sign_target": sign_target,
                    "write_target": (
                        "packages/registry.toml.sha256"
                        if args.write_digest
                        else ("[security].trusted_registry_sha256" if args.write_config else "preview")
                    ),
                    "write_action": (
                        "write-digest"
                        if args.write_digest
                        else ("write-config" if args.write_config else "preview")
                    ),
                    "preview": not args.write_digest and not args.write_config,
                    "ok": result.returncode == 0,
                    "result": parsed_stdout,
                    "stderr": result.stderr,
                }
                if isinstance(parsed_stdout, dict):
                    if "registry" in parsed_stdout:
                        payload["registry"] = parsed_stdout["registry"]
                    elif "register_sti" in parsed_stdout:
                        payload["registry"] = parsed_stdout["register_sti"]
                    elif "registry_path" in parsed_stdout:
                        payload["registry"] = parsed_stdout["registry_path"]
                    if "sha256" in parsed_stdout:
                        payload["sha256"] = parsed_stdout["sha256"]
                    elif "registry_sha256" in parsed_stdout:
                        payload["sha256"] = parsed_stdout["registry_sha256"]
                    if "digest_sti" in parsed_stdout:
                        payload["digest_path"] = parsed_stdout["digest_sti"]
                    if "digest_path" in parsed_stdout:
                        payload["digest_path"] = parsed_stdout["digest_path"]
                    for key in ("config", "legacy", "status"):
                        if key in parsed_stdout:
                            payload[key] = parsed_stdout[key]
                    if "endret" in parsed_stdout:
                        payload["changed"] = parsed_stdout["endret"]
                    elif "changed" in parsed_stdout:
                        payload["changed"] = parsed_stdout["changed"]
                    if "modus" in parsed_stdout:
                        payload["mode"] = parsed_stdout["modus"]
                    elif "mode" in parsed_stdout:
                        payload["mode"] = parsed_stdout["mode"]
                    if "register_finnes" in parsed_stdout:
                        payload["registry_exists"] = parsed_stdout["register_finnes"]
                    elif "registry_exists" in parsed_stdout:
                        payload["registry_exists"] = parsed_stdout["registry_exists"]
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Kjøretid: {runtime_path}")
                print("Handling: registersignering")
                print(f"Forhåndsvisning: {not args.write_digest and not args.write_config}")
                print(f"Signeringsmål: {sign_target}")
                write_target = (
                    "packages/registry.toml.sha256"
                    if args.write_digest
                    else ("[security].trusted_registry_sha256" if args.write_config else "preview")
                )
                print(f"Skrivemål: {write_target}")
                write_action = (
                    "write-digest"
                    if args.write_digest
                    else ("write-config" if args.write_config else "preview")
                )
                print(f"Handlingstype: {write_action}")
                registry_value = (
                    parsed_stdout.get("registry")
                    or parsed_stdout.get("register_sti")
                    or parsed_stdout.get("registry_path")
                )
                sha_value = parsed_stdout.get("sha256") or parsed_stdout.get("registry_sha256")
                if parsed_stdout.get("config"):
                    print(f"Konfig: {parsed_stdout['config']}")
                if registry_value:
                    print(f"Register: {registry_value}")
                if sha_value:
                    print(f"SHA256: {sha_value}")
                digest_value = parsed_stdout.get("digest_sti") or parsed_stdout.get("digest_path")
                if digest_value:
                    print(f"Digeststi: {digest_value}")
                if parsed_stdout.get("status"):
                    print(f"Status: {parsed_stdout['status']}")
                mode_value = parsed_stdout.get("modus") or parsed_stdout.get("mode")
                if mode_value:
                    print(f"Modus: {mode_value}")
                changed_value = parsed_stdout.get("endret")
                if changed_value is None:
                    changed_value = parsed_stdout.get("changed")
                if changed_value is not None:
                    print(f"Endret: {changed_value}")
                if parsed_stdout.get("legacy") is not None:
                    print(f"Legacyspor: {parsed_stdout['legacy']}")
                registry_exists_value = parsed_stdout.get("register_finnes")
                if registry_exists_value is None:
                    registry_exists_value = parsed_stdout.get("registry_exists")
                if registry_exists_value is not None:
                    print(f"Register finnes: {registry_exists_value}")
                if args.write_digest:
                    print("Skrivemodus: digest-sidevogn")
                elif args.write_config:
                    print("Skrivemodus: konfig")
                else:
                    print("Skrivemodus: forhåndsvisning")
                if args.write_digest:
                    print(
                        "Merk: registersignering skriver foreløpig en lokal digest-sidevogn, ikke konfig."
                    )
                elif args.write_config:
                    print(
                        "Merk: registersignering skriver nå også digest til [security].trusted_registry_sha256."
                    )
                else:
                    print("Merk: registersignering er foreløpig forhåndsvisning av prosjekt og konfig samt registerfil.")
                if result.stderr.strip():
                    print(result.stderr.rstrip(), file=sys.stderr)
            if result.returncode != 0:
                sys.exit(result.returncode)

        elif args.cmd == "registry-sync":
            if args.native_runtime and args.legacy_python:
                raise RuntimeError("registersynk støtter ikke --native-runtime og --legacy-python samtidig")
            if args.runtime_binary and args.legacy_python:
                raise RuntimeError("registersynk støtter ikke --runtime-binary sammen med --legacy-python")
            if args.require_all and args.no_fallback:
                raise RuntimeError("registersynk støtter ikke --require-all og --no-fallback samtidig")
            if isinstance(args.source, str) and args.source.strip() and args.require_all:
                raise RuntimeError("registersynk støtter ikke --require-all sammen med eksplisitt --source")
            if isinstance(args.source, str) and args.source.strip() and "://" not in args.source and args.allow_untrusted:
                raise RuntimeError("registersynk støtter ikke --allow-untrusted sammen med eksplisitt lokal --source")
            if isinstance(args.source, str) and args.source.strip() and "://" not in args.source and args.no_fallback:
                raise RuntimeError("registersynk støtter ikke --no-fallback sammen med eksplisitt lokal --source")
            native_safe_explicit_source = (
                isinstance(args.source, str)
                and bool(args.source.strip())
                and "://" not in args.source
            )
            source_kind = "default"
            if isinstance(args.source, str) and args.source.strip():
                source_kind = "explicit-remote" if "://" in args.source else "explicit-local"
            policy_flags: list[str] = []
            if args.allow_untrusted:
                policy_flags.append("allow-untrusted")
            if args.require_all:
                policy_flags.append("require-all")
            if args.no_fallback:
                policy_flags.append("no-fallback")
            use_native_registry_sync = (
                not args.legacy_python
                and (
                    args.native_runtime
                    or (
                        native_safe_explicit_source
                    )
                    or (
                        not args.source
                        and not args.allow_untrusted
                        and not args.require_all
                    )
                )
            )
            if use_native_registry_sync:
                runtime_path, result = run_native_registry_sync_command_captured(
                    source=args.source,
                    allow_untrusted=args.allow_untrusted,
                    require_all=args.require_all,
                    no_fallback=args.no_fallback,
                    runtime_binary=args.runtime_binary,
                )
                parsed_stdout = _parse_native_registry_sync_stdout(result.stdout)
                if args.json:
                    payload = {
                        "native_runtime": True,
                        "runtime_binary": str(runtime_path),
                        "source": args.source,
                        "source_kind": source_kind,
                        "sync_target": args.source or "default-registry",
                        "policy_flags": policy_flags,
                        "allow_untrusted": args.allow_untrusted,
                        "require_all": args.require_all,
                        "no_fallback": args.no_fallback,
                        "sync_action": (
                            "sync-source"
                            if args.source
                            else ("sync-policy" if (args.allow_untrusted or args.require_all or args.no_fallback) else "preview")
                        ),
                        "preview": not args.source and not args.allow_untrusted and not args.require_all and not args.no_fallback,
                        "ok": result.returncode == 0,
                        "result": parsed_stdout,
                        "stderr": result.stderr,
                    }
                    if isinstance(parsed_stdout, dict):
                        if "cache" in parsed_stdout:
                            payload["cache"] = parsed_stdout["cache"]
                        elif "register_sti" in parsed_stdout:
                            payload["cache"] = parsed_stdout["register_sti"]
                        elif "cache_path" in parsed_stdout:
                            payload["cache"] = parsed_stdout["cache_path"]
                        elif "registry_path" in parsed_stdout:
                            payload["cache"] = parsed_stdout["registry_path"]
                        elif "standard_register_sti" in parsed_stdout:
                            payload["cache"] = parsed_stdout["standard_register_sti"]
                        elif "default_registry_path" in parsed_stdout:
                            payload["cache"] = parsed_stdout["default_registry_path"]
                        if "count" in parsed_stdout:
                            payload["count"] = parsed_stdout["count"]
                        elif "pakke_antall" in parsed_stdout:
                            payload["count"] = parsed_stdout["pakke_antall"]
                        elif "package_count" in parsed_stdout:
                            payload["count"] = parsed_stdout["package_count"]
                        for key in ("sources", "failed_sources", "stale_fallback_used"):
                            if key in parsed_stdout:
                                payload[key] = parsed_stdout[key]
                        for key in ("config", "legacy", "status"):
                            if key in parsed_stdout:
                                payload[key] = parsed_stdout[key]
                        if "maal" in parsed_stdout:
                            payload["target"] = parsed_stdout["maal"]
                        elif "target" in parsed_stdout:
                            payload["target"] = parsed_stdout["target"]
                        if "endret" in parsed_stdout:
                            payload["changed"] = parsed_stdout["endret"]
                        elif "changed" in parsed_stdout:
                            payload["changed"] = parsed_stdout["changed"]
                        if "modus" in parsed_stdout:
                            payload["mode"] = parsed_stdout["modus"]
                        elif "mode" in parsed_stdout:
                            payload["mode"] = parsed_stdout["mode"]
                        if "register_finnes" in parsed_stdout:
                            payload["registry_exists"] = parsed_stdout["register_finnes"]
                        elif "registry_exists" in parsed_stdout:
                            payload["registry_exists"] = parsed_stdout["registry_exists"]
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Kjøretid: {runtime_path}")
                    print("Handling: registersynk")
                    sync_target = args.source or "default-registry"
                    preview = not args.source and not args.allow_untrusted and not args.require_all and not args.no_fallback
                    print(f"Forhåndsvisning: {preview}")
                    print(f"Synkmål: {sync_target}")
                    if args.source:
                        print(f"Kilde: {args.source}")
                    print(f"Kildetype: {source_kind}")
                    if policy_flags:
                        print(f"Policyflagg: {', '.join(policy_flags)}")
                    if args.allow_untrusted:
                        print("Policy: tillat-utrygg")
                    if args.require_all:
                        print("Policy: krev-alle")
                    if args.no_fallback:
                        print("Policy: uten-tilbakefall")
                    cache_value = (
                        parsed_stdout.get("cache")
                        or parsed_stdout.get("register_sti")
                        or parsed_stdout.get("cache_path")
                        or parsed_stdout.get("registry_path")
                        or parsed_stdout.get("standard_register_sti")
                        or parsed_stdout.get("default_registry_path")
                    )
                    count_value = parsed_stdout.get("count")
                    if count_value is None:
                        count_value = parsed_stdout.get("pakke_antall")
                    if count_value is None:
                        count_value = parsed_stdout.get("package_count")
                    if parsed_stdout.get("config"):
                        print(f"Konfig: {parsed_stdout['config']}")
                    target_value = parsed_stdout.get("maal") or parsed_stdout.get("target")
                    if target_value:
                        print(f"Mål: {target_value}")
                    if cache_value:
                        print(f"Lager: {cache_value}")
                    if count_value is not None:
                        print(f"Pakker i lager: {count_value}")
                    if parsed_stdout.get("status"):
                        print(f"Status: {parsed_stdout['status']}")
                    mode_value = parsed_stdout.get("modus") or parsed_stdout.get("mode")
                    if mode_value:
                        print(f"Modus: {mode_value}")
                    changed_value = parsed_stdout.get("endret")
                    if changed_value is None:
                        changed_value = parsed_stdout.get("changed")
                    if changed_value is not None:
                        print(f"Endret: {changed_value}")
                    if parsed_stdout.get("legacy") is not None:
                        print(f"Legacyspor: {parsed_stdout['legacy']}")
                    registry_exists_value = parsed_stdout.get("register_finnes")
                    if registry_exists_value is None:
                        registry_exists_value = parsed_stdout.get("registry_exists")
                    if registry_exists_value is not None:
                        print(f"Register finnes: {registry_exists_value}")
                    if args.source:
                        print("Skrivemodus: eksplisitt kilde")
                    elif args.allow_untrusted or args.require_all or args.no_fallback:
                        print("Skrivemodus: policy-utvidet synk")
                    else:
                        print("Skrivemodus: forhåndsvisning")
                    sync_action = (
                        "sync-source"
                        if args.source
                        else ("sync-policy" if (args.allow_untrusted or args.require_all or args.no_fallback) else "preview")
                    )
                    print(f"Handlingstype: {sync_action}")
                    if not args.native_runtime:
                        print("Merk: enkel registersynk bruker binærsporet som standard når standardflyten kan tas.")
                    if args.source or args.allow_untrusted or args.require_all or args.no_fallback:
                        print("Merk: registersynk kjører nå også med valgte kilde- og policy-flagg.")
                    else:
                        print("Merk: registersynk dekker foreløpig forhåndsvisning og enkel lokal registerinitialisering når filen mangler.")
                    if result.stdout.strip():
                        print(result.stdout.rstrip())
                    if result.stderr.strip():
                        print(result.stderr.rstrip(), file=sys.stderr)
                if result.returncode != 0:
                    sys.exit(result.returncode)
            else:
                payload = registry_sync(
                    source_override=args.source,
                    allow_untrusted=args.allow_untrusted,
                    require_all=args.require_all,
                    fallback_to_cache=not args.no_fallback,
                )
                payload["native_runtime"] = False
                payload["runtime_binary"] = None
                payload["source"] = args.source
                payload["allow_untrusted"] = args.allow_untrusted
                payload["require_all"] = args.require_all
                payload["no_fallback"] = args.no_fallback
                payload["preview"] = not args.source and not args.allow_untrusted and not args.require_all and not args.no_fallback
                payload["source_kind"] = source_kind
                payload["sync_target"] = args.source or "default-registry"
                payload["policy_flags"] = policy_flags
                payload["sync_action"] = (
                    "sync-source"
                    if args.source
                    else ("sync-policy" if (args.allow_untrusted or args.require_all or args.no_fallback) else "preview")
                )
                if args.json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Forhåndsvisning: {payload['preview']}")
                    print(f"Synkmål: {payload['sync_target']}")
                    if payload["source"]:
                        print(f"Kilde: {payload['source']}")
                    print(f"Kildetype: {payload['source_kind']}")
                    if payload["allow_untrusted"]:
                        print("Policy: tillat-utrygg")
                    if payload["require_all"]:
                        print("Policy: krev-alle")
                    if payload["no_fallback"]:
                        print("Policy: uten-tilbakefall")
                    if payload["policy_flags"]:
                        print(f"Policyflagg: {', '.join(payload['policy_flags'])}")
                    print(f"Handlingstype: {payload['sync_action']}")
                    print(f"Lager: {payload['cache']}")
                    print(f"Kilder: {len(payload['sources'])}")
                    for src in payload["sources"]:
                        print(f"  - {src}")
                    print(f"Pakker i lager: {payload['count']}")
                    if payload.get("failed_sources"):
                        print("Feilede kilder:")
                        for row in payload["failed_sources"]:
                            print(f"  - {row['source']}: {row['error']}")
                    if payload.get("stale_fallback_used"):
                        print("Tilbakefall: bruker eksisterende lokalt lager")

        elif args.cmd == "registry-mirror":
            if args.legacy_python:
                raise RuntimeError("registerspeiling støtter ikke lenger --legacy-python; kommandoen bruker nå binærsporet")
            if args.write_default and args.output:
                raise RuntimeError("registerspeiling støtter ikke --write-default og --output samtidig")
            writing_output = bool(args.write_default or args.output)
            output_kind = "default"
            if args.output:
                output_kind = "explicit-output"
            elif args.write_default:
                output_kind = "default-write"
            action = "write-default" if writing_output else None
            runtime_path, result = run_native_registry_mirror_command_captured(
                action=action,
                output=args.output,
                runtime_binary=args.runtime_binary,
            )
            parsed_stdout = _parse_native_registry_sign_stdout(result.stdout)
            if args.json:
                payload = {
                    "native_runtime": True,
                    "runtime_binary": str(runtime_path),
                    "write_default": args.write_default,
                    "write_output": bool(args.output),
                    "output_kind": output_kind,
                    "output_target": args.output or "default-output",
                    "write_action": (
                        "write-output"
                        if args.output
                        else ("write-default" if args.write_default else "preview")
                    ),
                    "preview": not writing_output,
                    "onsket_utdata": args.output,
                    "ok": result.returncode == 0,
                    "result": parsed_stdout,
                    "stderr": result.stderr,
                }
                if isinstance(parsed_stdout, dict):
                    if "output" in parsed_stdout:
                        payload["output"] = parsed_stdout["output"]
                    elif "utdata_sti" in parsed_stdout:
                        payload["output"] = parsed_stdout["utdata_sti"]
                    elif "output_path" in parsed_stdout:
                        payload["output"] = parsed_stdout["output_path"]
                    elif "standard_utdata_sti" in parsed_stdout:
                        payload["output"] = parsed_stdout["standard_utdata_sti"]
                    elif "default_output_path" in parsed_stdout:
                        payload["output"] = parsed_stdout["default_output_path"]
                    if "count" in parsed_stdout:
                        payload["count"] = parsed_stdout["count"]
                    elif "pakke_antall" in parsed_stdout:
                        payload["count"] = parsed_stdout["pakke_antall"]
                    elif "package_count" in parsed_stdout:
                        payload["count"] = parsed_stdout["package_count"]
                    if "written" in parsed_stdout:
                        payload["written"] = parsed_stdout["written"]
                    elif "status" in parsed_stdout:
                        payload["written"] = parsed_stdout["status"] in {"written", "ok", "updated"}
                    for key in ("config", "legacy", "status"):
                        if key in parsed_stdout:
                            payload[key] = parsed_stdout[key]
                    if "maal" in parsed_stdout:
                        payload["target"] = parsed_stdout["maal"]
                    elif "target" in parsed_stdout:
                        payload["target"] = parsed_stdout["target"]
                    if "endret" in parsed_stdout:
                        payload["changed"] = parsed_stdout["endret"]
                    elif "changed" in parsed_stdout:
                        payload["changed"] = parsed_stdout["changed"]
                    if "modus" in parsed_stdout:
                        payload["mode"] = parsed_stdout["modus"]
                    elif "mode" in parsed_stdout:
                        payload["mode"] = parsed_stdout["mode"]
                    if "register_finnes" in parsed_stdout:
                        payload["registry_exists"] = parsed_stdout["register_finnes"]
                    elif "registry_exists" in parsed_stdout:
                        payload["registry_exists"] = parsed_stdout["registry_exists"]
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Kjøretid: {runtime_path}")
                print("Handling: registerspeiling")
                print(f"Forhåndsvisning: {not writing_output}")
                print(f"Utdatatype: {output_kind}")
                output_target = args.output or "default-output"
                print(f"Utdatamål: {output_target}")
                write_action = (
                    "write-output"
                    if args.output
                    else ("write-default" if args.write_default else "preview")
                )
                print(f"Handlingstype: {write_action}")
                output_value = (
                    parsed_stdout.get("output")
                    or parsed_stdout.get("utdata_sti")
                    or parsed_stdout.get("output_path")
                    or parsed_stdout.get("standard_utdata_sti")
                    or parsed_stdout.get("default_output_path")
                )
                count_value = parsed_stdout.get("count")
                if count_value is None:
                    count_value = parsed_stdout.get("pakke_antall")
                if count_value is None:
                    count_value = parsed_stdout.get("package_count")
                if parsed_stdout.get("config"):
                    print(f"Konfig: {parsed_stdout['config']}")
                target_value = parsed_stdout.get("maal") or parsed_stdout.get("target")
                if target_value:
                    print(f"Mål: {target_value}")
                if output_value:
                    print(f"Utdata: {output_value}")
                if count_value is not None:
                    print(f"Pakker: {count_value}")
                if parsed_stdout.get("status"):
                    print(f"Status: {parsed_stdout['status']}")
                mode_value = parsed_stdout.get("modus") or parsed_stdout.get("mode")
                if mode_value:
                    print(f"Modus: {mode_value}")
                changed_value = parsed_stdout.get("endret")
                if changed_value is None:
                    changed_value = parsed_stdout.get("changed")
                if changed_value is not None:
                    print(f"Endret: {changed_value}")
                if parsed_stdout.get("legacy") is not None:
                    print(f"Legacyspor: {parsed_stdout['legacy']}")
                registry_exists_value = parsed_stdout.get("register_finnes")
                if registry_exists_value is None:
                    registry_exists_value = parsed_stdout.get("registry_exists")
                if registry_exists_value is not None:
                    print(f"Register finnes: {registry_exists_value}")
                if args.output:
                    print("Skrivemodus: eksplisitt utdata")
                    print("Merk: registerspeiling kjører nå også med eksplisitt utdata-sti.")
                elif args.write_default:
                    print("Skrivemodus: standard-utdata")
                    print(
                        "Merk: registerspeiling skriver foreløpig bare første standard-utdata, ikke full speilbygging."
                    )
                else:
                    print("Skrivemodus: forhåndsvisning")
                    print(
                        "Merk: registerspeiling er foreløpig forhåndsvisning av prosjekt og konfig, registeret og standard utdata-sti."
                    )
                if result.stderr.strip():
                    print(result.stderr.rstrip(), file=sys.stderr)
            if result.returncode != 0:
                sys.exit(result.returncode)

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
                print(f"Endringslogg: {'oppdatert' if payload['changed_changelog'] else 'uendret'} ({payload['changelog']})")

        elif args.cmd == "test":
            if args.file:
                target = Path(args.file).expanduser()
                if target.is_dir():
                    tests = discover_tests_in_dir(target.resolve())
                    if not tests:
                        raise RuntimeError(f"Fant ingen tester i {target.resolve()}")
                    results = []
                    for test_file in tests:
                        result = run_native_test_file(
                            str(test_file),
                            runtime_binary=args.runtime_binary,
                        )
                        results.append(result)
                        if not args.json:
                            print_test_result(result, verbose=args.verbose)
                    if args.json:
                        payload = {
                            "mode": "directory",
                            "target": str(target.resolve()),
                            "results": results,
                            "summary": summarize_test_results(results),
                        }
                        print(json.dumps(payload, ensure_ascii=False, indent=2))
                    if any(not r["success"] for r in results):
                        sys.exit(1)
                else:
                    result = run_native_test_file(
                        args.file,
                        runtime_binary=args.runtime_binary,
                    )
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
                tests = discover_tests()
                if not tests:
                    raise RuntimeError("Fant ingen tester i tests/")
                results = []
                for test_file in tests:
                    result = run_native_test_file(
                        str(test_file),
                        runtime_binary=args.runtime_binary,
                    )
                    results.append(result)
                    if not args.json:
                        print_test_result(result, verbose=args.verbose)

                snapshot_result = run_ir_snapshot_checks()
                results.append(snapshot_result)
                if not args.json:
                    print_test_result(snapshot_result, verbose=args.verbose)

                if not args.json:
                    total = len(results)
                    passed = sum(1 for r in results if r["success"])
                    failed = total - passed
                    print()
                    print(f"Tester kjørt: {total}")
                    print(f"Bestått: {passed}")
                    print(f"Feilet: {failed}")
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
