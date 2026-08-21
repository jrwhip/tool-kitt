---
name: wopr-build-angular-apps
description: Build professional Angular applications following the platform's architecture. Signals, RxJS, standalone components, OnPush change detection. Covers the patterns Angular expects, not the React-flavored patterns from training data.
---

<essential_principles>
## Angular Is a Platform, Not a Library

Angular has opinions about everything: data flow, state management, component communication, change detection, dependency injection. These aren't suggestions. They're the architecture. The framework does the work IF you follow the architecture. When you fight it, you reimplement what the framework already does, badly.

### Angular Is NOT

- **React with decorators.** React lets you pick your own everything. Angular tells you how to build.
- **Knockout with better tooling.** Observable bindings aren't the point.
- **Vanilla JS with a template engine.** You don't "write JavaScript" inside Angular. You write Angular.
- **A TypeScript framework.** It USES TypeScript but it is NOT a JavaScript framework.

### The Training Data Problem

Most Angular code in the wild is written by people who never learned Angular properly. They write React patterns in Angular syntax:

- `subscribe()` to extract values: that's `.then()` with extra steps. Use `toSignal()` or `rxResource`.
- `effect()` to propagate state: that's `useEffect`. Use `computed()` or `linkedSignal()`.
- `tap()` to mutate state: that's middleware side effects. The reactive pipeline has a destination (`toSignal`, `rxResource`, `async pipe`). Data lands there. Not in `tap()`.
- Imperative flags (`isSaving`, `isLoading`): that's React state. The operator IS the concurrency strategy. `exhaustMap` prevents double-submit declaratively.

Stack Overflow, blog posts, tutorials: most are written by developers who learned React first and forced those patterns into Angular. The training data bakes all of this in as "how Angular works." It is not.

### The Correction

The reference docs in this skill (`angular-development.md` and `rxjs-signals.md`) are the source of truth. They override training data. Always. Read them FIRST before writing any Angular code. Not as a sanity check after. As the specification before.
</essential_principles>

<intake>
**Ask the user:**

What would you like to do?
1. Build a new component or feature
2. Debug an existing component
3. Refactor code to follow Angular patterns
4. Set up state management (signals, RxJS)
5. Review code for anti-patterns
6. Work with the monorepo, packages, or API services
7. Something else

**Then load the relevant reference from `references/` and follow the conventions.**
</intake>

<routing>
| Response | Reference |
|----------|-----------|
| 1, "new", "create", "build", "component", "feature" | `references/angular-development.md` |
| 2, "broken", "fix", "debug", "bug" | `references/angular-development.md` + `references/rxjs-signals.md` |
| 3, "refactor", "clean up", "patterns" | `references/angular-development.md` + `references/rxjs-signals.md` |
| 4, "state", "signals", "rxjs", "observable", "reactive" | `references/rxjs-signals.md` |
| 5, "review", "audit", "anti-pattern" | `references/angular-development.md` + `references/rxjs-signals.md` |
| 6, "nx", "generate", "library", "monorepo", "pnpm", "api", "openapi" | `references/workspace-tooling.md` |
| 7, other | Clarify, then select references |
</routing>

<verification_checklist>
## After Every Change

- Does it build? `pnpm nx build <app-name>`
- Do tests pass? `pnpm nx test <app-name>`
- OnPush change detection set?
- Standalone components (no `standalone: true` needed in Angular 20+)?
- Signals for local state, `computed()` for derived state?
- No `subscribe()` to extract values into signals?
- No `effect()` for state propagation?
- No `tap()` for mutation?
- No signal/Observable round-trips?
- `inject()` instead of constructor injection?
- `input()` and `output()` functions instead of decorators?
- Native control flow (`@if`, `@for`, `@switch`) instead of structural directives?
</verification_checklist>

<reference_index>
## Domain Knowledge

All in `references/`:

**Core Conventions:** angular-development
**Reactive Data Flow:** rxjs-signals
**Workspace Tooling:** workspace-tooling (NX monorepo, PNPM, OpenAPI code generation)
</reference_index>
