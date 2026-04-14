use crate::error::RuntimeError;
use crate::builtins_text::format_value;
use crate::stdio::Io;
use crate::value::Value;
use crate::vm::Vm;
use std::path::{Path, PathBuf};
use std::process::Command;

pub(crate) fn handle_fs_builtin<I: Io>(
    vm: &mut Vm<I>,
    name: &str,
    args: &[Value],
) -> Result<Option<Value>, RuntimeError> {
    match name {
        "fil_eksisterer" => {
            let path = args.first().map(format_value).unwrap_or_default();
            let exists = expand_path(&path).exists();
            Ok(Some(Value::Bool(exists)))
        }
        "les_miljo" => {
            let key = args.first().map(format_value).unwrap_or_default();
            let value = std::env::var(&key).unwrap_or_default();
            Ok(Some(Value::Text(value)))
        }
        "les_input" => Ok(Some(Value::Text(String::new()))),
        "kjør_kommando" | "kjor_kommando" => {
            let command = match args.first() {
                Some(Value::List(items)) => items.borrow().iter().map(format_value).collect::<Vec<_>>(),
                Some(other) => vec![format_value(other)],
                None => Vec::new(),
            };
            if command.is_empty() {
                return Ok(Some(Value::Int(1)));
            }
            let status = Command::new(&command[0])
                .args(&command[1..])
                .status()
                .map_err(|err| RuntimeError::IoError(err.to_string()))?;
            Ok(Some(Value::Int(status.code().unwrap_or(1) as i64)))
        }
        "les_fil" => {
            let path = args.first().map(format_value).unwrap_or_default();
            let text = std::fs::read_to_string(expand_path(&path)).unwrap_or_default();
            Ok(Some(Value::Text(text)))
        }
        "skriv_fil" => {
            let path = args.first().map(format_value).unwrap_or_default();
            let content = args.get(1).map(format_value).unwrap_or_default();
            let path = expand_path(&path);
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent)
                    .map_err(|err| RuntimeError::IoError(err.to_string()))?;
            }
            std::fs::write(&path, content).map_err(|err| RuntimeError::IoError(err.to_string()))?;
            Ok(Some(Value::Int(1)))
        }
        "liste_filer" => {
            let root = args.first().map(format_value).unwrap_or_else(|| ".".to_string());
            let result = collect_files(expand_path(&root), false);
            Ok(Some(Value::list(result.into_iter().map(Value::Text).collect())))
        }
        "liste_filer_tre" => {
            let root = args.first().map(format_value).unwrap_or_else(|| ".".to_string());
            let result = collect_files(expand_path(&root), true);
            Ok(Some(Value::list(result.into_iter().map(Value::Text).collect())))
        }
        "builtin.skriv" => {
            let text = args.first().map(format_value).unwrap_or_else(|| "".to_string());
            vm.io.print(&format!("{text}\n"))?;
            Ok(Some(Value::Null))
        }
        _ => Ok(None),
    }
}

fn expand_path(input: &str) -> PathBuf {
    let trimmed = input.trim();
    if trimmed == "~" {
        return home_dir().unwrap_or_else(|| PathBuf::from(trimmed));
    }
    if let Some(rest) = trimmed.strip_prefix("~/") {
        if let Some(home) = home_dir() {
            return home.join(rest);
        }
    }
    PathBuf::from(trimmed)
}

fn home_dir() -> Option<PathBuf> {
    if let Some(home) = std::env::var_os("HOME") {
        if !home.is_empty() {
            return Some(PathBuf::from(home));
        }
    }
    if let Some(profile) = std::env::var_os("USERPROFILE") {
        if !profile.is_empty() {
            return Some(PathBuf::from(profile));
        }
    }
    None
}

fn collect_files(root: PathBuf, tree: bool) -> Vec<String> {
    if !root.exists() {
        return Vec::new();
    }
    if tree {
        let mut result = Vec::new();
        collect_tree_entries(&root, &root, "", &mut result);
        return result;
    }

    let mut result = Vec::new();
    let mut stack = vec![root.clone()];
    while let Some(path) = stack.pop() {
        if let Ok(entries) = std::fs::read_dir(&path) {
            for entry in entries.flatten() {
                let child = entry.path();
                let name = entry.file_name().to_string_lossy().to_string();
                if name.starts_with('.') {
                    continue;
                }
                if child.is_dir() {
                    if !["build", "dist", "__pycache__", ".venv"].contains(&name.as_str()) {
                        stack.push(child);
                    }
                } else if matches!(child.extension().and_then(|ext| ext.to_str()), Some("no" | "md" | "toml" | "py" | "sh" | "ps1")) {
                    if let Ok(rel) = child.strip_prefix(&root) {
                        result.push(rel.to_string_lossy().replace('\\', "/"));
                    } else {
                        result.push(child.to_string_lossy().replace('\\', "/"));
                    }
                }
            }
        }
    }
    result.sort();
    result
}

fn collect_tree_entries(root: &Path, path: &Path, prefix: &str, result: &mut Vec<String>) {
    let Ok(entries) = std::fs::read_dir(path) else {
        return;
    };
    let mut children: Vec<_> = entries.flatten().collect();
    children.sort_by_key(|entry| {
        let child = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        (!child.is_dir(), name.to_lowercase())
    });
    for entry in children {
        let child = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with('.') || ["build", "dist", "__pycache__", ".venv"].contains(&name.as_str()) {
            continue;
        }
        if child.is_dir() {
            result.push(format!("{prefix}{name}/"));
            let next_prefix = format!("{prefix}  ");
            collect_tree_entries(root, &child, &next_prefix, result);
        } else if matches!(child.extension().and_then(|ext| ext.to_str()), Some("no" | "md" | "toml" | "py" | "sh" | "ps1")) {
            if let Ok(rel) = child.strip_prefix(root) {
                result.push(format!("{prefix}{}", rel.to_string_lossy().replace('\\', "/")));
            } else {
                result.push(format!("{prefix}{}", child.file_name().unwrap_or_default().to_string_lossy()));
            }
        }
    }
}
