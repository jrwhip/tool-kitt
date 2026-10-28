# Mission Log

Standalone Angular CLI app (Angular ^22.2, TypeScript, npm, Vitest) that lists the crew's missions. Frontend only; the backend is a separate service.

## Read these first

- `kitt.yml`: project slug (`mission-log`), source root (`src/app`), spec paths, requirements location.
- `specs/coder-spec.md`: patterns production code must follow.
- `specs/tester-spec.md`: how tests are written and what they must cover.
- `LEARNINGS.md`: accumulated lessons; check it before starting work.
- `implementation-tracking.md`: current REQ status.

## Commands

- `npm start`: serve on http://localhost:4200/ (`/api` is proxied to http://localhost:8080 via `proxy.conf.json`).
- `npm test`: run the Vitest suite through `ng test`.
- `npm run build`: production build.

## API contract

- The contract is the OpenAPI document at `api/openapi.json` (Mission Log API 1.2.0).
- It is consumed through the generated client in `src/api/` (openapi-generator-cli 7.21.0, `typescript-angular` generator).
- **Never edit `src/api/`.** Hand edits are overwritten. If the contract needs to change, raise it with the backend side; do not patch the client.

## Framework patterns

- Standalone components, signals for state, `OnPush` change detection, the `inject()` function for DI, and the new control flow (`@if`, `@for`).
- Application code lives under `src/app`; feature code under `src/app/missions`.
- Call the API only through the generated client services.

## Requirements

Requirements are local REQ files in `requirements/` (`<REQ-ID>.md`). Work one REQ at a time and keep `implementation-tracking.md` current.
