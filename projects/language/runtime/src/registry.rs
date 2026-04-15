use crate::project::ProjectRoot;
use sha2::{Digest, Sha256};
use std::fs;

#[derive(Debug, Clone)]
pub struct RegistryProjectRoot {
    pub project: ProjectRoot,
}

impl RegistryProjectRoot {
    pub fn discover_from_cwd() -> Option<Self> {
        ProjectRoot::discover_from_cwd().map(|project| Self { project })
    }
}

#[derive(Debug, Clone)]
pub struct RegistrySyncPreview {
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub status: String,
    pub target: String,
    pub default_registry_path: String,
    pub registry_exists: bool,
    pub package_count: usize,
    pub mode: String,
}

#[derive(Debug, Clone)]
pub struct RegistrySyncWriteResult {
    pub config_path: String,
    pub status: String,
    pub target: String,
    pub registry_path: String,
    pub changed: bool,
    pub package_count: usize,
    pub mode: String,
}

#[derive(Debug, Clone)]
pub struct RegistrySignPreview {
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub status: String,
    pub registry_path: String,
    pub registry_exists: bool,
    pub registry_sha256: Option<String>,
    pub mode: String,
}

#[derive(Debug, Clone)]
pub struct RegistrySignWriteResult {
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub status: String,
    pub registry_path: String,
    pub registry_exists: bool,
    pub registry_sha256: Option<String>,
    pub digest_path: String,
    pub changed: bool,
    pub mode: String,
}

#[derive(Debug, Clone)]
pub struct RegistrySignConfigWriteResult {
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub status: String,
    pub registry_path: String,
    pub registry_exists: bool,
    pub registry_sha256: Option<String>,
    pub config_changed: bool,
    pub mode: String,
}

#[derive(Debug, Clone)]
pub struct RegistryMirrorPreview {
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub status: String,
    pub target: String,
    pub default_output_path: String,
    pub registry_exists: bool,
    pub package_count: usize,
    pub mode: String,
}

#[derive(Debug, Clone)]
pub struct RegistryMirrorWriteResult {
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub status: String,
    pub target: String,
    pub output_path: String,
    pub registry_exists: bool,
    pub package_count: usize,
    pub changed: bool,
    pub mode: String,
}

pub fn preview_registry_sync() -> Option<RegistrySyncPreview> {
    let project_root = RegistryProjectRoot::discover_from_cwd()?;
    let config_path = project_root.project.config.display().to_string();
    let registry_path = project_root
        .project
        .root
        .join("packages")
        .join("registry.toml");
    let registry_exists = registry_path.exists();
    let package_count = read_registry_package_count(&registry_path);
    let default_registry_path = registry_path.display().to_string();

    Some(RegistrySyncPreview {
        config_path,
        uses_legacy_config: project_root.project.uses_legacy_config(),
        status: "preview".to_string(),
        target: "default".to_string(),
        default_registry_path,
        registry_exists,
        package_count,
        mode: "preview".to_string(),
    })
}

pub fn try_registry_sync_local() -> Option<RegistrySyncWriteResult> {
    let project_root = RegistryProjectRoot::discover_from_cwd()?;
    let config_path = project_root.project.config.display().to_string();
    let registry_path = project_root.project.root.join("packages").join("registry.toml");
    let parent = registry_path.parent()?;
    let existed = registry_path.exists();

    if !parent.exists() {
        fs::create_dir_all(parent).ok()?;
    }

    if !existed {
        fs::write(&registry_path, "[packages]\n").ok()?;
    }

    Some(RegistrySyncWriteResult {
        config_path,
        status: if existed {
            "unchanged".to_string()
        } else {
            "updated".to_string()
        },
        target: "default".to_string(),
        registry_path: registry_path.display().to_string(),
        changed: !existed,
        package_count: read_registry_package_count(&registry_path),
        mode: if existed {
            "local-noop".to_string()
        } else {
            "local-init".to_string()
        },
    })
}

