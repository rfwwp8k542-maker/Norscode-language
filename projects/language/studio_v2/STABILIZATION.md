# Studio v2 Stabilization

Studio v2 is now treated as a stable app surface for new work.

## Stable module set

The following modules are considered the public Studio v2 surface:

- `studio_v2/main.no`
- `studio_v2/studio_state.no`
- `studio_v2/project.no`
- `studio_v2/editor.no`
- `studio_v2/symbol.no`
- `studio_v2/actions.no`
- `studio_v2/diagnostics.no`
- `studio_v2/ai_context.no`
- `studio_v2/ui.no`
- `studio_v2/ai.no`

## Supported workflow

- Start the app with `make studio-v2`
- Or use `./scripts/studio-v2.sh`
- Or use `./dist/norscode studio-v2 --gui-backend tk` when the standalone binary is available

## What is legacy

- Earlier Studio launchers are kept only for compatibility
- New development should target Studio v2
- Bootstrap entrypoints are no longer part of the Studio v2 launch path

## AI contract

- AI remains optional
- Provider selection stays provider-agnostic
- AI context remains explicit and preview-first
- Patch application should continue to be accept/reject based
