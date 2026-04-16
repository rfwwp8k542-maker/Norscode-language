use crate::error::RuntimeError;
use crate::stdio::Io;
use crate::value::Value;
use crate::vm::Vm;
use std::fs;
use std::path::Path;
use std::path::PathBuf;
use std::process::Command;

pub(crate) fn handle_source_builtin<I: Io>(
    _vm: &mut Vm<I>,
    name: &str,
    args: &[Value],
) -> Result<Option<Value>, RuntimeError> {
    match name {
        "kjor_kilde" | "kjør_kilde" => {
            let source = args.first().map(crate::builtins_text::format_value).unwrap_or_default();
            let stamp = format!(
                "norscode_source_{}_{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map_err(|err| RuntimeError::IoError(err.to_string()))?
                    .as_nanos()
            );
            let temp_dir = std::env::temp_dir();
            let work_dir = temp_dir.join(stamp);
            fs::create_dir_all(&work_dir).map_err(|err| RuntimeError::IoError(err.to_string()))?;
            let source_path = work_dir.join("source.no");
            let bytecode_path = work_dir.join("program.ncb.json");
            fs::write(&source_path, source).map_err(|err| RuntimeError::IoError(err.to_string()))?;

            let project_root = std::env::current_dir().map_err(|err| RuntimeError::IoError(err.to_string()))?;
            let main_py = project_root.join("main.py");
            if !main_py.exists() {
                let _ = fs::remove_dir_all(&work_dir);
                return Ok(Some(Value::Text("Feil: fant ikke main.py".to_string())));
            }

            let build = Command::new("python3")
                .arg(&main_py)
                .arg("bytecode-build")
                .arg(&source_path)
                .arg("--output")
                .arg(&bytecode_path)
                .output()
                .map_err(|err| RuntimeError::IoError(err.to_string()))?;
            if !build.status.success() {
                let mut message = String::from_utf8_lossy(&build.stderr).trim().to_string();
                if message.is_empty() {
                    message = String::from_utf8_lossy(&build.stdout).trim().to_string();
                }
                let _ = fs::remove_dir_all(&work_dir);
                return Ok(Some(Value::Text(format!("Feil: {}", message.trim()))));
            }

            let run = if let Some(native_runtime) = find_native_runtime(&project_root) {
                Command::new(native_runtime)
                    .arg("run")
                    .arg(&bytecode_path)
                    .output()
                    .map_err(|err| RuntimeError::IoError(err.to_string()))?
            } else {
                Command::new("python3")
                    .arg(&main_py)
                    .arg("bytecode-run")
                    .arg(&bytecode_path)
                    .arg("--bytecode")
                    .output()
                    .map_err(|err| RuntimeError::IoError(err.to_string()))?
            };

            let mut output = String::from_utf8_lossy(&run.stdout).to_string();
            if !run.stderr.is_empty() {
                if !output.ends_with('\n') && !output.is_empty() {
                    output.push('\n');
                }
                output.push_str(&String::from_utf8_lossy(&run.stderr));
            }

            let _ = fs::remove_dir_all(&work_dir);

            if !run.status.success() {
                return Ok(Some(Value::Text(format!("Feil: {}", output.trim()))));
            }
            Ok(Some(Value::Text(output)))
        }
        _ => Ok(None),
    }
}

fn find_native_runtime(project_root: &Path) -> Option<PathBuf> {
    let runtime_dirs = [
        project_root.join("projects/language/runtime"),
        project_root.join("runtime"),
    ];
    for runtime_dir in runtime_dirs {
        let candidates = [
            runtime_dir.join("target/debug/norscode-runtime"),
            runtime_dir.join("target/release/norscode-runtime"),
            runtime_dir.join("target/debug/norscode-runtime.exe"),
            runtime_dir.join("target/release/norscode-runtime.exe"),
        ];
        if let Some(binary) = candidates.into_iter().find(|path| path.exists()) {
            return Some(binary);
        }
    }
    None
}
