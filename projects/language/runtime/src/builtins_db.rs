use crate::builtins_text::format_value;
use crate::db;
use crate::error::RuntimeError;
use crate::value::Value;

pub(crate) fn handle_db_builtin(
    name: &str,
    args: &[Value],
) -> Result<Option<Value>, RuntimeError> {
    match name {
        "db_open" | "db.open" => {
            let url = args.first().map(format_value).unwrap_or_default();
            let handle = db::open_connection(&url)?;
            Ok(Some(Value::Text(handle)))
        }
        "db_close" | "db.close" => {
            let handle = args.first().map(format_value).unwrap_or_default();
            db::close_connection(&handle)?;
            Ok(Some(Value::Null))
        }
        "db_begin" | "db.begin" => {
            let handle = args
                .first()
                .filter(|value| is_db_handle(value))
                .map(format_value);
            let tx_handle = db::begin(handle.as_deref())?;
            Ok(Some(Value::Text(tx_handle)))
        }
        "db_commit" | "db.commit" => {
            let handle = args.first().map(format_value).unwrap_or_default();
            db::commit(&handle)?;
            Ok(Some(Value::Null))
        }
        "db_rollback" | "db.rollback" => {
            let handle = args.first().map(format_value).unwrap_or_default();
            db::rollback(&handle)?;
            Ok(Some(Value::Null))
        }
        "db_exec" | "db.exec" => {
            let (handle, sql, params) = parse_db_call(args)?;
            let affected = db::exec(handle.as_deref(), &sql, &params)?;
            Ok(Some(Value::Int(affected)))
        }
        "db_query" | "db.query" => {
            let (handle, sql, params) = parse_db_call(args)?;
            let rows = db::query(handle.as_deref(), &sql, &params)?;
            let rows = rows.into_iter().map(Value::Text).collect();
            Ok(Some(Value::list(rows)))
        }
        _ => Ok(None),
    }
}

fn parse_db_call(args: &[Value]) -> Result<(Option<String>, String, Vec<Value>), RuntimeError> {
    match args {
        [] => Err(RuntimeError::DbError(
            "mangler databaseargumenter".to_string(),
        )),
        [sql] => Ok((None, format_value(sql), Vec::new())),
        [sql, params] if matches!(params, Value::List(_)) => Ok((None, format_value(sql), list_values(params))),
        [handle, sql] if is_db_handle(handle) => Ok((Some(format_value(handle)), format_value(sql), Vec::new())),
        [sql, params] => Ok((None, format_value(sql), vec![params.clone()])),
        [handle, sql, params] if is_db_handle(handle) && matches!(params, Value::List(_)) => {
            Ok((Some(format_value(handle)), format_value(sql), list_values(params)))
        }
        [handle, sql, rest @ ..] if is_db_handle(handle) => {
            Ok((Some(format_value(handle)), format_value(sql), rest.to_vec()))
        }
        [sql, params @ ..] => {
            let mut collected = Vec::new();
            if !params.is_empty() {
                collected.extend_from_slice(params);
            }
            Ok((None, format_value(sql), collected))
        }
    }
}

fn is_db_handle(value: &Value) -> bool {
    match value {
        Value::Text(text) => text.starts_with("db:") || text.starts_with("tx:"),
        _ => false,
    }
}

fn list_values(value: &Value) -> Vec<Value> {
    match value {
        Value::List(items) => items.borrow().clone(),
        _ => vec![value.clone()],
    }
}
