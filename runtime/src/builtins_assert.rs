use crate::builtins_text::format_value;
use crate::error::RuntimeError;
use crate::value::Value;

pub(crate) fn handle_assert_builtin(
    name: &str,
    args: &[Value],
) -> Result<Option<Value>, RuntimeError> {
    match name {
        "builtin.assert" | "assert" => {
            let value = args.first().cloned().unwrap_or(Value::Bool(false));
            if !value.is_truthy() {
                return Err(RuntimeError::InvalidOperand("Assert feilet".to_string()));
            }
            Ok(Some(Value::Null))
        }
        "builtin.assert_eq" | "assert_eq" => {
            if args.len() != 2 {
                return Err(RuntimeError::InvalidOperand(
                    "builtin.assert_eq forventer to argumenter".to_string(),
                ));
            }
            if args[0] != args[1] {
                return Err(RuntimeError::InvalidOperand(format!(
                    "assert_eq feilet: {} != {}",
                    format_value(&args[0]),
                    format_value(&args[1])
                )));
            }
            Ok(Some(Value::Null))
        }
        "builtin.assert_ne" | "assert_ne" => {
            if args.len() != 2 {
                return Err(RuntimeError::InvalidOperand(
                    "builtin.assert_ne forventer to argumenter".to_string(),
                ));
            }
            if args[0] == args[1] {
                return Err(RuntimeError::InvalidOperand(format!(
                    "assert_ne feilet: {} == {}",
                    format_value(&args[0]),
                    format_value(&args[1])
                )));
            }
            Ok(Some(Value::Null))
        }
        _ => Ok(None),
    }
}
