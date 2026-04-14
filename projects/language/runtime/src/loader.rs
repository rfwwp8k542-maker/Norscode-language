use crate::error::RuntimeError;
use crate::operand::Operand;
use crate::opcode::Opcode;
use crate::value::Value;
use serde::Deserialize;
use serde_json::Value as JsonValue;
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

const BYTECODE_FORMAT: &str = "norscode-bytecode-v1";

#[derive(Debug, Clone)]
pub struct Instruction {
    pub opcode: Opcode,
    pub operands: Vec<Operand>,
}

#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct Function {
    pub name: String,
    pub module: String,
    pub params: Vec<String>,
    pub code: Vec<Instruction>,
    pub labels: BTreeMap<String, usize>,
}

#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct Program {
    pub format: String,
    pub entry: String,
    pub imports: Vec<(String, String)>,
    pub functions: BTreeMap<String, Function>,
    pub globals: BTreeMap<String, Value>,
    pub constants: Vec<Value>,
}

#[derive(Debug, Deserialize)]
struct RawProgram {
    format: String,
    entry: String,
    #[serde(default)]
    imports: Vec<RawImport>,
    #[serde(default)]
    functions: BTreeMap<String, RawFunction>,
    #[serde(default)]
    globals: BTreeMap<String, JsonValue>,
    #[serde(default)]
    constants: Vec<JsonValue>,
}

#[derive(Debug, Deserialize)]
struct RawImport {
    module: String,
    alias: String,
}

#[derive(Debug, Deserialize)]
struct RawFunction {
    name: String,
    module: String,
    #[serde(default)]
    params: Vec<String>,
    #[serde(default)]
    code: Vec<RawInstruction>,
}

#[derive(Debug, Deserialize)]
struct RawInstruction(Vec<JsonValue>);

impl RawInstruction {
    fn into_instruction(self) -> Result<Instruction, RuntimeError> {
        let mut parts = self.0.into_iter();
        let Some(op_value) = parts.next() else {
            return Err(RuntimeError::InvalidFormat("tom instruksjon mangler opcode".to_string()));
        };
        let Some(op_name) = op_value.as_str() else {
            return Err(RuntimeError::InvalidFormat("opcode må være tekst".to_string()));
        };
        let opcode = Opcode::parse(op_name)
            .ok_or_else(|| RuntimeError::InvalidOpcode(op_name.to_string()))?;

        let mut operands = Vec::new();
        for value in parts {
            operands.push(parse_operand(op_name, &value)?);
        }

        validate_arity(op_name, operands.len())?;
        Ok(Instruction { opcode, operands })
    }
}

fn build_labels(function_name: &str, code: &[Instruction]) -> Result<BTreeMap<String, usize>, RuntimeError> {
    let mut labels = BTreeMap::new();
    for (index, instr) in code.iter().enumerate() {
        if matches!(instr.opcode, Opcode::Label) {
            if let Some(Operand::Label(name)) = instr.operands.first() {
                if name.trim().is_empty() {
                    return Err(RuntimeError::InvalidFormat(format!(
                        "label kan ikke være tom i funksjon {function_name}"
                    )));
                }
                if labels.insert(name.clone(), index).is_some() {
                    return Err(RuntimeError::InvalidFormat(format!(
                        "duplisert label i funksjon {function_name}: {name}"
                    )));
                }
            }
        }
    }
    Ok(labels)
}

fn validate_jump_targets(function_name: &str, code: &[Instruction], labels: &BTreeMap<String, usize>) -> Result<(), RuntimeError> {
    for instr in code {
        let target = match instr.opcode {
            Opcode::Jump | Opcode::JumpIfFalse => match instr.operands.first() {
                Some(Operand::Label(name)) => Some(name),
                _ => None,
            },
            _ => None,
        };
        if let Some(target) = target {
            if !labels.contains_key(target) {
                return Err(RuntimeError::InvalidJumpTarget(format!(
                    "{function_name}:{target}"
                )));
            }
        }
    }
    Ok(())
}

fn validate_function_identity(key: &str, function: &RawFunction) -> Result<(), RuntimeError> {
    if function.module.trim().is_empty() {
        return Err(RuntimeError::InvalidFormat(format!(
            "funksjonsmodul kan ikke være tom for nøkkel {key}"
        )));
    }
    if function.name.trim().is_empty() {
        return Err(RuntimeError::InvalidFormat(format!(
            "funksjonsnavn kan ikke være tomt for nøkkel {key}"
        )));
    }
    let expected = format!("{}.{}", function.module, function.name);
    if key != expected {
        return Err(RuntimeError::InvalidFormat(format!(
            "funksjonsnøkkel stemmer ikke med modul og navn: forventet {expected}, fikk {key}"
        )));
    }
    Ok(())
}

