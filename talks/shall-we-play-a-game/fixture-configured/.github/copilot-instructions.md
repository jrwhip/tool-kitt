# Mission Log: Copilot instructions

Standalone Angular CLI app (Angular ^22.2, TypeScript, npm, Vitest). Read `AGENTS.md` at the repository root for the full context, then `kitt.yml`, `specs/coder-spec.md`, `specs/tester-spec.md`, and `LEARNINGS.md`.

- Commands: `npm start`, `npm test`, `npm run build`.
- The API contract is `api/openapi.json`, consumed through the generated client in `src/api/`. Never edit `src/api/`; hand edits are overwritten.
- Use standalone components, signals, `OnPush`, and `inject()`. Call the API only through the generated client.
- Requirements are local REQ files in `requirements/`.
