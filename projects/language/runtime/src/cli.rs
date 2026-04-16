use crate::lock::{
    LockAction, LockCheckResult, LockConfigLoad, LockDocument, LockProjectRoot, LockVerifyResult, LockWriteResult,
};

pub const FUTURE_BINARY_CLI_COMMANDS: &[&str] = &["run", "check", "build", "test", "lock"];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FutureCliCommand {
    Run,
    Check,
    Build,
    Test,
    Lock,
}

#[derive(Debug, Clone)]
pub struct LockCommandResult {
    pub action: LockAction,
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub dependency_count: usize,
    pub document_json: String,
    pub write: Option<LockWriteResult>,
    pub check: Option<LockCheckResult>,
    pub verify: Option<LockVerifyResult>,
}

pub fn run_lock_command(action: LockAction) -> Option<LockCommandResult> {
    let project_root = LockProjectRoot::discover_from_cwd()?;
    let config = LockConfigLoad::from_project_root(&project_root).ok()?;
    let document = LockDocument::from_config(&project_root, &config);
    Some(LockCommandResult {
        action,
        config_path: config.config_path.display().to_string(),
        uses_legacy_config: config.uses_legacy_config,
        dependency_count: document.dependencies.len(),
        document_json: document.to_json_pretty().ok()?,
        write: match action {
            LockAction::Write => document.write_to_disk(&project_root).ok(),
            _ => None,
        },
        check: match action {
            LockAction::Check => document.check_against_disk(&project_root).ok(),
            _ => None,
        },
        verify: match action {
            LockAction::Verify => LockDocument::verify_against_disk(&project_root).ok(),
            _ => None,
        },
    })
}

pub fn future_cli_note() -> &'static str {
    "Fremtidig full `norscode` binar-CLI skal eie prosjektkommandoer som `lock`."
}
