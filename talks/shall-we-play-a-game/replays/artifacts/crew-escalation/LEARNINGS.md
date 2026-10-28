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


## LRN-2026-10-28-a: TypeScript 6 and Angular 22 default strict and strictTemplates on when the flags are absent

```meta
date: 2026-10-28
project: mission-log
stack: [angular, typescript]
req: [REQ-ML-1]
auditor_run: AUDIT_REPORT.md@2026-10-28T06:10Z
severity: warning
origin: crew-auditor
```

**What happened.** The orchestrator saw that `tsconfig.json` set neither `strict` nor `strictTemplates`. It concluded that plain `ng build` was not a strict build, ran an ad hoc out-of-band `ngc` check, and logged a follow-up asking for strict to be enabled as its own REQ. In fact TypeScript 6 (`getStrictOptionValue`: `strict !== false`) and Angular compiler-cli 22 (`strictTemplates !== false`) both default these flags on. A probe build with an implicit `any` and a possibly-undefined template access failed with TS7006 and TS2532.

**Why it matters.** Reading strictness from whether a flag is present gives the wrong answer on current toolchains. That leads to unnecessary gate overrides and unnecessary REQs, and it erodes trust in correctly recorded results.

**Pattern to encode.** On TS 6+ / Angular 22+, treat strict mode as on unless a tsconfig explicitly sets `false`. Settle the question with a deliberate-violation probe build in a throwaway copy, not by reading the config. `tsc --showConfig` does not show defaulted strict flags.


## LRN-2026-10-28-b: Order-preservation pins are blind when the fixture's API order matches a natural sort key

```meta
date: 2026-10-28
project: mission-log
stack: [angular, vitest, testing]
req: [REQ-ML-1]
auditor_run: AUDIT_REPORT.md@2026-10-28T06:10Z
severity: blocker
origin: crew-auditor
```

**What happened.** REQ-ML-1 requires the list "in API order". The pinning test asserted the exact title sequence, but the fixture's API order (priorities 1, 2, 3; ids m-1, m-2, m-3) was also ascending priority and ascending id order. Reintroducing `sort((a, b) => a.priority - b.priority)` left all 15 tests green. A descending sort was caught, which made the pin look sound.

**Why it matters.** Sorting by a visible field (priority, date, id) is the most likely way a list-order requirement regresses. A fixture whose natural order coincides with such a key makes the pin pass for the wrong reason. Exact-sequence assertions look thorough, but they discriminate only as well as the fixture order allows.

**Pattern to encode.** For any "preserves source order" criterion, build the fixture so its source order differs from every sort key the UI shows or the model carries (for example priorities 2, 3, 1). At audit, falsify the pin by reintroducing an ascending sort on each such key, not only a reversal.
