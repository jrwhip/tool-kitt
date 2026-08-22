## LRN-2024-01-01-a: New components must declare OnPush change detection

```meta
date: 2024-01-01
project: _seed
stack: [angular]
req: []
auditor_run: seed@angular
severity: warning
seed: true
```

**What happened.** Components without `changeDetection: ChangeDetectionStrategy.OnPush` re-render on every change-detection cycle the application runs. With signals as the reactivity primitive in Angular 21+, OnPush plus signals gives the framework the precise re-render hints it needs; default change detection throws that away.

**Why it matters.** Default change detection is the single biggest source of "Angular feels slow" complaints. New code that omits OnPush eventually drives a performance regression no operator can attribute to one component.

**Pattern to encode.** Every new component sets `changeDetection: ChangeDetectionStrategy.OnPush`. Default CD on a `@Component` is a coder-spec violation and a BLOCKER at audit.


## LRN-2024-01-01-b: Never use @Inject decorator as setter injection

```meta
date: 2024-01-01
project: _seed
stack: [angular]
req: []
auditor_run: seed@angular
severity: warning
seed: true
```

**What happened.** `@Inject` decorator placed on a class property (setter injection) is invisible to the constructor signature, hides the dependency graph from `TestBed.configureTestingModule`, and produces `NullInjectorError` at test time because the test never wires the setter.

**Why it matters.** This is the one form of Angular DI that genuinely breaks. The modern `inject()` function at field level (the Angular 21+ recommended form), `inject()` inside the constructor body, and classic constructor-parameter injection (`constructor(private foo: Foo) {}`) all wire dependencies through the injector and all work in tests. Only `@Inject` as a property decorator skips the injector handshake.

**Pattern to encode.** Two accepted forms. (a) `inject()` at the field level or in the constructor body, preferred for new code. (b) Classic constructor-parameter injection, still valid for legacy code paths. Forbidden form: `@Inject` decorator on a class property. The previous version of this entry incorrectly conflated "field-level injection" with "setter injection" and rejected the modern `inject()` field pattern; that wording was wrong and produced contradictory guidance.


## LRN-2024-01-01-c: Subscriptions in components require teardown

```meta
date: 2024-01-01
project: _seed
stack: [angular]
req: []
auditor_run: seed@angular
severity: blocker
seed: true
```

**What happened.** A `.subscribe(...)` call in a component body without `takeUntilDestroyed(this.destroyRef)` (or equivalent teardown) keeps the subscription alive after the component is destroyed. Memory leak and surprising side effects.

**Why it matters.** The leaked subscription holds references to the destroyed component, blocks GC, and may continue to call handlers on a torn-down component. The bug is invisible in dev and shows up under prod traffic.

**Pattern to encode.** Prefer the `async` pipe in templates or `toSignal()` for component-local consumption. When `.subscribe()` is unavoidable, chain `.pipe(takeUntilDestroyed())`. Bare `.subscribe(...)` is a BLOCKER.


## LRN-2024-01-01-d: Generated API client files are overwrite-only

```meta
date: 2024-01-01
project: _seed
stack: [angular, openapi-generator]
req: []
auditor_run: seed@angular
severity: blocker
seed: true
```

**What happened.** A coder hand-edited a method in `libs/<api-name>/src/api/` to map a `*/*` response to `Blob`. The fix worked locally but was lost the next time the client regenerated.

**Why it matters.** Generated files are an output, not source. Any edit is silently reverted on the next generator run, leaving the team mystified when the bug "comes back."

**Pattern to encode.** Customizations to generated clients go in a Mustache template under `openapi-overrides/` with a header comment explaining what the default produced and why we overrode it. Never edit the generated file directly. Auditor BLOCKS on hand-edits in the generator output path.


## LRN-2024-01-01-e: Tests import from 'vitest', not '@jest/globals'

```meta
date: 2024-01-01
project: _seed
stack: [angular]
req: []
auditor_run: seed@angular
severity: warning
seed: true
```

**What happened.** A test file imported `describe`/`it`/`expect` from `@jest/globals` and `vi.fn` was written as `jest.fn()`. Vitest accepted the test through transparency but the spec subtly behaved like a Jest test (different timer handling, different module-mocking semantics).

**Why it matters.** Mixed conventions are worse than either. A future maintainer reads the test and assumes Jest semantics; Vitest's actual behavior diverges in edge cases that surface as flaky tests.

**Pattern to encode.** All Vitest specs import from `'vitest'`. Mocks use `vi.fn()`, `vi.spyOn()`, `vi.mock()`. The string `@jest/globals` never appears in this project. Filenames are `.spec.ts`, never `.test.ts`.


## LRN-2026-08-21-a: openapi-typescript peer-pins TypeScript 5, Angular 22 ships TypeScript 6

```meta
date: 2026-08-21
project: _seed
stack: [angular, openapi-generator]
req: []
auditor_run: seed@angular
severity: warning
seed: true
```

**What happened.** `npm install -D openapi-typescript` on a fresh Angular 22 project failed on peer dependency resolution: `openapi-typescript` declares a peer of `typescript@^5`, but Angular 22's scaffold installs TypeScript 6. The reflex fixes both make things worse: `--legacy-peer-deps` silently accepts a peer mismatch that may bite later, and downgrading the project's TypeScript to 5.x fights the framework's own pin.

**Why it matters.** The failure looks like a broken package rather than a lagging peer range, so the obvious fixes attack the wrong layer. Downgrading TypeScript project-wide to satisfy one dev-only codegen tool is a worse trade than isolating the tool.

**Pattern to encode.** Run `openapi-typescript` through a version-pinned `npx` invocation (e.g. `npx -y openapi-typescript@latest ...` in its own step) so its peer resolution stays local to that invocation, or add a `resolutions`/`overrides` entry scoped to that package only. Do not reach for `--legacy-peer-deps` or downgrade the project's TypeScript version.
