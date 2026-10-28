## LRN-2026-10-28-a: A "pure" rules function that returns a module-level constant by reference lets callers corrupt the rules

```meta
date: 2026-10-28
project: arcade
stack: [typescript, vitest, amplify-gen2]
req: [REQ-ARC-3]
auditor_run: AUDIT_REPORT.md@2026-10-28
severity: warning
origin: crew-auditor
```

**What happened.** A pure game-rules module returned the winning line inside each new state by reference to its own `WINNING_LINES` table. The table was only `readonly` at the type level. The separate read function deep-copied and froze, but the move function did not. 100% coverage and 16 per-line tests passed, since every test compared the line with `toEqual` and none mutated it.

**Why it matters.** Types do not stop runtime writes. One caller mutating a returned `result.line` changes win detection for every later game in the process. Tests that only assert equality cannot see aliasing.

**Pattern to encode.** When an authority module returns data derived from a module-level constant table, either freeze the table (and its rows) at definition or copy on return. Add one test that mutates a returned value and then re-runs the rule. Review every return path of a "pure" function for shared references, not only the read API.
