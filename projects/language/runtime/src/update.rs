use crate::project::ProjectRoot;
use crate::lock::LockConfigLoad;
use std::fs;

#[derive(Debug, Clone)]
pub struct UpdateProjectRoot {
    pub project: ProjectRoot,
}

impl UpdateProjectRoot {
    pub fn discover_from_cwd() -> Option<Self> {
        ProjectRoot::discover_from_cwd().map(|project| Self { project })
    }
}

#[derive(Debug, Clone)]
pub struct UpdateCommandPreview {
    pub config_path: String,
    pub uses_legacy_config: bool,
    pub status: String,
    pub target: String,
    pub package_count: usize,
    pub updated_count: usize,
    pub unchanged_count: usize,
    pub skipped_count: usize,
    pub package_names: Vec<String>,
    pub items: Vec<UpdateItemPreview>,
    pub mode: String,
}

#[derive(Debug, Clone)]
pub struct UpdateItemPreview {
    pub name: String,
    pub status: String,
    pub reason: Option<String>,
}

#[derive(Debug, Clone)]
pub struct UpdateWriteResult {
    pub config_path: String,
    pub status: String,
    pub target: String,
    pub updated_count: usize,
    pub unchanged_count: usize,
    pub skipped_count: usize,
    pub items: Vec<UpdateItemPreview>,
    pub mode: String,
}

pub fn preview_update_command() -> Option<UpdateCommandPreview> {
    preview_update_command_for(None)
}

pub fn preview_update_command_for(target_package: Option<String>) -> Option<UpdateCommandPreview> {
    let project_root = UpdateProjectRoot::discover_from_cwd()?;
    let config = LockConfigLoad::from_project_root(&crate::lock::LockProjectRoot {
        project: project_root.project.clone(),
    })
    .ok()?;
    let mut dependencies = config.dependencies();
    if let Some(target) = target_package.as_ref() {
        dependencies.retain(|name, _| name == target);
    }
    let package_names = dependencies.keys().cloned().collect::<Vec<_>>();
    let items = dependencies
        .into_iter()
        .map(|(name, specifier)| {
            let (status, reason) = classify_update_preview_item(&specifier);
            UpdateItemPreview {
                name,
                status: status.to_string(),
                reason,
            }
        })
        .collect::<Vec<_>>();
    let unchanged_count = items.iter().filter(|item| item.status == "unchanged").count();
    let skipped_count = items.iter().filter(|item| item.status == "skipped").count();
    Some(UpdateCommandPreview {
        config_path: config.config_path.display().to_string(),
        uses_legacy_config: config.uses_legacy_config,
        status: "preview".to_string(),
        target: target_package.unwrap_or_else(|| "all".to_string()),
        package_count: package_names.len(),
        updated_count: 0,
        unchanged_count,
        skipped_count,
        package_names,
        items,
        mode: "preview".to_string(),
    })
}

pub fn future_update_note() -> &'static str {
    "Update skal vaere neste prosjektkommando etter lock i full norscode binar-CLI."
}

pub fn try_update_simple_dependencies() -> Option<UpdateWriteResult> {
    try_update_simple_dependencies_for(None)
}

pub fn try_update_simple_dependencies_for(target_package: Option<String>) -> Option<UpdateWriteResult> {
    let project_root = UpdateProjectRoot::discover_from_cwd()?;
    let config = LockConfigLoad::from_project_root(&crate::lock::LockProjectRoot {
        project: project_root.project.clone(),
    })
    .ok()?;

    let mut changed = false;
    let mut items = Vec::new();
    let mut rewritten_lines = Vec::new();
    let mut in_dependencies = false;

    for raw_line in config.raw_toml.lines() {
        let trimmed = raw_line.trim();
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            in_dependencies = trimmed == "[dependencies]";
            rewritten_lines.push(raw_line.to_string());
            continue;
        }

        if in_dependencies && trimmed.contains('=') && !trimmed.starts_with('#') {
            let (name_raw, value_raw) = trimmed.split_once('=')?;
            let name = name_raw.trim().to_string();
            let value = value_raw.trim().trim_matches('"').to_string();
            let targeted = target_package.as_ref().map(|target| target == &name).unwrap_or(true);
            if !targeted {
                rewritten_lines.push(raw_line.to_string());
                continue;
            }
            let (status, reason) = classify_update_preview_item(&value);
            if status == "unchanged" && value.starts_with("git+") && !value.contains('@') {
                changed = true;
                items.push(UpdateItemPreview {
                    name: name.clone(),
                    status: "updated".to_string(),
                    reason: Some("refreshed direct git source".to_string()),
                });
                rewritten_lines.push(format!("{name} = \"{value}\""));
                continue;
            }
            if status == "unchanged" && value.starts_with("url+") {
                changed = true;
                items.push(UpdateItemPreview {
                    name: name.clone(),
                    status: "updated".to_string(),
                    reason: Some("refreshed direct url source".to_string()),
                });
                rewritten_lines.push(format!("{name} = \"{value}\""));
                continue;
            }

            items.push(UpdateItemPreview {
                name,
                status: status.to_string(),
                reason,
            });
            rewritten_lines.push(raw_line.to_string());
            continue;
        }

        rewritten_lines.push(raw_line.to_string());
    }

    if changed {
        let mut output = rewritten_lines.join("\n");
        if !output.ends_with('\n') {
            output.push('\n');
        }
        fs::write(&config.config_path, output).ok()?;
    }

    let updated_count = items.iter().filter(|item| item.status == "updated").count();
    let unchanged_count = items.iter().filter(|item| item.status == "unchanged").count();
    let skipped_count = items.iter().filter(|item| item.status == "skipped").count();

    Some(UpdateWriteResult {
        config_path: config.config_path.display().to_string(),
        status: if changed {
            "updated".to_string()
        } else {
            "unchanged".to_string()
        },
        target: target_package.unwrap_or_else(|| "all".to_string()),
        updated_count,
        unchanged_count,
        skipped_count,
        items,
        mode: if changed {
            "simple-write".to_string()
        } else {
            "no-change".to_string()
        },
    })
}

fn classify_update_preview_item(specifier: &str) -> (&'static str, Option<String>) {
    if specifier.starts_with("git+") && specifier.contains('@') {
        return ("skipped", Some("pinned git ref".to_string()));
    }
    if specifier.starts_with("url+") {
        return ("unchanged", None);
    }
    if !specifier.starts_with("git+") && !specifier.starts_with("url+") {
        return ("skipped", Some("local path dependency".to_string()));
    }
    ("unchanged", None)
}
