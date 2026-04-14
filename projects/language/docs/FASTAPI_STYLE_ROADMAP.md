# FastAPI-style Web Roadmap

This roadmap tracks a Norscode package for building web APIs with the same kind of ergonomics people expect from FastAPI: typed handlers, validation, automatic docs, dependency injection, and a clean test story.

## Goal

- Make it easy to define HTTP APIs in Norscode
- Keep handlers short and declarative
- Validate input from paths, query strings, headers, and bodies automatically
- Generate OpenAPI-style docs from the same source of truth
- Provide a good in-memory test client for local development

## Proposed package shape

- `std.web.http`
- `std.web.router`
- `std.web.request`
- `std.web.response`
- `std.web.schema`
- `std.web.openapi`
- `std.web.deps`
- `std.web.test`
- `std.web.security`

## Backlog

### 1. HTTP primitives

- [x] Define request/response primitives for web handlers
- [x] Add status codes, headers, and body helpers
- [x] Add JSON response helpers
- [x] Add content-type handling for common payloads

Acceptance:
- HTTP request and response strings can be assembled from small helpers
- Common statuses and content types are available from `std.web`
- JSON, HTML, and plain-text responses can be created without repeated boilerplate

### 2. Router core

- [x] Add route registration for `GET`, `POST`, `PUT`, `PATCH`, `DELETE`
- [x] Add path parameter parsing
- [x] Add query parameter parsing
- [x] Add route grouping or prefix mounting

Acceptance:
- `GET /hello` and `GET /users/{id}` work
- Query parameters are available to handlers in a structured way

### 3. Typed inputs

- [x] Parse typed function arguments from path/query/body sources
- [x] Add body parsing for JSON objects
- [x] Add conversion errors for bad input
- [x] Add clear error payloads for validation failures

Acceptance:
- A handler can declare typed inputs from path, query, and JSON body sources and get automatic conversion
- Invalid payloads produce a consistent 422 response with a readable error payload

### 4. Schema layer

- [x] Define field metadata for names, defaults, required values, and examples
- [x] Add nested object and list schema support
- [x] Add enum-like validation
- [x] Add reusable schema definitions

Acceptance:
- A request model can be reused across multiple endpoints
- Nested models produce readable validation errors

### 5. Dependency injection

- [x] Add request-scoped dependency resolution
- [x] Add shared config and service providers
- [x] Add simple override support for tests
- [x] Add lifecycle hooks for startup/shutdown

Acceptance:
- A handler can request services without manual wiring
- Tests can override dependencies cleanly

### 6. Middleware and hooks

- [x] Add middleware registration
- [x] Add before/after request hooks
- [x] Add exception mapping hooks
- [x] Add CORS support

Acceptance:
- Cross-cutting concerns can be added without touching every handler

### 7. OpenAPI generation

- [x] Generate OpenAPI JSON from routes and schemas
- [x] Expose a `/openapi.json` endpoint
- [x] Expose docs pages like `/docs` and `/redoc` or a single Norscode docs page
- [x] Include examples, tags, and response schemas

Acceptance:
- The API docs are generated from the same handler definitions
- The docs show inputs, outputs, and validation rules

### 8. Testing tools

- [x] Add an in-memory test client
- [x] Add request fixtures and response assertions
- [x] Add route snapshot helpers for docs
- [x] Add simple auth overrides for tests

Acceptance:
- API endpoints can be tested without starting a full server
- Tests can verify status, headers, JSON body, and validation errors

### 9. Security helpers

- [x] Add auth headers and bearer token parsing
- [x] Add optional session helpers
- [x] Add rate limiting hooks
- [x] Add CORS/CSRF guidance for common deployments

Acceptance:
- A small authenticated API can be built without reimplementing boilerplate

### 10. Developer ergonomics

- [x] Add `norscode web init`
- [x] Add `norscode web dev`
- [x] Add `norscode web test`
- [x] Add a starter template for API apps

Acceptance:
- A new API project can be scaffolded quickly
- The local dev loop feels natural and short

### 11. Example apps

- [x] Add a hello-world API
- [x] Add a CRUD sample with validation
- [x] Add an auth-protected route sample
- [x] Add a small JSON service example

Acceptance:
- A newcomer can copy a working example and extend it safely

### 12. Stabilization

- [x] Freeze the package names and public API surface
- [x] Write a migration note for any breaking changes
- [x] Document the minimal production deployment story
- [x] Decide whether the docs UI should be bundled or optional

Acceptance:
- The package is stable enough to recommend as the default web-API path

## Suggested order of work

1. HTTP primitives
2. Router core
3. Typed inputs
4. Schema layer
5. Dependency injection
6. OpenAPI generation
7. Testing tools
8. Developer ergonomics
9. Security helpers
10. Example apps
11. Stabilization

## Notes

- The roadmap is intentionally API-first, not server-framework-first.
- The goal is to let Norscode feel close to FastAPI in ergonomics, while still staying idiomatic to Norscode syntax and tooling.
- The runtime work already completed makes this feasible without needing C for normal execution.
