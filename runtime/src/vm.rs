use crate::error::RuntimeError;
use crate::builtins_text::format_value;
use crate::gui::GuiState;
use crate::loader::Program;
use crate::opcode::Opcode;
use crate::stdio::Io;
use crate::value::Value;
use std::collections::BTreeMap;

#[derive(Debug, Clone)]
pub struct Frame {
    pub function_name: String,
    pub ip: usize,
    pub locals: BTreeMap<String, Value>,
}

pub struct Vm<I: Io> {
    pub stack: Vec<Value>,
    pub frames: Vec<Frame>,
    #[allow(dead_code)]
    pub globals: BTreeMap<String, Value>,
    pub program_args: Vec<String>,
    pub program: Program,
    pub gui: GuiState,
    pub io: I,
}

impl<I: Io> Vm<I> {
    #[allow(dead_code)]
    pub fn new(program: Program, io: I) -> Self {
        Self {
            stack: Vec::new(),
            frames: Vec::new(),
            globals: BTreeMap::new(),
            program_args: Vec::new(),
            program,
            gui: GuiState::new(),
            io,
        }
    }

    pub fn with_program_args(program: Program, io: I, program_args: Vec<String>) -> Self {
        Self {
            stack: Vec::new(),
            frames: Vec::new(),
            globals: BTreeMap::new(),
            program_args,
            program,
            gui: GuiState::new(),
            io,
        }
    }

    pub fn push(&mut self, value: Value) {
        self.stack.push(value);
    }

    pub fn pop(&mut self) -> Result<Value, RuntimeError> {
        self.stack.pop().ok_or(RuntimeError::StackUnderflow)
    }

    pub fn peek(&self) -> Result<&Value, RuntimeError> {
        self.stack.last().ok_or(RuntimeError::StackUnderflow)
    }

    pub fn run(&mut self) -> Result<(), RuntimeError> {
        let entry = self.program.entry.clone();
        self.frames.push(self.make_frame(&entry)?);
        while !self.frames.is_empty() {
            self.step()?;
        }
        Ok(())
    }

