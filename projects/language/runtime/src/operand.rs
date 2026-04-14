#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Operand {
    Int(i64),
    Bool(bool),
    Null,
    Text(String),
    Function(String),
    Label(String),
}