fn validate_function_params(function: &RawFunction) -> Result<(), RuntimeError> {
    let mut seen = BTreeMap::new();
    for param in &function.params {
        if param.trim().is_empty() {
            return Err(RuntimeError::InvalidFormat(format!(
                "parameter kan ikke være tom i funksjon {}.{}",
                function.module, function.name
            )));
        }
        if seen.insert(param.clone(), ()).is_some() {
            return Err(RuntimeError::InvalidFormat(format!(
                "duplisert parameter i funksjon {}.{}: {}",
                function.module, function.name, param
            )));
        }
    }
    Ok(())
}

fn validate_imports(imports: &[RawImport]) -> Result<(), RuntimeError> {
    let mut aliases = BTreeMap::new();
    for import in imports {
        if import.module.trim().is_empty() {
            return Err(RuntimeError::InvalidFormat("import-modul kan ikke være tom".to_string()));
        }
        if import.alias.trim().is_empty() {
            return Err(RuntimeError::InvalidFormat(format!(
                "import-alias kan ikke være tom for modul {}",
                import.module
            )));
        }
        if aliases.insert(import.alias.clone(), import.module.clone()).is_some() {
            return Err(RuntimeError::InvalidFormat(format!(
                "duplisert import-alias: {}",
                import.alias
            )));
        }
    }
    Ok(())
}

fn validate_globals(globals: &BTreeMap<String, JsonValue>) -> Result<(), RuntimeError> {
    for name in globals.keys() {
        if name.trim().is_empty() {
            return Err(RuntimeError::InvalidFormat("globalnavn kan ikke være tomt".to_string()));
        }
    }
    Ok(())
}

fn validate_entry(entry: &str) -> Result<(), RuntimeError> {
    if entry.trim().is_empty() {
        return Err(RuntimeError::InvalidFormat("entry kan ikke være tom".to_string()));
    }
    Ok(())
}

fn parse_operand(op: &str, value: &JsonValue) -> Result<Operand, RuntimeError> {
    if let Some(n) = value.as_i64() {
        return Ok(Operand::Int(n));
    }
    if let Some(b) = value.as_bool() {
        return Ok(Operand::Bool(b));
    }
    if value.is_null() {
        return Ok(Operand::Null);
    }
    if let Some(s) = value.as_str() {
        return Ok(match op {
            "CALL" => Operand::Function(s.to_string()),
            "JUMP" | "JUMP_IF_FALSE" | "LABEL" => Operand::Label(s.to_string()),
            _ => Operand::Text(s.to_string()),
        });
    }
    Err(RuntimeError::InvalidOperand(format!("ugyldig operand for {op}: {value}")))
}

fn validate_arity(op: &str, arity: usize) -> Result<(), RuntimeError> {
    let expected = match op {
        "PUSH_CONST" | "LOAD_NAME" | "STORE_NAME" | "BUILD_LIST" | "JUMP" | "JUMP_IF_FALSE" | "LABEL" => 1,
        "CALL" => 2,
        "POP" | "PRINT" | "INDEX_GET" | "INDEX_SET" | "UNARY_NEG" | "UNARY_NOT" | "BINARY_ADD" | "BINARY_SUB"
        | "BINARY_MUL" | "BINARY_DIV" | "BINARY_AND" | "BINARY_OR" | "COMPARE_EQ" | "COMPARE_NE"
        | "COMPARE_GT" | "COMPARE_LT" | "COMPARE_GE" | "COMPARE_LE" | "RET" | "HALT" | "RETURN" => 0,
        _ => return Err(RuntimeError::InvalidOpcode(op.to_string())),
    };
    if arity != expected {
        return Err(RuntimeError::InvalidOperand(format!(
            "opcode {op} forventer {expected} operand(er), fikk {arity}"
        )));
    }
    Ok(())
}

fn parse_value(value: &JsonValue) -> Value {
    match value {
        JsonValue::Null => Value::Null,
        JsonValue::Bool(v) => Value::Bool(*v),
        JsonValue::Number(num) => Value::Int(num.as_i64().unwrap_or(0)),
        JsonValue::String(text) => Value::Text(text.clone()),
        JsonValue::Array(items) => Value::list(items.iter().map(parse_value).collect()),
        JsonValue::Object(_) => Value::Null,
    }
}

