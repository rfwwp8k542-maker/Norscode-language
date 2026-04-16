use crate::error::RuntimeError;
use crate::stdio::Io;
use crate::value::Value;
use crate::vm::Vm;

pub(crate) fn handle_list_builtin<I: Io>(
    _vm: &mut Vm<I>,
    name: &str,
    args: &[Value],
) -> Result<Option<Value>, RuntimeError> {
    match name {
        "legg_til" | "builtin.legg_til" | "std.liste.legg_til" | "__main__.legg_til" => {
            let Some(Value::List(items)) = args.first() else {
                return Err(RuntimeError::InvalidOperand("legg_til forventer liste".to_string()));
            };
            let value = args.get(1).cloned().unwrap_or(Value::Null);
            items.borrow_mut().push(value);
            Ok(Some(Value::Null))
        }
        "pop_siste" | "builtin.pop_siste" | "std.liste.pop_siste" | "__main__.pop_siste" => {
            let Some(Value::List(items)) = args.first() else {
                return Err(RuntimeError::InvalidOperand("pop_siste forventer liste".to_string()));
            };
            let mut items = items.borrow_mut();
            if let Some(value) = items.pop() {
                Ok(Some(value))
            } else {
                Ok(Some(Value::Int(0)))
            }
        }
        "fjern_indeks" | "builtin.fjern_indeks" | "std.liste.fjern_indeks" | "__main__.fjern_indeks" => {
            let Some(Value::List(items)) = args.first() else {
                return Err(RuntimeError::InvalidOperand("fjern_indeks forventer liste".to_string()));
            };
            let index = match args.get(1) {
                Some(Value::Int(n)) if *n >= 0 => *n as usize,
                Some(Value::Int(_)) => {
                    let items = items.borrow();
                    return Ok(Some(Value::Int(items.len() as i64)));
                }
                Some(_) => {
                    return Err(RuntimeError::InvalidOperand("fjern_indeks forventer heltall som indeks".to_string()));
                }
                None => return Err(RuntimeError::InvalidOperand("mangler indeks".to_string())),
            };
            let mut items = items.borrow_mut();
            if index >= items.len() {
                return Ok(Some(Value::Int(items.len() as i64)));
            }
            items.remove(index);
            Ok(Some(Value::Int(items.len() as i64)))
        }
        "sett_inn" | "builtin.sett_inn" | "std.liste.sett_inn" | "__main__.sett_inn" => {
            let Some(Value::List(items)) = args.first() else {
                return Err(RuntimeError::InvalidOperand("sett_inn forventer liste".to_string()));
            };
            let index = match args.get(1) {
                Some(Value::Int(n)) => *n,
                Some(_) => {
                    return Err(RuntimeError::InvalidOperand("sett_inn forventer heltall som indeks".to_string()));
                }
                None => return Err(RuntimeError::InvalidOperand("mangler indeks".to_string())),
            };
            let value = args.get(2).cloned().unwrap_or(Value::Null);
            let mut items = items.borrow_mut();
            let idx = index.max(0) as usize;
            if idx < items.len() {
                items[idx] = value;
            } else if idx == items.len() {
                items.push(value);
            } else {
                let fill_value = if matches!(items.first(), Some(Value::Text(_))) {
                    Value::Text(String::new())
                } else {
                    Value::Int(0)
                };
                while items.len() < idx {
                    items.push(fill_value.clone());
                }
                items.push(value);
            }
            Ok(Some(Value::Null))
        }
        _ => Ok(None),
    }
}
