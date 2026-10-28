# Coder Spec - WOPR Arcade

> **Stack:** Angular 22 (standalone Angular CLI project, zoneless), TypeScript 6, Vitest, Playwright; AWS Amplify Gen 2 backend in `amplify/` (Cognito, Amplify Data / AppSync GraphQL, DynamoDB, TypeScript Lambda functions, EventBridge Scheduler, Bedrock). Node 24 via `.mise.toml`.
> **This file:** stack-pre-filled starting point. Adjust per project; do not start from scratch.
> **For the deep version with every consideration spelled out:** see the generic `coder-spec.template.md` that ships in the crew pack's templates (fetch via `get_pack_template`, `pack="crew"`, `name="coder-spec.template.md"`).

---

## Migration Context

Net-new project. No structural changes this session; implement REQs as written in `requirements/`.

- The project scaffold (Angular app, `amplify/` skeleton, ESLint, Playwright) is created by Step 1 of `/build-arcade` before the first crew run.
- All backend code is TypeScript. No Python.
- The profanity blocklist is `requirements/blocklist.json`; code reads that one list.
- The visual design is `requirements/design-standard.md`; theme tokens in `src/styles.scss` match its section 2 exactly.
- `requirements/` is operator-owned: agents never edit REQ files, the design standard, or the blocklist.
- Playwright's WebKit does not run natively on the operator's Arch Linux machine; WebKit projects run inside the official Playwright image with `podman` (see Build and Test Commands).

---

## Build and Test Commands

Run every node/npm/npx command through `mise exec --` so Node 24 is used.

| Purpose | Command |
|---|---|
| Install dependencies | `npm install` |
| Build | `ng build` |
| Unit tests | `ng test` |
| Backend typecheck | `npx tsc -p amplify/tsconfig.json --noEmit` |
| Lint | `ng lint` |
| Deploy the backend sandbox | `npx ampx sandbox --once` (local AWS profile) |
| End-to-end tests (Chromium, Firefox) | `npx playwright test` |
| End-to-end tests (WebKit) | `podman run --rm --network host --ipc=host -v "$PWD":/work:Z -w /work mcr.microsoft.com/playwright:v<installed version>-noble npx playwright test --project=<webkit projects>` |
| Visual regression | `npx playwright test --grep @visual` |

The coder does NOT point at individual test files.

---

## Source Layout

| Concern | Location |
|---|---|
| App source | `src/app/` |
| App-level routes | `src/app/app.routes.ts` |
| Standalone components | colocated with their feature or route |
| Global theme tokens | `src/styles.scss` |
| Backend definition | `amplify/backend.ts` |
| Auth | `amplify/auth/resource.ts` |
| API contract (GraphQL schema) | `amplify/data/resource.ts` |
| Lambda functions | `amplify/functions/<name>/` (`resource.ts` + `handler.ts`) |
| Generated backend outputs | `amplify_outputs.json` (DO NOT EDIT, not committed) |
| End-to-end and visual tests | `e2e/` |

`base_package` does not apply. One feature per folder.

---

## Architecture Patterns

### Standalone components only
No `NgModule`. New code uses `standalone: true` (the default in Angular 21+). Components, directives, and pipes import their own dependencies via the `imports` array.

### Signals for reactive state
- Component state: `signal()`, `computed()`, `linkedSignal()`.
- Async: `resource()` / `httpResource()` (Angular 20+). Falls back to `toSignal(observable$)` when interop with RxJS is required.
- Forms: signal-based forms (`Control` from `@angular/forms/signals`) for new code; existing reactive forms (`FormGroup`) are tolerated but new feature work uses signals.
- Do NOT use `BehaviorSubject` for component-local state. Use `signal()`.

### OnPush change detection
Every new component declares `changeDetection: ChangeDetectionStrategy.OnPush`. The default `Default` strategy is forbidden in new code; it costs performance and hides re-render bugs.

### Dependency injection
- `inject()` function inside the constructor body or as a class field. Constructor parameter injection is the older style; new code uses `inject()`.
- `providedIn: 'root'` for app-wide services. Feature-scoped services use a feature-local provider.

### Routing
Lazy-load every feature route via `loadComponent` / `loadChildren`. Eager imports are reserved for the shell.

---

## API Consumption (Amplify Data)

The API contract is the Amplify Data schema in `amplify/data/resource.ts`. Agents cite contract items by operation or type name in that schema.

1. Front-end code calls the backend only through `generateClient<Schema>()` from `aws-amplify/data`, using the `Schema` type exported by `amplify/data/resource.ts`. Never hand-write GraphQL operation strings, HTTP calls, or copies of schema types.
2. Every state change the REQs require the server to decide (moves, matchmaking, ratings, chat moderation, claims) is a custom mutation with a Lambda handler; clients never write game state directly.
3. Live updates use schema subscriptions. Correctness never depends on one subscription message arriving (REQ-ARC-4 AC2): clients re-read authoritative state on gaps.
4. Never edit `amplify_outputs.json`; `ampx sandbox` generates it.

The pinned client version lives in `wopr.yml` (`api_contract.pinned_generator_version`) and must match `package.json`. If a needed operation is missing from the schema, the coder adds it in the same REQ.

---

## Styling

- Component-scoped SCSS unless the project explicitly uses Tailwind.
- Theme tokens are CSS custom properties in `src/styles.scss`; components reference tokens, never raw color values.
- Global CSS is forbidden except for resets in the shell.

---

## Anti-Patterns (auditor surfaces these as BLOCKERs)

- `@Component` without `changeDetection: OnPush` in new code.
- `NgModule` usage in new code.
- Hand-written GraphQL operation strings, HTTP calls, or schema type copies instead of `generateClient<Schema>()`.
- Hand-edits to `amplify_outputs.json`.
- Client code that writes game state the server must decide.
- Process or history comments in product source: REQ numbers, audit findings, rulings, learning IDs, dates, or narratives of how the code came to be. Comments explain only non-obvious code.
- Reactive forms (`FormGroup`/`FormControl`) for new feature work when signal-based forms are available.
- `subscribe()` inside a component body without a teardown. Prefer `async` pipe, `toSignal`, or `takeUntilDestroyed`.
- Importing `rxjs/internal/*`. Use the public RxJS surface only.
- Accessing `document` / `window` directly. Use `DOCUMENT` token / `WINDOW` token.

---

## Coverage Gate

The five-condition gate (the orchestrator owns and enforces it; the tester records `coverage_status`; the auditor independently re-verifies):

1. Build passes. `ng build` exits 0.
2. Full test suite passes. `ng test` exits 0.
3. Traceability: every acceptance criterion of the REQ maps to at least one named test. Line and branch coverage are recorded as a diagnostic, not a pass metric.
4. Single project, no handoff contract. If the REQ changed the schema, the backend typecheck passes and the sandbox deploys.
5. Static analysis: `ng lint` and the backend typecheck are clean.

---

## Spec Maintenance

When `spec_writes` is ON (`wopr.yml` `specs.spec_writes`; default OFF), the coder amends this spec when a new pattern emerges. Examples that belong here the moment they are used:

- A new component pattern this project will repeat (a route guard idiom, a form composition shape, etc.).
- A naming convention for a new category of file.
- A decision about how to handle a specific Angular API quirk.
- A build-config rule the next coder needs (build-target tweak, dependency version pin, profile gotcha).

Two inconsistent patterns are NEVER tolerated. If the new pattern replaces an old one, rewrite the old usage.
