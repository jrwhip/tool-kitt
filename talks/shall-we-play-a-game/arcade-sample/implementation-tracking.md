# WOPR Arcade - Implementation Tracking

> **Last updated:** 2026-09-26 (fresh rebuild; baseline set, nothing built)
> **Scope:** Full app per `requirements/REQ-ARC-1` through `REQ-ARC-10`.
> **Status legend:** `⏳ Pending`, `🔄 In Progress`, `✅ Implemented`, `❌ Out of Scope`
> **Spec version pinned:** `@aws-amplify/backend` (version recorded at scaffold)
> **Generator version pinned:** `aws-amplify 6.22.0`
> **Structural context:** Net-new build. Stack and rules are in `specs/coder-spec.md` (Migration Context). `requirements/` is operator-owned. Commit locally after each UNBLOCKED REQ; never push.

## Session Intake (2026-09-26)

- **Run type:** crew run (scout, designer, coder, tester, auditor). Light run never used.
- **Scope:** REQ-ARC-1 through REQ-ARC-10, in number order, one crew run per REQ.
- **Structural context:** none beyond the header above and the coder spec's Migration Context. Additional decisions made by the orchestrator, standing for the whole session:
  - Operator instruction: the orchestrator makes every decision without pausing; open questions are answered by the orchestrator and recorded here.
  - Models: every crew role runs on Opus (operator instruction), overriding the pack's haiku/sonnet defaults.
  - Visual baselines: the operator delegated baseline review to the orchestrator for this session. The orchestrator inspects the designer's candidate screenshots against `requirements/design-standard.md` before committing them, and records each approval in the implementation log.
  - Project hooks: prompt-log and git-branch-guard both declined. Work happens on `main`, one local commit per UNBLOCKED REQ, never pushed.
  - Backend deploys go to the Amplify sandbox in the default AWS profile (account 019918485675). Unit tests never touch the network; e2e tests run against the deployed sandbox.
  - JOSHUA is a reserved callsign from REQ-ARC-1 onward (REQ-ARC-10 AC8), so the identity layer refuses it from the start rather than retrofitting.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Angular 22 (zoneless, standalone, signals) |
| Backend | AWS Amplify Gen 2, TypeScript Lambda functions |
| Database | DynamoDB |
| API contract | Amplify Data / AppSync GraphQL schema (`amplify/data/resource.ts`) |
| Auth | Cognito (email accounts, identity-pool guests) |
| Timers | EventBridge Scheduler |
| AI | Amazon Bedrock (Nova) for JOSHUA's live chat replies |
| Testing | Vitest, Playwright (4 browsers, 6 viewports) |
| Build | Angular CLI, npm, Node 24 via mise |

---

## Requirements Baseline

| REQ ID | Description | Status | Notes |
|---|---|---|---|
| REQ-ARC-1 | Identity and callsigns | ⏳ Pending | |
| REQ-ARC-2 | Matchmaking | ⏳ Pending | |
| REQ-ARC-3 | Game rules and server authority | ⏳ Pending | |
| REQ-ARC-4 | Live state and disconnect resilience | ⏳ Pending | |
| REQ-ARC-5 | Ratings, history, and leaderboard | ⏳ Pending | |
| REQ-ARC-6 | JOSHUA, the AI host | ⏳ Pending | |
| REQ-ARC-7 | Player chat | ⏳ Pending | |
| REQ-ARC-8 | Rematch | ⏳ Pending | |
| REQ-ARC-9 | Client experience and visual design | ⏳ Pending | |
| REQ-ARC-10 | Play against JOSHUA | ⏳ Pending | |

---

## Gap Analysis (Latest Session)

Not run yet. The scout fills this at the start of each crew run.

---

## Current Implementation Log

No entries yet.

---

## Key Files

- `requirements/` (REQs, `design-standard.md`, `blocklist.json`)
- `specs/coder-spec.md`
- `specs/tester-spec.md`
- `amplify/data/resource.ts`
- `AUDIT_REPORT.md`
