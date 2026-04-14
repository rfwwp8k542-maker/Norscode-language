use crate::error::RuntimeError;
use crate::value::Value;
use postgres::types::{ToSql, Type};
use postgres::{Client, NoTls, Row};
use std::cell::RefCell;
use std::collections::BTreeMap;
use std::env;

thread_local! {
    static DB_RUNTIME: RefCell<DbRuntime> = RefCell::new(DbRuntime::default());
}

#[derive(Default)]
struct DbRuntime {
    next_handle: usize,
    default_handle: Option<String>,
    connections: BTreeMap<String, DbConnection>,
}

struct DbConnection {
    client: Client,
}

pub fn initialize_from_env() -> Result<(), RuntimeError> {
    DB_RUNTIME.with(|runtime| {
        let mut runtime = runtime.borrow_mut();
        *runtime = DbRuntime::from_env()?;
        Ok(())
    })
}

pub fn open_connection(url: &str) -> Result<String, RuntimeError> {
    DB_RUNTIME.with(|runtime| runtime.borrow_mut().open_connection(url))
}

pub fn close_connection(handle: &str) -> Result<(), RuntimeError> {
    DB_RUNTIME.with(|runtime| runtime.borrow_mut().close_connection(handle))
}

pub fn exec(handle: Option<&str>, sql: &str, params: &[Value]) -> Result<i64, RuntimeError> {
    DB_RUNTIME.with(|runtime| runtime.borrow_mut().exec(handle, sql, params))
}

pub fn query(handle: Option<&str>, sql: &str, params: &[Value]) -> Result<Vec<String>, RuntimeError> {
    DB_RUNTIME.with(|runtime| runtime.borrow_mut().query(handle, sql, params))
}

pub fn begin(handle: Option<&str>) -> Result<String, RuntimeError> {
    DB_RUNTIME.with(|runtime| runtime.borrow_mut().begin(handle))
}

pub fn commit(handle: &str) -> Result<(), RuntimeError> {
    DB_RUNTIME.with(|runtime| runtime.borrow_mut().commit(handle))
}

pub fn rollback(handle: &str) -> Result<(), RuntimeError> {
    DB_RUNTIME.with(|runtime| runtime.borrow_mut().rollback(handle))
}

impl DbRuntime {
    fn from_env() -> Result<Self, RuntimeError> {
        let backend = env::var("HELPDESK_STORAGE_BACKEND")
            .unwrap_or_default()
            .trim()
            .to_ascii_lowercase();
        let database_url = env::var("DATABASE_URL")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());

        if backend == "postgres" && database_url.is_none() {
            return Err(RuntimeError::DbError(
                "HELPDESK_STORAGE_BACKEND=postgres krever DATABASE_URL".to_string(),
            ));
        }

