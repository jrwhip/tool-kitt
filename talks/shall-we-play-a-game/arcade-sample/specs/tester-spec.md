# Tester Spec - WOPR Arcade

> **Stack:** Angular 22, Vitest (NOT Jest), Playwright; Amplify Gen 2 backend with TypeScript Lambda functions. Run every node/npm/npx command through `mise exec --`.
> **This file:** stack-pre-filled starting point.
> **For the deep version:** the generic `tester-spec.template.md` in the crew pack's templates (fetch via `get_pack_template`, `pack="crew"`, `name="tester-spec.template.md"`).

---

## Requirements Sources

| Document | Path | Purpose |
|---|---|---|
| Implementation tracking | `implementation-tracking.md` | Which REQs need coverage |
| Requirements | `requirements/REQ-ARC-<n>.md` | Acceptance criteria per REQ |
| Design standard | `requirements/design-standard.md` | Appearance rules (designer-owned `@visual` tests) |
| Coder spec | `specs/coder-spec.md` | Commands and production-code rules |
| API contract | `amplify/data/resource.ts` | Operation shapes; tests use its `Schema` type |

---

## Build and Test Commands

Use the commands table in `specs/coder-spec.md`. Coverage: `ng test --coverage`. Never point Vitest at individual files.

---

## Test File Layout

| Type | Location | Naming |
|---|---|---|
| Component test | next to the component | `<name>.component.spec.ts` |
| Service test | next to the service | `<name>.service.spec.ts` |
| Pipe / directive | next to the source | `<name>.pipe.spec.ts` / `<name>.directive.spec.ts` |
| Route guard | next to the guard | `<name>.guard.spec.ts` |
| Lambda handler | next to the handler in `amplify/functions/<name>/` | `handler.spec.ts` |
| E2E (Playwright) | `e2e/` | `<feature>.e2e-spec.ts` |

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

Every schema operation (query, mutation, subscription):
- Success path
- Authorization denied (wrong player, non-participant)
- Business rejection (the REQ's named refusal, with its reason)

Every acceptance criterion involving two players, timing, or disconnects has an end-to-end test against the deployed sandbox.

---

## Fixtures and Mocks

### Use generated types
Test fixtures use the `Schema` type exported by `amplify/data/resource.ts`.
Never declare shape-only copies of API models in test files. When the spec changes, the compiler should tell you.

### Coverage exclusions
Generated files (`amplify_outputs.json`, `.amplify/**`) MUST be excluded from coverage denominators. The exclusion pattern lives in the project's `vitest.config.ts` `coverage.exclude` list. If the coverage math looks wrong on a regenerated client, check this list first.

---

## Anti-Patterns (auditor surfaces these as BLOCKERs)

- `.test.ts` filenames (Vitest convention is `.spec.ts`; mixed conventions break the test runner's discovery).
- Imports from `'@jest/globals'` (this is Vitest, not Jest).
- Hand-written shape-only copies of schema types in test files.
- Unit tests that touch real network; mock at the `generateClient` boundary. End-to-end tests run against the deployed sandbox.
- Tests that restate the implementation instead of checking the acceptance criterion.
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
- Every acceptance criterion maps to at least one named test (criterion -> test map on the log entry). Coverage percentages are a diagnostic only.
- `ng lint` and the backend typecheck are clean.

Never report `gate: PASS` without a fresh `ng test --coverage` measurement. The auditor re-measures and drift is a BLOCKER.

---

## Spec Maintenance

When `spec_writes` is ON (`wopr.yml` `specs.spec_writes`; default OFF), amend this spec when a new coverage shape or fixture idiom emerges. Examples:

- A new fixture-construction idiom (builder for nested signal-based forms).
- A coverage rule for a new test category.
- A new isolation rule discovered after a flaky test was diagnosed.
- A naming convention for a new test category (parameterized cases, property-based tests).
- A coverage-tool exclusion pattern other test authors will need.

---

## Visual Regression (only when `wopr.yml` declares `specs.design_spec`)

The `crew-designer` role owns these tests; the tester never writes or edits `@visual` tests, and the designer never writes anything else. Listed here because they live in the same e2e tree and the auditor runs them at the gate.

- Mechanism: Playwright screenshot assertions (`await expect(page).toHaveScreenshot(...)`), one per appearance acceptance criterion, tagged `@visual`.
- Command: `specs.visual_check` from `wopr.yml` (canonically `npx playwright test --grep @visual`).
- Baselines: committed to the repo at Playwright's default `__screenshots__/` layout. **Only the operator commits or updates a baseline.** The designer generates candidates and lists them; a machine-approved baseline grades the screenshot against itself.
- Coverage rule: a REQ whose acceptance criteria include appearance with no corresponding `@visual` test is a BLOCKER at audit (auditor checklist item 11).
