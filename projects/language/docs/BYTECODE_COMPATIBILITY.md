# Bytecode Compatibility

This note defines the compatibility boundary for the current bytecode path.

## Canonical contract

The canonical bytecode contract lives in [BYTECODE_CONTRACT.md](./BYTECODE_CONTRACT.md).

## Compatibility rule

Phase 1 treats the following as stable:

- the current `norscode-bytecode-v1` payload family
- the shape of core runtime-loaded program data
- the bytecode handoff between compiler/backend and runtime validation

## What this means in practice

- `build` may change internally, but should continue to emit compatible bytecode for the current contract.
- `check` may add validation, but should continue to validate against the same bytecode contract.
- `run` and `test` may move between orchestrators, but should continue to consume the same stable bytecode boundary.

## Allowed change pattern

Compatible evolution should prefer:

- adding validation
- improving diagnostics
- extending internals behind the same contract

Breaking evolution should require:

- an explicit new bytecode format/version
- an updated contract document
- a migration note

## Phase 1 conclusion

For Phase 1, bytecode compatibility is considered documented through:

- the full contract in [BYTECODE_CONTRACT.md](./BYTECODE_CONTRACT.md)
- this shorter compatibility note for roadmap and implementation work
