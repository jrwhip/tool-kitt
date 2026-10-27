"""Shared atomic-write helpers for tool modules.

Tool modules persist operator state (TO-DOs, notes, time tracking,
handoff documents) and generated artifacts (kitt.yml, spec stubs,
LEARNINGS.md). A naive ``path.write_text`` is non-atomic: a crash
between truncation and full write leaves a partial file, and
concurrent writers race the bytes. The cost of a partial write
varies per file (notes are recoverable from memory; learnings have
no recovery path), so every module that persists state should use
these helpers instead of rolling its own pattern.

``atomic_write_text`` stages the bytes to a per-call temp name beside
the destination, fsyncs the temp, then ``os.replace`` over the
target. ``os.replace`` is atomic on POSIX and on Windows when the
source and destination live on the same volume.

Caveats this module does NOT solve:

* No directory fsync. A crash between the rename and the directory
  metadata flush could lose the rename on a power failure. For
  operator-driven, single-call-per-write usage this is acceptable;
  battery-backed FS journals make it effectively invisible. If a
  caller needs the directory metadata durable (release artifacts,
  lock files, etc.), it must fsync the parent dir itself.
* No signal handling. A SIGTERM between ``tmp.open()`` and
  ``os.replace()`` orphans the temp file. KITT is interactive; a
  background sweep of ``.<name>.*.tmp`` is left to the operator if
  it ever matters.
* No cross-process locking. Two concurrent writers race the replace
  calls; last writer wins silently. KITT is single-operator, so this
  is out of scope.

These are the same caveats the original ``kitt_yml`` writer carried
in its inline docstring; extracting the helper means every module
benefits from the same explicit posture rather than each module
reinventing it (or, worse, not).
"""

from __future__ import annotations

import contextlib
import os
import secrets
from pathlib import Path

# ``os`` is imported as a module reference here (not ``from os import
# replace``) so tests can patch ``_atomic_write.os.replace`` and
# ``_atomic_write.os.fsync`` as the documented hook for simulating
# rename failure and verifying fsync semantics. A future refactor that
# switches to ``from os import replace`` would silently break the
# patches and the tests would pass vacuously.


def atomic_write_text(target: Path, content: str, *, fsync: bool = True) -> None:
    """Write ``content`` to ``target`` atomically.

    Stages the content to a per-call temp file beside the destination,
    optionally fsyncs the temp's data, then ``os.replace``s into place.
    A crash anywhere before the replace leaves the original ``target``
    intact (or absent, if it did not exist) and orphans only the temp.

    Args:
        target: Destination path. Its parent directory must already
            exist; this helper does not create parents because the
            caller usually owns the directory contract (workspace
            root, ~/.kitt, etc.) and creating parents implicitly here
            could mask a misconfiguration.
        content: UTF-8 text to write.
        fsync: When True (the default), flush and ``os.fsync`` the
            temp file before the replace. The fsync is the only thing
            that turns "wrote bytes" into "durable across crash."
            Tests pass ``fsync=False`` to avoid the syscall cost; real
            operator-data writes leave it on.

    Raises:
        OSError: On any failure to write, fsync, or replace. The temp
            file is best-effort cleaned up before the exception
            propagates so a failed write does not leave stale temps
            beside the destination.
    """
    tmp = target.parent / f".{target.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(content)
            if fsync:
                fh.flush()
                os.fsync(fh.fileno())
        os.replace(tmp, target)
    except OSError:
        # Best-effort temp cleanup. Suppress so the original write
        # error is the one that surfaces to the caller.
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise


def atomic_create_text(target: Path, content: str, *, fsync: bool = True) -> None:
    """Create ``target`` exclusively (no overwrite) and write ``content``.

    Uses ``open(target, "x")`` so the create-or-fail check is a single
    filesystem operation with no exists()+write race window. A crash
    mid-write may leave a partial file that blocks future creates; the
    operator resolves that by deleting the partial and re-running.

    Args:
        target: Destination path. Must not already exist.
        content: UTF-8 text to write.
        fsync: When True (the default), flush and ``os.fsync`` the
            file before returning. Same rationale as
            :func:`atomic_write_text`.

    Raises:
        FileExistsError: When ``target`` already exists.
        OSError: On any other write or fsync failure. Unlike
            :func:`atomic_write_text` there is no temp to clean up,
            but the partial file at ``target`` may persist.
    """
    with target.open("x", encoding="utf-8") as fh:
        fh.write(content)
        if fsync:
            fh.flush()
            os.fsync(fh.fileno())


def atomic_write_bytes(target: Path, content: bytes, *, fsync: bool = True) -> None:
    """Binary-mode counterpart to :func:`atomic_write_text`.

    Same durability contract: stage to a per-call temp file beside the
    destination, optionally ``os.fsync``, then ``os.replace`` into
    place. A crash anywhere before the replace leaves the original
    target intact and orphans only the temp.

    Sidecar artifacts (``.npz``, etc.) that need atomic guarantees use
    this rather than rolling their own temp/fsync/replace dance. The
    patch hook is the same: tests can monkeypatch
    ``_atomic_write.os.replace`` and ``_atomic_write.os.fsync`` to
    simulate failures across both text and binary writers.

    Args:
        target: Destination path. Parent directory must exist.
        content: Bytes to write.
        fsync: When True (the default), flush and ``os.fsync`` the
            temp file's data before the replace. Same rationale as
            :func:`atomic_write_text`.

    Raises:
        OSError: On any failure to write, fsync, or replace. The temp
            file is best-effort cleaned up before propagating.
    """
    tmp = target.parent / f".{target.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    try:
        with tmp.open("wb") as fh:
            fh.write(content)
            if fsync:
                fh.flush()
                os.fsync(fh.fileno())
        os.replace(tmp, target)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise
