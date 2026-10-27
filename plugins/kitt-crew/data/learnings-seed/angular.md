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
