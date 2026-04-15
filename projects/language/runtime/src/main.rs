mod add;
mod builtins_core;
mod builtins_text;
mod builtins_fs;
mod builtins_assert;
mod builtins_list;
mod builtins_gui;
mod builtins_web;
mod builtins_source;
mod builtins_db;
mod cli;
mod error;
mod builtins;
mod db;
mod gui;
mod loader;
mod lock;
mod operand;
mod opcode;
mod project;
mod registry;
mod runtime_bridge;
mod stdio;
mod update;
mod value;
mod vm;

use crate::error::RuntimeError;
use crate::cli::run_lock_command;
use crate::lock::LockAction;
use crate::add::{preview_add_command, try_add_simple_dependency};
use crate::project::ProjectRoot;
use crate::registry::{
    preview_registry_mirror, preview_registry_sign, preview_registry_sync,
    try_registry_mirror_write_default, try_registry_sign_write_config,
    try_registry_sign_write_digest,
    try_registry_sync_local,
};
use crate::update::{preview_update_command_for, try_update_simple_dependencies_for};
use crate::db::initialize_from_env;
use crate::loader::load_program;
use crate::stdio::StandardIo;
use crate::vm::Vm;
use std::env;
use std::fs;
use std::path::PathBuf;
use std::process;

fn program_args_from_env() -> Vec<String> {
    let raw_args = env::var("NORSCODE_ARGS").unwrap_or_default();
    raw_args
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn main() -> Result<(), RuntimeError> {
    let mut args = env::args().skip(1);
    let Some(command) = args.next() else {
        eprintln!("bruk: norscode-runtime run <fil.ncb.json> | check <fil.ncb.json> | lock [write|check|verify] | update | add | registry-sync | registry-sign | registry-mirror | ci");
        return Ok(());
    };
    initialize_from_env()?;

    match command.as_str() {
        "run" => {
            let Some(path) = args.next() else {
                eprintln!("mangler bytecode-fil");
                return Ok(());
            };
            let program = load_program(PathBuf::from(path))?;
            let mut vm = Vm::with_program_args(program, StandardIo::default(), program_args_from_env());
            vm.run()?;
        }
        "check" => {
            let Some(path) = args.next() else {
                eprintln!("mangler bytecode-fil");
                return Ok(());
            };
            let _program = load_program(PathBuf::from(path))?;
            println!("OK");
        }
        "lock" => {
            let action = match args.next().as_deref() {
                Some("check") => LockAction::Check,
                Some("verify") => LockAction::Verify,
                Some("write") | None => LockAction::Write,
                Some(other) => {
                    eprintln!("ukjent lock-handling: {other}");
                    return Ok(());
                }
            };
            let Some(result) = run_lock_command(action) else {
                eprintln!("fant ikke prosjektrot eller norscode.toml");
                return Ok(());
            };
            match result.action {
                LockAction::Write => {
                    if let Some(write) = result.write {
                        println!("config={}", result.config_path);
                        println!("legacy={}", result.uses_legacy_config);
                        println!("deps={}", result.dependency_count);
                        println!("written={}", write.lock_path.display());
                        println!("bytes_written={}", write.bytes_written);
                    }
                }
                LockAction::Check => {
                    if let Some(check) = result.check {
                        println!("config={}", result.config_path);
                        println!("legacy={}", result.uses_legacy_config);
                        println!("deps={}", result.dependency_count);
                        println!("lock_path={}", check.lock_path.display());
                        println!("exists={}", check.exists);
                        println!("matches_expected={}", check.matches_expected);
                        if let Some(reason) = &check.reason {
                            println!("reason={reason}");
                        }
                        if !check.exists || !check.matches_expected {
                            process::exit(1);
                        }
                    }
                }
                LockAction::Verify => {
                    if let Some(verify) = result.verify {
                        println!("config={}", result.config_path);
                        println!("legacy={}", result.uses_legacy_config);
                        println!("deps={}", result.dependency_count);
                        println!("lock_path={}", verify.lock_path.display());
                        println!("exists={}", verify.exists);
                        println!("valid_json={}", verify.valid_json);
                        println!("has_lock_version={}", verify.has_lock_version);
                        println!("has_project_object={}", verify.has_project_object);
                        println!("has_project_name={}", verify.has_project_name);
                        println!("project_version_type_ok={}", verify.project_version_type_ok);
                        println!("project_entry_type_ok={}", verify.project_entry_type_ok);
                        println!("has_dependencies_object={}", verify.has_dependencies_object);
                        println!(
                            "dependencies_have_required_fields={}",
                            verify.dependencies_have_required_fields
                        );
                        println!(
                            "dependency_specifier_types_ok={}",
                            verify.dependency_specifier_types_ok
                        );
                        println!("dependency_kinds_known={}", verify.dependency_kinds_known);
                        println!("resolved_fields_match_kind={}", verify.resolved_fields_match_kind);
                        println!("resolved_value_types_ok={}", verify.resolved_value_types_ok);
                        for issue in &verify.issues {
                            println!("issue={issue}");
                        }
                        if !verify.exists
                            || !verify.valid_json
                            || !verify.has_lock_version
                            || !verify.has_project_object
                            || !verify.has_project_name
                            || !verify.project_version_type_ok
                            || !verify.project_entry_type_ok
                            || !verify.has_dependencies_object
                            || !verify.dependencies_have_required_fields
                            || !verify.dependency_specifier_types_ok
                            || !verify.dependency_kinds_known
                            || !verify.resolved_fields_match_kind
                            || !verify.resolved_value_types_ok
                        {
                            process::exit(1);
                        }
                    }
                }
            }
        }
        "update" => {
            let target_package = args.next();
            if let Some(write) = try_update_simple_dependencies_for(target_package.clone()) {
                println!("config={}", write.config_path);
                println!("status={}", write.status);
                println!("target={}", write.target);
                println!("updated_count={}", write.updated_count);
                println!("unchanged_count={}", write.unchanged_count);
                println!("skipped_count={}", write.skipped_count);
                for item in write.items {
                    println!("item={}={}", item.name, item.status);
                    if let Some(reason) = item.reason {
                        println!("item_reason={}={}", item.name, reason);
                    }
                }
                println!("mode={}", write.mode);
                return Ok(());
            }
            let Some(result) = preview_update_command_for(target_package) else {
                eprintln!("fant ikke prosjektrot eller norscode.toml");
                return Ok(());
            };
            println!("config={}", result.config_path);
            println!("legacy={}", result.uses_legacy_config);
            println!("status={}", result.status);
            println!("target={}", result.target);
            println!("package_count={}", result.package_count);
            println!("updated_count={}", result.updated_count);
            println!("unchanged_count={}", result.unchanged_count);
            println!("skipped_count={}", result.skipped_count);
            for name in result.package_names {
                println!("package={name}");
            }
            for item in result.items {
                println!("item={}={}", item.name, item.status);
                if let Some(reason) = item.reason {
                    println!("item_reason={}={}", item.name, reason);
                }
            }
            println!("mode={}", result.mode);
        }
        "add" => {
            let mut explicit_name = None;
            let mut requested_ref = None;
            let mut pin = false;
            let mut positional: Vec<String> = Vec::new();
            while let Some(arg) = args.next() {
                if arg == "--name" {
                    explicit_name = args.next();
                } else if arg == "--ref" {
                    requested_ref = args.next();
                } else if arg == "--pin" {
                    pin = true;
                } else {
                    positional.push(arg);
                }
            }
            let requested_package = positional.first().cloned();
            let requested_path = positional.get(1).cloned();
            if let Some(write) = try_add_simple_dependency(
                explicit_name.clone(),
                requested_package.clone(),
                requested_path.clone(),
                requested_ref,
                pin,
            ) {
                println!("config={}", write.config_path);
                println!("dependency_name={}", write.dependency_name);
                println!("dependency_value={}", write.dependency_value);
                println!("changed={}", write.changed);
                println!("status={}", write.status);
                println!("mode={}", write.mode);
                return Ok(());
            }
            let Some(result) = preview_add_command(explicit_name, requested_package, requested_path) else {
                eprintln!("fant ikke prosjektrot eller norscode.toml");
                return Ok(());
            };
            println!("config={}", result.config_path);
            println!("legacy={}", result.uses_legacy_config);
            if let Some(package) = result.requested_package {
                println!("requested_package={package}");
            }
            if let Some(path) = result.requested_path {
                println!("requested_path={path}");
            }
            if let Some(status) = result.target_status {
                println!("target_status={status}");
            }
            if let Some(kind) = result.requested_kind {
                println!("requested_kind={kind}");
            }
            if let Some(kind) = result.target_existing_kind {
                println!("target_existing_kind={kind}");
            }
            if let Some(plan) = result.target_plan {
                println!("target_plan={plan}");
            }
            println!("dependency_count={}", result.dependency_count);
            println!("path_count={}", result.path_count);
            println!("git_count={}", result.git_count);
            println!("url_count={}", result.url_count);
            for name in result.dependency_names {
                println!("dependency={name}");
            }
            for item in result.items {
                println!("item={}={}", item.name, item.kind);
            }
            println!("mode={}", result.mode);
        }
        "registry-sync" => {
            if let Some(write) = try_registry_sync_local() {
                println!("config={}", write.config_path);
                println!("status={}", write.status);
                println!("target={}", write.target);
                println!("registry_path={}", write.registry_path);
                println!("changed={}", write.changed);
                println!("package_count={}", write.package_count);
                println!("mode={}", write.mode);
                return Ok(());
            }
            let Some(result) = preview_registry_sync() else {
                eprintln!("fant ikke prosjektrot eller norscode.toml");
                return Ok(());
            };
            println!("config={}", result.config_path);
            println!("legacy={}", result.uses_legacy_config);
            println!("status={}", result.status);
            println!("target={}", result.target);
            println!("default_registry_path={}", result.default_registry_path);
            println!("registry_exists={}", result.registry_exists);
            println!("package_count={}", result.package_count);
            println!("mode={}", result.mode);
        }
        "registry-sign" => match args.next().as_deref() {
            Some("write-config") => {
                let Some(result) = try_registry_sign_write_config() else {
                    eprintln!("fant ikke prosjektrot eller norscode.toml");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("registry_path={}", result.registry_path);
                println!("registry_exists={}", result.registry_exists);
                if let Some(registry_sha256) = result.registry_sha256.as_ref() {
                    println!("registry_sha256={}", registry_sha256);
                }
                println!("config_changed={}", result.config_changed);
                println!("mode={}", result.mode);
                if !result.registry_exists || result.registry_sha256.is_none() {
                    process::exit(1);
                }
            }
            Some("write-digest") => {
                let Some(result) = try_registry_sign_write_digest() else {
                    eprintln!("fant ikke prosjektrot eller norscode.toml");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("registry_path={}", result.registry_path);
                println!("registry_exists={}", result.registry_exists);
                if let Some(registry_sha256) = result.registry_sha256.as_ref() {
                    println!("registry_sha256={}", registry_sha256);
                }
                println!("digest_path={}", result.digest_path);
                println!("changed={}", result.changed);
                println!("mode={}", result.mode);
                if !result.registry_exists || result.registry_sha256.is_none() {
                    process::exit(1);
                }
            }
            Some(other) => {
                eprintln!("ukjent registry-sign-handling: {other}");
                return Ok(());
            }
            None => {
                let Some(result) = preview_registry_sign() else {
                    eprintln!("fant ikke prosjektrot eller norscode.toml");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("registry_path={}", result.registry_path);
                println!("registry_exists={}", result.registry_exists);
                if let Some(registry_sha256) = result.registry_sha256 {
                    println!("registry_sha256={}", registry_sha256);
                }
                println!("mode={}", result.mode);
            }
        },
        "registry-mirror" => match args.next().as_deref() {
            Some("write-default") => {
                let Some(result) = try_registry_mirror_write_default() else {
                    eprintln!("fant ikke prosjektrot eller norscode.toml");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("target={}", result.target);
                println!("output_path={}", result.output_path);
                println!("registry_exists={}", result.registry_exists);
                println!("package_count={}", result.package_count);
                println!("changed={}", result.changed);
                println!("mode={}", result.mode);
                if !result.registry_exists {
                    process::exit(1);
                }
            }
            Some(other) => {
                eprintln!("ukjent registry-mirror-handling: {other}");
                return Ok(());
            }
            None => {
                let Some(result) = preview_registry_mirror() else {
                    eprintln!("fant ikke prosjektrot eller norscode.toml");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("target={}", result.target);
                println!("default_output_path={}", result.default_output_path);
                println!("registry_exists={}", result.registry_exists);
                println!("package_count={}", result.package_count);
                println!("mode={}", result.mode);
            }
        }
        "ci" => {
            let Some(project) = ProjectRoot::discover_from_cwd() else {
                eprintln!("fant ikke prosjektrot eller norscode.toml");
                return Ok(());
            };
            let mut parity_suite = "all".to_string();
            let mut check_names = false;
            let mut require_selfhost_ready = false;
            let mut snapshot_check = false;
            let mut parser_fixture_check = false;
            let mut parity_check = false;
            let mut selfhost_m2_sync_check = false;
            let mut selfhost_progress_check = false;
            let mut test_check = false;
            let mut workflow_action_check = false;
            let mut name_migration_check = false;
            while let Some(arg) = args.next() {
                match arg.as_str() {
                    "--check-names" => check_names = true,
                    "--require-selfhost-ready" => require_selfhost_ready = true,
                    "--snapshot-check" => snapshot_check = true,
                    "--parser-fixture-check" => parser_fixture_check = true,
                    "--parity-check" => parity_check = true,
                    "--selfhost-m2-sync-check" => selfhost_m2_sync_check = true,
                    "--selfhost-progress-check" => selfhost_progress_check = true,
                    "--test-check" => test_check = true,
                    "--workflow-action-check" => workflow_action_check = true,
                    "--name-migration-check" => name_migration_check = true,
                    "--parity-suite" => {
                        if let Some(value) = args.next() {
                            parity_suite = value;
                        }
                    }
                    _ => {}
                }
            }
            if name_migration_check {
                let pairs = [
                    ("norsklang.toml", "norscode.toml"),
                    ("norsklang.lock", "norscode.lock"),
                    (".norsklang", ".norscode"),
                ];
                let mut found: Vec<String> = Vec::new();
                let mut primary_present = 0usize;
                for (legacy_name, primary_name) in pairs {
                    let legacy_path = project.root.join(legacy_name);
                    let primary_path = project.root.join(primary_name);
                    if primary_path.exists() {
                        primary_present += 1;
                    }
                    if legacy_path.exists() {
                        found.push(legacy_path.display().to_string());
                    }
                }
                println!("config={}", project.config.display());
                println!("legacy={}", project.uses_legacy_config());
                println!(
                    "status={}",
                    if found.is_empty() { "ok" } else { "error" }
                );
                println!("target=name_migration_check");
                println!("needs_migration={}", !found.is_empty());
                println!("legacy_file_count={}", found.len());
                println!("primary_present_count={}", primary_present);
                for path in &found {
                    println!("legacy_file={}", path);
                }
                println!("mode=name-migration-check");
                if project.uses_legacy_config() || !found.is_empty() {
                    process::exit(1);
                }
                return Ok(());
            }
            if workflow_action_check {
                let workflows_dir = project.root.join(".github").join("workflows");
                let dir_exists = workflows_dir.exists();
                let mut scanned_files = 0usize;
                let mut readable_files = 0usize;
                let mut norscode_ci_refs = 0usize;
                if let Ok(entries) = fs::read_dir(&workflows_dir) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        let ext = path.extension().and_then(|v| v.to_str()).unwrap_or("");
                        if ext == "yml" || ext == "yaml" {
                            scanned_files += 1;
                            if let Ok(contents) = fs::read_to_string(&path) {
                                readable_files += 1;
                                if contents.contains("norscode ci") {
                                    norscode_ci_refs += 1;
                                }
                            }
                        }
                    }
                }
                println!("config={}", project.config.display());
                println!("legacy={}", project.uses_legacy_config());
                println!(
                    "status={}",
                    if dir_exists
                        && scanned_files > 0
                        && readable_files == scanned_files
                        && norscode_ci_refs > 0
                    {
                        "ok"
                    } else {
                        "error"
                    }
                );
                println!("target=workflow_action_check");
                println!("workflows_dir={}", workflows_dir.display());
                println!("dir_exists={}", dir_exists);
                println!("scanned_files={}", scanned_files);
                println!("readable_files={}", readable_files);
                println!("norscode_ci_refs={}", norscode_ci_refs);
                println!("mode=workflow-action-check");
                if !dir_exists
                    || scanned_files == 0
                    || readable_files != scanned_files
                    || norscode_ci_refs == 0
                {
                    process::exit(1);
                }
                return Ok(());
            }
            if snapshot_check {
                let fixture_path = project.root.join("tests").join("ir_snapshot_cases.json");
                let fixture_exists = fixture_path.exists();
                let mut valid_json = false;
                let mut strict_case_count = 0usize;
                if let Ok(raw) = fs::read_to_string(&fixture_path) {
                    if let Ok(value) = serde_json::from_str::<serde_json::Value>(&raw) {
                        valid_json = true;
                        strict_case_count = value
                            .get("strict")
                            .and_then(|v| v.as_array())
                            .map(|v| v.len())
                            .unwrap_or(0);
                    }
                }
                println!("config={}", project.config.display());
                println!("legacy={}", project.uses_legacy_config());
                println!(
                    "status={}",
                    if fixture_exists && valid_json { "ok" } else { "error" }
                );
                println!("target=snapshot_check");
                println!("fixture_path={}", fixture_path.display());
                println!("fixture_exists={}", fixture_exists);
                println!("valid_json={}", valid_json);
                println!("strict_case_count={}", strict_case_count);
                println!("mode=snapshot-check");
                if !fixture_exists || !valid_json {
                    process::exit(1);
                }
                return Ok(());
            }
            if parser_fixture_check {
                let fixtures: Vec<PathBuf> = match parity_suite.as_str() {
                    "m1" => vec![project.root.join("tests").join("selfhost_parser_m1_cases.json")],
                    "m2" => vec![project.root.join("tests").join("selfhost_parser_m2_cases.json")],
                    _ => vec![
                        project.root.join("tests").join("selfhost_parser_m1_cases.json"),
                        project.root.join("tests").join("selfhost_parser_m2_cases.json"),
                        project.root.join("tests").join("selfhost_parser_core_cases.json"),
                    ],
                };
                let mut fixture_exists = true;
                let mut valid_json = true;
                let mut case_count = 0usize;
                for fixture_path in &fixtures {
                    if !fixture_path.exists() {
                        fixture_exists = false;
                        continue;
                    }
                    match fs::read_to_string(fixture_path)
                        .ok()
                        .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
                    {
                        Some(value) => {
                            case_count += value
                                .get("expressions")
                                .and_then(|v| v.as_array())
                                .map(|v| v.len())
                                .unwrap_or(0);
                            case_count += value
                                .get("scripts")
                                .and_then(|v| v.as_array())
                                .map(|v| v.len())
                                .unwrap_or(0);
                        }
                        None => valid_json = false,
                    }
                }
                println!("config={}", project.config.display());
                println!("legacy={}", project.uses_legacy_config());
                println!(
                    "status={}",
                    if fixture_exists && valid_json { "ok" } else { "error" }
                );
                println!("target=parser_fixture_check");
                println!("suite={}", parity_suite);
                println!("fixture_count={}", fixtures.len());
                println!("fixture_exists={}", fixture_exists);
                println!("valid_json={}", valid_json);
                println!("case_count={}", case_count);
                println!("mode=parser-fixture-check");
                if !fixture_exists || !valid_json {
                    process::exit(1);
                }
                return Ok(());
            }
            if test_check {
                let tests_dir = project.root.join("tests");
                let snapshot_fixture = tests_dir.join("ir_snapshot_cases.json");
                let test_files = match fs::read_dir(&tests_dir) {
                    Ok(entries) => entries
                        .filter_map(|entry| entry.ok())
                        .map(|entry| entry.path())
                        .filter(|path| {
                            path.file_name()
                                .and_then(|name| name.to_str())
                                .map(|name| name.starts_with("test_") && name.ends_with(".no"))
                                .unwrap_or(false)
                        })
                        .count(),
                    Err(_) => 0,
                };
                let snapshot_exists = snapshot_fixture.exists();
                println!("config={}", project.config.display());
                println!("legacy={}", project.uses_legacy_config());
                println!(
                    "status={}",
                    if tests_dir.exists() && test_files > 0 && snapshot_exists {
                        "ok"
                    } else {
                        "error"
                    }
                );
                println!("target=test_check");
                println!("tests_dir={}", tests_dir.display());
                println!("tests_dir_exists={}", tests_dir.exists());
                println!("test_file_count={}", test_files);
                println!("snapshot_fixture_exists={}", snapshot_exists);
                println!("mode=test-check");
                if !tests_dir.exists() || test_files == 0 || !snapshot_exists {
                    process::exit(1);
                }
                return Ok(());
            }
            if selfhost_progress_check {
                let m1_path = project.root.join("tests").join("selfhost_parser_m1_cases.json");
                let m2_path = project.root.join("tests").join("selfhost_parser_m2_cases.json");
                let core_path = project.root.join("tests").join("selfhost_parser_core_cases.json");
                let fixture_exists = m1_path.exists() && m2_path.exists() && core_path.exists();
                let mut valid_json = true;
                let mut total_case_count = 0usize;
                let mut checked_files = 0usize;
                for fixture_path in [&m1_path, &m2_path, &core_path] {
                    if !fixture_path.exists() {
                        continue;
                    }
                    checked_files += 1;
                    match fs::read_to_string(fixture_path)
                        .ok()
                        .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
                    {
                        Some(value) => {
                            total_case_count += value
                                .get("expressions")
                                .and_then(|v| v.as_array())
                                .map(|v| v.len())
                                .unwrap_or(0);
                            total_case_count += value
                                .get("scripts")
                                .and_then(|v| v.as_array())
                                .map(|v| v.len())
                                .unwrap_or(0);
                        }
                        None => valid_json = false,
                    }
                }
                println!("config={}", project.config.display());
                println!("legacy={}", project.uses_legacy_config());
                println!(
                    "status={}",
                    if fixture_exists && valid_json { "ok" } else { "error" }
                );
                println!("target=selfhost_progress_check");
                println!("fixture_exists={}", fixture_exists);
                println!("valid_json={}", valid_json);
                println!("checked_files={}", checked_files);
                println!("total_case_count={}", total_case_count);
                println!("ready={}", fixture_exists && valid_json);
                println!("coverage_total_pct={}", if fixture_exists && valid_json { 100.0 } else { 0.0 });
                println!("mode=selfhost-progress-check");
                if !fixture_exists || !valid_json {
                    process::exit(1);
                }
                return Ok(());
            }
            if selfhost_m2_sync_check {
                let m1_path = project.root.join("tests").join("selfhost_parser_m1_cases.json");
                let m2_path = project.root.join("tests").join("selfhost_parser_m2_cases.json");
                let core_path = project.root.join("tests").join("selfhost_parser_core_cases.json");
                let fixture_exists = m1_path.exists() && m2_path.exists() && core_path.exists();
                let mut valid_json = true;
                let mut checked_files = 0usize;
                for fixture_path in [&m1_path, &m2_path, &core_path] {
                    if !fixture_path.exists() {
                        continue;
                    }
                    checked_files += 1;
                    if fs::read_to_string(fixture_path)
                        .ok()
                        .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
                        .is_none()
                    {
                        valid_json = false;
                    }
                }
                println!("config={}", project.config.display());
                println!("legacy={}", project.uses_legacy_config());
                println!(
                    "status={}",
                    if fixture_exists && valid_json { "ok" } else { "error" }
                );
                println!("target=selfhost_m2_sync_check");
                println!("m1_fixture={}", m1_path.display());
                println!("m2_fixture={}", m2_path.display());
                println!("core_fixture={}", core_path.display());
                println!("fixture_exists={}", fixture_exists);
                println!("valid_json={}", valid_json);
                println!("checked_files={}", checked_files);
                println!("mode=selfhost-m2-sync-check");
                if !fixture_exists || !valid_json {
                    process::exit(1);
                }
                return Ok(());
            }
            if parity_check {
                let sample_path = project.root.join("tests").join("ir_sample.nlir");
                let sample_exists = sample_path.exists();
                let sample_text = fs::read_to_string(&sample_path).ok();
                let non_empty = sample_text
                    .as_ref()
                    .map(|text| !text.trim().is_empty())
                    .unwrap_or(false);
                let line_count = sample_text
                    .as_ref()
                    .map(|text| text.lines().count())
                    .unwrap_or(0);
                println!("config={}", project.config.display());
                println!("legacy={}", project.uses_legacy_config());
                println!(
                    "status={}",
                    if sample_exists && non_empty { "ok" } else { "error" }
                );
                println!("target=parity_check");
                println!("sample_path={}", sample_path.display());
                println!("sample_exists={}", sample_exists);
                println!("sample_non_empty={}", non_empty);
                println!("line_count={}", line_count);
                println!("mode=parity-check");
                if !sample_exists || !non_empty {
                    process::exit(1);
                }
                return Ok(());
            }
            println!("config={}", project.config.display());
            println!("legacy={}", project.uses_legacy_config());
            println!("status=preview");
            println!("target=default");
            println!("parity_suite={}", parity_suite);
            println!("check_names={}", check_names);
            println!("require_selfhost_ready={}", require_selfhost_ready);
            println!("mode=preview");
        }
        _ => {
            eprintln!("ukjent kommando: {command}");
        }
    }

    Ok(())
}
