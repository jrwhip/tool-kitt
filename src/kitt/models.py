"""Typed data structures for KITT.

Replaces raw dicts with TypedDicts for JSON-persisted structures.
Provides type safety for mypy and IDE support without runtime overhead.
"""

from __future__ import annotations

from typing import TypedDict

# ============================================================================
# LOCK FILE
# ============================================================================


class LockFileData(TypedDict, total=False):
    """Data stored in kitt.lock.yaml."""

    version: str
    installed_packs: list[str]
    installed_at: str
    catalog_source: str


# ============================================================================
# TIME TRACKING
# ============================================================================


class ActiveTimer(TypedDict):
    """A currently running timer."""

    id: str
    task: str
    project: str
    start: str


class TimeEntry(TypedDict):
    """A completed time entry."""

    id: str
    task: str
    project: str
    start: str
    end: str
    duration_minutes: int
    synced_to_toggl: bool


class TimeTrackingData(TypedDict):
    """Root structure for time-tracking.json."""

    entries: list[TimeEntry]
    active_timer: ActiveTimer | None


# ============================================================================
# NOTES
# ============================================================================


class Note(TypedDict):
    """A single note entry."""

    id: str
    content: str
    tags: list[str]
    created: str


class NotesData(TypedDict):
    """Root structure for notes.json."""

    notes: list[Note]
