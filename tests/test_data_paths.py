"""Tests for the shared catalog-vs-bundled data-file resolver.

``wopr.tools._data_paths`` centralizes the repo-vs-bundled
path math three tool modules previously duplicated. Pinning the
return order and the fallback semantics here keeps a future module
re-layout from silently changing what doctor, learnings, and
wopr_yml see.
"""

from __future__ import annotations

from pathlib import Path

from wopr.tools import _data_paths
from wopr.tools._data_paths import (
    candidate_data_paths,
    resolve_data_path,
)


class TestCandidateDataPaths:
    def test_returns_two_candidates_repo_first(self):
        """The dev (repo) candidate must come before the bundled one.

        This ordering is what lets editable installs pick up edits to
        catalog/ without reinstalling. If the order ever flips, the dev
        loop silently breaks.
        """
        result = candidate_data_paths("foo", "bar", "baz.yaml")
        assert len(result) == 2
        repo, bundled = result
        # Repo candidate is rooted under the project root + "catalog/...".
        assert "catalog" in repo.parts
        # Bundled candidate is rooted inside the installed package +
        # "resources/...".
        assert "resources" in bundled.parts

    def test_subtree_overrides_are_honored(self):
        result = candidate_data_paths(
            "x.txt", repo_subtree="custom_repo", bundled_subtree="custom_bundle",
        )
        repo, bundled = result
        assert "custom_repo" in repo.parts
        assert "custom_bundle" not in repo.parts
        assert "custom_bundle" in bundled.parts
        assert "custom_repo" not in bundled.parts

    def test_empty_parts_returns_subtree_roots(self):
        repo, bundled = candidate_data_paths()
        assert repo.name == "catalog"
        assert bundled.name == "resources"

    def test_does_not_filter_by_existence(self, tmp_path: Path):
        """``candidate_data_paths`` is pure; non-existent candidates remain."""
        result = candidate_data_paths("definitely-not-real.yaml")
        # Neither needs to exist; both Path objects are still returned.
        assert len(result) == 2
        assert all(isinstance(p, Path) for p in result)


class TestResolveDataPath:
    def test_returns_first_existing_candidate(self, monkeypatch):
        """When both candidates exist, the repo one wins."""
        repo_path = Path("/tmp/__wopr_test_repo")
        bundled_path = Path("/tmp/__wopr_test_bundled")

        def _stub_candidates(*_args, **_kwargs):
            return [repo_path, bundled_path]

        # Pretend both exist.
        monkeypatch.setattr(_data_paths, "candidate_data_paths", _stub_candidates)

        # Patch Path.exists to return True for both candidates.
        original_exists = Path.exists

        def _exists(self):
            if self in {repo_path, bundled_path}:
                return True
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", _exists)
        assert resolve_data_path("anything") == repo_path

    def test_falls_through_to_bundled_when_repo_missing(self, monkeypatch):
        repo_path = Path("/tmp/__wopr_test_repo_missing")
        bundled_path = Path("/tmp/__wopr_test_bundled_present")

        def _stub_candidates(*_args, **_kwargs):
            return [repo_path, bundled_path]

        monkeypatch.setattr(_data_paths, "candidate_data_paths", _stub_candidates)

        original_exists = Path.exists

        def _exists(self):
            if self == repo_path:
                return False
            if self == bundled_path:
                return True
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", _exists)
        assert resolve_data_path("anything") == bundled_path

    def test_returns_none_when_neither_candidate_exists(self, monkeypatch):
        repo_path = Path("/tmp/__wopr_neither_repo")
        bundled_path = Path("/tmp/__wopr_neither_bundled")

        def _stub_candidates(*_args, **_kwargs):
            return [repo_path, bundled_path]

        monkeypatch.setattr(_data_paths, "candidate_data_paths", _stub_candidates)

        original_exists = Path.exists

        def _exists(self):
            if self in {repo_path, bundled_path}:
                return False
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", _exists)
        assert resolve_data_path("anything") is None