        let mut runtime = Self::default();
        if backend == "postgres" {
            let Some(url) = database_url else {
                return Err(RuntimeError::DbError(
                    "HELPDESK_STORAGE_BACKEND=postgres krever DATABASE_URL".to_string(),
                ));
            };
            let handle = runtime.open_connection(&url)?;
            runtime.default_handle = Some(handle);
        }
        Ok(runtime)
    }

    fn open_connection(&mut self, url: &str) -> Result<String, RuntimeError> {
        let url = url.trim();
        if url.is_empty() {
            return Err(RuntimeError::DbError("DATABASE_URL kan ikke være tom".to_string()));
        }
        let client = Client::connect(url, NoTls).map_err(map_db_error)?;
        let handle = self.new_handle();
        self.connections.insert(handle.clone(), DbConnection { client });
        Ok(handle)
    }

    fn close_connection(&mut self, handle: &str) -> Result<(), RuntimeError> {
        let resolved = self.resolve_handle(Some(handle))?;
        self.connections.remove(&resolved);
        if self.default_handle.as_deref() == Some(resolved.as_str()) {
            self.default_handle = None;
        }
        Ok(())
    }

    fn exec(&mut self, handle: Option<&str>, sql: &str, params: &[Value]) -> Result<i64, RuntimeError> {
        let resolved = self.resolve_handle(handle)?;
        let client = self.connection_mut(&resolved)?;
        let boxed_params = build_params(params)?;
        let param_refs = boxed_params
            .iter()
            .map(|param| param.as_ref() as &(dyn ToSql + Sync))
            .collect::<Vec<_>>();
        let affected = client
            .client
            .execute(sql, &param_refs)
            .map_err(map_db_error)?;
        Ok(affected as i64)
    }

    fn query(
        &mut self,
        handle: Option<&str>,
        sql: &str,
        params: &[Value],
    ) -> Result<Vec<String>, RuntimeError> {
        let resolved = self.resolve_handle(handle)?;
        let client = self.connection_mut(&resolved)?;
        let boxed_params = build_params(params)?;
        let param_refs = boxed_params
            .iter()
            .map(|param| param.as_ref() as &(dyn ToSql + Sync))
            .collect::<Vec<_>>();
        let rows = client
            .client
            .query(sql, &param_refs)
            .map_err(map_db_error)?;
        Ok(rows.into_iter().map(row_to_text).collect())
    }

    fn begin(&mut self, handle: Option<&str>) -> Result<String, RuntimeError> {
        let resolved = self.resolve_handle(handle)?;
        let client = self.connection_mut(&resolved)?;
        client
            .client
            .batch_execute("BEGIN")
            .map_err(map_db_error)?;
        Ok(resolved)
    }

    fn commit(&mut self, handle: &str) -> Result<(), RuntimeError> {
        let resolved = self.resolve_handle(Some(handle))?;
        let client = self.connection_mut(&resolved)?;
        client
            .client
            .batch_execute("COMMIT")
            .map_err(map_db_error)?;
        Ok(())
    }

    fn rollback(&mut self, handle: &str) -> Result<(), RuntimeError> {
        let resolved = self.resolve_handle(Some(handle))?;
        let client = self.connection_mut(&resolved)?;
        client
            .client
            .batch_execute("ROLLBACK")
            .map_err(map_db_error)?;
        Ok(())
    }

    fn resolve_handle(&self, handle: Option<&str>) -> Result<String, RuntimeError> {
        let candidate = handle
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToString::to_string)
            .or_else(|| self.default_handle.clone())
            .ok_or_else(|| RuntimeError::DbError("ingen aktiv databaseforbindelse".to_string()))?;
        if self.connections.contains_key(&candidate) {
            return Ok(candidate);
        }
        Err(RuntimeError::DbError(format!("ukjent databaseforbindelse: {candidate}")))
    }

    fn connection_mut(&mut self, handle: &str) -> Result<&mut DbConnection, RuntimeError> {
        self.connections
            .get_mut(handle)
            .ok_or_else(|| RuntimeError::DbError(format!("ukjent databaseforbindelse: {handle}")))
    }

    fn new_handle(&mut self) -> String {
        self.next_handle += 1;
        format!("db:{}", self.next_handle)
    }
}

fn build_params(values: &[Value]) -> Result<Vec<Box<dyn ToSql + Sync>>, RuntimeError> {
    let mut params = Vec::with_capacity(values.len());
    for value in values {
        params.push(build_param(value)?);
    }
    Ok(params)
}

fn build_param(value: &Value) -> Result<Box<dyn ToSql + Sync>, RuntimeError> {
    match value {
        Value::Int(number) => Ok(Box::new(*number)),
        Value::Bool(flag) => Ok(Box::new(*flag)),
        Value::Text(text) => Ok(Box::new(text.clone())),
        Value::Null => Ok(Box::new(Option::<String>::None)),
        Value::List(_) => Err(RuntimeError::DbError(
            "DB-parametere kan ikke være lister".to_string(),
        )),
    }
}

fn row_to_text(row: Row) -> String {
    row.columns()
        .iter()
        .enumerate()
        .map(|(index, column)| format_value(&row_cell_to_value(&row, index, column.type_())))
        .collect::<Vec<_>>()
        .join("|")
}

fn row_cell_to_value(row: &Row, index: usize, ty: &Type) -> Value {
    match *ty {
        Type::BOOL => row
            .try_get::<usize, Option<bool>>(index)
            .ok()
            .flatten()
            .map(Value::Bool)
            .unwrap_or(Value::Null),
        Type::INT2 => row
            .try_get::<usize, Option<i16>>(index)
            .ok()
            .flatten()
            .map(|value| Value::Int(value as i64))
            .unwrap_or(Value::Null),
        Type::INT4 => row
            .try_get::<usize, Option<i32>>(index)
            .ok()
            .flatten()
            .map(|value| Value::Int(value as i64))
            .unwrap_or(Value::Null),
        Type::INT8 => row
            .try_get::<usize, Option<i64>>(index)
            .ok()
            .flatten()
            .map(Value::Int)
            .unwrap_or(Value::Null),
        Type::TEXT | Type::VARCHAR | Type::BPCHAR | Type::NAME | Type::UUID | Type::JSON | Type::JSONB => row
            .try_get::<usize, Option<String>>(index)
            .ok()
            .flatten()
            .map(Value::Text)
            .unwrap_or(Value::Null),
        _ => row
            .try_get::<usize, Option<String>>(index)
            .ok()
            .flatten()
            .map(Value::Text)
            .unwrap_or(Value::Null),
    }
}

fn map_db_error(err: postgres::Error) -> RuntimeError {
    RuntimeError::DbError(err.to_string())
}
