use crate::project::ProjectRoot;
use crate::lock::{LockConfigLoad, LockProjectRoot};
use std::fs;

#[derive(Debug, Clone)]
pub struct AddProjectRoot {
    pub project: ProjectRoot,
}

impl AddProjectRoot {
    pub fn discover_from_cwd() -> Option<Self> {
        ProjectRoot::discover_from_cwd().map(|project| Self { project })
    }
}

#[derive(Debug, Clone)]
pub struct AddCommandPreview {
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub requested_package: Option<String>,
    pub requested_path: Option<String>,
    pub target_status: Option<String>,
    pub requested_kind: Option<String>,
    pub target_existing_kind: Option<String>,
    pub target_plan: Option<String>,
    pub dependency_count: usize,
    pub dependency_names: Vec<String>,
    pub path_count: usize,
    pub git_count: usize,
    pub url_count: usize,
    pub items: Vec<AddDependencyPreview>,
    pub mode: String,
}

#[derive(Debug, Clone)]
pub struct AddDependencyPreview {
    pub name: String,
    pub kind: String,
}

#[derive(Debug, Clone)]
pub struct AddWriteResult {
    pub config_path: String,
    pub dependency_name: String,
    pub dependency_value: String,
    pub changed: bool,
    pub status: String,
    pub mode: String,
}

pub fn preview_add_command(
    explicit_name: Option<String>,
    requested_package: Option<String>,
    requested_path: Option<String>,
) -> Option<AddCommandPreview> {
    let project_root = AddProjectRoot::discover_from_cwd()?;
    let config = LockConfigLoad::from_project_root(&LockProjectRoot {
        project: project_root.project.clone(),
    })
    .ok()?;
    let dependencies = config.dependencies();
    let dependency_names = dependencies.keys().cloned().collect::<Vec<_>>();
    let requested_target_name = requested_dependency_name(
        explicit_name.as_ref(),
        requested_package.as_ref(),
        requested_path.as_ref(),
    );
    let target_status = requested_target_name.as_ref().map(|package| {
        if dependencies.contains_key(package) {
            "already-present".to_string()
        } else {
            "candidate".to_string()
        }
    });
    let requested_kind = requested_package
        .as_ref()
        .map(|package| classify_requested_package_kind(package, requested_path.as_ref()).to_string());
    let target_existing_kind = requested_target_name.as_ref().and_then(|package| {
        dependencies
            .get(package)
            .map(|specifier| classify_add_dependency_kind(specifier).to_string())
    });
    let target_plan = match (&target_status, &requested_kind, &target_existing_kind) {
        (Some(status), Some(requested_kind), Some(existing_kind)) if status == "already-present" => {
            Some(format!("present:{existing_kind}"))
        }
        (Some(status), Some(requested_kind), None) if status == "candidate" => {
            Some(format!("candidate:{requested_kind}"))
        }
        _ => None,
    };
    let items = dependencies
        .iter()
        .map(|(name, specifier)| AddDependencyPreview {
            name: name.clone(),
            kind: classify_add_dependency_kind(specifier).to_string(),
        })
        .collect::<Vec<_>>();
    let path_count = items.iter().filter(|item| item.kind == "path").count();
    let git_count = items.iter().filter(|item| item.kind == "git").count();
    let url_count = items.iter().filter(|item| item.kind == "url").count();
    Some(AddCommandPreview {
        config_path: config.config_path.display().to_string(),
        uses_legacy_config: config.uses_legacy_config,
        requested_package,
        requested_path,
        target_status,
        requested_kind,
        target_existing_kind,
        target_plan,
        dependency_count: dependency_names.len(),
        dependency_names,
        path_count,
        git_count,
        url_count,
        items,
        mode: "preview".to_string(),
    })
}

pub fn future_add_note() -> &'static str {
    "Add skal bli en tidlig prosjektkommando i full norscode binar-CLI."
}

