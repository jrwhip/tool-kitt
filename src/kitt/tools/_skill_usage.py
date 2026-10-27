"""Skill usage telemetry sidecar: counts and lifecycle labels, nothing else.

WOPR ships roughly 100 skills across its packs and, until this module,
could not answer "which of these does anyone actually use." That
question drives pack slimming and per-pack plugin packaging, so it
needs a real, durable answer rather than a guess.

The design is ported from hermes-agent's ``tools/skill_usage.py``
(sidecar JSON keyed by skill name, atomic writes, best-effort bumps,
active/stale/archived lifecycle, a pinned opt-out). Three deliberate
divergences, each because WOPR's ownership model differs from Hermes's:

1. **Archiving never touches the filesystem.** In Hermes a skill lives
   in the user's own ``~/.hermes/skills/`` and the curator may move it
   to ``.archive/``. WOPR skills are catalog-authored and installed by
   the installer into directories WOPR reconciles on every run. A
   sidecar that moved or deleted one would be fighting the installer,
   and the next install would put it right back. Here ``archived`` is a
   LABEL: "nothing has been observed
   using this for a long time; consider dropping the pack or declaring
   the skill dormant." The operator acts on it; this module never does.
2. **No provenance/eligibility filter.** Hermes needs one because it
   mixes bundled, hub-installed, and agent-authored skills with
   different owners. Every skill WOPR counts came from a pack, so the
   only per-skill policy knob needed is ``pinned``.
3. **No file lock.** Hermes takes an flock around the read-modify-write.
   WOPR's declared posture (see ``_atomic_write``) is single-operator,
   no cross-process locking, and the failure mode here is bounded and
   one-directional: a lost race drops counts, never invents them. That
   is consistent with the coverage contract below, where every count is
   already a lower bound.

Privacy: this sidecar stores skill NAMES, COUNTS, TIMESTAMPS, and the
SOURCE that observed each invocation. It never stores prompts, task
descriptions, arguments, file paths, or any other conversation content.
``record_invocation`` takes no free-text parameter for that reason: the
schema makes the leak impossible rather than promising it will not
happen.

COVERAGE BOUNDARY (read this before trusting a number)
------------------------------------------------------
Counts are a LOWER BOUND on real usage, per CLI, and the gap differs
per CLI. There is no path by which this module can observe every
invocation, so the report ships the coverage facts alongside the
numbers instead of presenting a total that looks authoritative:

* ``mcp`` -- the ``run_skill`` MCP tool. That tool does NOT ship in
  this repo (the cross-CLI shim layer was retired), so this source is
  currently historical: records written by an older install are still
  read and reported, but nothing here writes new ones.
* ``hook:claude`` -- the optional ``skill-usage-hook.py`` Stop hook
  (``catalog/_core/hooks/``), which reads Claude Code's own
  transcript and counts native ``Skill`` tool calls. Covers Claude Code
  natively-invoked skills, but ONLY on projects where the operator
  registered the hook. Not registered by default; zero counts from this
  source mean "not wired up", not "not used".
* **Uncovered: Copilot CLI and Gemini CLI native skill invocation.**
  Both install skills natively (``~/.copilot/skills/``,
  ``~/.gemini/skills/``) and invoke them entirely inside the CLI, never
  touching WOPR's MCP server. Copilot has an ``agentStop`` hook and a
  session transcript, so an equivalent counter is buildable, but what a
  native skill invocation looks like in that transcript has not been
  verified on a real session -- and an unverified counter that silently
  returns zero is worse than a documented gap. Same for Gemini.

Therefore: a zero count means UNOBSERVED, never "unused". Comparing
counts ACROSS skills is only valid when the same sources cover both,
which is why every report row carries its own ``sources`` breakdown.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, TypeAlias

from .._atomic_write import atomic_write_text
from ..catalog import get_global_home
from ..product import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


def is_safe_entry_name(name: str) -> bool:
    """True when ``name`` is a single, safe path component.

    Rejects empty names, ``.``/``..``, path separators (both flavors,
    so a name written on one OS cannot smuggle a separator past the
    other), NUL, and ``:``. The colon matters on Windows: it is illegal
    in filenames there, and a name like ``D:evil`` is drive-relative, so
    ``Path(base) / "D:evil"`` REPLACES ``base`` instead of joining onto
    it (it also kills NTFS alternate-data-stream forms like
    ``foo:stream``).

    Lived in the install manifest module in the prior toolset, which
    does not cross over; the sidecar is now its only consumer, so it
    lives here.
    """
    if not name or name in (".", ".."):
        return False
    return not any(sep in name for sep in ("/", "\\", "\x00", ":"))


USAGE_FILENAME = "skill-usage.json"
USAGE_VERSION = 1

State: TypeAlias = Literal["active", "stale", "archived"]
STATE_ACTIVE: State = "active"
STATE_STALE: State = "stale"
STATE_ARCHIVED: State = "archived"
VALID_STATES: frozenset[str] = frozenset((STATE_ACTIVE, STATE_STALE, STATE_ARCHIVED))

SOURCE_MCP = "mcp"
SOURCE_HOOK_CLAUDE = "hook:claude"
# Closed set on purpose. An unknown source is a caller bug or a
# tampered file; recording it would put an unbounded, unreviewed string
# into the sidecar, and the whole privacy claim above rests on the
# schema being closed.
KNOWN_SOURCES: frozenset[str] = frozenset((SOURCE_MCP, SOURCE_HOOK_CLAUDE))

# Thresholds are generous because the observed signal is a lower bound
# (see the coverage boundary above). Calling something stale after a
# month when the only wired-up source is the MCP fallback path would
# label most of the catalog stale on day 31 for no good reason.
DEFAULT_STALE_AFTER_DAYS = 120
DEFAULT_ARCHIVE_AFTER_DAYS = 365

# Guard against a hostile or buggy caller inflating the file. Skill
# directory names are path components; anything longer is not one.
MAX_NAME_LENGTH = 128


def usage_path() -> Path:
    """Path of the telemetry sidecar (respects ``WOPR_HOME``)."""
    return get_global_home() / USAGE_FILENAME


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def parse_iso(value: object) -> datetime | None:
    """Parse a stored ISO timestamp defensively; ``None`` when unusable.

    A naive timestamp (no offset) is assumed UTC so comparisons against
    :func:`_now` cannot raise. Anything unparseable returns ``None``,
    which every caller treats as "no signal" rather than as "epoch".
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _empty_record(now: datetime) -> dict[str, Any]:
    return {
        "count": 0,
        "sources": {},
        "first_seen_at": _iso(now),
        "last_used_at": None,
        "state": STATE_ACTIVE,
        "state_changed_at": None,
        "pinned": False,
    }


