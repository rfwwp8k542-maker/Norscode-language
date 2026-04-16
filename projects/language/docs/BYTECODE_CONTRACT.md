# Bytecode Contract

This document defines the runtime contract that the native Norscode VM should follow.
It mirrors the behavior that is currently used by the shipped interpreter and bytecode backend.

## Value Model

Runtime values are:

- `Int`
- `Bool`
- `Text`
- `List`
- `Null`

## Truthy Rules

The runtime treats these as false:

- `0`
- `false`
- `null`

Everything else is true.

## Stack Rules

- The VM uses a last-in, first-out stack.
- `PUSH` adds a value to the top of the stack.
- `POP` removes the top value.
- `DUP` duplicates the top value.
- `SWAP` exchanges the top two values.
- `OVER` copies the second value from the top.
- `PRINT` writes the top value without removing it.
- Stack underflow is a runtime error.

## Control Flow

- `JMP` jumps unconditionally.
- `JZ` jumps when the condition is false.
- `CALL` enters a new call frame.
- `RET` returns from the current frame.
- `HALT` stops execution.

## Core Operations

Arithmetic:

- `ADD`
- `SUB`
- `MUL`
- `DIV`
- `MOD`

Comparison and boolean logic:

- `EQ`
- `GT`
- `LT`
- `AND`
- `OR`
- `NOT`

Output:

- `PRINT`

## Operand Types

The contract uses these operand shapes:

- integer literal
- string literal
- label reference
- function reference
- stack/local/global index

## Current Opcode Set

The currently supported runtime vocabulary is:

- `PUSH`
- `LABEL`
- `JMP`
- `JZ`
- `CALL`
- `LOAD`
- `STORE`
- `ADD`
- `SUB`
- `MUL`
- `DIV`
- `MOD`
- `EQ`
- `GT`
- `LT`
- `AND`
- `OR`
- `NOT`
- `DUP`
- `POP`
- `SWAP`
- `OVER`
- `PRINT`
- `HALT`
- `RET`

## Bytecode File Format

The compiled bytecode payload uses the current `norscode-bytecode-v1` format.

Top-level fields:

- `format`: format tag string
- `entry`: entry function name, such as `__main__.start`
- `imports`: list of imported modules
- `globals`: optional module-level values
- `functions`: object keyed by fully-qualified function name

Function objects contain:

- `name`
- `module`
- `params`
- `code`

Instruction objects are stored as JSON arrays. Common shapes are:

- `[\"PUSH_CONST\", value]`
- `[\"LOAD_NAME\", name]`
- `[\"STORE_NAME\", name]`
- `[\"BUILD_LIST\", count]`
- `[\"CALL\", function_name, argc]`
- `[\"JUMP\", label]`
- `[\"JUMP_IF_FALSE\", label]`
- `[\"LABEL\", label]`
- `[\"POP\"]`
- `[\"INDEX_GET\"]`
- `[\"INDEX_SET\"]`
- `[\"BINARY_ADD\"]`
- `[\"BINARY_SUB\"]`
- `[\"COMPARE_EQ\"]`
- `[\"COMPARE_NE\"]`
- `[\"COMPARE_GT\"]`
- `[\"COMPARE_LT\"]`
- `[\"COMPARE_GE\"]`
- `[\"COMPARE_LE\"]`
- `[\"RET\"]`
- `[\"HALT\"]`
- `[\"RETURN\"]`

The loader should reject payloads with the wrong format, missing entrypoint,
invalid function metadata, or unknown instructions.

## Function Frames

Each call frame should track:

- current instruction pointer
- return address
- local values
- function/module identity

## Error Cases

The native runtime should fail clearly for:

- invalid bytecode version
- unknown opcode
- invalid operand
- stack underflow
- invalid jump target
- unknown function
- division by zero
- return without a frame
- I/O failure

## Print Semantics

`PRINT` should write the top value in a stable, readable form.
The current runtime leaves the value on the stack after printing.

## Scope Notes

- This contract is the baseline for the native runtime.
- Python and C implementations are reference paths, not the long-term runtime target.
- If a future language feature needs a new runtime rule, the contract should be updated before the feature becomes canonical.
