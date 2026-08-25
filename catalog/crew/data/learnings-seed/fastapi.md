## LRN-2026-08-21-a: Postgres 18's official image moved the data volume mount

```meta
date: 2026-08-21
project: _seed
stack: [fastapi, postgres]
req: []
auditor_run: seed@fastapi
severity: blocker
seed: true
```

**What happened.** A compose file mounted a named volume at `/var/lib/postgresql/data`, the mount point used by every prior major version's official image. Against `postgres:18` the container exited 1 on first start.

**Why it matters.** The Postgres 18 official image changed its default `PGDATA` location to `/var/lib/postgresql` (the parent directory, not the versioned `data` subdirectory). A compose file written against the old convention fails immediately, before the app container ever gets a chance to connect.

**Pattern to encode.** For `postgres:18` and later, mount the volume at `/var/lib/postgresql`, not `/var/lib/postgresql/data`. Check the image's current `PGDATA` default when bumping the major version pin; do not assume the mount path carries forward.


## LRN-2026-08-21-b: httpx 0.28 removed the app keyword on AsyncClient

```meta
date: 2026-08-21
project: _seed
stack: [fastapi, httpx]
req: []
auditor_run: seed@fastapi
severity: blocker
seed: true
```

**What happened.** Test fixtures constructed `httpx.AsyncClient` passing the ASGI app directly via an `app` keyword argument, paired with `base_url="http://testserver"`, for in-process ASGI testing. Against httpx 0.28+, this raises `TypeError` at construction because that keyword no longer exists on `AsyncClient`.

**Why it matters.** Passing the app straight to `AsyncClient` was the standard idiom for testing FastAPI apps without a network listener for years, so it shows up in a lot of muscle memory and older tutorials. Any test suite pinned to httpx>=0.28 that still uses it fails before the first assertion runs.

**Pattern to encode.** Route the ASGI app through an explicit transport: `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")`. This is the only supported way to test an in-process ASGI app on httpx 0.28+.
