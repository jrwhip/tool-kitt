## LRN-2026-08-21-c: openapi-typescript peer-pins TypeScript 5, Angular 22 ships TypeScript 6

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


## LRN-2026-10-27-a: Default-selection tests on a native select are vacuous in jsdom

```meta
date: 2026-10-27
project: mission-log
stack: angular, vitest, jsdom
req: REQ-ML-1
auditor_run: AUDIT_REPORT.md@2026-10-27
severity: low
origin: crew-auditor
```

What happened: REQ-ML-1's criterion 1 ("All is selected on first render") was pinned by asserting `select.value === 'all'` and that the selected option reads "All". "All" is the first option, and jsdom (like browsers) selects the first option when none is marked selected. The `[selected]` bindings in the template could be deleted and the test would stay green.

Why it matters: the pin looks like coverage in the criterion map but cannot discriminate. A regression to the default state (for example a different initial signal value with an unbound select) would go unnoticed.

Pattern to encode: for a "default selected" criterion on a select or radio group, make the default discriminating. Either assert against a non-first default, or run a throwaway mutation that removes the binding and confirm the test fails. Treat first-option defaults as untested until mutated.
