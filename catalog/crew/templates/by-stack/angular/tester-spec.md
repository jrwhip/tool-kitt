# Tester Spec - TODO: project name

> **Stack:** Angular 21+, Vitest, pnpm, OpenAPI client. NOT Jest.
> **This file:** stack-pre-filled starting point.
> **For the deep version:** `catalog/crew/templates/by-stack/_generic/tester-spec.md`.

---

## Requirements Sources

| Document | Path | Purpose |
|---|---|---|
| Implementation tracking | `IMPLEMENTATION_TRACKING.md` | Which REQs need coverage, which need disabled stubs |
| Extracted requirements | (legacy projects) `EXTRACTED_REQUIREMENTS.md` | Acceptance criteria per REQ |
| Coder spec | `specs/coder-spec.md` | What the production code should look like |
| OpenAPI spec | path in `wopr.yml` (`openapi.spec_url`) | Source of truth for endpoint shapes; tests assert against generated types |

---

## Build and Test Commands

| Purpose | Command |
|---|---|
| Run tests for the affected app | `pnpm nx test <app>` |
| Run all tests | `pnpm nx run-many --target=test --all` |
| Run a single test with watch | `pnpm nx test <app> --watch` |
| Run with coverage | `pnpm nx test <app> --coverage` |
| Lint | `pnpm nx lint <app>` |

Never point Vitest at individual files (`vitest tests/foo.spec.ts`). Always go through `pnpm nx test`.

---

## Test File Layout

| Type | Location | Naming |
|---|---|---|
| Component test | next to the component | `<name>.component.spec.ts` |
| Service test | next to the service | `<name>.service.spec.ts` |
| Pipe / directive | next to the source | `<name>.pipe.spec.ts` / `<name>.directive.spec.ts` |
| Route guard | next to the guard | `<name>.guard.spec.ts` |
| E2E (Playwright) | `apps/<app>-e2e/src/` | `<feature>.e2e-spec.ts` |

Co-location is mandatory. Tests do NOT live in a separate `tests/` tree.

---

## Vitest Configuration

- Specs import from `'vitest'` (`describe`, `it`, `expect`, `vi`). Never `'@jest/globals'` or implicit Jest globals.
- Spec files end in `.spec.ts`. Never `.test.ts`.
- `vi.fn()` for mocks. Never `jest.fn()`.
- Async assertions use `await expect(...).resolves` / `await expect(...).rejects`.

---

## What to Test

Every public service method:
- Happy path
- Null / empty / undefined input
- Validation failure / error response

Every component:
- Renders without throwing
- Reacts to input signal changes
- Emits expected outputs on user interactions
- Handles loading and error states from resources

Every route guard:
- Allow path
- Deny path
- Edge cases (no token, expired token, etc. per project rules)

Every endpoint consumed via the generated API client:
- 200 success path
- 4xx client error path
- 5xx server error path

---

## Fixtures and Mocks

### Use generated types
Test fixtures import response models from the generated API client.
```typescript
import type { CaseResponse } from '@org/api-client';
const fixture: CaseResponse = { id: 1, status: 'open', ... };
```
Never declare shape-only copies of API models in test files. When the spec changes, the compiler should tell you.

### `uniqueItems: true` collection fields
If an OpenAPI schema declares `uniqueItems: true`, the generator may emit `Set<T>` at that boundary. Build fixtures with the same container type the generator emits.

### Coverage exclusions
Generated files (`libs/<api-name>/src/api/**`) MUST be excluded from coverage denominators. The exclusion pattern lives in the project's `vitest.config.ts` `coverage.exclude` list. If the coverage math looks wrong on a regenerated client, check this list first.

---

## Anti-Patterns (auditor surfaces these as BLOCKERs)

- `.test.ts` filenames (Vitest convention is `.spec.ts`; mixed conventions break the test runner's discovery).
- Imports from `'@jest/globals'` (this is Vitest, not Jest).
- Hand-written shape-only copies of API response types in test files.
- Tests that touch real network. Mock at the HTTP-client boundary or use a generated client mock.
- Tests that depend on render order, animation timing, or `setTimeout` without `vi.useFakeTimers()`.
- Snapshot tests for component output. Snapshot rot is real; prefer explicit assertions.
- Skipping flaky tests with `it.skip`. Fix the flake or delete the test; never both leave it and ignore it.

---

## Coverage Gate (tester records, auditor cross-checks)

After tests pass, record on the REQ's implementation-tracking log entry:

```
coverage_status: line XX% / branch YY% / gate: PASS
```

Or, when the gate fails:

```
coverage_status: line XX% / branch YY% / gate: FAIL (specific reason, e.g. "REQ-CASE-3 missing 404 path")
```

PASS means:
- Build passes.
- Full test suite passes (zero new failures).
- Line >= `[TODO: floor]`, branch >= `[TODO: floor]`.
- Quality Gate (SonarCloud or equivalent) is `Passed` for the relevant commit.

Never report `gate: PASS` without a fresh `pnpm nx test <app> --coverage` measurement. The auditor re-measures and drift is a BLOCKER.

---

## Spec Maintenance

When `spec_writes` is ON (default), amend this spec when a new coverage shape or fixture idiom emerges. Examples:

- A new fixture-construction idiom (builder for nested signal-based forms).
- A coverage rule for a new test category.
- A new isolation rule discovered after a flaky test was diagnosed.
- A naming convention for a new test category (parameterized cases, property-based tests).
- A coverage-tool exclusion pattern other test authors will need.
