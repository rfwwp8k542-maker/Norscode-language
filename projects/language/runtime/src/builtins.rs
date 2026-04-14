use crate::error::RuntimeError;
use crate::stdio::Io;
use crate::value::Value;
use crate::vm::Vm;
use crate::builtins_core::handle_core_builtin;
use crate::builtins_assert::handle_assert_builtin;
use crate::builtins_db::handle_db_builtin;
use crate::builtins_gui::handle_gui_builtin;
use crate::builtins_list::handle_list_builtin;
use crate::builtins_fs::handle_fs_builtin;
use crate::builtins_source::handle_source_builtin;
use crate::builtins_web::handle_web_builtin;
use crate::builtins_text::handle_text_builtin;

impl<I: Io> Vm<I> {
    pub(crate) fn call_builtin(
        &mut self,
        name: &str,
        args: &[Value],
    ) -> Result<Option<Value>, RuntimeError> {
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_fs_builtin(self, candidate, args))? {
            return Ok(Some(value));
        }
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_source_builtin(self, candidate, args))? {
            return Ok(Some(value));
        }
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_web_builtin(self, candidate, args))? {
            return Ok(Some(value));
        }
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_db_builtin(candidate, args))? {
            return Ok(Some(value));
        }
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_text_builtin(candidate, args))? {
            return Ok(Some(value));
        }
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_list_builtin(self, candidate, args))? {
            return Ok(Some(value));
        }
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_gui_builtin(self, candidate, args))? {
            return Ok(Some(value));
        }
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_assert_builtin(candidate, args))? {
            return Ok(Some(value));
        }
        if let Some(value) = try_builtin_aliases(name, |candidate| handle_core_builtin(self, candidate, args))? {
            return Ok(Some(value));
        }
        Ok(None)
    }
}

fn try_builtin_aliases<F>(
    name: &str,
    mut handler: F,
) -> Result<Option<Value>, RuntimeError>
where
    F: FnMut(&str) -> Result<Option<Value>, RuntimeError>,
{
    for candidate in builtin_name_candidates(name) {
        if let Some(value) = handler(&candidate)? {
            return Ok(Some(value));
        }
    }
    Ok(None)
}

fn builtin_name_candidates(name: &str) -> Vec<String> {
    let mut candidates = Vec::new();
    candidates.push(name.to_string());
    if name.contains('.') {
        let parts: Vec<&str> = name.split('.').collect();
        for start in 1..parts.len() {
            candidates.push(parts[start..].join("."));
        }
    }
    candidates
}
