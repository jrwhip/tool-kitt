# [PROJECT NAME] - Frontend Handoff Contract

> **For pack users:** this is a skeleton for the frontend-backend handoff contract. When the legacy-migration crew produces a rewritten backend, the frontend team needs to know what changed at the API surface so they can migrate their calls. This document is that handoff.
>
> The coder agent updates this document on every API change. The auditor agent blocks merge if the document is out of sync with the code. The frontend team reads it as a work breakdown.
>
> This template assumes a REST API. For GraphQL, gRPC, or other contracts, adapt the tables to match your surface.

---

# [PROJECT NAME] API - Frontend Handoff Contract

> **Created:** [YYYY-MM-DD]
> **Audience:** Frontend team migrating from the legacy backend to the [STACK: target stack] rewrite
> **Purpose:** Documents every new, changed, or removed API surface item introduced in this rewrite. Every endpoint entry has a REQ ID linking back to the extracted-requirements document and a JSON Pointer linking forward to the OpenAPI spec. The spec is the source of truth; this document is a human-readable work breakdown for the frontend team, not a duplicate contract.
> **OpenAPI spec URL or artifact path:** `[STACK: e.g. https://api.example.com/v3/api-docs, or specs/openapi.json committed in <backend-repo>]`
> **Spec version:** `[STACK: e.g. 4.2.1]` (as of [YYYY-MM-DD])
> **Generator version pinned:** `[STACK: e.g. openapi-generator-cli 7.21.0]`
> **Migration Context summary:** [STACK: one-line summary. Full content in the extracted-requirements document's Migration Context section.]

---

## Clean-Break Notice

> **DELETE or EDIT this section** based on your migration strategy.
>
> If the rewrite does NOT preserve legacy path aliases, header names, or status codes, say so explicitly here. Example:
>
> This rewrite does not preserve any legacy path aliases. All endpoints are under `[STACK: e.g. /api/v1/]` using plural kebab-case resource names. There are no `[STACK: list legacy-style paths being removed]` legacy-style paths in this build.
>
> If the rewrite IS dual-path compatible for a migration window, say that instead and list the compatibility expiration date.

---

## [YYYY-MM-DD] - [Controller or Resource Group Name]

**Base path:** `[STACK: e.g. /api/v1/widgets]`
**Covers REQs:** REQ-[DOMAIN]-N[, ...]

| Method | Path | Success Status | REQ ID | Spec Ref (JSON Pointer) | Legacy Path / Migration Note |
|---|---|---|---|---|---|
| `GET` | `[STACK: e.g. /api/v1/widgets]` | 200 | REQ-[DOMAIN]-1 | `[STACK: e.g. #/paths/~1api~1v1~1widgets/get]` | [STACK: legacy path, or "new", or "consolidated from /web/widgets + /admin/widgets", or "renamed from /getWidgets"] |
| `GET` | `[STACK: e.g. /api/v1/widgets/{id}]` | 200 | REQ-[DOMAIN]-3 | `[STACK: e.g. #/paths/~1api~1v1~1widgets~1{id}/get]` | [STACK] |
| `POST` | `[STACK: e.g. /api/v1/widgets]` | **201** | REQ-[DOMAIN]-6 | `[STACK: e.g. #/paths/~1api~1v1~1widgets/post]` | [STACK] |
| `PUT` | `[STACK: e.g. /api/v1/widgets/{id}]` | 200 | REQ-[DOMAIN]-8 | `[STACK]` | [STACK] |
| `DELETE` | `[STACK: e.g. /api/v1/widgets/{id}]` | 200 | REQ-[DOMAIN]-9 | `[STACK]` | [STACK] |

**JSON Pointer syntax reminder:** forward slashes in paths are escaped as `~1`. A path segment `{id}` stays literal. `~` itself is escaped as `~0`. Example: `/api/v1/widgets/{id}` becomes `~1api~1v1~1widgets~1{id}` inside a JSON Pointer.

**Notes and gotchas:**

- [STACK: example contract delta, e.g. "POST returns **HTTP 201 Created**, not 200. Update any frontend code that checks for 200 on create."]
- [STACK: example query behavior, e.g. "GET with `?admin=true` returns all rows; without the param, returns only the caller's rows. Full role enforcement is deferred until auth is live."]
- [STACK: example placeholder header or auth note, e.g. "Request header `X-User-Email` is the identity placeholder until auth is wired. Default: `test@example.com`."]
- [STACK: example action semantics, e.g. "PUT `/{id}/all-update`: the `actionType` field in the request body controls behavior."]
- [STACK: example `uniqueItems` gotcha, e.g. "`GET /api/v1/widgets/{id}` returns `tags` as a `Set<string>`, not an array. The generated client's type reflects this; consumers that expect an array will fail to compile."]

**UI action required:**

- [STACK: e.g. "Update all CRUD calls to the new base path via the generated client"]
- [STACK: e.g. "Handle 201 on create"]
- [STACK: e.g. "Pass the identity placeholder header if auth is not yet wired"]
- [STACK: e.g. "Migrate save/submit logic to the new composite endpoint"]
- [STACK: e.g. "Regenerate client if not already on the pinned generator version"]

---

## [YYYY-MM-DD] - [Next Controller or Resource Group]

**Base path:** `[STACK]`
**Covers REQs:** REQ-[DOMAIN]-N[, ...]

| Method | Path | Success Status | REQ ID | Spec Ref (JSON Pointer) | Legacy Path / Migration Note |
|---|---|---|---|---|---|
| | | | | | |

**Notes and gotchas:**

-

**UI action required:**

-

---

## Deferred or Deleted Endpoints

Endpoints that existed in the legacy API but are NOT fully in the rewrite. Frontend must not wire UI to these. Two flavors:

- **Removed from spec:** the endpoint is not in the OpenAPI spec at all. The generated client does not include it. Calling it from UI code won't compile.
- **Deferred in scope:** the endpoint is in the spec (stubbed or functional) but this migration phase marks it out-of-scope. The generated client includes it; the frontend should not wire UI to it yet. The auditor flags any UI code that does.

| Legacy endpoint | Status | Reason | Replacement (if any) | Spec Ref (if still in spec) |
|---|---|---|---|---|
| `[STACK: legacy path]` | Removed from spec | [STACK: e.g. "Functionality dropped; replaced by event-driven flow"] | none | N/A |
| `[STACK: legacy path]` | Deferred in scope | [STACK: e.g. "Deferred until auth is wired"] | [STACK: legacy-compatible alternative or "none"] | `[STACK: JSON Pointer if in spec]` |
| `[STACK: legacy path]` | Removed from spec | [STACK: e.g. "Functionality moved to admin-only endpoint X"] | [STACK] | N/A |

---

## Header Contracts

Document any cross-cutting header the backend reads or emits.

| Header | Direction | Purpose | Default | Example |
|---|---|---|---|---|
| `[STACK: e.g. X-User-Email]` | Request | [STACK: identity placeholder until auth is wired] | `test@example.com` | `X-User-Email: user@example.com` |
| `[STACK: e.g. X-Request-Id]` | Request/Response | [STACK: correlation ID propagation] | generated | |

---

## Error Response Shape

The JSON shape of 4xx and 5xx responses. The frontend error handler must match this shape.

```json
[STACK: fill in the standard error shape, e.g.:
{
  "status": 400,
  "error": "Bad Request",
  "message": "name length must not exceed 40 characters",
  "path": "/api/v1/widgets",
  "timestamp": "2026-04-07T12:34:56.789Z"
}
]
```

**Status codes in use:**

| Status | Meaning | Where thrown |
|---|---|---|
| 400 | [STACK: e.g. Validation failed] | [STACK: controller boundary] |
| 401 | [STACK: e.g. Missing or invalid auth] | [STACK] |
| 403 | [STACK: e.g. Authenticated but not authorized] | [STACK] |
| 404 | [STACK: e.g. Resource not found] | [STACK] |
| 406 | [STACK: e.g. Business rule rejects the request] | [STACK] |
| 500 | [STACK: e.g. Unhandled server error] | [STACK] |
