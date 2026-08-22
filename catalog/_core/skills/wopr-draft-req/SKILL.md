---
name: wopr-draft-req
description: "Write executable requirement documents from decided scope, stored as REQ files, Jira issues, or GitHub issues. Use when drafting a new requirement, writing acceptance criteria for a decided feature, adding a REQ to an existing backlog, or choosing where requirements live."
---

<purpose>
Turns decided scope into requirement documents an agent crew can execute and an auditor can verify. Used by wopr-wargame's formalize phase, or standalone to add one REQ to an existing backlog. Scoping decisions are the operator's and arrive already made; this skill owns the format, the quality bar, and where the documents live.
</purpose>

<storage>
Ask once per project, before drafting anything, and record the answer in the tracking document and `wopr.yml`:

| Store | Crew support | Tradeoff |
|---|---|---|
| REQ files in `requirements/` (default) | Native (`requirements.source: local`) | Git-versioned, zero integration, invisible to non-repo stakeholders |
| Jira | Native (`requirements.source: jira`, Atlassian MCP) | Team visibility and workflow; heavy MCP context cost, so defer tool loading |
| GitHub issues | NOT yet a crew source | `gh` CLI is nearly free, but the crew cannot resolve REQs from issues today: pair with exported files, or extend the crew's req_resolution first |

A hybrid is normal: files as the drafting store, published to Jira or GitHub after sign-off (one issue per REQ, body verbatim, key/number recorded back into the file frontmatter as `jira:` or `github:`).
</storage>

<format>
```markdown
---
id: REQ-<KEY>-<n>
title: <short imperative title>
priority: <1..n, unique>
depends_on: [<REQ ids, or empty>]
status: pending
---

## Requirement
<2-6 sentences: what, for whom, and the boundary of what this REQ does NOT cover.>

## Acceptance criteria
1. <numbered, mechanically checkable>
```

In Jira or GitHub, the body is identical; frontmatter maps to issue fields (priority, links for depends_on), and the issue key or number is the id.
</format>

<quality_bar>
- Every criterion is mechanically checkable: an auditor verifies it against code, tests, or a live endpoint without judgment calls. Exact status codes, concrete inputs and outputs, named boundaries.
- If two honest reviewers could disagree about whether a criterion is met, rewrite it.
- Boundaries get their own criteria: the exact min, the exact max, one past the max.
- Every REQ is sized to one crew run; split anything bigger.
- Every REQ ends with the standing criteria: full test suite green including pre-existing tests, and the change visible in the OpenAPI document when it touches the API surface.
- No implementation design: no file names, no schema sketches, no library choices, except constraints the operator explicitly decided.
</quality_bar>

<standalone_use>
When adding a REQ outside a wargame session: read the existing baseline first, take the next id, check dependencies against existing REQs, draft, add the row to the Requirements Baseline table, and present for operator review before any publish step.
</standalone_use>
