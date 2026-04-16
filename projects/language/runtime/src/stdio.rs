use crate::error::RuntimeError;
use std::io::{self, BufRead, Write};

pub trait Io {
    fn print(&mut self, text: &str) -> Result<(), RuntimeError>;
    #[allow(dead_code)]
    fn read_line(&mut self) -> Result<String, RuntimeError>;
}

#[derive(Default)]
pub struct StandardIo;

impl Io for StandardIo {
    fn print(&mut self, text: &str) -> Result<(), RuntimeError> {
        let mut stdout = io::stdout().lock();
        stdout
            .write_all(text.as_bytes())
            .and_then(|_| stdout.flush())
            .map_err(|err| RuntimeError::IoError(err.to_string()))
    }

    fn read_line(&mut self) -> Result<String, RuntimeError> {
        let mut line = String::new();
        io::stdin()
            .lock()
            .read_line(&mut line)
            .map_err(|err| RuntimeError::IoError(err.to_string()))?;
        Ok(line)
    }
}
