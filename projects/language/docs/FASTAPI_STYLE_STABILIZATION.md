# FastAPI-style Web Stabilization

This note captures the current stabilized shape of the Norscode web package.
The goal is to keep the public surface small, predictable, and easy to migrate.

## Frozen package names

The intended public package layout is:

- `std.web.http`
- `std.web.router`
- `std.web.request`
- `std.web.response`
- `std.web.schema`
- `std.web.openapi`
- `std.web.deps`
- `std.web.test`
- `std.web.security`

These names are treated as the stable API surface for the web package.

## Public API stability

The following groups are now considered stable enough for normal use:

- HTTP primitives
- router helpers
- typed input helpers
- schema helpers
- dependency injection helpers
- middleware and hooks
- OpenAPI generation helpers
- in-memory test client helpers
- security helpers
- developer ergonomics commands

If a future change needs to break one of these names or behaviors, the change
should come with a migration note and a compatibility plan.

## Migration note

If you previously used older website-centric paths, migrate to the new
web layout:

- use `website/index.no` for the current homepage source
- use `examples/web_*.no` for copyable API examples
- use `norscode web init` to scaffold a fresh app
- use `norscode web test` to run the web test files in a project

The old `website.no`-style normal execution path is no longer part of the
recommended flow.

## Minimal production deployment story

The smallest production story is:

1. build the project with the native runtime
2. run the app behind your preferred reverse proxy or platform
3. expose the API routes plus `/openapi.json`
4. optionally expose the docs page generated from `std.web.openapi_docs_respons(...)`

For local development, `norscode web dev` remains the recommended loop.

## Docs UI policy

The docs UI is optional, not mandatory.

- The canonical machine-readable contract is `/openapi.json`
- The HTML docs page is a convenience layer on top of that contract
- Projects may ship with the docs page enabled, disabled, or behind access control

## Current recommendation

- Keep `std.web` as the canonical namespace for web APIs
- Keep the docs UI optional
- Keep the runtime path strict native for normal execution
- Use the example apps in `examples/` as reference implementations
