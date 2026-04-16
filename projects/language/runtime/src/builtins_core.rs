use crate::error::RuntimeError;
use crate::stdio::Io;
use crate::value::Value;
use crate::vm::Vm;

pub(crate) fn handle_core_builtin<I: Io>(
    vm: &mut Vm<I>,
    name: &str,
    _args: &[Value],
) -> Result<Option<Value>, RuntimeError> {
    match name {
        "argv" => {
            let items = vm
                .program_args
                .iter()
                .cloned()
                .map(Value::Text)
                .collect();
            Ok(Some(Value::list(items)))
        }
        _ => Ok(None),
    }
}
