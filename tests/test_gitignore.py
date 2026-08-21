"""Tests for ``tools._gitignore.ensure_sidecar_gitignored`` ([TICKET-ID]).

The helper guarantees that ``<workspace>/.gitignore`` lists
``LEARNINGS.embeddings.npz`` so the machine-specific embeddings
sidecar never lands in source control. Idempotent; called from
``append_learnings`` and ``seed_learnings`` after every in-workspace
write.

Integration with the learnings public API (the actual call sites)
is exercised in ``test_learnings.py``; this file pins the helper's
behavior in isolation.
"""

from __future__ import annotations

from pathlib import Path

from wopr.tools._embeddings import EMBEDDINGS_SIDECAR_FILENAME
from wopr.tools._gitignore import ensure_sidecar_gitignored


class TestEnsureSidecarGitignored:
    def test_creates_gitignore_when_missing(self, tmp_path: Path):
        ensure_sidecar_gitignored(tmp_path)
        gitignore = tmp_path / ".gitignore"
        assert gitignore.is_file()
        text = gitignore.read_text(encoding="utf-8")
        assert EMBEDDINGS_SIDECAR_FILENAME in text
        # Section is labelled so the operator can see what WOPR added.
        assert "# WOPR" in text

    def test_appends_to_existing_gitignore_under_wopr_section(self, tmp_path: Path):
        existing = "# operator content\nbuild/\nnode_modules/\n"
        (tmp_path / ".gitignore").write_text(existing, encoding="utf-8")

        ensure_sidecar_gitignored(tmp_path)

        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        # Operator content is preserved verbatim.
        assert "# operator content" in text
        assert "build/" in text
        assert "node_modules/" in text
        # WOPR section is appended.
        assert EMBEDDINGS_SIDECAR_FILENAME in text
        assert "# WOPR" in text
        # WOPR content lands after the operator content.
        assert text.index("node_modules/") < text.index(EMBEDDINGS_SIDECAR_FILENAME)

    def test_no_op_when_sidecar_already_listed(self, tmp_path: Path):
        existing = f"build/\n{EMBEDDINGS_SIDECAR_FILENAME}\nnode_modules/\n"
        (tmp_path / ".gitignore").write_text(existing, encoding="utf-8")

        ensure_sidecar_gitignored(tmp_path)

        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        # File is unchanged; WOPR did not append a duplicate entry.
        assert text == existing
        assert "# WOPR" not in text  # No section header added either.

    def test_no_op_when_sidecar_already_listed_with_leading_slash(self, tmp_path: Path):
        existing = f"build/\n/{EMBEDDINGS_SIDECAR_FILENAME}\n"
        (tmp_path / ".gitignore").write_text(existing, encoding="utf-8")

        ensure_sidecar_gitignored(tmp_path)

        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert text == existing

    def test_idempotent_across_repeat_calls(self, tmp_path: Path):
        ensure_sidecar_gitignored(tmp_path)
        first = (tmp_path / ".gitignore").read_text(encoding="utf-8")

        ensure_sidecar_gitignored(tmp_path)
        second = (tmp_path / ".gitignore").read_text(encoding="utf-8")

        ensure_sidecar_gitignored(tmp_path)
        third = (tmp_path / ".gitignore").read_text(encoding="utf-8")

        # File content stabilizes after the first call; subsequent
        # calls produce no change.
        assert first == second == third
        # And the sidecar appears exactly once in the final content.
        assert first.count(EMBEDDINGS_SIDECAR_FILENAME) == 1

    def test_ignores_commented_sidecar_line(self, tmp_path: Path):
        # An operator-written comment that mentions the sidecar by name
        # is NOT a real exclude. WOPR must still add the real entry.
        existing = f"# we should gitignore {EMBEDDINGS_SIDECAR_FILENAME} someday\n"
        (tmp_path / ".gitignore").write_text(existing, encoding="utf-8")

        ensure_sidecar_gitignored(tmp_path)

        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        # Comment is preserved.
        assert "we should gitignore" in text
        # Real entry is now present.
        lines = [line.strip() for line in text.splitlines()]
        assert EMBEDDINGS_SIDECAR_FILENAME in lines

    def test_preserves_trailing_newline_in_existing_file(self, tmp_path: Path):
        existing = "build/\nnode_modules/\n"
        (tmp_path / ".gitignore").write_text(existing, encoding="utf-8")

        ensure_sidecar_gitignored(tmp_path)

        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        # File ends with a newline.
        assert text.endswith("\n")

    def test_handles_existing_file_without_trailing_newline(self, tmp_path: Path):
        existing = "build/\nnode_modules/"  # No trailing newline.
        (tmp_path / ".gitignore").write_text(existing, encoding="utf-8")

        ensure_sidecar_gitignored(tmp_path)

        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        # WOPR section is on its own line; the missing newline did not
        # cause the WOPR header to glom onto the operator's last line.
        assert "node_modules/\n" in text
        assert "# WOPR" in text

    def test_swallows_oserror_on_read(self, tmp_path: Path, monkeypatch):
        # If reading the .gitignore fails (permission denied, etc.),
        # the helper logs and returns without raising. The caller's
        # learnings.append_learnings has already succeeded; this
        # follow-up integration is best-effort.
        from pathlib import Path as _Path

        original_read_text = _Path.read_text

        def boom(self, *args, **kwargs):
            if self.name == ".gitignore":
                raise OSError("simulated permission denied")
            return original_read_text(self, *args, **kwargs)

        # Pre-create the file so the code path that reads it is taken.
        (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
        monkeypatch.setattr(_Path, "read_text", boom)

        # No exception escapes the helper.
        ensure_sidecar_gitignored(tmp_path)
