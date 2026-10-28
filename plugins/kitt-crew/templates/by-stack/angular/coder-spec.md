# Coder Spec - TODO: project name

> **Stack:** Angular 21+, TypeScript, Vitest, OpenAPI consumer. Works for a standalone Angular CLI project or an Nx monorepo; adjust the commands below to match.
> **This file:** stack-pre-filled starting point. Adjust per project; do not start from scratch.
> **For the deep version with every consideration spelled out:** see the generic `coder-spec.template.md` that ships in the crew pack's templates (fetch via `get_pack_template`, `pack="crew"`, `name="coder-spec.template.md"`).

---

## Migration Context

Structural decisions for this session live here. Examples:

- Module consolidation: `[TODO if applicable]`
- Endpoint renames: `[TODO if applicable]`
- Excluded scope: `[TODO if applicable]`
- Known-wrong legacy behaviors NOT to preserve: `[TODO if applicable]`

If this is a net-new project, write `No structural changes this session; implement REQs as extracted.`

---

## Build and Test Commands

The coder runs these before marking any requirement complete. Use the project's package manager (npm, pnpm, yarn) for install; standalone Angular CLI projects use `ng`, Nx monorepos use the workspace's Nx runner.

| Purpose | Standalone (Angular CLI) | Nx monorepo |
|---|---|---|
| Install dependencies | `npm install` | `npm install` |
| Build the affected app(s) | `ng build` | `npx nx build <app>` |
| Build everything | `ng build` | `npx nx run-many --target=build --all` |
| Run tests for an app | `ng test` | `npx nx test <app>` |
| Run all tests | `ng test` | `npx nx run-many --target=test --all` |
| Lint | `ng lint` | `npx nx lint <app>` |
| Regenerate the OpenAPI client | [STACK: project-specific script] | `npx nx run <api-lib>:generate-api` |

The coder does NOT point at individual test files. Always use the `ng`/Nx target above.

---

## Source Layout

| Concern | Standalone (Angular CLI) | Nx monorepo |
|---|---|---|
| App source | `src/app/` | `apps/*/src/app/` |
| Shared libraries | n/a (or a local `src/lib/`) | `libs/*/src/lib/` |
| Generated API clients | `src/api/` (DO NOT EDIT) | `libs/<api-name>/src/api/` (DO NOT EDIT) |
| App-level routes | `src/app/app.routes.ts` | `apps/*/src/app/app.routes.ts` |
| Standalone components | colocated with their feature or route | colocated with their feature or route |

`base_package` does not apply to Angular. Omit it from `kitt.yml`.

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

## API Consumption (OpenAPI Generator)

The frontend consumes the backend's OpenAPI spec via a generated client. Two rules are load-bearing:

1. **Never hand-write HTTP services or request/response types.** Always import from the generated client.
   ```typescript
   import { CaseService, CaseResponse } from '@org/api-client';
   ```
2. **Never hand-edit the generated files.** If a customization is needed (e.g. mapping a `*/*` response to `Blob`), the fix is a custom Mustache template at `openapi-overrides/api.mustache` with a header comment explaining what the default produced and why we overrode it.

The pinned generator version lives in `kitt.yml` (`api_contract.pinned_generator_version`). The pin must match the backend's `spec_version`.

If a needed endpoint is missing from the generated client, STOP and flag it as a missing backend dependency. Do not write a fallback.

---

## Styling

- Component-scoped SCSS unless the project explicitly uses Tailwind.
- Theme tokens come from the shared theme library (see `libs/<theme>` if present).
- Global CSS is forbidden except for resets in the shell.

---

## Anti-Patterns (auditor surfaces these as BLOCKERs)

- `@Component` without `changeDetection: OnPush` in new code.
- `NgModule` usage in new code.
- Hand-rolled HTTP services that duplicate the generated client.
- Hand-edits to generated API files.
- Reactive forms (`FormGroup`/`FormControl`) for new feature work when signal-based forms are available.
- `subscribe()` inside a component body without a teardown. Prefer `async` pipe, `toSignal`, or `takeUntilDestroyed`.
- Importing `rxjs/internal/*`. Use the public RxJS surface only.
- Accessing `document` / `window` directly. Use `DOCUMENT` token / `WINDOW` token.

---

## Coverage Gate

The five-condition gate (the orchestrator owns and enforces it; the tester records `coverage_status`; the auditor independently re-verifies):

1. Build passes. `ng build` (or `npx nx build <app>` in an Nx monorepo) exits 0.
2. Full test suite passes. `ng test` (or `npx nx run-many --target=test --all` in an Nx monorepo) exits 0.
3. Line coverage >= **TODO: project floor (start at 80)**. Branch coverage >= **TODO: project floor (start at 70)**.
4. If the REQ touched the API surface, the frontend handoff contract has a line item with a JSON Pointer into the OpenAPI spec.
5. Static-analysis Quality Gate (the project's configured tool, e.g. SonarCloud, SonarQube, or ESLint CI gate) reports `Passed` for the latest scan covering this REQ's commits.

---

## Spec Maintenance

When `spec_writes` is ON (`kitt.yml` `specs.spec_writes`; default OFF), the coder amends this spec when a new pattern emerges. Examples that belong here the moment they are used:

- A new component pattern this project will repeat (a route guard idiom, a form composition shape, etc.).
- A naming convention for a new category of file.
- A decision about how to handle a specific Angular API quirk.
- A build-config rule the next coder needs (build-target tweak, dependency version pin, profile gotcha).

Two inconsistent patterns are NEVER tolerated. If the new pattern replaces an old one, rewrite the old usage.
