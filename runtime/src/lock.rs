use crate::project::ProjectRoot;
use chrono::Utc;
use serde::Serialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LockAction {
    Write,
    Check,
    Verify,
}

#[derive(Debug, Clone)]
pub struct LockProjectRoot {
    pub project: ProjectRoot,
}

impl LockProjectRoot {
    pub fn discover_from_cwd() -> Option<Self> {
        ProjectRoot::discover_from_cwd().map(|project| Self { project })
    }
}

#[derive(Debug, Clone)]
pub struct LockConfigLoad {
    pub config_path: std::path::PathBuf,
    pub uses_legacy_config: bool,
    pub raw_toml: String,
}

impl LockConfigLoad {
    pub fn from_project_root(project_root: &LockProjectRoot) -> std::io::Result<Self> {
        let raw_toml = fs::read_to_string(&project_root.project.config)?;
        Ok(Self {
            config_path: project_root.project.config.clone(),
            uses_legacy_config: project_root.project.uses_legacy_config(),
            raw_toml,
        })
    }

    pub fn project_name(&self) -> Option<String> {
        parse_project_field(&self.raw_toml, "name")
    }

    pub fn project_version(&self) -> Option<String> {
        parse_project_field(&self.raw_toml, "version")
    }

    pub fn project_entry(&self) -> Option<String> {
        parse_project_field(&self.raw_toml, "entry")
    }

    pub fn dependencies(&self) -> BTreeMap<String, String> {
        parse_dependencies_section(&self.raw_toml)
    }
}

#[derive(Debug, Clone)]
pub struct LockCheckResult {
    pub lock_path: PathBuf,
    pub exists: bool,
    pub matches_expected: bool,
    pub reason: Option<String>,
}

#[derive(Debug, Clone)]
pub struct LockWriteResult {
    pub lock_path: PathBuf,
    pub bytes_written: usize,
}

