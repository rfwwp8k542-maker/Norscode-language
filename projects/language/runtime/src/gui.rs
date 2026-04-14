use crate::error::RuntimeError;
use crate::value::Value;
use std::collections::BTreeMap;
use std::path::Path;

#[derive(Debug, Clone)]
struct GuiObject {
    kind: String,
    parent: Option<usize>,
    text: String,
    visible: bool,
    items: Vec<String>,
    selected_index: isize,
    cursor_line: i64,
    cursor_col: i64,
    click_callback: Option<String>,
    change_callback: Option<String>,
    key_callbacks: BTreeMap<String, String>,
}

#[derive(Debug, Clone)]
pub struct GuiState {
    next_id: usize,
    objects: BTreeMap<usize, GuiObject>,
}

impl GuiState {
    pub fn new() -> Self {
        Self {
            next_id: 1,
            objects: BTreeMap::new(),
        }
    }

    pub fn parent_from_value(value: Option<&Value>) -> Result<Option<usize>, RuntimeError> {
        match value {
            None | Some(Value::Null) => Ok(None),
            Some(Value::Int(n)) if *n >= 0 => Ok(Some(*n as usize)),
            Some(other) => Err(RuntimeError::InvalidOperand(format!(
                "GUI-forelder må være et heltall, fikk {other:?}"
            ))),
        }
    }

    pub fn create_window(&mut self, title: &str) -> usize {
        self.create_widget("window", None, title)
    }

    pub fn create_widget(&mut self, kind: &str, parent: Option<usize>, text: &str) -> usize {
        let object_id = self.next_id;
        self.next_id += 1;
        self.objects.insert(
            object_id,
            GuiObject {
                kind: kind.to_string(),
                parent,
                text: text.to_string(),
                visible: false,
                items: Vec::new(),
                selected_index: -1,
                cursor_line: 1,
                cursor_col: 1,
                click_callback: None,
                change_callback: None,
                key_callbacks: BTreeMap::new(),
            },
        );
        object_id
    }

    pub fn parent_of(&self, object_id: usize) -> Result<usize, RuntimeError> {
        let obj = self.get(object_id)?;
        Ok(obj.parent.unwrap_or(0))
    }

    pub fn child_at(&self, parent_id: usize, index: usize) -> Result<usize, RuntimeError> {
        let children: Vec<usize> = self
            .objects
            .iter()
            .filter(|(_, obj)| obj.parent == Some(parent_id))
            .map(|(object_id, _)| *object_id)
            .collect();
        if index >= children.len() {
            return Ok(0);
        }
        Ok(children[index])
    }

