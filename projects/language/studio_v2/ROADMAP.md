# Norscode Studio v2 Roadmap

This roadmap tracks a full rebuild of Norscode Studio in Norscode.
The goal is to make Studio feel modern, fast, and AI-assisted from day one,
without inheriting the old GUI-first structure.

## Goal

- Build a new Studio in Norscode, not a gradual patch of the old one
- Make the editor, project tree, search, run/check/test, and AI panel feel like one product
- Keep AI optional, privacy-aware, and provider-agnostic
- Keep the core architecture simple enough that the app can evolve without becoming a second legacy codebase

## Product principles

- Norscode first: Studio should be written in Norscode and use the Norscode runtime and tooling
- AI as a helper, not a dependency: the app must still work without any model configured
- Explicit context: only send the minimum relevant source, diagnostics, and selection to the AI layer
- Safe edits: AI suggestions should be previewed before they are applied
- Single source of truth: file tree, editor, diagnostics, and AI actions should all share the same workspace state
- Small modules: each concern should live in its own module instead of one large Studio file

## Proposed module shape

- `studio/workspace.no`
- `studio/editor.no`
- `studio/project.no`
- `studio/search.no`
- `studio/actions.no`
- `studio/diagnostics.no`
- `studio/ai.no`
- `studio/ai_context.no`
- `studio/ai_text.no`
- `studio/ui.no`
- `studio/main.no`

## Phase 1: Studio foundation

- [x] Define the new Studio app entrypoint
- [x] Define workspace state for open files, project root, and active file
- [x] Define file tree loading and project metadata loading
- [x] Define a bootstrap command for starting Studio from the CLI
- [x] Define the app shell layout: file tree, editor, side panel, status bar

Acceptance:
- Studio can open a project root and show the file tree
- The active file is tracked centrally in workspace state
- The app shell renders without needing AI or advanced editor features

## Phase 2: Editor core

- [x] Add text buffer state
- [x] Add cursor movement and selection state
- [x] Add line numbers, active line highlight, and scrolling
- [x] Add open/save/reload actions
- [x] Add search within the current file

Acceptance:
- A file can be opened, edited, saved, and reloaded
- The editor keeps cursor and selection state stable
- Search works without leaving the editor

## Phase 3: Project navigation and symbol intelligence

- [x] Add symbol index loading from Norscode source files
- [x] Add `Def`/`Bruk` navigation
- [x] Add go-to-definition and find-references actions
- [x] Add rename preview for local symbols
- [x] Add quick file jump and symbol palette

Acceptance:
- The user can jump from usage to definition and back
- Rename operations show a preview before applying changes
- Search and navigation work across the whole workspace, not only the current file

## Phase 4: Command surface

- [x] Add run/check/test actions from Studio
- [x] Add diagnostics refresh from the current workspace
- [x] Add action palette for editor and project commands
- [x] Add a simple task/status output area

Acceptance:
- Studio can invoke the same project commands as the CLI
- Diagnostics are visible inside the app without switching tools
- Common commands are discoverable from a palette or menu

## Phase 5: AI integration

- [x] Define an AI provider interface
- [x] Define local, remote, and disabled AI modes
- [x] Define context collection for file, selection, diagnostics, and project summary
- [x] Add explain-code and summarize-file actions
- [x] Add refactor suggestions and test generation actions
- [x] Add AI-generated patch preview with accept/reject

Acceptance:
- AI can explain selected code or the active file
- AI can propose edits without applying them immediately
- AI can run with no provider configured, and the app still works
- The AI layer only receives explicit, inspectable context

## Phase 6: Safety and privacy

- [x] Add opt-in controls for sending code to an external provider
- [x] Add a clear privacy policy for AI context
- [x] Add redaction or context trimming for sensitive text
- [x] Add offline-only mode
- [x] Add per-workspace AI settings

Acceptance:
- The user can disable AI completely
- The user can see what is being sent to the AI layer
- Workspace settings can override global defaults

## Phase 7: UX polish and performance

- [x] Add keyboard shortcuts
- [x] Add theme support
- [x] Add faster workspace loading for large projects
- [x] Add incremental diagnostics refresh
- [x] Add session restore for the last open workspace

Acceptance:
- Studio feels fast for small and medium projects
- The UI can be used mostly from the keyboard
- Reopening Studio restores a useful working state

## Phase 8: Stabilization and migration

- [x] Freeze the public Studio module names
- [x] Write a migration note from the old Studio to Studio v2
- [x] Decide what stays legacy and what gets retired
- [x] Document the minimum supported Studio workflow
- [x] Make the AI provider contract stable

Acceptance:
- New Studio code can be built on top of a stable module layout
- The old Studio can be retired without breaking the new app
- AI integration has a stable contract, even if providers change later

## Phase 8 Notes

The public Studio v2 surface is now treated as stable around the modules in
`studio_v2/`, especially `main.no`, `workspace.no`, `project.no`, `editor.no`,
`symbol.no`, `actions.no`, `diagnostics.no`, `ai_context.no`, `ui.no`, and
`ai.no`.

The migration note lives in [MIGRATION.md](MIGRATION.md), and the stabilization
note lives in [STABILIZATION.md](STABILIZATION.md).

The old Studio remains legacy-only, while Studio v2 is the supported path for
new work.

## Suggested work order

1. Studio foundation
2. Editor core
3. Project navigation and symbol intelligence
4. Command surface
5. AI integration
6. Safety and privacy
7. UX polish and performance
8. Stabilization and migration

## AI integration notes

- AI should consume a small, explicit context object instead of raw workspace state
- Suggestions should be returned as structured actions when possible
- The app should support at least three modes:
  - disabled
  - local model
  - remote provider
- Prompts should be kept separate from the UI layer
- AI patch application should always be preview-first

## Notes

- This roadmap is intentionally for a new build, not a rebrand of the old Studio.
- The old Studio app can stay around as legacy while Studio v2 is built in parallel.
- The most important design choice is to keep AI as an additive layer, not the core of the editor itself.