pub fn preview_registry_sign() -> Option<RegistrySignPreview> {
    let project_root = RegistryProjectRoot::discover_from_cwd()?;
    let config_path = project_root.project.config.display().to_string();
    let registry_path = project_root.project.root.join("packages").join("registry.toml");
    let registry_exists = registry_path.exists();
    let registry_sha256 = compute_registry_sha256(&registry_path);

    Some(RegistrySignPreview {
        config_path,
        uses_legacy_config: project_root.project.uses_legacy_config(),
        status: "preview".to_string(),
        registry_path: registry_path.display().to_string(),
        registry_exists,
        registry_sha256,
        mode: "preview".to_string(),
    })
}

pub fn try_registry_sign_write_digest() -> Option<RegistrySignWriteResult> {
    let project_root = RegistryProjectRoot::discover_from_cwd()?;
    let config_path = project_root.project.config.display().to_string();
    let registry_path = project_root.project.root.join("packages").join("registry.toml");
    let digest_path = project_root
        .project
        .root
        .join("packages")
        .join("registry.toml.sha256");
    let registry_exists = registry_path.exists();
    let registry_sha256 = compute_registry_sha256(&registry_path);

    if !registry_exists || registry_sha256.is_none() {
        return Some(RegistrySignWriteResult {
            config_path,
            uses_legacy_config: project_root.project.uses_legacy_config(),
            status: "error".to_string(),
            registry_path: registry_path.display().to_string(),
            registry_exists,
            registry_sha256,
            digest_path: digest_path.display().to_string(),
            changed: false,
            mode: "sidecar-missing-registry".to_string(),
        });
    }

    let digest = registry_sha256.clone().unwrap_or_default();
    let changed = match fs::read_to_string(&digest_path) {
        Ok(existing) if existing.trim() == digest => false,
        _ => {
            fs::write(&digest_path, format!("{digest}\n")).ok()?;
            true
        }
    };

    Some(RegistrySignWriteResult {
        config_path,
        uses_legacy_config: project_root.project.uses_legacy_config(),
        status: if changed {
            "updated".to_string()
        } else {
            "unchanged".to_string()
        },
        registry_path: registry_path.display().to_string(),
        registry_exists,
        registry_sha256,
        digest_path: digest_path.display().to_string(),
        changed,
        mode: if changed {
            "sidecar-write".to_string()
        } else {
            "sidecar-noop".to_string()
        },
    })
}

pub fn try_registry_sign_write_config() -> Option<RegistrySignConfigWriteResult> {
    let project_root = RegistryProjectRoot::discover_from_cwd()?;
    let config_path = project_root.project.config.clone();
    let registry_path = project_root.project.root.join("packages").join("registry.toml");
    let registry_exists = registry_path.exists();
    let registry_sha256 = compute_registry_sha256(&registry_path);

    if !registry_exists || registry_sha256.is_none() {
        return Some(RegistrySignConfigWriteResult {
            config_path: config_path.display().to_string(),
            uses_legacy_config: project_root.project.uses_legacy_config(),
            status: "error".to_string(),
            registry_path: registry_path.display().to_string(),
            registry_exists,
            registry_sha256,
            config_changed: false,
            mode: "config-missing-registry".to_string(),
        });
    }

    let digest = registry_sha256.clone().unwrap_or_default();
    let raw_toml = fs::read_to_string(&config_path).ok()?;
    let (updated_toml, changed) = upsert_security_trusted_registry_sha256(&raw_toml, &digest);
    if changed {
        fs::write(&config_path, updated_toml).ok()?;
    }

    Some(RegistrySignConfigWriteResult {
        config_path: config_path.display().to_string(),
        uses_legacy_config: project_root.project.uses_legacy_config(),
        status: if changed {
            "updated".to_string()
        } else {
            "unchanged".to_string()
        },
        registry_path: registry_path.display().to_string(),
        registry_exists,
        registry_sha256,
        config_changed: changed,
        mode: if changed {
            "config-write".to_string()
        } else {
            "config-noop".to_string()
        },
    })
}

