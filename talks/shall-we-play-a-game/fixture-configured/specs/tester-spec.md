# Tester Spec - Mission Log

> **Stack:** Angular 21+, Vitest, OpenAPI client. NOT Jest. Works for a standalone Angular CLI project or an Nx monorepo; adjust the commands below to match.
> **This file:** stack-pre-filled starting point.
> **For the deep version:** the generic `tester-spec.template.md` in the crew pack's templates (fetch via `get_pack_template`, `pack="crew"`, `name="tester-spec.template.md"`).

---

## Requirements Sources

| Document | Path | Purpose |
|---|---|---|
| Implementation tracking | `IMPLEMENTATION_TRACKING.md` | Which REQs need coverage, which need disabled stubs |
| Extracted requirements | (legacy projects) `EXTRACTED_REQUIREMENTS.md` | Acceptance criteria per REQ |
| Coder spec | `specs/coder-spec.md` | What the production code should look like |
| OpenAPI spec | path in `kitt.yml` (`api_contract.spec_url`) | Source of truth for endpoint shapes; tests assert against generated types |

---

## Build and Test Commands

| Purpose | Standalone (Angular CLI) | Nx monorepo |
|---|---|---|
| Run tests for the affected app | `ng test` | `npx nx test <app>` |
| Run all tests | `ng test` | `npx nx run-many --target=test --all` |
| Run a single test with watch | `ng test --watch` | `npx nx test <app> --watch` |
| Run with coverage | `ng test --coverage` | `npx nx test <app> --coverage` |
| Lint | `ng lint` | `npx nx lint <app>` |

Never point Vitest at individual files (`vitest tests/foo.spec.ts`). Always go through the `ng`/Nx target above.

---

## Test File Layout

| Type | Location | Naming |
|---|---|---|
| Component test | next to the component | `<name>.component.spec.ts` |
| Service test | next to the service | `<name>.service.spec.ts` |
| Pipe / directive | next to the source | `<name>.pipe.spec.ts` / `<name>.directive.spec.ts` |
| Route guard | next to the guard | `<name>.guard.spec.ts` |
| E2E (Playwright) | `e2e/` (standalone) or `apps/<app>-e2e/src/` (Nx monorepo) | `<feature>.e2e-spec.ts` |

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
Generated files (`src/api/**`, or `libs/<api-name>/src/api/**` in an Nx monorepo) MUST be excluded from coverage denominators. The exclusion pattern lives in the project's `vitest.config.ts` `coverage.exclude` list. If the coverage math looks wrong on a regenerated client, check this list first.

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
coverage_status: line XX% / branch YY% / static_analysis: PASS / gate: PASS
```

Or, when the gate fails:

```
coverage_status: line XX% / branch YY% / static_analysis: PASS / gate: FAIL (specific reason, e.g. "REQ-CASE-3 missing 404 path")
```

PASS means:
- Build passes.
- Full test suite passes (zero new failures).
- Every acceptance criterion maps to at least one named test (the criterion-to-test map is the pass metric).
- Coverage percentages: this project has no coverage provider installed yet, so record `coverage: n/a (no provider)`. Do not install one inside a feature REQ; that is its own REQ.
- Static analysis: this project has no lint target or Sonar; a strict `ng build` (strict TypeScript, strict templates) stands in. Record `static_analysis: ng build strict`.

Never report `gate: PASS` without a fresh `ng test` run and a fresh `ng build`. The auditor re-runs both and drift is a BLOCKER.

---

## Spec Maintenance

When `spec_writes` is ON (`kitt.yml` `specs.spec_writes`; default OFF), amend this spec when a new coverage shape or fixture idiom emerges. Examples:

- A new fixture-construction idiom (builder for nested signal-based forms).
- A coverage rule for a new test category.
- A new isolation rule discovered after a flaky test was diagnosed.
- A naming convention for a new test category (parameterized cases, property-based tests).
- A coverage-tool exclusion pattern other test authors will need.

---

## Visual Regression (only when `kitt.yml` declares `specs.design_spec`)

The `crew-designer` role owns these tests; the tester never writes or edits `@visual` tests, and the designer never writes anything else. Listed here because they live in the same e2e tree and the auditor runs them at the gate.

- Mechanism: Playwright screenshot assertions (`await expect(page).toHaveScreenshot(...)`), one per appearance acceptance criterion, tagged `@visual`.
- Command: `specs.visual_check` from `kitt.yml` (canonically `npx playwright test --grep @visual`).
- Baselines: committed to the repo at Playwright's default `__screenshots__/` layout. **Only the operator commits or updates a baseline.** The designer generates candidates and lists them; a machine-approved baseline grades the screenshot against itself.
- Coverage rule: a REQ whose acceptance criteria include appearance with no corresponding `@visual` test is a BLOCKER at audit (auditor checklist item 11).
