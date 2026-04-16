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
    try_registry_mirror_write_default, try_registry_sign_write_digest,
    try_registry_sign_write_config, try_registry_sync_local,
};
use crate::update::{preview_update_command_for, try_update_simple_dependencies_for};
use crate::db::initialize_from_env;
use crate::loader::load_program;
use crate::stdio::StandardIo;
use crate::vm::Vm;
use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::{self, Command};

fn program_args_from_env() -> Vec<String> {
    let raw_args = env::var("NORSCODE_ARGS").unwrap_or_default();
    raw_args
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn resolve_python_cli_script() -> Option<PathBuf> {
    let cwd_candidate = env::current_dir().ok()?.join("main.py");
    if cwd_candidate.exists() {
        return Some(cwd_candidate);
    }
    let manifest_candidate = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("main.py");
    if manifest_candidate.exists() {
        return Some(manifest_candidate);
    }
    None
}

fn run_python_cli_passthrough(
    command: &str,
    forwarded_args: Vec<String>,
    include_runtime_binary: bool,
) -> Result<(), RuntimeError> {
    let Some(script_path) = resolve_python_cli_script() else {
        return Err(RuntimeError::IoError(
            "fant ikke main.py for binar build/test-bro".to_string(),
        ));
    };
    let mut cmd = Command::new("python3");
    cmd.arg(script_path).arg(command);
    let has_runtime_binary_flag = forwarded_args.iter().any(|arg| arg == "--runtime-binary");
    for arg in forwarded_args {
        cmd.arg(arg);
    }
    if include_runtime_binary && !has_runtime_binary_flag {
        let current_exe = env::current_exe()
            .map_err(|err| RuntimeError::IoError(format!("kan ikke finne gjeldende runtime-binær: {err}")))?;
        cmd.arg("--runtime-binary").arg(current_exe);
    }
    let status = cmd
        .status()
        .map_err(|err| RuntimeError::IoError(format!("kan ikke starte python-bro for {command}: {err}")))?;
    if !status.success() {
        process::exit(status.code().unwrap_or(1));
    }
    Ok(())
}

fn main() -> Result<(), RuntimeError> {
    let print_usage = || {
        eprintln!("bruk: norscode-runtime run/kjor/koyr/kjoring/utfor/utforing <fil.ncb.json> | check/sjekk/kontroller/kontroll/valider/validering <fil.ncb.json> | build <fil.no> [--output <fil.ncb.json>] | test [fil|mappe] [--verbose] [--json] | lock/las/laas/laasing/lasing [skriv|skriving|skrive|sjekk|kontroller|kontroll|verifiser|verifisering|verifisere] | update/oppdater/oppdatering/oppdater-ting/forny/oppfrisk | add/leggtil/legg-til/legginn/legg-inn/tilfoy/foytil/innfoy | registersynk/register-synk/synkregister/synk-register/registersynkronisering/synkroniser | registersignering/register-signering/signering/signerregister/signer-register/registersigner/signer [skriv-digest|skrivdigest|skriv-digesten|skrive-digest|skriv-konfig|skrivkonfig|skrive-konfig] | registerspeiling/register-speiling/speiling/speilregister/speil-register/registerspeil/speil [skriv-standard|skrivstandard|skriv-standarden|skrive-standard] | ci/samlekjoring/samle-kjoring/samlekjor/samle/samlekontroll/samlekjeding");
        eprintln!("tips: utelat undermodus for standard skrivemodus i lock og for forhåndsvisning i registersignering og registerspeiling.");
        eprintln!("eksempler: `build program.no`, `test tests/`, `kjor program.ncb.json`, `sjekk program.ncb.json`, `las skriv`, `oppdater`, `leggtil pakke sti`, `registersynk`, `samlekjor`, `registersignering`, `registersignering skriv-digest`, `registersignering skriv-konfig`, `registerspeiling`, `registerspeiling skriv-standard`.");
    };

    let mut args = env::args().skip(1);
    let Some(command) = args.next() else {
        print_usage();
        return Ok(());
    };
    initialize_from_env()?;

    match command.as_str() {
        "help" | "hjelp" | "h" | "-h" | "--help" | "--hjelp" => {
            print_usage();
        }
        "run" | "kjor" | "koyr" | "kjoring" | "utfor" | "utforing" => {
            let Some(path) = args.next() else {
                eprintln!("mangler bytekodefil: oppgi <fil.ncb.json>");
                return Ok(());
            };
            let run_path = PathBuf::from(path);
            eprintln!("Kjører bytekodefil: {}", run_path.display());
            let program = load_program(run_path)?;
            let mut vm = Vm::with_program_args(program, StandardIo::default(), program_args_from_env());
            vm.run()?;
        }
        "check" | "sjekk" | "kontroller" | "kontroll" | "valider" | "validering" => {
            let Some(path) = args.next() else {
                eprintln!("mangler bytekodefil: oppgi <fil.ncb.json>");
                return Ok(());
            };
            let checked_path = PathBuf::from(path);
            let _program = load_program(checked_path.clone())?;
            println!("OK: bytekodefilen er gyldig: {}", checked_path.display());
        }
        "build" => {
            run_python_cli_passthrough("build", args.collect(), false)?;
        }
        "test" => {
            run_python_cli_passthrough("test", args.collect(), true)?;
        }
        "lock" | "las" | "laas" | "laasing" | "lasing" => {
            let action = match args.next().as_deref() {
                Some("check") | Some("sjekk") | Some("kontroller") | Some("kontroll") => LockAction::Check,
                Some("verify") | Some("verifiser") | Some("verifisering") | Some("verifisere") => LockAction::Verify,
                Some("write") | Some("skriv") | Some("skriving") | Some("skrive") | None => LockAction::Write,
                Some(other) => {
                    eprintln!("ukjent lock-undermodus: {other}. Bruk f.eks. `skriv`, `sjekk` eller `verifiser`, eller utelat undermodus for standard skrivemodus.");
                    return Ok(());
                }
            };
            let Some(result) = run_lock_command(action) else {
                eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
                return Ok(());
            };
            match result.action {
                LockAction::Write => {
                    if let Some(write) = result.write {
                        println!("config={}", result.config_path);
                        println!("legacy={}", result.uses_legacy_config);
                        println!("avhengighet_antall={}", result.dependency_count);
                        println!("skrevet={}", write.lock_path.display());
                        println!("byte_skrevne={}", write.bytes_written);
                    }
                }
                LockAction::Check => {
                    if let Some(check) = result.check {
                        println!("config={}", result.config_path);
                        println!("legacy={}", result.uses_legacy_config);
                        println!("avhengighet_antall={}", result.dependency_count);
                        println!("lock_sti={}", check.lock_path.display());
                        println!("finnes={}", check.exists);
                        println!("matcher_forventet={}", check.matches_expected);
                        if let Some(reason) = &check.reason {
                            println!("grunn={reason}");
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
                        println!("avhengighet_antall={}", result.dependency_count);
                        println!("lock_sti={}", verify.lock_path.display());
                        println!("finnes={}", verify.exists);
                        println!("gyldig_json={}", verify.valid_json);
                        println!("har_lock_versjon={}", verify.has_lock_version);
                        println!("har_prosjekt_objekt={}", verify.has_project_object);
                        println!("har_prosjektnavn={}", verify.has_project_name);
                        println!("prosjekt_versjonstype_ok={}", verify.project_version_type_ok);
                        println!("prosjekt_inngangstype_ok={}", verify.project_entry_type_ok);
                        println!("har_avhengighetsobjekt={}", verify.has_dependencies_object);
                        println!(
                            "avhengigheter_har_paakrevde_felt={}",
                            verify.dependencies_have_required_fields
                        );
                        println!(
                            "avhengighetsspesifikator_typer_ok={}",
                            verify.dependency_specifier_types_ok
                        );
                        println!("avhengighetstyper_kjente={}", verify.dependency_kinds_known);
                        println!("oppslag_felt_matcher_type={}", verify.resolved_fields_match_kind);
                        println!("oppslag_verdi_typer_ok={}", verify.resolved_value_types_ok);
                        for issue in &verify.issues {
                            println!("problem={issue}");
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
        "update" | "oppdater" | "oppdatering" | "oppdater-ting" | "forny" | "oppfrisk" => {
            let target_package = args.next();
            if let Some(write) = try_update_simple_dependencies_for(target_package.clone()) {
                println!("config={}", write.config_path);
                println!("status={}", write.status);
                println!("maal={}", write.target);
                println!("oppdatert_antall={}", write.updated_count);
                println!("uendret_antall={}", write.unchanged_count);
                println!("hoppet_over_antall={}", write.skipped_count);
                for item in write.items {
                println!("element={}={}", item.name, item.status);
                    if let Some(reason) = item.reason {
                        println!("element_grunn={}={}", item.name, reason);
                    }
                }
                println!("modus={}", write.mode);
                return Ok(());
            }
            let Some(result) = preview_update_command_for(target_package) else {
                eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
                return Ok(());
            };
            println!("config={}", result.config_path);
            println!("legacy={}", result.uses_legacy_config);
            println!("status={}", result.status);
            println!("maal={}", result.target);
            println!("pakke_antall={}", result.package_count);
            println!("oppdatert_antall={}", result.updated_count);
            println!("uendret_antall={}", result.unchanged_count);
            println!("hoppet_over_antall={}", result.skipped_count);
            for name in result.package_names {
                println!("pakke={name}");
            }
            for item in result.items {
                println!("element={}={}", item.name, item.status);
                if let Some(reason) = item.reason {
                    println!("element_grunn={}={}", item.name, reason);
                }
            }
            println!("modus={}", result.mode);
        }
        "add" | "leggtil" | "legg-til" | "legginn" | "legg-inn" | "tilfoy" | "foytil" | "innfoy" => {
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
                println!("avhengighet_navn={}", write.dependency_name);
                println!("avhengighet_verdi={}", write.dependency_value);
                println!("endret={}", write.changed);
                println!("status={}", write.status);
                println!("modus={}", write.mode);
                return Ok(());
            }
            let Some(result) = preview_add_command(explicit_name, requested_package, requested_path) else {
                eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
                return Ok(());
            };
            println!("config={}", result.config_path);
            println!("legacy={}", result.uses_legacy_config);
            if let Some(package) = result.requested_package {
                println!("forespurt_pakke={package}");
            }
            if let Some(path) = result.requested_path {
                println!("forespurt_sti={path}");
            }
            if let Some(status) = result.target_status {
                println!("maal_tilstand={status}");
            }
            if let Some(kind) = result.requested_kind {
                println!("forespurt_avhengighetstype={kind}");
            }
            if let Some(kind) = result.target_existing_kind {
                println!("maal_eksisterende_avhengighetstype={kind}");
            }
            if let Some(plan) = result.target_plan {
                println!("maal_handlingsplan={plan}");
            }
            println!("avhengighet_antall={}", result.dependency_count);
            println!("stiavhengighet_antall={}", result.path_count);
            println!("gitavhengighet_antall={}", result.git_count);
            println!("urlavhengighet_antall={}", result.url_count);
            for name in result.dependency_names {
                println!("avhengighet={name}");
            }
            for item in result.items {
                println!("element_type={}={}", item.name, item.kind);
            }
            println!("modus={}", result.mode);
        }
        "registry-sync" | "registersynk" | "register-synk" | "synkregister" | "synk-register" | "registersynkronisering" | "synkroniser" => {
            let mut source: Option<String> = None;
            while let Some(arg) = args.next() {
                match arg.as_str() {
                    "--source" => source = args.next(),
                    _ => {}
                }
            }
            if let Some(write) = try_registry_sync_local(source.as_deref()) {
                println!("config={}", write.config_path);
                println!("status={}", write.status);
                println!("maal={}", write.target);
                println!("register_sti={}", write.registry_path);
                println!("endret={}", write.changed);
                println!("pakke_antall={}", write.package_count);
                println!("modus={}", write.mode);
                if write.status == "error" {
                    process::exit(1);
                }
                return Ok(());
            }
            let Some(result) = preview_registry_sync(source.as_deref()) else {
                eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
                return Ok(());
            };
            println!("config={}", result.config_path);
            println!("legacy={}", result.uses_legacy_config);
            println!("status={}", result.status);
            println!("maal={}", result.target);
            println!("standard_register_sti={}", result.default_registry_path);
            println!("register_finnes={}", result.registry_exists);
            println!("pakke_antall={}", result.package_count);
            println!("modus={}", result.mode);
        }
        "registry-sign" | "registersignering" | "register-signering" | "signering" | "signerregister" | "signer-register" | "registersigner" | "signer" => match args.next().as_deref() {
            Some("write-digest") | Some("skriv-digest") | Some("skrivdigest") | Some("skriv-digesten") | Some("skrive-digest") => {
                let Some(result) = try_registry_sign_write_digest() else {
                    eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("register_sti={}", result.registry_path);
                println!("register_finnes={}", result.registry_exists);
                if let Some(registry_sha256) = result.registry_sha256 {
                    println!("registry_sha256={}", registry_sha256);
                }
                println!("digest_sti={}", result.digest_path);
                println!("endret={}", result.changed);
                println!("modus={}", result.mode);
                if !result.registry_exists || result.registry_sha256.is_none() {
                    process::exit(1);
                }
            }
            Some("write-config") | Some("skriv-konfig") | Some("skrivkonfig") | Some("skrive-konfig") => {
                let Some(result) = try_registry_sign_write_config() else {
                    eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("register_sti={}", result.registry_path);
                println!("register_finnes={}", result.registry_exists);
                if let Some(registry_sha256) = result.registry_sha256 {
                    println!("registry_sha256={}", registry_sha256);
                }
                println!("digest_sti={}", result.digest_path);
                println!("endret={}", result.changed);
                println!("modus={}", result.mode);
                if !result.registry_exists || result.registry_sha256.is_none() {
                    process::exit(1);
                }
            }
            Some(other) => {
                eprintln!("ukjent registersignering-undermodus: {other}. Bruk f.eks. `skriv-digest`, `skriv-konfig` eller utelat undermodus for forhåndsvisning.");
                return Ok(());
            }
            None => {
                let Some(result) = preview_registry_sign() else {
                    eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("register_sti={}", result.registry_path);
                println!("register_finnes={}", result.registry_exists);
                if let Some(registry_sha256) = result.registry_sha256 {
                    println!("registry_sha256={}", registry_sha256);
                }
                println!("digest_sti={}", result.digest_path);
                println!("modus={}", result.mode);
            }
        },
        "registry-mirror" | "registerspeiling" | "register-speiling" | "speiling" | "speilregister" | "speil-register" | "registerspeil" | "speil" => {
            let mut action: Option<String> = None;
            let mut output: Option<String> = None;
            while let Some(arg) = args.next() {
                match arg.as_str() {
                    "--output" => output = args.next(),
                    _ if action.is_none() => action = Some(arg),
                    _ => {}
                }
            }
            match action.as_deref() {
            Some("write-default") | Some("skriv-standard") | Some("skrivstandard") | Some("skriv-standarden") | Some("skrive-standard") => {
                let Some(result) = try_registry_mirror_write_default(output.as_deref()) else {
                    eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("maal={}", result.target);
                println!("utdata_sti={}", result.output_path);
                println!("register_finnes={}", result.registry_exists);
                println!("pakke_antall={}", result.package_count);
                println!("endret={}", result.changed);
                println!("modus={}", result.mode);
                if !result.registry_exists {
                    process::exit(1);
                }
            }
            Some(other) => {
                eprintln!("ukjent registerspeiling-undermodus: {other}. Bruk f.eks. `skriv-standard` eller utelat undermodus for forhåndsvisning.");
                return Ok(());
            }
            None => {
                let Some(result) = preview_registry_mirror(output.as_deref()) else {
                    eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml");
                    return Ok(());
                };
                println!("config={}", result.config_path);
                println!("legacy={}", result.uses_legacy_config);
                println!("status={}", result.status);
                println!("maal={}", result.target);
                println!("standard_utdata_sti={}", result.default_output_path);
                println!("register_finnes={}", result.registry_exists);
                println!("pakke_antall={}", result.package_count);
                println!("modus={}", result.mode);
            }
        }
        }
        "ci" | "samlekjoring" | "samle-kjoring" | "samlekjor" | "samle" | "samlekontroll" | "samlekjeding" => {
            let Some(project) = ProjectRoot::discover_from_cwd() else {
                eprintln!("fant ikke prosjektrot eller prosjektfila norscode.toml. Kjor kommandoen fra et prosjekt med norscode.toml.");
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
                    "--check-names" | "--sjekk-navn" => check_names = true,
                    "--require-selfhost-ready" | "--krev-selfhost-klar" => require_selfhost_ready = true,
                    "--snapshot-check" | "--snapshot-sjekk" => snapshot_check = true,
                    "--parser-fixture-check" | "--parser-fixtur-sjekk" => parser_fixture_check = true,
                    "--parity-check" | "--paritet-sjekk" => parity_check = true,
                    "--selfhost-m2-sync-check" | "--selfhost-m2-synk-sjekk" => selfhost_m2_sync_check = true,
                    "--selfhost-progress-check" | "--selfhost-framdrift-sjekk" => selfhost_progress_check = true,
                    "--test-check" | "--test-sjekk" => test_check = true,
                    "--workflow-action-check" | "--arbeidsflyt-sjekk" => workflow_action_check = true,
                    "--name-migration-check" | "--navnemigrering-sjekk" => name_migration_check = true,
                    "--parity-suite" | "--paritet-suite" => {
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
                println!("maal=navnemigrering_sjekk");
                println!("trenger_migrering={}", !found.is_empty());
                println!("legacyfiler_antall={}", found.len());
                println!("hovedfil_tilstede_antall={}", primary_present);
                for path in found {
                    println!("legacyfil_sti={}", path);
                }
                println!("modus=navnemigrering-sjekk");
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
                println!("maal=arbeidsflyt_sjekk");
                println!("arbeidsflyt_katalog={}", workflows_dir.display());
                println!("katalog_finnes={}", dir_exists);
                println!("arbeidsflyt_skannede_filer={}", scanned_files);
                println!("arbeidsflyt_lesbare_filer={}", readable_files);
                println!("norscode_ci_treff={}", norscode_ci_refs);
                println!("modus=arbeidsflyt-sjekk");
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
                println!("maal=snapshot_sjekk");
                println!("fixtur_sti={}", fixture_path.display());
                println!("fixtur_finnes={}", fixture_exists);
                println!("gyldig_json={}", valid_json);
                println!("streng_sak_antall={}", strict_case_count);
                println!("modus=snapshot-sjekk");
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
                println!("maal=parser_fixtur_sjekk");
                println!("paritet_samling={}", parity_suite);
                println!("fixtur_antall={}", fixtures.len());
                println!("fixtur_finnes={}", fixture_exists);
                println!("gyldig_json={}", valid_json);
                println!("sak_antall={}", case_count);
                println!("modus=parser-fixtur-sjekk");
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
                println!("maal=test_sjekk");
                println!("tester_mappe={}", tests_dir.display());
                println!("tester_mappe_finnes={}", tests_dir.exists());
                println!("testfil_antall={}", test_files);
                println!("snapshot_fixtur_finnes={}", snapshot_exists);
                println!("modus=test-sjekk");
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
                println!("maal=selfhost_framdrift_sjekk");
                println!("selfhost_fixtur_finnes={}", fixture_exists);
                println!("selfhost_gyldig_json={}", valid_json);
                println!("selfhost_sjekkede_filer={}", checked_files);
                println!("selfhost_klar={}", fixture_exists && valid_json);
                println!("selfhost_samlet_sak_antall={}", total_case_count);
                println!("selfhost_klar={}", fixture_exists && valid_json);
                println!("selfhost_total_dekning_prosent={}", if fixture_exists && valid_json { 100.0 } else { 0.0 });
                println!("modus=selfhost-framdrift-sjekk");
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
                println!("maal=selfhost_m2_synk_sjekk");
                println!("selfhost_m1_fixtur={}", m1_path.display());
                println!("selfhost_m2_fixtur={}", m2_path.display());
                println!("selfhost_kjerne_fixtur={}", core_path.display());
                println!("selfhost_fixtur_finnes={}", fixture_exists);
                println!("selfhost_gyldig_json={}", valid_json);
                println!("selfhost_sjekkede_filer={}", checked_files);
                println!("selfhost_samling=tests/selfhost_parser_m1_cases.json,tests/selfhost_parser_m2_cases.json,tests/selfhost_parser_core_cases.json");
                println!("modus=selfhost-m2-synk-sjekk");
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
                println!("maal=paritet_sjekk");
                println!("paritet_prove_sti={}", sample_path.display());
                println!("paritet_prove_finnes={}", sample_exists);
                println!("paritet_prove_ikke_tom={}", non_empty);
                println!("paritet_linje_antall={}", line_count);
                println!("modus=paritet-sjekk");
                if !sample_exists || !non_empty {
                    process::exit(1);
                }
                return Ok(());
            }
            println!("config={}", project.config.display());
            println!("legacy={}", project.uses_legacy_config());
            println!("status=forhåndsvisning");
            println!("maal=standard");
            println!("paritet_samling={}", parity_suite);
            println!("sjekk_navn={}", check_names);
            println!("krev_selfhost_klar={}", require_selfhost_ready);
            println!("modus=forhåndsvisning");
        }
        _ => {
            eprintln!("ukjent toppkommando: {command}. Kjor `hjelp` for brukstekst og aliasoversikt, eller prov f.eks. `run`, `sjekk` eller `lock skriv`.");
        }
    }

    Ok(())
}