    pub fn editor_jump_to_line(&mut self, object_id: usize, line_number: i64) -> Result<usize, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        if obj.kind != "editor" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en editor"
            )));
        }
        let line = if line_number < 1 { 1 } else { line_number };
        obj.cursor_line = line;
        obj.cursor_col = 1;
        Ok(object_id)
    }

    pub fn editor_cursor(&self, object_id: usize) -> Result<Value, RuntimeError> {
        let obj = self.get(object_id)?;
        if obj.kind != "editor" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en editor"
            )));
        }
        Ok(Value::list(vec![
            Value::Text(obj.cursor_line.to_string()),
            Value::Text(obj.cursor_col.to_string()),
        ]))
    }

    pub fn editor_replace_range(
        &mut self,
        object_id: usize,
        start_line: i64,
        start_col: i64,
        end_line: i64,
        end_col: i64,
        replacement: &str,
    ) -> Result<Option<String>, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        if obj.kind != "editor" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en editor"
            )));
        }
        let (updated, cursor_line, cursor_col) = replace_text_range(
            &obj.text,
            start_line,
            start_col,
            end_line,
            end_col,
            replacement,
        );
        obj.text = updated;
        obj.cursor_line = cursor_line;
        obj.cursor_col = cursor_col;
        Ok(obj.change_callback.clone())
    }

    pub fn list_add(&mut self, object_id: usize, text: &str) -> Result<usize, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        if obj.kind != "list" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en liste"
            )));
        }
        obj.items.push(text.to_string());
        Ok(object_id)
    }

    pub fn list_clear(&mut self, object_id: usize) -> Result<usize, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        if obj.kind != "list" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en liste"
            )));
        }
        obj.items.clear();
        obj.selected_index = -1;
        Ok(object_id)
    }

    pub fn list_len(&self, object_id: usize) -> Result<usize, RuntimeError> {
        let obj = self.get(object_id)?;
        if obj.kind != "list" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en liste"
            )));
        }
        Ok(obj.items.len())
    }

    pub fn list_get(&self, object_id: usize, index: i64) -> Result<String, RuntimeError> {
        let obj = self.get(object_id)?;
        if obj.kind != "list" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en liste"
            )));
        }
        if index >= 0 {
            let index = index as usize;
            if index < obj.items.len() {
                return Ok(obj.items[index].clone());
            }
        }
        Ok(String::new())
    }

    pub fn list_remove(&mut self, object_id: usize, index: i64) -> Result<Option<String>, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        if obj.kind != "list" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en liste"
            )));
        }
        if index >= 0 {
            let index = index as usize;
            if index < obj.items.len() {
                obj.items.remove(index);
                let selected = obj.selected_index;
                if selected == index as isize {
                    obj.selected_index = -1;
                    return Ok(obj.change_callback.clone());
                }
                if selected > index as isize {
                    obj.selected_index -= 1;
                }
            }
        }
        Ok(None)
    }

    pub fn list_selected_text(&self, object_id: usize) -> Result<String, RuntimeError> {
        let obj = self.get(object_id)?;
        if obj.kind != "list" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en liste"
            )));
        }
        if obj.selected_index >= 0 {
            let index = obj.selected_index as usize;
            if index < obj.items.len() {
                return Ok(obj.items[index].clone());
            }
        }
        Ok(String::new())
    }

    pub fn list_select(&mut self, object_id: usize, index: i64) -> Result<Option<String>, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        if obj.kind != "list" {
            return Err(RuntimeError::InvalidOperand(format!(
                "GUI-elementet {object_id} er ikke en liste"
            )));
        }
        let previous = obj.selected_index;
        if index >= 0 {
            let index = index as usize;
            obj.selected_index = if index < obj.items.len() {
                index as isize
            } else {
                -1
            };
        } else {
            obj.selected_index = -1;
        }
        if obj.selected_index != previous {
            return Ok(obj.change_callback.clone());
        }
        Ok(None)
    }

    pub fn register_click(&mut self, object_id: usize, callback_name: &str) -> Result<usize, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        obj.click_callback = Some(callback_name.to_string());
        Ok(object_id)
    }

    pub fn register_change(&mut self, object_id: usize, callback_name: &str) -> Result<usize, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        obj.change_callback = Some(callback_name.to_string());
        Ok(object_id)
    }

    pub fn register_key(
        &mut self,
        object_id: usize,
        key_name: &str,
        callback_name: &str,
    ) -> Result<usize, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        obj.key_callbacks
            .insert(normalize_key_name(key_name), callback_name.to_string());
        Ok(object_id)
    }

    pub fn trigger_click(&self, object_id: usize) -> Result<Option<String>, RuntimeError> {
        let obj = self.get(object_id)?;
        Ok(obj.click_callback.clone())
    }

    pub fn trigger_key(&self, object_id: usize, key_name: &str) -> Result<Option<String>, RuntimeError> {
        let obj = self.get(object_id)?;
        Ok(obj.key_callbacks.get(&normalize_key_name(key_name)).cloned())
    }

    pub fn set_text(&mut self, object_id: usize, text: &str) -> Result<Option<String>, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        obj.text = text.to_string();
        if obj.kind == "text_field" {
            return Ok(obj.change_callback.clone());
        }
        Ok(None)
    }

    pub fn get_text(&self, object_id: usize) -> Result<String, RuntimeError> {
        Ok(self.get(object_id)?.text.clone())
    }

    pub fn show(&mut self, object_id: usize) -> Result<usize, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        obj.visible = true;
        Ok(object_id)
    }

    pub fn close(&mut self, object_id: usize) -> Result<usize, RuntimeError> {
        let obj = self.get_mut(object_id)?;
        obj.visible = false;
        Ok(object_id)
    }

    pub fn list_files_tree(root: &str) -> Vec<String> {
        let root = expand_path(root);
        if !root.exists() {
            return Vec::new();
        }
        let mut result = Vec::new();
        collect_tree_entries(&root, &root, "", &mut result);
        result
    }

    fn get(&self, object_id: usize) -> Result<&GuiObject, RuntimeError> {
        self.objects
            .get(&object_id)
            .ok_or_else(|| RuntimeError::InvalidOperand(format!("Ukjent GUI-element: {object_id}")))
    }

    fn get_mut(&mut self, object_id: usize) -> Result<&mut GuiObject, RuntimeError> {
        self.objects
            .get_mut(&object_id)
            .ok_or_else(|| RuntimeError::InvalidOperand(format!("Ukjent GUI-element: {object_id}")))
    }
}

