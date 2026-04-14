mod builtins_core;
mod builtins_text;
mod builtins_fs;
mod builtins_assert;
mod builtins_list;
mod builtins_gui;
mod builtins_web;
mod builtins_source;
mod builtins_db;
mod error;
mod builtins;
mod db;
mod gui;
mod loader;
mod operand;
mod opcode;
mod stdio;
mod value;
mod vm;

use crate::error::RuntimeError;
use crate::db::initialize_from_env;
use crate::loader::load_program;
use crate::stdio::StandardIo;
use crate::vm::Vm;
use std::env;
use std::path::PathBuf;

fn program_args_from_env() -> Vec<String> {
    let raw_args = env::var("NORSCODE_ARGS").unwrap_or_default();
    raw_args
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn main() -> Result<(), RuntimeError> {
    let mut args = env::args().skip(1);
    let Some(command) = args.next() else {
        eprintln!("bruk: norscode-runtime run <fil.ncb.json> | check <fil.ncb.json>");
        return Ok(());
    };
    initialize_from_env()?;

    match command.as_str() {
        "run" => {
            let Some(path) = args.next() else {
                eprintln!("mangler bytecode-fil");
                return Ok(());
            };
            let program = load_program(PathBuf::from(path))?;
            let mut vm = Vm::with_program_args(program, StandardIo::default(), program_args_from_env());
            vm.run()?;
        }
        "check" => {
            let Some(path) = args.next() else {
                eprintln!("mangler bytecode-fil");
                return Ok(());
            };
            let _program = load_program(PathBuf::from(path))?;
            println!("OK");
        }
        _ => {
            eprintln!("ukjent kommando: {command}");
        }
    }

    Ok(())
}
