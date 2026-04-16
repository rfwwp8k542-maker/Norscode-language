# Studio v2 Migration Note

This note explains how to move from earlier Studio launchers to Studio v2.

## Recommended start path

- Use `make studio-v2`
- Or use `./scripts/studio-v2.sh`
- If you have already built the standalone binary, use `./dist/norscode studio-v2`

## What changes

- Studio v2 is the supported app for new work
- The app opens as a native launcher path instead of a separate bootstrap path
- Workspace, editor, symbol, diagnostics, actions, and AI state live in separate modules

## What stays compatibility-only

- Earlier launchers can remain installed during migration
- Existing workflows can keep using the older app path while migrating
- No new features should depend on the older Studio path

## Migration checklist

- Point new documentation at `studio_v2/README.md`
- Use the native launcher scripts in demos and examples
- Keep AI integration provider-agnostic
- Prefer the new module names in new code
- Treat earlier Studio launchers as compatibility-only