pub fn load_program(path: PathBuf) -> Result<Program, RuntimeError> {
    let text = fs::read_to_string(&path)
        .map_err(|err| RuntimeError::IoError(format!("{}: {}", path.display(), err)))?;
    let raw: RawProgram = serde_json::from_str(&text)
        .map_err(|err| RuntimeError::InvalidFormat(format!("kan ikke lese bytecode: {err}")))?;

    if raw.format != BYTECODE_FORMAT {
        return Err(RuntimeError::InvalidFormat(format!(
            "forventet {BYTECODE_FORMAT}, fikk {}",
            raw.format
        )));
    }

    validate_entry(&raw.entry)?;
    validate_imports(&raw.imports)?;
    validate_globals(&raw.globals)?;
    if raw.functions.is_empty() {
        return Err(RuntimeError::InvalidFormat("bytecode må inneholde minst én funksjon".to_string()));
    }

    let mut functions = BTreeMap::new();
    for (key, raw_fn) in raw.functions {
        validate_function_identity(&key, &raw_fn)?;
        validate_function_params(&raw_fn)?;
        let code = raw_fn
            .code
            .into_iter()
            .map(|instr| instr.into_instruction())
            .collect::<Result<Vec<_>, _>>()?;
        let labels = build_labels(&raw_fn.name, &code)?;
        validate_jump_targets(&raw_fn.name, &code, &labels)?;
        functions.insert(
            key,
            Function {
                name: raw_fn.name,
                module: raw_fn.module,
                params: raw_fn.params,
                code,
                labels,
            },
        );
    }

    if !functions.contains_key(&raw.entry) {
        return Err(RuntimeError::InvalidFormat(format!(
            "entry funksjon finnes ikke: {}",
            raw.entry
        )));
    }

    let imports = raw
        .imports
        .into_iter()
        .map(|item| (item.module, item.alias))
        .collect();
    let globals = raw
        .globals
        .into_iter()
        .map(|(key, value)| (key, parse_value(&value)))
        .collect();
    let constants = raw.constants.into_iter().map(|value| parse_value(&value)).collect();

    Ok(Program {
        format: raw.format,
        entry: raw.entry,
        imports,
        functions,
        globals,
        constants,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_minimal_bytecode_program() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "imports": [],
            "globals": {
                "answer": 42
            },
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": [],
                    "code": [["RETURN"]]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-test-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let program = load_program(path).unwrap();
        assert_eq!(program.format, BYTECODE_FORMAT);
        assert_eq!(program.entry, "__main__.start");
        assert!(program.functions.contains_key("__main__.start"));
        assert_eq!(program.globals.get("answer"), Some(&Value::Int(42)));
        assert_eq!(
            program.functions["__main__.start"]
                .labels
                .get("missing"),
            None
        );
    }

    #[test]
    fn rejects_duplicate_labels() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": [],
                    "code": [
                        ["LABEL", "entry"],
                        ["LABEL", "entry"],
                        ["RETURN"]
                    ]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-dup-label-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("duplisert label")));
    }

    #[test]
    fn rejects_empty_labels() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": [],
                    "code": [
                        ["LABEL", ""],
                        ["RETURN"]
                    ]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-empty-label-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("label kan ikke være tom")));
    }

    #[test]
    fn rejects_missing_jump_target() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": [],
                    "code": [
                        ["JUMP", "missing"],
                        ["RETURN"]
                    ]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-missing-jump-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidJumpTarget(target) if target.contains("missing")));
    }

    #[test]
    fn rejects_mismatched_function_identity() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "functions": {
                "__main__.start": {
                    "name": "run",
                    "module": "__main__",
                    "params": [],
                    "code": [["RETURN"]]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-mismatch-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("funksjonsnøkkel")));
    }

    #[test]
    fn rejects_duplicate_import_aliases() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "imports": [
                {"module": "std.math", "alias": "math"},
                {"module": "std.tekst", "alias": "math"}
            ],
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": [],
                    "code": [["RETURN"]]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-dup-import-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("duplisert import-alias")));
    }

    #[test]
    fn rejects_empty_global_names() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "globals": {
                "": 42
            },
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": [],
                    "code": [["RETURN"]]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-empty-global-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("globalnavn")));
    }

    #[test]
    fn rejects_programs_without_functions() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "functions": {}
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-empty-functions-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("minst én funksjon")));
    }

    #[test]
    fn rejects_duplicate_function_parameters() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": ["x", "x"],
                    "code": [["RETURN"]]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-dup-params-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("duplisert parameter")));
    }

    #[test]
    fn rejects_empty_function_metadata() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "functions": {
                "__main__.start": {
                    "name": "",
                    "module": "",
                    "params": [],
                    "code": [["RETURN"]]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-empty-fn-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("kan ikke være tom")));
    }

    #[test]
    fn rejects_empty_import_metadata() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "__main__.start",
            "imports": [
                {"module": "", "alias": "math"}
            ],
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": [],
                    "code": [["RETURN"]]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-empty-import-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("import-modul")));
    }

    #[test]
    fn rejects_empty_entry() {
        let payload = serde_json::json!({
            "format": "norscode-bytecode-v1",
            "entry": "",
            "functions": {
                "__main__.start": {
                    "name": "start",
                    "module": "__main__",
                    "params": [],
                    "code": [["RETURN"]]
                }
            }
        });

        let mut path = std::env::temp_dir();
        path.push(format!("norscode-runtime-loader-empty-entry-{}.ncb.json", std::process::id()));
        fs::write(&path, payload.to_string()).unwrap();

        let err = load_program(path).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidFormat(msg) if msg.contains("entry kan ikke være tom")));
    }
}
