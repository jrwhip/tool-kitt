"""Tests for the shared atomic-write helpers.

``kitt._atomic_write`` is the single source of truth for all
operator-state and config writes. The helpers' contract is:

- ``atomic_write_text`` stages to a per-call temp file, optionally
  fsyncs, then ``os.replace``s into place. A crash anywhere before
  the replace leaves the original target intact and orphans only the
  temp; the temp is best-effort cleaned up before any raised OSError
  propagates.
- ``atomic_create_text`` uses ``open("x")`` so the create-or-fail
  check is a single filesystem operation. Raises ``FileExistsError``
  when the target already exists.

These tests pin each documented promise individually so a future
refactor cannot regress one without breaking a named test.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kitt import _atomic_write
from kitt._atomic_write import atomic_create_text, atomic_write_text


class TestAtomicWriteText:
    def test_happy_path_writes_content(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        atomic_write_text(target, "hello", fsync=False)
        assert target.read_text(encoding="utf-8") == "hello"

    def test_overwrites_existing_content(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        target.write_text("original", encoding="utf-8")
        atomic_write_text(target, "new", fsync=False)
        assert target.read_text(encoding="utf-8") == "new"

    def test_leaves_no_temp_files_on_success(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        atomic_write_text(target, "content", fsync=False)
        leftover = [p for p in tmp_path.iterdir() if p.name.startswith(f".{target.name}")]
        assert leftover == []

    def test_replace_failure_cleans_up_temp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """When os.replace raises, the temp file must not linger."""
        target = tmp_path / "file.txt"
        target.write_text("original", encoding="utf-8")

        def _raise(*_args, **_kwargs):
            raise OSError("simulated rename failure")

        monkeypatch.setattr(_atomic_write.os, "replace", _raise)

        with pytest.raises(OSError, match="simulated rename failure"):
            atomic_write_text(target, "new", fsync=False)

        # Original survives.
        assert target.read_text(encoding="utf-8") == "original"
        # No temp file left for the operator to clean up.
        leftover = [p for p in tmp_path.iterdir() if p.name.startswith(f".{target.name}")]
        assert leftover == []

    def test_write_failure_cleans_up_temp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """When the temp write itself raises, no stray temp lingers."""
        target = tmp_path / "file.txt"
        target.write_text("original", encoding="utf-8")

        real_open = Path.open

        def _open_raises(self, *args, **kwargs):
            if str(self).startswith(str(tmp_path)) and self.name.startswith(
                f".{target.name}"
            ):
                raise OSError("simulated open failure")
            return real_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", _open_raises)

        with pytest.raises(OSError, match="simulated open failure"):
            atomic_write_text(target, "new", fsync=False)

        # Original untouched. No temp lingers (the open never returned
        # a handle so nothing to clean, but the cleanup path must still
        # tolerate the missing file silently).
        assert target.read_text(encoding="utf-8") == "original"
        leftover = [p for p in tmp_path.iterdir() if p.name.startswith(f".{target.name}")]
        assert leftover == []

    def test_fsync_true_calls_os_fsync(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """With fsync=True the helper invokes os.fsync on the temp's fd."""
        target = tmp_path / "file.txt"
        seen_fds: list[int] = []
        real_fsync = os.fsync

        def _capture(fd: int):
            seen_fds.append(fd)
            return real_fsync(fd)

        monkeypatch.setattr(_atomic_write.os, "fsync", _capture)
        atomic_write_text(target, "content", fsync=True)
        assert len(seen_fds) == 1
        assert isinstance(seen_fds[0], int)

    def test_fsync_false_skips_os_fsync(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """With fsync=False the helper must NOT invoke os.fsync."""
        target = tmp_path / "file.txt"
        called = False

        def _record(_fd: int):
            nonlocal called
            called = True

        monkeypatch.setattr(_atomic_write.os, "fsync", _record)
        atomic_write_text(target, "content", fsync=False)
        assert called is False

    def test_temp_filename_is_hidden_and_unique(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Temp filename starts with a dot and embeds pid + random hex.

        Verified by mocking out os.replace so the temp survives, then
        inspecting the directory. The pattern lets concurrent in-process
        callers race without colliding on a fixed temp name.
        """
        target = tmp_path / "file.txt"

        observed: list[str] = []

        def _capture_then_keep(src: str, _dst: str):
            observed.append(Path(src).name)
            # Don't actually replace; we want to inspect the temp.

        monkeypatch.setattr(_atomic_write.os, "replace", _capture_then_keep)
        atomic_write_text(target, "content", fsync=False)

        assert len(observed) == 1
        name = observed[0]
        assert name.startswith(f".{target.name}.")
        assert name.endswith(".tmp")
        # pid + 16 hex chars = 17 chars at minimum between the dots.
        parts = name.split(".")
        assert len(parts) >= 4  # ['', 'file', 'txt', '<pid>', '<hex>', 'tmp']


class TestAtomicCreateText:
    def test_creates_when_target_missing(self, tmp_path: Path):
        target = tmp_path / "new.txt"
        atomic_create_text(target, "content", fsync=False)
        assert target.read_text(encoding="utf-8") == "content"

    def test_raises_file_exists_when_target_present(self, tmp_path: Path):
        target = tmp_path / "existing.txt"
        target.write_text("original", encoding="utf-8")
        with pytest.raises(FileExistsError):
            atomic_create_text(target, "new", fsync=False)
        # Original untouched.
        assert target.read_text(encoding="utf-8") == "original"

    def test_fsync_true_calls_os_fsync(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        target = tmp_path / "new.txt"
        seen_fds: list[int] = []
        real_fsync = os.fsync

        def _capture(fd: int):
            seen_fds.append(fd)
            return real_fsync(fd)

        monkeypatch.setattr(_atomic_write.os, "fsync", _capture)
        atomic_create_text(target, "content", fsync=True)
        assert len(seen_fds) == 1

    def test_fsync_false_skips_os_fsync(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        target = tmp_path / "new.txt"
        called = False

        def _record(_fd: int):
            nonlocal called
            called = True

        monkeypatch.setattr(_atomic_write.os, "fsync", _record)
        atomic_create_text(target, "content", fsync=False)
        assert called is False
