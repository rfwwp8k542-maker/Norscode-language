use std::cell::RefCell;
use std::rc::Rc;

#[derive(Debug, Clone)]
pub enum Value {
    Int(i64),
    Bool(bool),
    Text(String),
    List(Rc<RefCell<Vec<Value>>>),
    Null,
}

impl Value {
    pub fn list(items: Vec<Value>) -> Self {
        Value::List(Rc::new(RefCell::new(items)))
    }

    pub fn is_truthy(&self) -> bool {
        match self {
            Value::Int(0) => false,
            Value::Bool(false) => false,
            Value::Text(text) if text.is_empty() => false,
            Value::List(items) if items.borrow().is_empty() => false,
            Value::Null => false,
            _ => true,
        }
    }
}

impl PartialEq for Value {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (Value::Int(left), Value::Int(right)) => left == right,
            (Value::Bool(left), Value::Bool(right)) => left == right,
            (Value::Text(left), Value::Text(right)) => left == right,
            (Value::List(left), Value::List(right)) => left.borrow().as_slice() == right.borrow().as_slice(),
            (Value::Null, Value::Null) => true,
            _ => false,
        }
    }
}