    pub fn step(&mut self) -> Result<(), RuntimeError> {
        let (function_name, ip) = {
            let frame = self.frames.last().ok_or(RuntimeError::ReturnWithoutFrame)?;
            (frame.function_name.clone(), frame.ip)
        };
        let function = self
            .program
            .functions
            .get(&function_name)
            .ok_or_else(|| RuntimeError::UnknownFunction(function_name.clone()))?;
        let instruction = function
            .code
            .get(ip)
            .cloned()
            .ok_or_else(|| RuntimeError::InvalidJumpTarget(format!("{function_name}:{ip}")))?;

        if let Some(frame) = self.frames.last_mut() {
            frame.ip += 1;
        }

        match instruction.opcode {
            Opcode::Label => {}
            Opcode::PushConst => {
                self.push(read_operand_value(&instruction.operands, 0)?);
            }
            Opcode::LoadName => {
                let name = read_operand_text(&instruction.operands, 0)?;
                let value = self
                    .read_local_or_global(&name)?
                    .clone();
                self.push(value);
            }
            Opcode::StoreName => {
                let name = read_operand_text(&instruction.operands, 0)?;
                let value = self.pop()?;
                self.write_name(name, value)?;
            }
            Opcode::Pop => {
                let _ = self.pop()?;
            }
            Opcode::Dup => {
                let value = self.peek()?.clone();
                self.push(value);
            }
            Opcode::Swap => {
                if self.stack.len() < 2 {
                    return Err(RuntimeError::StackUnderflow);
                }
                let len = self.stack.len();
                self.stack.swap(len - 1, len - 2);
            }
            Opcode::Over => {
                if self.stack.len() < 2 {
                    return Err(RuntimeError::StackUnderflow);
                }
                let len = self.stack.len();
                let value = self.stack[len - 2].clone();
                self.push(value);
            }
            Opcode::Print => {
                let value = self.peek()?.clone();
                self.io.print(&format!("{}\n", format_value(&value)))?;
            }
            Opcode::BuildList => {
                let count = read_operand_nonnegative_usize(&instruction.operands, 0, "BUILD_LIST")?;
                if self.stack.len() < count {
                    return Err(RuntimeError::StackUnderflow);
                }
                let start = self.stack.len() - count;
                let items = self.stack.split_off(start);
                self.push(Value::list(items));
            }
            Opcode::IndexGet => {
                let index = self.pop()?;
                let target = self.pop()?;
                match (target, index) {
                    (Value::List(items), Value::Int(idx)) if idx >= 0 => {
                        let idx = idx as usize;
                        let value = items.borrow().get(idx).cloned().ok_or_else(|| {
                            RuntimeError::InvalidOperand(format!("listeindeks utenfor range: {idx}"))
                        })?;
                        self.push(value);
                    }
                    _ => return Err(RuntimeError::InvalidOperand("INDEX_GET forventer liste og int".to_string())),
                }
            }
            Opcode::IndexSet => {
                let value = self.pop()?;
                let index = self.pop()?;
                let target = self.pop()?;
                match (target, index) {
                    (Value::List(items), Value::Int(idx)) if idx >= 0 => {
                        let idx = idx as usize;
                        {
                            let mut items_ref = items.borrow_mut();
                            if idx >= items_ref.len() {
                                return Err(RuntimeError::InvalidOperand(format!("listeindeks utenfor range: {idx}")));
                            }
                            items_ref[idx] = value;
                        }
                        self.push(Value::List(items));
                    }
                    _ => return Err(RuntimeError::InvalidOperand("INDEX_SET forventer liste og int".to_string())),
                }
            }
            Opcode::UnaryNeg => {
                let value = self.pop()?;
                match value {
                    Value::Int(n) => self.push(Value::Int(-n)),
                    _ => return Err(RuntimeError::InvalidOperand("UNARY_NEG forventer int".to_string())),
                }
            }
            Opcode::UnaryNot => {
                let value = self.pop()?;
                self.push(Value::Bool(!value.is_truthy()));
            }
            Opcode::BinaryAdd | Opcode::BinarySub | Opcode::BinaryMul | Opcode::BinaryDiv | Opcode::BinaryAnd | Opcode::BinaryOr | Opcode::CompareEq | Opcode::CompareNe | Opcode::CompareGt | Opcode::CompareLt | Opcode::CompareGe | Opcode::CompareLe => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(self.eval_binary(&instruction.opcode, a, b)?);
            }
            Opcode::Jump => {
                let target = read_operand_label(&instruction.operands, 0)?;
                self.jump_to(&function_name, &target)?;
            }
            Opcode::JumpIfFalse => {
                let target = read_operand_label(&instruction.operands, 0)?;
                let cond = self.pop()?;
                if !cond.is_truthy() {
                    self.jump_to(&function_name, &target)?;
                }
            }
            Opcode::Call => {
                let target = read_operand_function(&instruction.operands, 0)?;
                let argc = read_operand_nonnegative_usize(&instruction.operands, 1, "CALL")?;
                let mut args = Vec::with_capacity(argc);
                for _ in 0..argc {
                    args.push(self.pop()?);
                }
                args.reverse();
                self.call_function(target, args)?;
            }
            Opcode::Ret | Opcode::Return => {
                let return_value = self.stack.pop().unwrap_or(Value::Null);
                self.frames.pop();
                if self.frames.is_empty() {
                    self.push(return_value);
                    return Ok(());
                }
                self.push(return_value);
            }
            Opcode::Halt => {
                self.frames.clear();
            }
        }
        Ok(())
    }

    fn make_frame(&self, function_name: &str) -> Result<Frame, RuntimeError> {
        let function = self
            .program
            .functions
            .get(function_name)
            .ok_or_else(|| RuntimeError::UnknownFunction(function_name.to_string()))?;
        let mut locals = BTreeMap::new();
        for param in &function.params {
            locals.insert(param.clone(), Value::Null);
        }
        Ok(Frame {
            function_name: function_name.to_string(),
            ip: 0,
            locals,
        })
    }

    fn read_local_or_global(&self, name: &str) -> Result<&Value, RuntimeError> {
        if let Some(value) = self.frames.last().and_then(|frame| frame.locals.get(name)) {
            return Ok(value);
        }
        self.program
            .globals
            .get(name)
            .ok_or_else(|| RuntimeError::InvalidOperand(format!("ukjent variabel: {name}")))
    }

    fn write_name(&mut self, name: String, value: Value) -> Result<(), RuntimeError> {
        if let Some(frame) = self.frames.last_mut() {
            frame.locals.insert(name, value);
            return Ok(());
        }
        self.program.globals.insert(name, value);
        Ok(())
    }

    fn jump_to(&mut self, function_name: &str, label: &str) -> Result<(), RuntimeError> {
        let function = self
            .program
            .functions
            .get(function_name)
            .ok_or_else(|| RuntimeError::UnknownFunction(function_name.to_string()))?;
        let target = function
            .labels
            .get(label)
            .copied()
            .ok_or_else(|| RuntimeError::InvalidJumpTarget(label.to_string()))?;
        if let Some(frame) = self.frames.last_mut() {
            frame.ip = target;
        }
        Ok(())
    }

    fn call_function(&mut self, name: String, args: Vec<Value>) -> Result<(), RuntimeError> {
        let value = self.invoke_function(&name, args)?;
        self.push(value);
        Ok(())
    }

    pub fn invoke_function(&mut self, name: &str, args: Vec<Value>) -> Result<Value, RuntimeError> {
        if let Some(value) = self.call_builtin(name, &args)? {
            return Ok(value);
        }
        let params = self
            .program
            .functions
            .get(name)
            .ok_or_else(|| RuntimeError::UnknownFunction(name.to_string()))?
            .params
            .clone();
        if args.len() != params.len() {
            return Err(RuntimeError::InvalidOperand(format!(
                "funksjon {name} forventer {} argument(er), fikk {}",
                params.len(),
                args.len()
            )));
        }
        let stack_depth = self.stack.len();
        let frame_depth = self.frames.len();
        let mut frame = self.make_frame(name)?;
        for (param, value) in params.into_iter().zip(args.into_iter()) {
            frame.locals.insert(param, value);
        }
        self.frames.push(frame);
        while self.frames.len() > frame_depth {
            self.step()?;
        }
        let result = self.stack.last().cloned().unwrap_or(Value::Null);
        self.stack.truncate(stack_depth);
        Ok(result)
    }

    pub(crate) fn resolve_function_name(&self, name: &str) -> Option<String> {
        if self.program.functions.contains_key(name) {
            return Some(name.to_string());
        }
        let short_name = name.rsplit('.').next().unwrap_or(name);
        self.program.functions.keys().find_map(|candidate| {
            if candidate.rsplit('.').next().unwrap_or(candidate) == short_name {
                Some(candidate.clone())
            } else {
                None
            }
        })
    }

    fn eval_binary(&self, op: &Opcode, a: Value, b: Value) -> Result<Value, RuntimeError> {
        match op {
            Opcode::BinaryAdd => match (a, b) {
                (Value::Int(left), Value::Int(right)) => Ok(Value::Int(left + right)),
                (Value::Text(left), Value::Text(right)) => Ok(Value::Text(left + &right)),
                _ => Err(RuntimeError::InvalidOperand("BINARY_ADD forventer tall eller tekst".to_string())),
            },
            Opcode::BinarySub => match (a, b) {
                (Value::Int(left), Value::Int(right)) => Ok(Value::Int(left - right)),
                _ => Err(RuntimeError::InvalidOperand("BINARY_SUB forventer tall".to_string())),
            },
            Opcode::BinaryMul => match (a, b) {
                (Value::Int(left), Value::Int(right)) => Ok(Value::Int(left * right)),
                _ => Err(RuntimeError::InvalidOperand("BINARY_MUL forventer tall".to_string())),
            },
            Opcode::BinaryDiv => match (a, b) {
                (Value::Int(_), Value::Int(0)) => Err(RuntimeError::DivisionByZero),
                (Value::Int(left), Value::Int(right)) => Ok(Value::Int(left / right)),
                _ => Err(RuntimeError::InvalidOperand("BINARY_DIV forventer tall".to_string())),
            },
            Opcode::BinaryAnd => Ok(Value::Bool(a.is_truthy() && b.is_truthy())),
            Opcode::BinaryOr => Ok(Value::Bool(a.is_truthy() || b.is_truthy())),
            Opcode::CompareEq => Ok(Value::Bool(a == b)),
            Opcode::CompareNe => Ok(Value::Bool(a != b)),
            Opcode::CompareGt => match (a, b) {
                (Value::Int(left), Value::Int(right)) => Ok(Value::Bool(left > right)),
                _ => Err(RuntimeError::InvalidOperand("COMPARE_GT forventer tall".to_string())),
            },
            Opcode::CompareLt => match (a, b) {
                (Value::Int(left), Value::Int(right)) => Ok(Value::Bool(left < right)),
                _ => Err(RuntimeError::InvalidOperand("COMPARE_LT forventer tall".to_string())),
            },
            Opcode::CompareGe => match (a, b) {
                (Value::Int(left), Value::Int(right)) => Ok(Value::Bool(left >= right)),
                _ => Err(RuntimeError::InvalidOperand("COMPARE_GE forventer tall".to_string())),
            },
            Opcode::CompareLe => match (a, b) {
                (Value::Int(left), Value::Int(right)) => Ok(Value::Bool(left <= right)),
                _ => Err(RuntimeError::InvalidOperand("COMPARE_LE forventer tall".to_string())),
            },
            _ => Err(RuntimeError::InvalidOpcode(format!("{op:?}"))),
        }
    }
}

