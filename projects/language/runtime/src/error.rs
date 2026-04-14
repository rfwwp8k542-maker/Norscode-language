use std::fmt::{Display, Formatter};

#[derive(Debug)]
pub enum RuntimeError {
    InvalidFormat(String),
    InvalidOpcode(String),
    InvalidOperand(String),
    StackUnderflow,
    InvalidJumpTarget(String),
    UnknownFunction(String),
    DivisionByZero,
    ReturnWithoutFrame,
    IoError(String),
    DbError(String),
}

impl Display for RuntimeError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            RuntimeError::InvalidFormat(msg) => write!(f, "invalid format: {msg}"),
            RuntimeError::InvalidOpcode(op) => write!(f, "invalid opcode: {op}"),
            RuntimeError::InvalidOperand(msg) => write!(f, "invalid operand: {msg}"),
            RuntimeError::StackUnderflow => write!(f, "stack underflow"),
            RuntimeError::InvalidJumpTarget(target) => write!(f, "invalid jump target: {target}"),
            RuntimeError::UnknownFunction(name) => write!(f, "unknown function: {name}"),
            RuntimeError::DivisionByZero => write!(f, "division by zero"),
            RuntimeError::ReturnWithoutFrame => write!(f, "return without frame"),
            RuntimeError::IoError(msg) => write!(f, "io error: {msg}"),
            RuntimeError::DbError(msg) => write!(f, "db error: {msg}"),
        }
    }
}

impl std::error::Error for RuntimeError {}
