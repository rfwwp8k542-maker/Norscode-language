use std::path::{Path, PathBuf};

pub const PROJECT_CONFIG_NAME: &str = "norscode.toml";
pub const LEGACY_PROJECT_CONFIG_NAME: &str = "norsklang.toml";

#[derive(Debug, Clone)]
pub struct ProjectRoot {
    pub root: PathBuf,
    pub config: PathBuf,
}

impl ProjectRoot {
    pub fn new(root: PathBuf, config: PathBuf) -> Self {
        Self { root, config }
    }

    pub fn discover_from(start: &Path) -> Option<Self> {
        for candidate_dir in start.ancestors() {
            let primary = candidate_dir.join(PROJECT_CONFIG_NAME);
            if primary.exists() {
                return Some(Self::new(candidate_dir.to_path_buf(), primary));
            }

            let legacy = candidate_dir.join(LEGACY_PROJECT_CONFIG_NAME);
            if legacy.exists() {
                return Some(Self::new(candidate_dir.to_path_buf(), legacy));
            }
        }
        None
    }

    pub fn discover_from_cwd() -> Option<Self> {
        let cwd = std::env::current_dir().ok()?;
        Self::discover_from(&cwd)
    }

    pub fn uses_legacy_config(&self) -> bool {
        self.config.file_name().and_then(|name| name.to_str()) == Some(LEGACY_PROJECT_CONFIG_NAME)
    }
}
