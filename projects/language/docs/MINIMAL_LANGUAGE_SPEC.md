# Minimal Language Spec

This document defines the minimum stable language surface for the Norscode core.

## Scope

This is not a full language manual.
It is the minimum contract that Phase 1 depends on.

## Source files

- Primary source files use the `.no` extension.
- A project entrypoint is defined through `[project].entry` in `norscode.toml`.
- Module loading is rooted in the project or import base directory.

## Lexing

- Tokens are whitespace-insensitive except where whitespace is part of string contents.
- Line comments are ignored by the parser.
- Identifiers are case-sensitive.
- Keywords and punctuation must tokenize deterministically before semantic analysis.

## Parsing

- Parsing must produce a deterministic AST for the same source text.
- Parse failures must include enough location data to identify the failing source position.
- Module imports must preserve declared module names and aliases.

## Imports and modules

- Imports are resolved relative to the current module root / loader root.
- Import aliases must be preserved into semantic analysis.
- Missing modules are hard errors.
- Duplicate or ambiguous alias resolution is a hard error.

## Semantic rules

- Function names, parameters, and imported names must resolve deterministically.
- Invalid references are hard errors.
- Semantic analysis is allowed to enrich metadata, but must not change source meaning.

## Error handling

- Lexing, parsing, semantic analysis, bytecode build, and runtime validation are all allowed to fail fast.
- Failure messages should stay specific enough for CLI use and CI gating.
- Legacy names and formats may warn, but core language failures must remain hard errors.

## CLI-facing core behaviors

- `run` is native-first.
- `check` combines semantic validation and native runtime validation.
- `build` is bytecode-first.
- `test` is native-first.

## Stability boundary

The minimum stable core for Phase 1 is:

- deterministic lexing
- deterministic parsing
- deterministic module/import resolution
- deterministic semantic failure behavior
- deterministic bytecode contract handoff to runtime