fn upsert_security_trusted_registry_sha256(raw_toml: &str, digest: &str) -> (String, bool) {
    let desired_line = format!("trusted_registry_sha256 = "{}"", digest);
    let mut lines: Vec<String> = raw_toml.lines().map(ToString::to_string).collect();
    let mut security_start: Option<usize> = None;
    let mut security_end = lines.len();

    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if trimmed == "[security]" {
            security_start = Some(idx);
            continue;
        }
        if security_start.is_some() && trimmed.starts_with('[') && trimmed.ends_with(']') {
            security_end = idx;
            break;
        }
    }

    if let Some(start) = security_start {
        for idx in (start + 1)..security_end {
            if lines[idx].trim_start().starts_with("trusted_registry_sha256") {
                if lines[idx].trim() == desired_line {
                    return (raw_toml.to_string(), false);
                }
                lines[idx] = desired_line;
                return (lines.join("\n") + "\n", true);
            }
        }
        lines.insert(start + 1, desired_line);
        return (lines.join("\n") + "\n", true);
    }

    let mut output = raw_toml.trim_end().to_string();
    if !output.is_empty() {
        output.push_str("\n\n");
    }
    output.push_str("[security]\n");
    output.push_str(&desired_line);
    output.push('\n');
    (output, true)
}

pub fn preview_registry_mirror() -> Option<RegistryMirrorPreview> {
    let project_root = RegistryProjectRoot::discover_from_cwd()?;
    let config_path = project_root.project.config.display().to_string();
    let registry_path = project_root.project.root.join("packages").join("registry.toml");
    let default_output_path = project_root
        .project
        .root
        .join("build")
        .join("registry_mirror.json");
    let registry_exists = registry_path.exists();
    let package_count = read_registry_package_count(&registry_path);

    Some(RegistryMirrorPreview {
        config_path,
        uses_legacy_config: project_root.project.uses_legacy_config(),
        status: "preview".to_string(),
        target: "default".to_string(),
        default_output_path: default_output_path.display().to_string(),
        registry_exists,
        package_count,
        mode: "preview".to_string(),
    })
}

pub fn try_registry_mirror_write_default() -> Option<RegistryMirrorWriteResult> {
    let project_root = RegistryProjectRoot::discover_from_cwd()?;
    let config_path = project_root.project.config.display().to_string();
    let registry_path = project_root.project.root.join("packages").join("registry.toml");
    let output_path = project_root
        .project
        .root
        .join("build")
        .join("registry_mirror.json");
    let registry_exists = registry_path.exists();
    let package_count = read_registry_package_count(&registry_path);

    if !registry_exists {
        return Some(RegistryMirrorWriteResult {
            config_path,
            uses_legacy_config: project_root.project.uses_legacy_config(),
            status: "error".to_string(),
            target: "default".to_string(),
            output_path: output_path.display().to_string(),
            registry_exists,
            package_count,
            changed: false,
            mode: "default-write-missing-registry".to_string(),
        });
    }

    let parent = output_path.parent()?;
    if !parent.exists() {
        fs::create_dir_all(parent).ok()?;
    }

    let payload = format!(
        "{{\n  \"source\": \"packages/registry.toml\",\n  \"package_count\": {package_count}\n}}\n"
    );
    let changed = match fs::read_to_string(&output_path) {
        Ok(existing) if existing == payload => false,
        _ => {
            fs::write(&output_path, payload).ok()?;
            true
        }
    };

    Some(RegistryMirrorWriteResult {
        config_path,
        uses_legacy_config: project_root.project.uses_legacy_config(),
        status: if changed {
            "updated".to_string()
        } else {
            "unchanged".to_string()
        },
        target: "default".to_string(),
        output_path: output_path.display().to_string(),
        registry_exists,
        package_count,
        changed,
        mode: if changed {
            "default-write".to_string()
        } else {
            "default-noop".to_string()
        },
    })
}

pub fn future_registry_note() -> &'static str {
    "Registry-logikk skal bo i egen prosjektmodul, ikke i runtime-kjernen."
}

fn read_registry_package_count(registry_path: &std::path::Path) -> usize {
    let Ok(raw) = std::fs::read_to_string(registry_path) else {
        return 0;
    };

    let mut current_section = String::new();
    let mut count = 0;
    for line in raw.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            current_section = trimmed[1..trimmed.len() - 1].trim().to_string();
            continue;
        }
        if (current_section == "packages" || current_section == "registry.packages")
            && trimmed.contains('=')
        {
            count += 1;
        }
    }
    count
}

fn compute_registry_sha256(registry_path: &std::path::Path) -> Option<String> {
    let bytes = fs::read(registry_path).ok()?;
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    Some(format!("{:x}", hasher.finalize()))
}