def _sanitize_record(raw: object, now: datetime) -> dict[str, Any] | None:
    """Coerce one on-disk record into the current shape, or drop it.

    Every field is validated independently: a corrupt ``sources`` map
    must not cost the operator their ``pinned`` flag, and a bogus
    ``state`` must not make the record unreadable. Returns ``None`` only
    when the entry is not a JSON object at all.
    """
    if not isinstance(raw, dict):
        return None
    record = _empty_record(now)

    count = raw.get("count")
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        record["count"] = count

    sources = raw.get("sources")
    if isinstance(sources, dict):
        clean_sources: dict[str, int] = {}
        for source, value in sources.items():
            if source not in KNOWN_SOURCES:
                continue
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                clean_sources[source] = value
        record["sources"] = clean_sources

    for field in ("first_seen_at", "last_used_at", "state_changed_at"):
        if parse_iso(raw.get(field)) is not None:
            record[field] = raw[field]
    # A record with no parseable first_seen_at keeps the fresh anchor
    # from _empty_record: an unanchored clock must start now, never at
    # epoch, or a single corrupt field would archive the skill.

    state = raw.get("state")
    if state in VALID_STATES:
        record["state"] = state

    record["pinned"] = raw.get("pinned") is True
    return record


def load_usage() -> dict[str, dict[str, Any]]:
    """Read the sidecar as ``{skill_name: record}``.

    Returns an empty map when the file is absent, unreadable, or not a
    JSON object. Telemetry is never load-bearing for a tool call, so a
    broken sidecar degrades to "no data" instead of raising.
    """
    path = usage_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("skill-usage: cannot read %s (%s); treating as empty", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    skills = data.get("skills")
    if not isinstance(skills, dict):
        return {}
    now = _now()
    out: dict[str, dict[str, Any]] = {}
    for name, raw in skills.items():
        if not isinstance(name, str) or not is_valid_skill_name(name):
            logger.debug("skill-usage: dropping invalid skill key %r", name)
            continue
        record = _sanitize_record(raw, now)
        if record is not None:
            out[name] = record
    return out


def save_usage(records: dict[str, dict[str, Any]]) -> bool:
    """Write the sidecar atomically. Returns True on success.

    Failures are logged at DEBUG and reported via the return value
    rather than raised: every caller is either a best-effort counter
    bump on the side of a real tool call, or a report that is still
    useful without the write landing.
    """
    path = usage_path()
    payload = {
        "version": USAGE_VERSION,
        "skills": {name: records[name] for name in sorted(records)},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
    except OSError as e:
        logger.debug("skill-usage: could not write %s: %s", path, e)
        return False
    return True


def is_valid_skill_name(name: object) -> bool:
    """True when ``name`` is usable as a sidecar key.

    A skill name is the on-disk directory name, so it must be a single
    safe path component (:func:`is_safe_entry_name`)
    and bounded in length. This is the only validation between an
    arbitrary caller (including a hook subprocess reading a transcript)
    and the file's key space.
    """
    if not isinstance(name, str) or not name.strip():
        return False
    if len(name) > MAX_NAME_LENGTH:
        return False
    return is_safe_entry_name(name)


def record_invocation(
    skill_name: str,
    source: str,
    *,
    count: int = 1,
    now: datetime | None = None,
) -> bool:
    """Count ``count`` invocations of ``skill_name`` observed by ``source``.

    Best-effort by contract: returns False (and logs at DEBUG) on an
    invalid name, an unknown source, a non-positive count, or a failed
    write. Callers MUST NOT let the result affect the tool call they are
    instrumenting -- telemetry that can break a skill invocation is
    worse than no telemetry.

    Only names and counts are persisted; there is deliberately no
    parameter for task text, arguments, or workspace paths.
    """
    if not is_valid_skill_name(skill_name):
        logger.debug("skill-usage: refusing invalid skill name %r", skill_name)
        return False
    if source not in KNOWN_SOURCES:
        logger.debug("skill-usage: refusing unknown source %r", source)
        return False
    if count <= 0:
        return False

    moment = now or _now()
    records = load_usage()
    record = records.get(skill_name) or _empty_record(moment)
    record["count"] = int(record.get("count", 0)) + count
    sources = record.get("sources")
    if not isinstance(sources, dict):
        sources = {}
    sources[source] = int(sources.get(source, 0)) + count
    record["sources"] = sources
    record["last_used_at"] = _iso(moment)
    # Use resets the lifecycle: an invocation is direct evidence the
    # skill still earns its place, and a stale/archived label that
    # survived one would be actively misleading.
    if record.get("state") != STATE_ACTIVE:
        record["state"] = STATE_ACTIVE
        record["state_changed_at"] = _iso(moment)
    records[skill_name] = record
    return save_usage(records)


def set_pinned(skill_name: str, pinned: bool, *, now: datetime | None = None) -> bool:
    """Pin (or unpin) a skill, exempting it from automatic transitions.

    The opt-out for deliberately-rare skills: a release-checklist skill
    that fires twice a year is not stale, it is seasonal, and no amount
    of observation window makes the counter right about it. Pinning
    creates the record if it does not exist yet, so a skill can be
    protected before it is ever observed.
    """
    if not is_valid_skill_name(skill_name):
        logger.debug("skill-usage: refusing invalid skill name %r", skill_name)
        return False
    moment = now or _now()
    records = load_usage()
    record = records.get(skill_name) or _empty_record(moment)
    record["pinned"] = bool(pinned)
    if pinned and record.get("state") != STATE_ACTIVE:
        # Pinning restores active: the pin says "the clock does not
        # apply here", and leaving a stale label on a pinned skill would
        # keep recommending an action the operator just refused.
        record["state"] = STATE_ACTIVE
        record["state_changed_at"] = _iso(moment)
    records[skill_name] = record
    return save_usage(records)


def forget(skill_name: str) -> bool:
    """Drop a skill's record entirely (e.g. after its pack is removed)."""
    records = load_usage()
    if skill_name not in records:
        return False
    del records[skill_name]
    return save_usage(records)


def classify(
    record: dict[str, Any],
    *,
    now: datetime,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    archive_after_days: int = DEFAULT_ARCHIVE_AFTER_DAYS,
) -> State:
    """Derive the lifecycle label for one record. Pure; no I/O.

    The clock runs from the last observed invocation, falling back to
    ``first_seen_at`` (the moment WOPR first saw the skill installed) so
    a never-invoked skill ages from when it appeared rather than from
    epoch -- the seed-on-first-sight rule hermes-agent's curator uses.

    ``pinned`` short-circuits to ``active``: that is the opt-out, and it
    beats every threshold. A record whose anchor is unparseable also
    stays ``active``; absence of a judgeable signal is not evidence of
    staleness (same posture as ``_curator.plan_curation``).
    """
    if record.get("pinned") is True:
        return STATE_ACTIVE
    anchor = parse_iso(record.get("last_used_at")) or parse_iso(
        record.get("first_seen_at")
    )
    if anchor is None:
        return STATE_ACTIVE
    idle = now - anchor
    if idle > timedelta(days=archive_after_days):
        return STATE_ARCHIVED
    if idle > timedelta(days=stale_after_days):
        return STATE_STALE
    return STATE_ACTIVE


def refresh(
    records: dict[str, dict[str, Any]],
    installed: list[str],
    *,
    now: datetime,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    archive_after_days: int = DEFAULT_ARCHIVE_AFTER_DAYS,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Seed records for ``installed`` skills and recompute every state.

    Returns ``(records, changed)`` where ``changed`` is True when the
    caller should persist. Pure apart from the clock passed in.

    Seeding matters: a skill with no record has no anchor, so its
    staleness clock cannot start. Recording ``first_seen_at`` the first
    time WOPR sees the skill installed is what makes "never invoked in
    120 days" a statement about the skill rather than about when the
    operator installed WOPR.

    Records for skills that are no longer installed are KEPT. A pack
    can be removed and re-added, and history that survives that is more
    useful than history that silently resets; :func:`forget` is the
    explicit way to drop one.
    """
    updated = dict(records)
    changed = False

    for name in installed:
        if not is_valid_skill_name(name) or name in updated:
            continue
        updated[name] = _empty_record(now)
        changed = True

    for name, record in updated.items():
        state = classify(
            record,
            now=now,
            stale_after_days=stale_after_days,
            archive_after_days=archive_after_days,
        )
        if record.get("state") != state:
            record["state"] = state
            record["state_changed_at"] = _iso(now)
            changed = True
        updated[name] = record

    return updated, changed


def coverage_note() -> dict[str, Any]:
    """The machine-readable coverage boundary shipped with every report.

    Deliberately part of the payload rather than a docs footnote: a
    consumer that reads ``count`` without reading this would draw
    conclusions the data cannot support (see the module docstring).
    """
    return {
        "counts_are": "lower bound",
        "observed_sources": {
            SOURCE_MCP: (
                "run_skill MCP tool. Covers every CLI that loads skills "
                "through the WOPR MCP server."
            ),
            SOURCE_HOOK_CLAUDE: (
                "skill-usage-hook.py Stop hook, counting native Skill tool "
                "calls in Claude Code's transcript. Only present on "
                "projects where the operator registered the hook."
            ),
        },
        "uncovered": [
            "Copilot CLI native skill invocation (~/.copilot/skills/): "
            "handled entirely inside the CLI, never reaches the MCP "
            "server. A hook-based counter is buildable but the transcript "
            "shape for a skill invocation is unverified, so none ships.",
            "Gemini CLI native skill invocation (~/.gemini/skills/): "
            "same situation as Copilot.",
        ],
        "reading_zero": (
            "A zero count means UNOBSERVED, not unused. Do not remove a "
            "skill on a zero count alone; check which sources are wired up "
            "on this machine first."
        ),
    }


def report(
    installed: list[str],
    *,
    now: datetime | None = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    archive_after_days: int = DEFAULT_ARCHIVE_AFTER_DAYS,
) -> dict[str, Any]:
    """Build the usage report, seeding and persisting refreshed state.

    ``installed`` is the list of skill names currently reachable (the
    caller enumerates them; this module does not know where skills
    live). Rows are returned for every known record, with
    ``installed: false`` on records whose skill is no longer present.
    """
    moment = now or _now()
    records, changed = refresh(
        load_usage(),
        installed,
        now=moment,
        stale_after_days=stale_after_days,
        archive_after_days=archive_after_days,
    )
    persisted = save_usage(records) if changed else True

    installed_set = set(installed)
    rows = [
        {
            "name": name,
            "count": record.get("count", 0),
            "sources": record.get("sources", {}),
            "state": record.get("state", STATE_ACTIVE),
            "pinned": record.get("pinned") is True,
            "first_seen_at": record.get("first_seen_at"),
            "last_used_at": record.get("last_used_at"),
            "installed": name in installed_set,
        }
        for name, record in sorted(records.items())
    ]
    return {
        "generated_at": _iso(moment),
        "sidecar": str(usage_path()),
        "persisted": persisted,
        "thresholds": {
            "stale_after_days": stale_after_days,
            "archive_after_days": archive_after_days,
        },
        "coverage": coverage_note(),
        "totals": {
            "skills": len(rows),
            "observed": sum(1 for row in rows if row["count"] > 0),
            "unobserved": sum(1 for row in rows if row["count"] == 0),
            "pinned": sum(1 for row in rows if row["pinned"]),
        },
        "skills": rows,
    }