fn read_operand_value(operands: &[crate::operand::Operand], index: usize) -> Result<Value, RuntimeError> {
    match operands.get(index) {
        Some(crate::operand::Operand::Int(value)) => Ok(Value::Int(*value)),
        Some(crate::operand::Operand::Bool(value)) => Ok(Value::Bool(*value)),
        Some(crate::operand::Operand::Null) => Ok(Value::Null),
        Some(crate::operand::Operand::Text(text)) => Ok(Value::Text(text.clone())),
        Some(crate::operand::Operand::Function(name)) => Ok(Value::Text(name.clone())),
        Some(crate::operand::Operand::Label(label)) => Ok(Value::Text(label.clone())),
        None => Err(RuntimeError::InvalidOperand("mangler operand".to_string())),
    }
}

fn read_operand_int(operands: &[crate::operand::Operand], index: usize) -> Result<i64, RuntimeError> {
    match operands.get(index) {
        Some(crate::operand::Operand::Int(value)) => Ok(*value),
        Some(other) => Err(RuntimeError::InvalidOperand(format!("forventet heltall, fikk {other:?}"))),
        None => Err(RuntimeError::InvalidOperand("mangler operand".to_string())),
    }
}

fn read_operand_nonnegative_usize(
    operands: &[crate::operand::Operand],
    index: usize,
    op_name: &str,
) -> Result<usize, RuntimeError> {
    let value = read_operand_int(operands, index)?;
    if value < 0 {
        return Err(RuntimeError::InvalidOperand(format!(
            "{op_name} forventer ikke-negativt heltall, fikk {value}"
        )));
    }
    Ok(value as usize)
}