pub fn try_add_simple_dependency(
    explicit_name: Option<String>,
    requested_package: Option<String>,
    requested_path: Option<String>,
    requested_ref: Option<String>,
    pin: bool,
) -> Option<AddWriteResult> {
    let dependency_name = requested_dependency_name(
        explicit_name.as_ref(),
        requested_package.as_ref(),
        requested_path.as_ref(),
    )?;
    let dependency_value = requested_dependency_value(
        requested_package.as_ref(),
        requested_path.as_ref(),
        requested_ref.as_ref(),
    )?;
    let requested_kind = classify_requested_package_kind(&dependency_value, None);
    if !matches!(requested_kind, "path" | "git" | "url") {
        return None;
    }
    if pin && requested_kind == "git" && !dependency_value.contains('@') {
        return None;
    }

    let project_root = AddProjectRoot::discover_from_cwd()?;
    let config = LockConfigLoad::from_project_root(&LockProjectRoot {
        project: project_root.project.clone(),
    })
    .ok()?;

    let dependencies = config.dependencies();
    if dependencies.contains_key(&dependency_name) {
        return Some(AddWriteResult {
            config_path: config.config_path.display().to_string(),
            dependency_name,
            dependency_value,
            changed: false,
            status: "unchanged".to_string(),
            mode: "already-present".to_string(),
        });
    }

    let mut updated = config.raw_toml.clone();
    let new_line = format!("{dependency_name} = \"{dependency_value}\"");
    if updated.contains("\n[dependencies]\n") {
        updated.push_str(&format!("{new_line}\n"));
    } else if updated.contains("\n[dependencies]") {
        updated.push_str(&format!("\n{new_line}\n"));
    } else {
        if !updated.ends_with('\n') {
            updated.push('\n');
        }
        updated.push_str("\n[dependencies]\n");
        updated.push_str(&new_line);
        updated.push('\n');
    }

    fs::write(&config.config_path, updated).ok()?;

    Some(AddWriteResult {
        config_path: config.config_path.display().to_string(),
        dependency_name,
        dependency_value,
        changed: true,
        status: "updated".to_string(),
        mode: if pin && requested_kind == "git" {
            "git-write-pinned".to_string()
        } else {
            format!("{requested_kind}-write")
        },
    })
}

fn classify_add_dependency_kind(specifier: &str) -> &'static str {
    if specifier.starts_with("git+") {
        return "git";
    }
    if specifier.starts_with("url+") {
        return "url";
    }
    "path"
}

fn classify_requested_package_kind(package: &str, requested_path: Option<&String>) -> &'static str {
    if requested_path.is_some() {
        return "path";
    }
    if package.starts_with("git+") {
        return "git";
    }
    if package.starts_with("url+") {
        return "url";
    }
    if package.contains('/') || package.contains('\\') || package.starts_with('.') {
        return "path";
    }
    "name"
}

fn requested_dependency_name(
    explicit_name: Option<&String>,
    requested_package: Option<&String>,
    requested_path: Option<&String>,
) -> Option<String> {
    if let Some(name) = explicit_name {
        return Some(name.clone());
    }
    if requested_path.is_some() {
        return requested_package.cloned();
    }
    requested_package.and_then(|package| {
        if classify_requested_package_kind(package, None) == "path" {
            dependency_name_from_path(package)
        } else {
            Some(package.clone())
        }
    })
}

fn requested_dependency_value(
    requested_package: Option<&String>,
    requested_path: Option<&String>,
    requested_ref: Option<&String>,
) -> Option<String> {
    if let Some(path) = requested_path {
        return Some(path.clone());
    }
    requested_package.map(|package| {
        if let Some(reference) = requested_ref {
            if package.starts_with("git+") && !package.contains('@') {
                return format!("{package}@{reference}");
            }
        }
        package.clone()
    })
}

fn dependency_name_from_path(package: &str) -> Option<String> {
    let normalized = package.trim_end_matches(['/', '\\']);
    let candidate = std::path::Path::new(normalized)
        .file_name()
        .and_then(|value| value.to_str())?;
    if candidate.is_empty() {
        return None;
    }
    Some(candidate.to_string())
}