#[derive(Debug, Clone)]
pub struct LockVerifyResult {
    pub lock_path: PathBuf,
    pub exists: bool,
    pub valid_json: bool,
    pub has_lock_version: bool,
    pub has_project_object: bool,
    pub has_project_name: bool,
    pub project_version_type_ok: bool,
    pub project_entry_type_ok: bool,
    pub has_dependencies_object: bool,
    pub dependencies_have_required_fields: bool,
    pub dependency_specifier_types_ok: bool,
    pub dependency_kinds_known: bool,
    pub resolved_fields_match_kind: bool,
    pub resolved_value_types_ok: bool,
    pub issues: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct LockDocument {
    pub lock_version: u32,
    pub generated_at: String,
    pub project: LockProjectMeta,
    pub dependencies: BTreeMap<String, LockDependencyEntry>,
}

#[derive(Debug, Clone, Serialize)]
pub struct LockProjectMeta {
    pub name: String,
    pub version: Option<String>,
    pub entry: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct LockDependencyEntry {
    pub specifier: String,
    pub kind: LockDependencyKind,
    pub resolved: LockDependencyResolved,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum LockDependencyKind {
    Path,
    Git,
    Url,
}

#[derive(Debug, Clone, Serialize)]
pub struct LockDependencyResolved {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exists: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entry: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub r#ref: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pinned: Option<bool>,
}

impl LockDocument {
    pub fn empty(project_root: &LockProjectRoot, config: Option<&LockConfigLoad>) -> Self {
        let project_name = config
            .and_then(|cfg| cfg.project_name())
            .or_else(|| {
                project_root
                    .project
                    .root
                    .file_name()
                    .and_then(|name| name.to_str())
                    .map(ToString::to_string)
            })
            .unwrap_or_else(|| "norscode-project".to_string());

        Self {
            lock_version: 1,
            generated_at: unix_timestamp_rfc3339ish(),
            project: LockProjectMeta {
                name: project_name,
                version: config.and_then(|cfg| cfg.project_version()),
                entry: config.and_then(|cfg| cfg.project_entry()),
            },
            dependencies: BTreeMap::new(),
        }
    }

    pub fn from_config(project_root: &LockProjectRoot, config: &LockConfigLoad) -> Self {
        let mut document = Self::empty(project_root, Some(config));
        for (name, specifier) in config.dependencies() {
            let kind = classify_dependency_kind(&specifier);
            let resolved = resolve_dependency(&specifier, project_root);
            document.add_dependency(name, specifier, kind, resolved);
        }
        document
    }

    pub fn add_dependency(
        &mut self,
        name: impl Into<String>,
        specifier: impl Into<String>,
        kind: LockDependencyKind,
        resolved: LockDependencyResolved,
    ) {
        self.dependencies.insert(
            name.into(),
            LockDependencyEntry {
                specifier: specifier.into(),
                kind,
                resolved,
            },
        );
    }

    pub fn to_json_pretty(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string_pretty(self)
    }

    pub fn lock_path(project_root: &LockProjectRoot) -> PathBuf {
        project_root.project.root.join("norscode.lock")
    }

    pub fn check_against_disk(&self, project_root: &LockProjectRoot) -> std::io::Result<LockCheckResult> {
        let lock_path = Self::lock_path(project_root);
        if !lock_path.exists() {
            return Ok(LockCheckResult {
                lock_path,
                exists: false,
                matches_expected: false,
                reason: Some("mangler lockfile".to_string()),
            });
        }
        let current = fs::read_to_string(&lock_path)?;
        let mut current_value: serde_json::Value =
            serde_json::from_str(&current).map_err(|err| std::io::Error::other(err.to_string()))?;
        let mut expected_value =
            serde_json::to_value(self).map_err(|err| std::io::Error::other(err.to_string()))?;
        if let Some(obj) = current_value.as_object_mut() {
            obj.remove("generated_at");
        }
        if let Some(obj) = expected_value.as_object_mut() {
            obj.remove("generated_at");
        }
        Ok(LockCheckResult {
            lock_path,
            exists: true,
            matches_expected: current_value == expected_value,
            reason: if current_value == expected_value {
                None
            } else {
                Some("lockfile matcher ikke forventet innhold".to_string())
            },
        })
    }

    pub fn write_to_disk(&self, project_root: &LockProjectRoot) -> std::io::Result<LockWriteResult> {
        let lock_path = Self::lock_path(project_root);
        let rendered = self
            .to_json_pretty()
            .map_err(|err| std::io::Error::other(err.to_string()))?;
        fs::write(&lock_path, format!("{rendered}\n"))?;
        Ok(LockWriteResult {
            lock_path,
            bytes_written: rendered.len() + 1,
        })
    }

    pub fn verify_against_disk(project_root: &LockProjectRoot) -> std::io::Result<LockVerifyResult> {
        let lock_path = Self::lock_path(project_root);
        if !lock_path.exists() {
            return Ok(LockVerifyResult {
                lock_path,
                exists: false,
                valid_json: false,
                has_lock_version: false,
                has_project_object: false,
                has_project_name: false,
                project_version_type_ok: false,
                project_entry_type_ok: false,
                has_dependencies_object: false,
                dependencies_have_required_fields: false,
                dependency_specifier_types_ok: false,
                dependency_kinds_known: false,
                resolved_fields_match_kind: false,
                resolved_value_types_ok: false,
                issues: vec!["mangler lockfile".to_string()],
            });
        }

        let current = fs::read_to_string(&lock_path)?;
        let parsed: serde_json::Value = match serde_json::from_str(&current) {
            Ok(value) => value,
            Err(_) => {
                return Ok(LockVerifyResult {
                    lock_path,
                    exists: true,
                    valid_json: false,
                    has_lock_version: false,
                    has_project_object: false,
                    has_project_name: false,
                    project_version_type_ok: false,
                    project_entry_type_ok: false,
                    has_dependencies_object: false,
                    dependencies_have_required_fields: false,
                    dependency_specifier_types_ok: false,
                    dependency_kinds_known: false,
                    resolved_fields_match_kind: false,
                    resolved_value_types_ok: false,
                    issues: vec!["ugyldig JSON".to_string()],
                })
            }
        };

        let has_lock_version = parsed.get("lock_version").is_some();
        let has_project_object = parsed
            .get("project")
            .map(|project| project.is_object())
            .unwrap_or(false);
        let has_project_name = parsed
            .get("project")
            .and_then(|project| project.as_object())
            .and_then(|project| project.get("name"))
            .and_then(|name| name.as_str())
            .map(|name| !name.trim().is_empty())
            .unwrap_or(false);
        let project_version_type_ok = parsed
            .get("project")
            .and_then(|project| project.as_object())
            .and_then(|project| project.get("version"))
            .map(|value| value.is_null() || value.is_string())
            .unwrap_or(true);
        let project_entry_type_ok = parsed
            .get("project")
            .and_then(|project| project.as_object())
            .and_then(|project| project.get("entry"))
            .map(|value| value.is_null() || value.is_string())
            .unwrap_or(true);
        let has_dependencies_object = parsed
            .get("dependencies")
            .map(|deps| deps.is_object())
            .unwrap_or(false);
        let dependencies_have_required_fields = parsed
            .get("dependencies")
            .and_then(|deps| deps.as_object())
            .map(|deps| {
                deps.values().all(|entry| {
                    entry
                        .as_object()
                        .map(|obj| {
                            obj.contains_key("specifier")
                                && obj.contains_key("kind")
                                && obj.contains_key("resolved")
                        })
                        .unwrap_or(false)
                })
            })
            .unwrap_or(false);
        let dependency_specifier_types_ok = parsed
            .get("dependencies")
            .and_then(|deps| deps.as_object())
            .map(|deps| {
                deps.values().all(|entry| {
                    entry
                        .as_object()
                        .and_then(|obj| obj.get("specifier"))
                        .map(|value| value.is_string())
                        .unwrap_or(false)
                })
            })
            .unwrap_or(false);
        let dependency_kinds_known = parsed
            .get("dependencies")
            .and_then(|deps| deps.as_object())
            .map(|deps| {
                deps.values().all(|entry| {
                    entry
                        .as_object()
                        .and_then(|obj| obj.get("kind"))
                        .and_then(|value| value.as_str())
                        .map(|kind| matches!(kind, "Path" | "Git" | "Url" | "path" | "git" | "url"))
                        .unwrap_or(false)
                })
            })
            .unwrap_or(false);
        let resolved_fields_match_kind = parsed
            .get("dependencies")
            .and_then(|deps| deps.as_object())
            .map(|deps| {
                deps.values().all(|entry| {
                    let Some(obj) = entry.as_object() else {
                        return false;
                    };
                    let Some(kind) = obj.get("kind").and_then(|v| v.as_str()) else {
                        return false;
                    };
                    let Some(resolved) = obj.get("resolved").and_then(|v| v.as_object()) else {
                        return false;
                    };
                    match kind {
                        "Path" | "path" => resolved.contains_key("path") && resolved.contains_key("exists"),
                        "Git" | "git" => resolved.contains_key("url") && resolved.contains_key("pinned"),
                        "Url" | "url" => resolved.contains_key("url") && resolved.contains_key("pinned"),
                        _ => false,
                    }
                })
            })
            .unwrap_or(false);
        let resolved_value_types_ok = parsed
            .get("dependencies")
            .and_then(|deps| deps.as_object())
            .map(|deps| {
                deps.values().all(|entry| {
                    let Some(obj) = entry.as_object() else {
                        return false;
                    };
                    let Some(kind) = obj.get("kind").and_then(|value| value.as_str()) else {
                        return false;
                    };
                    let Some(resolved) = obj.get("resolved").and_then(|value| value.as_object()) else {
                        return false;
                    };
                    match kind {
                        "Path" | "path" => {
                            resolved.get("path").map(|v| v.is_string()).unwrap_or(false)
                                && resolved.get("exists").map(|v| v.is_boolean()).unwrap_or(false)
                                && resolved
                                    .get("project_name")
                                    .map(|v| v.is_null() || v.is_string())
                                    .unwrap_or(true)
                                && resolved
                                    .get("project_version")
                                    .map(|v| v.is_null() || v.is_string())
                                    .unwrap_or(true)
                                && resolved
                                    .get("entry")
                                    .map(|v| v.is_null() || v.is_string())
                                    .unwrap_or(true)
                        }
                        "Git" | "git" => {
                            resolved.get("url").map(|v| v.is_string()).unwrap_or(false)
                                && resolved.get("pinned").map(|v| v.is_boolean()).unwrap_or(false)
                                && resolved
                                    .get("ref")
                                    .map(|v| v.is_null() || v.is_string())
                                    .unwrap_or(true)
                        }
                        "Url" | "url" => {
                            resolved.get("url").map(|v| v.is_string()).unwrap_or(false)
                                && resolved.get("pinned").map(|v| v.is_boolean()).unwrap_or(false)
                        }
                        _ => false,
                    }
                })
            })
            .unwrap_or(false);

        let mut issues = Vec::new();
        if !has_lock_version {
            issues.push("mangler lock_version".to_string());
        }
        if !has_project_object {
            issues.push("mangler project-objekt".to_string());
        }
        if !has_project_name {
            issues.push("mangler project.name".to_string());
        }
        if !project_version_type_ok {
            issues.push("project.version må være streng eller null".to_string());
        }
        if !project_entry_type_ok {
            issues.push("project.entry må være streng eller null".to_string());
        }
        if !has_dependencies_object {
            issues.push("mangler dependencies-objekt".to_string());
        }
        if !dependencies_have_required_fields {
            issues.push("dependency entries mangler specifier/kind/resolved".to_string());
        }
        if !dependency_specifier_types_ok {
            issues.push("dependency specifier må være streng".to_string());
        }
        if !dependency_kinds_known {
            issues.push("dependency kind må være kjent verdi".to_string());
        }
        if !resolved_fields_match_kind {
            issues.push("resolved-felter matcher ikke dependency-typen".to_string());
        }
        if !resolved_value_types_ok {
            issues.push("resolved-felter har ugyldige verdityper".to_string());
        }

        Ok(LockVerifyResult {
            lock_path,
            exists: true,
            valid_json: true,
            has_lock_version,
            has_project_object,
            has_project_name,
            project_version_type_ok,
            project_entry_type_ok,
            has_dependencies_object,
            dependencies_have_required_fields,
            dependency_specifier_types_ok,
            dependency_kinds_known,
            resolved_fields_match_kind,
            resolved_value_types_ok,
            issues,
        })
    }
}

pub fn future_lock_note() -> &'static str {
    "Lock skal bli forste prosjektkommando i full norscode binar-CLI."
}

fn parse_project_field(raw_toml: &str, wanted_key: &str) -> Option<String> {
    let mut current_section = String::new();
    for line in raw_toml.lines() {
        let stripped = line.trim();
        if stripped.is_empty() || stripped.starts_with('#') {
            continue;
        }
        if stripped.starts_with('[') && stripped.ends_with(']') {
            current_section = stripped[1..stripped.len() - 1].trim().to_string();
            continue;
        }
        if current_section == "project" {
            let (key, value) = stripped.split_once('=')?;
            if key.trim() == wanted_key {
                let value = value.trim();
                if value.starts_with('"') && value.ends_with('"') && value.len() >= 2 {
                    return Some(value[1..value.len() - 1].to_string());
                }
            }
        }
    }
    None
}

fn parse_dependencies_section(raw_toml: &str) -> BTreeMap<String, String> {
    let mut current_section = String::new();
    let mut out = BTreeMap::new();
    for line in raw_toml.lines() {
        let stripped = line.trim();
        if stripped.is_empty() || stripped.starts_with('#') {
            continue;
        }
        if stripped.starts_with('[') && stripped.ends_with(']') {
            current_section = stripped[1..stripped.len() - 1].trim().to_string();
            continue;
        }
        if current_section == "dependencies" {
            let Some((key, value)) = stripped.split_once('=') else {
                continue;
            };
            let key = key.trim();
            let value = value.trim();
            if key.is_empty() {
                continue;
            }
            if value.starts_with('"') && value.ends_with('"') && value.len() >= 2 {
                out.insert(key.to_string(), value[1..value.len() - 1].to_string());
            }
        }
    }
    out
}

fn classify_dependency_kind(specifier: &str) -> LockDependencyKind {
    if specifier.starts_with("git+") {
        LockDependencyKind::Git
    } else if specifier.starts_with("url+") {
        LockDependencyKind::Url
    } else {
    LockDependencyKind::Path
}

fn resolve_dependency(specifier: &str, project_root: &LockProjectRoot) -> LockDependencyResolved {
    match classify_dependency_kind(specifier) {
        LockDependencyKind::Git => {
            let raw = specifier.strip_prefix("git+").unwrap_or(specifier);
            let (url, git_ref) = match raw.split_once('@') {
                Some((url, git_ref)) => (url.to_string(), Some(git_ref.to_string())),
                None => (raw.to_string(), None),
            };
            LockDependencyResolved {
                path: None,
                exists: None,
                project_name: None,
                project_version: None,
                entry: None,
                url: Some(url),
                r#ref: git_ref.clone(),
                pinned: Some(git_ref.is_some()),
            }
        }
        LockDependencyKind::Url => LockDependencyResolved {
            path: None,
            exists: None,
            project_name: None,
            project_version: None,
            entry: None,
            url: Some(specifier.strip_prefix("url+").unwrap_or(specifier).to_string()),
            r#ref: None,
            pinned: Some(true),
        },
        LockDependencyKind::Path => {
            let path = project_root.project.root.join(specifier).resolve_path_fallback();
            let exists = path.exists();
            let (project_name, project_version, entry) = if exists && path.is_dir() {
                load_path_project_metadata(&path)
            } else {
                (None, None, None)
            };
            LockDependencyResolved {
                path: Some(path.display().to_string()),
                exists: Some(exists),
                project_name,
                project_version,
                entry,
                url: None,
                r#ref: None,
                pinned: None,
            }
        }
    }
}

trait ResolvePathFallback {
    fn resolve_path_fallback(self) -> PathBuf;
}

impl ResolvePathFallback for PathBuf {
    fn resolve_path_fallback(self) -> PathBuf {
        self.canonicalize().unwrap_or(self)
    }
}

fn load_path_project_metadata(path: &std::path::Path) -> (Option<String>, Option<String>, Option<String>) {
    let config_path = ["norscode.toml", "norsklang.toml"]
        .into_iter()
        .map(|name| path.join(name))
        .find(|candidate| candidate.exists());

    let Some(config_path) = config_path else {
        return (None, None, None);
    };

    let Ok(raw_toml) = fs::read_to_string(config_path) else {
        return (None, None, None);
    };

    (
        parse_project_field(&raw_toml, "name"),
        parse_project_field(&raw_toml, "version"),
        parse_project_field(&raw_toml, "entry"),
    )
}

fn unix_timestamp_rfc3339ish() -> String {
    Utc::now().to_rfc3339()
}
}