fn read_operand_text(operands: &[crate::operand::Operand], index: usize) -> Result<String, RuntimeError> {
    match operands.get(index) {
        Some(crate::operand::Operand::Text(text)) => Ok(text.clone()),
        Some(crate::operand::Operand::Label(text)) => Ok(text.clone()),
        Some(crate::operand::Operand::Function(text)) => Ok(text.clone()),
        Some(other) => Err(RuntimeError::InvalidOperand(format!("forventet tekst, fikk {other:?}"))),
        None => Err(RuntimeError::InvalidOperand("mangler operand".to_string())),
    }
}

fn read_operand_label(operands: &[crate::operand::Operand], index: usize) -> Result<String, RuntimeError> {
    match operands.get(index) {
        Some(crate::operand::Operand::Label(text)) => Ok(text.clone()),
        Some(other) => Err(RuntimeError::InvalidOperand(format!("forventet label, fikk {other:?}"))),
        None => Err(RuntimeError::InvalidOperand("mangler operand".to_string())),
    }
}

fn read_operand_function(operands: &[crate::operand::Operand], index: usize) -> Result<String, RuntimeError> {
    match operands.get(index) {
        Some(crate::operand::Operand::Function(text)) => Ok(text.clone()),
        Some(other) => Err(RuntimeError::InvalidOperand(format!("forventet funksjon, fikk {other:?}"))),
        None => Err(RuntimeError::InvalidOperand("mangler operand".to_string())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::loader::{Function, Instruction, Program};
    use crate::opcode::Opcode;
    use crate::stdio::Io;
    use std::collections::BTreeMap;

    #[derive(Default)]
    struct TestIo {
        output: String,
    }

    impl Io for TestIo {
        fn print(&mut self, text: &str) -> Result<(), RuntimeError> {
            self.output.push_str(text);
            Ok(())
        }

        fn read_line(&mut self) -> Result<String, RuntimeError> {
            Ok(String::new())
        }
    }

    #[test]
    fn stack_helpers_work() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.push(Value::Int(1));
        assert_eq!(vm.peek().unwrap(), &Value::Int(1));
        assert_eq!(vm.pop().unwrap(), Value::Int(1));
    }

    #[test]
    fn step_without_frames_returns_error() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        let err = vm.step().unwrap_err();
        assert!(matches!(err, RuntimeError::ReturnWithoutFrame));
    }

    #[test]
    fn invoke_function_reports_unknown_function() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        let err = vm.invoke_function("mangler", vec![]).unwrap_err();
        assert!(matches!(err, RuntimeError::UnknownFunction(name) if name == "mangler"));
    }

    #[test]
    fn invoke_function_rejects_wrong_arity() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec!["x".to_string()],
                code: vec![Instruction { opcode: Opcode::Return, operands: vec![] }],
                labels: BTreeMap::new(),
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        let err = vm.invoke_function("__main__.start", vec![]).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidOperand(msg) if msg.contains("forventer 1 argument(er), fikk 0")));
    }

    #[test]
    fn build_list_rejects_negative_count() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::BuildList, operands: vec![crate::operand::Operand::Int(-1)] },
                ],
                labels: BTreeMap::new(),
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        let err = vm.step().unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidOperand(msg) if msg.contains("BUILD_LIST forventer ikke-negativt heltall, fikk -1")));
    }

    #[test]
    fn executes_simple_add_program() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(2)] },
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(3)] },
                    Instruction { opcode: Opcode::BinaryAdd, operands: vec![] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(5)]);
    }

    #[test]
    fn load_name_falls_back_to_globals_and_print_keeps_stack() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::LoadName, operands: vec![crate::operand::Operand::Text("answer".to_string())] },
                    Instruction { opcode: Opcode::Print, operands: vec![] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        let mut globals = BTreeMap::new();
        globals.insert("answer".to_string(), Value::Int(42));
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals,
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(42)]);
    }

    #[test]
    fn argv_builtin_uses_program_args() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::with_program_args(
            program,
            TestIo::default(),
            vec!["første".to_string(), "andre".to_string()],
        );
        let value = vm.call_builtin("argv", &[]).unwrap().unwrap();
        assert_eq!(
            value,
            Value::list(vec![Value::Text("første".to_string()), Value::Text("andre".to_string())])
        );
    }

    #[test]
    fn list_builtins_mutate_shared_lists() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        let list = Value::list(vec![Value::Int(1)]);
        let shared = list.clone();

        vm.call_builtin("legg_til", &[list, Value::Int(2)]).unwrap();
        assert_eq!(shared, Value::list(vec![Value::Int(1), Value::Int(2)]));

        let popped = vm.call_builtin("pop_siste", &[shared.clone()]).unwrap().unwrap();
        assert_eq!(popped, Value::Int(2));
        assert_eq!(shared, Value::list(vec![Value::Int(1)]));

        let inserted = Value::list(vec![Value::Text("a".to_string())]);
        let inserted_shared = inserted.clone();
        vm.call_builtin(
            "sett_inn",
            &[inserted, Value::Int(2), Value::Text("b".to_string())],
        )
        .unwrap();
        assert_eq!(
            inserted_shared,
            Value::list(vec![
                Value::Text("a".to_string()),
                Value::Text(String::new()),
                Value::Text("b".to_string()),
            ])
        );

        let removed = Value::list(vec![Value::Int(9), Value::Int(8), Value::Int(7)]);
        let removed_shared = removed.clone();
        let len = vm
            .call_builtin("fjern_indeks", &[removed, Value::Int(1)])
            .unwrap()
            .unwrap();
        assert_eq!(len, Value::Int(2));
        assert_eq!(removed_shared, Value::list(vec![Value::Int(9), Value::Int(7)]));
    }

    #[test]
    fn file_exists_builtin_checks_paths() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        let current_file = std::path::Path::new(file!());
        let existing = vm
            .call_builtin("fil_eksisterer", &[Value::Text(current_file.to_string_lossy().to_string())])
            .unwrap()
            .unwrap();
        assert_eq!(existing, Value::Bool(true));

        let missing = vm
            .call_builtin("fil_eksisterer", &[Value::Text("__definitely_missing_norscode_file__".to_string())])
            .unwrap()
            .unwrap();
        assert_eq!(missing, Value::Bool(false));
    }

    #[test]
    fn file_helpers_read_write_and_list() {
        let unique = format!(
            "norscode_runtime_files_{}_{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("klokke gikk bakover")
                .as_nanos()
        );
        let base = std::env::temp_dir().join(unique);
        let root = base.join("probe");
        let file_path = root.join("hello.no");
        let file_text = "funksjon start() -> heltall { returner 0 }".to_string();

        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());

        let wrote = vm
            .call_builtin(
                "skriv_fil",
                &[
                    Value::Text(file_path.to_string_lossy().to_string()),
                    Value::Text(file_text.clone()),
                ],
            )
            .unwrap()
            .unwrap();
        assert_eq!(wrote, Value::Int(1));

        let read_back = vm
            .call_builtin("les_fil", &[Value::Text(file_path.to_string_lossy().to_string())])
            .unwrap()
            .unwrap();
        assert_eq!(read_back, Value::Text(file_text.clone()));

        let flat = vm
            .call_builtin("liste_filer", &[Value::Text(root.to_string_lossy().to_string())])
            .unwrap()
            .unwrap();
        match flat {
            Value::List(items) => {
                assert!(items.borrow().iter().any(|item| item == &Value::Text("hello.no".to_string())));
            }
            other => panic!("forventet liste, fikk {other:?}"),
        }

        let tree = vm
            .call_builtin("liste_filer_tre", &[Value::Text(base.to_string_lossy().to_string())])
            .unwrap()
            .unwrap();
        match tree {
            Value::List(items) => {
                assert!(items.borrow().len() >= 2);
            }
            other => panic!("forventet liste, fikk {other:?}"),
        }

        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn env_builtin_reads_environment_variables() {
        struct EnvIo;
        impl Io for EnvIo {
            fn print(&mut self, _text: &str) -> Result<(), RuntimeError> {
                Ok(())
            }

            fn read_line(&mut self) -> Result<String, RuntimeError> {
                Ok(String::new())
            }
        }

        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, EnvIo);
        let value = vm
            .call_builtin("les_miljo", &[Value::Text("PATH".to_string())])
            .unwrap()
            .unwrap();
        match value {
            Value::Text(text) => assert!(!text.is_empty()),
            other => panic!("forventet tekst, fikk {other:?}"),
        }
    }

    #[test]
    fn input_builtin_returns_empty_string_by_default() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        let value = vm.call_builtin("les_input", &[]).unwrap().unwrap();
        assert_eq!(value, Value::Text(String::new()));
    }

    #[test]
    fn text_slice_builtin_matches_interpreter_semantics() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        let value = vm
            .call_builtin(
                "tekst_slice",
                &[
                    Value::Text("Hei verden".to_string()),
                    Value::Int(0),
                    Value::Int(3),
                ],
        )
        .unwrap()
        .unwrap();
        assert_eq!(value, Value::Text("Hei".to_string()));
    }

    #[test]
    fn word_char_builtin_matches_interpreter_semantics() {
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions: BTreeMap::new(),
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        assert_eq!(
            vm.call_builtin("tekst_er_ordtegn", &[Value::Text("_".to_string())])
                .unwrap()
                .unwrap(),
            Value::Bool(true)
        );
        assert_eq!(
            vm.call_builtin("tekst_er_ordtegn", &[Value::Text("-".to_string())])
                .unwrap()
                .unwrap(),
            Value::Bool(false)
        );
    }

    #[test]
    fn stack_opcodes_work() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::Dup, operands: vec![] },
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(2)] },
                    Instruction { opcode: Opcode::Swap, operands: vec![] },
                    Instruction { opcode: Opcode::Over, operands: vec![] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(1), Value::Int(2), Value::Int(1)]);
    }

    #[test]
    fn call_and_ret_work() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.inc".to_string(),
            Function {
                name: "inc".to_string(),
                module: "__main__".to_string(),
                params: vec!["n".to_string()],
                code: vec![
                    Instruction { opcode: Opcode::LoadName, operands: vec![crate::operand::Operand::Text("n".to_string())] },
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::BinaryAdd, operands: vec![] },
                    Instruction { opcode: Opcode::Ret, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(41)] },
                    Instruction { opcode: Opcode::Call, operands: vec![crate::operand::Operand::Function("__main__.inc".to_string()), crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(42)]);
    }

    #[test]
    fn ret_without_value_returns_null() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.noop".to_string(),
            Function {
                name: "noop".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![Instruction { opcode: Opcode::Ret, operands: vec![] }],
                labels: BTreeMap::new(),
            },
        );
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::Call, operands: vec![crate::operand::Operand::Function("__main__.noop".to_string()), crate::operand::Operand::Int(0)] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Null]);
    }

    #[test]
    fn call_frames_keep_local_state_isolated() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.shadow".to_string(),
            Function {
                name: "shadow".to_string(),
                module: "__main__".to_string(),
                params: vec!["x".to_string()],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(2)] },
                    Instruction { opcode: Opcode::StoreName, operands: vec![crate::operand::Operand::Text("x".to_string())] },
                    Instruction { opcode: Opcode::LoadName, operands: vec![crate::operand::Operand::Text("x".to_string())] },
                    Instruction { opcode: Opcode::Ret, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::StoreName, operands: vec![crate::operand::Operand::Text("x".to_string())] },
                    Instruction { opcode: Opcode::LoadName, operands: vec![crate::operand::Operand::Text("x".to_string())] },
                    Instruction { opcode: Opcode::Call, operands: vec![crate::operand::Operand::Function("__main__.shadow".to_string()), crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::LoadName, operands: vec![crate::operand::Operand::Text("x".to_string())] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(1), Value::Int(2), Value::Int(1)]);
    }

    #[test]
    fn halt_stops_execution() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(99)] },
                    Instruction { opcode: Opcode::Halt, operands: vec![] },
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: BTreeMap::new(),
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(99)]);
    }

    #[test]
    fn jump_skips_later_instructions() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::Jump, operands: vec![crate::operand::Operand::Label("done".to_string())] },
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(99)] },
                    Instruction { opcode: Opcode::Label, operands: vec![crate::operand::Operand::Label("done".to_string())] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: {
                    let mut labels = BTreeMap::new();
                    labels.insert("done".to_string(), 3);
                    labels
                },
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(1)]);
    }

    #[test]
    fn jump_if_false_skips_later_instructions() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Bool(false)] },
                    Instruction { opcode: Opcode::JumpIfFalse, operands: vec![crate::operand::Operand::Label("done".to_string())] },
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(99)] },
                    Instruction { opcode: Opcode::Label, operands: vec![crate::operand::Operand::Label("done".to_string())] },
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(1)] },
                    Instruction { opcode: Opcode::Return, operands: vec![] },
                ],
                labels: {
                    let mut labels = BTreeMap::new();
                    labels.insert("done".to_string(), 3);
                    labels
                },
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(1)]);
    }

    #[test]
    fn jump_if_false_falls_through_when_true() {
        let mut functions = BTreeMap::new();
        functions.insert(
            "__main__.start".to_string(),
            Function {
                name: "start".to_string(),
                module: "__main__".to_string(),
                params: vec![],
                code: vec![
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Bool(true)] },
                    Instruction { opcode: Opcode::JumpIfFalse, operands: vec![crate::operand::Operand::Label("done".to_string())] },
                    Instruction { opcode: Opcode::PushConst, operands: vec![crate::operand::Operand::Int(99)] },
                    Instruction { opcode: Opcode::Label, operands: vec![crate::operand::Operand::Label("done".to_string())] },
                    Instruction { opcode: Opcode::Halt, operands: vec![] },
                ],
                labels: {
                    let mut labels = BTreeMap::new();
                    labels.insert("done".to_string(), 3);
                    labels
                },
            },
        );
        let program = Program {
            format: "norscode-bytecode-v1".to_string(),
            entry: "__main__.start".to_string(),
            imports: vec![],
            functions,
            globals: BTreeMap::new(),
            constants: vec![],
        };
        let mut vm = Vm::new(program, TestIo::default());
        vm.run().unwrap();
        assert_eq!(vm.stack, vec![Value::Int(99)]);
    }
}