fn normalize_key_name(key_name: &str) -> String {
    let lowered = key_name.trim().to_lowercase();
    match lowered.as_str() {
        "return" | "kp_enter" => "enter".to_string(),
        "tab" => "tab".to_string(),
        "ctrl+space" | "ctrl-space" | "control+space" | "control-space" => "ctrl+space".to_string(),
        other => other.to_string(),
    }
}

fn replace_text_range(
    text: &str,
    start_line: i64,
    start_col: i64,
    end_line: i64,
    end_col: i64,
    replacement: &str,
) -> (String, i64, i64) {
    let mut lines: Vec<String> = if text.is_empty() {
        vec![String::new()]
    } else {
        text.split('\n').map(ToString::to_string).collect()
    };
    let start_line = start_line.max(1) as usize;
    let start_col = start_col.max(1) as usize;
    let end_line = end_line.max(start_line as i64) as usize;
    let end_col = end_col.max(1) as usize;

    if start_line > lines.len() {
        lines.resize(start_line, String::new());
    }
    if end_line > lines.len() {
        lines.resize(end_line, String::new());
    }

    let start_idx = start_line - 1;
    let end_idx = end_line - 1;
    let prefix = lines[start_idx][..start_col.saturating_sub(1).min(lines[start_idx].len())].to_string();
    let suffix = lines[end_idx][end_col.saturating_sub(1).min(lines[end_idx].len())..].to_string();

    if start_idx == end_idx {
        lines[start_idx] = format!("{prefix}{replacement}{suffix}");
    } else {
        lines.splice(start_idx..=end_idx, [format!("{prefix}{replacement}{suffix}")]);
    }

    let updated = lines.join("\n");
    if replacement.contains('\n') {
        let repl_lines: Vec<&str> = replacement.split('\n').collect();
        let cursor_line = start_line as i64 + repl_lines.len() as i64 - 1;
        let cursor_col = repl_lines.last().map(|line| line.chars().count() as i64 + 1).unwrap_or(1);
        (updated, cursor_line, cursor_col)
    } else {
        (updated, start_line as i64, start_col as i64 + replacement.chars().count() as i64)
    }
}

fn expand_path(input: &str) -> std::path::PathBuf {
    let trimmed = input.trim();
    if trimmed == "~" {
        return home_dir().unwrap_or_else(|| std::path::PathBuf::from(trimmed));
    }
    if let Some(rest) = trimmed.strip_prefix("~/") {
        if let Some(home) = home_dir() {
            return home.join(rest);
        }
    }
    std::path::PathBuf::from(trimmed)
}

fn home_dir() -> Option<std::path::PathBuf> {
    if let Some(home) = std::env::var_os("HOME") {
        if !home.is_empty() {
            return Some(std::path::PathBuf::from(home));
        }
    }
    if let Some(profile) = std::env::var_os("USERPROFILE") {
        if !profile.is_empty() {
            return Some(std::path::PathBuf::from(profile));
        }
    }
    None
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
