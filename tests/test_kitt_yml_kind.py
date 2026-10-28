"""Tests for the ``kitt.yml`` kind classifier.

One classifier owns the rules for telling a project file from a
workspace file; these tests pin those rules so every reader that calls
it (write side, stub writers, detection, learnings) inherits them.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from kitt.tools._kitt_yml_kind import (
    KIND_INVALID,
    KIND_PROJECT,
    KIND_WORKSPACE,
    WORKSPACE_ROLES,
    DescribedMember,
    classify_kitt_yml_data,
    describe_members,
    find_enclosing_workspace,
    kitt_yml_kind,
    load_kitt_yml,
)

WORKSPACE_YML = """
workspace:
  slug: myproduct
  name: My Product
  projects:
    - path: backend
      slug: product-api
      role: backend
    - path: frontend
      role: frontend
    - path: tests
"""


def _data(text: str) -> object:
    return yaml.safe_load(text)


class TestClassify:
    def test_project_yml_is_project_kind(self):
        info = classify_kitt_yml_data({"project": {"slug": "api"}})
        assert info.kind == KIND_PROJECT
        assert info.is_project
        assert info.error is None
        assert info.workspace is None

    def test_workspace_yml_is_workspace_kind_with_defaults(self):
        info = classify_kitt_yml_data(_data(WORKSPACE_YML))
        assert info.kind == KIND_WORKSPACE
        assert info.is_workspace
        assert info.workspace is not None
        assert info.workspace.slug == "myproduct"
        assert info.workspace.name == "My Product"
        members = {m.path: m for m in info.workspace.members}
        assert list(members) == ["backend", "frontend", "tests"]
        assert members["backend"].slug == "product-api"
        assert members["frontend"].slug == "frontend"  # defaulted from the basename
        assert members["frontend"].role == "frontend"
        assert members["tests"].role == "other"  # defaulted

    @pytest.mark.parametrize(
        "spelling", ["./apps/api/", "apps//api", "apps/./api", "apps\\api", " apps/api "]
    )
    def test_member_path_is_normalized(self, spelling: str):
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "projects": [{"path": spelling}]}
        })
        assert info.kind == KIND_WORKSPACE, info.error
        assert info.workspace is not None
        assert info.workspace.members[0].path == "apps/api"
        assert info.workspace.members[0].slug == "api"

    @pytest.mark.parametrize("raw", ["backend", "./backend", "././backend", "backend//"])
    def test_duplicate_detection_sees_through_spellings(self, raw: str):
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "projects": [{"path": "backend"}, {"path": raw}]}
        })
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "more than once" in info.error

    @pytest.mark.parametrize("entry", ["just-a-string", 7, None, ["path", "x"]])
    def test_non_mapping_member_entry_is_invalid(self, entry: object):
        info = classify_kitt_yml_data({"workspace": {"slug": "p", "projects": [entry]}})
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "projects[0]" in info.error and "mapping" in info.error

    @pytest.mark.parametrize("slug", ["", "   ", 3, ["a"]])
    def test_non_string_or_blank_slug_is_invalid(self, slug: object):
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "projects": [{"path": "x", "slug": slug}]}
        })
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "slug" in info.error

    def test_non_string_name_is_invalid(self):
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "name": 42, "projects": [{"path": "x"}]}
        })
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "workspace.name" in info.error

    @pytest.mark.parametrize("block", ["text", 1, ["a"], None])
    def test_workspace_block_must_be_a_mapping(self, block: object):
        info = classify_kitt_yml_data({"workspace": block})
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "mapping" in info.error

    def test_both_project_and_workspace_is_invalid(self):
        info = classify_kitt_yml_data({
            "project": {"slug": "a"},
            "workspace": {"slug": "b", "projects": [{"path": "x"}]},
        })
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "both" in info.error

    def test_neither_block_is_invalid(self):
        info = classify_kitt_yml_data({"specs": {}})
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "project" in info.error

    def test_non_mapping_is_invalid(self):
        info = classify_kitt_yml_data(["not", "a", "mapping"])
        assert info.kind == KIND_INVALID
        assert info.data is None

    @pytest.mark.parametrize(
        ("path", "fragment"),
        [
            ("../sibling", ".."),
            ("x/../../y", ".."),
            ("/abs/path", "absolute"),
            ("\\foo", "absolute"),
            ("C:\\foo", "absolute"),
            ("C:/foo", "absolute"),
            (".", "root itself"),
            ("./", "root itself"),
            ("", "non-empty"),
            ("   ", "non-empty"),
        ],
    )
    def test_bad_member_paths_are_invalid(self, path: str, fragment: str):
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "projects": [{"path": path}]}
        })
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert fragment in info.error

    def test_duplicate_member_path_is_invalid(self):
        info = classify_kitt_yml_data({
            "workspace": {
                "slug": "p",
                "projects": [{"path": "backend"}, {"path": "./backend/"}],
            }
        })
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "more than once" in info.error

    def test_unknown_role_is_invalid(self):
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "projects": [{"path": "x", "role": "db"}]}
        })
        assert info.kind == KIND_INVALID
        assert info.error is not None
        for role in WORKSPACE_ROLES:
            assert role in info.error

    def test_empty_projects_list_is_invalid(self):
        info = classify_kitt_yml_data({"workspace": {"slug": "p", "projects": []}})
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "projects" in info.error

    def test_missing_slug_is_invalid(self):
        info = classify_kitt_yml_data({"workspace": {"projects": [{"path": "x"}]}})
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "workspace.slug" in info.error

    def test_project_only_sections_at_root_are_warnings_not_invalid(self):
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "projects": [{"path": "x"}]},
            "specs": {"coder_spec": "a.md"},
            "api_contract": {"spec_url": "x"},
        })
        assert info.kind == KIND_WORKSPACE
        assert len(info.warnings) == 2
        assert any("`specs`" in w for w in info.warnings)
        assert any("`api_contract`" in w for w in info.warnings)

    def test_learnings_section_at_root_is_allowed_silently(self):
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "projects": [{"path": "x"}]},
            "learnings": {"embeddings": {"provider": "none"}},
        })
        assert info.kind == KIND_WORKSPACE
        assert info.warnings == ()


class TestLoad:
    def test_absent_file_returns_none(self, tmp_path: Path):
        assert load_kitt_yml(tmp_path / "kitt.yml") is None
        assert kitt_yml_kind(tmp_path) is None

    def test_parse_failure_is_invalid(self, tmp_path: Path):
        (tmp_path / "kitt.yml").write_text("project: [unclosed", encoding="utf-8")
        info = load_kitt_yml(tmp_path / "kitt.yml")
        assert info is not None
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "parse" in info.error

    def test_kind_of_directory(self, tmp_path: Path):
        (tmp_path / "kitt.yml").write_text(WORKSPACE_YML, encoding="utf-8")
        assert kitt_yml_kind(tmp_path) == KIND_WORKSPACE

    def test_unreadable_file_is_invalid_not_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        target = tmp_path / "kitt.yml"
        target.write_text(WORKSPACE_YML, encoding="utf-8")

        def _boom(self: Path, *args: object, **kwargs: object) -> str:
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "read_text", _boom)
        info = load_kitt_yml(target)
        assert info is not None
        assert info.kind == KIND_INVALID
        assert info.error is not None
        assert "cannot read" in info.error


class TestFindEnclosingWorkspace:
    def test_finds_the_nearest_workspace_root_above_a_member(self, tmp_path: Path):
        root = tmp_path / "myproduct"
        member = root / "apps" / "api"
        member.mkdir(parents=True)
        (root / "kitt.yml").write_text(
            "workspace:\n  slug: p\n  projects:\n    - path: apps/api\n", encoding="utf-8"
        )
        found = find_enclosing_workspace(member)
        assert found is not None
        assert found[0] == root
        assert found[1].members[0].path == "apps/api"

    def test_skips_project_kind_ancestors(self, tmp_path: Path):
        root = tmp_path / "myproduct"
        mid = root / "mid"
        member = mid / "api"
        member.mkdir(parents=True)
        (mid / "kitt.yml").write_text("project:\n  slug: mid\n", encoding="utf-8")
        (root / "kitt.yml").write_text(
            "workspace:\n  slug: p\n  projects:\n    - path: mid/api\n", encoding="utf-8"
        )
        found = find_enclosing_workspace(member)
        assert found is not None
        assert found[0] == root

    def test_does_not_consider_the_start_directory_itself(self, tmp_path: Path):
        """Only ancestors count; a workspace file in ``start`` is not "enclosing"."""
        root = tmp_path / "myproduct"
        root.mkdir()
        (root / "kitt.yml").write_text(WORKSPACE_YML, encoding="utf-8")
        assert find_enclosing_workspace(root) is None


class TestDescribeMembers:
    def test_reports_each_member_in_declared_order(self, tmp_path: Path):
        root = tmp_path / "myproduct"
        root.mkdir()
        (root / "kitt.yml").write_text(WORKSPACE_YML, encoding="utf-8")
        backend = root / "backend"
        backend.mkdir()
        (backend / "kitt.yml").write_text("project:\n  slug: api\n", encoding="utf-8")
        (backend / "LEARNINGS.md").write_text("", encoding="utf-8")
        (root / "frontend").mkdir()
        # ``tests`` is declared but does not exist.

        info = load_kitt_yml(root / "kitt.yml")
        assert info is not None and info.workspace is not None
        members = describe_members(root, info.workspace)

        assert [m.path for m in members] == ["backend", "frontend", "tests"]
        assert members[0] == DescribedMember(
            path="backend",
            abs_path=backend,
            slug="product-api",
            role="backend",
            exists=True,
            has_kitt_yml=True,
            kitt_yml_kind=KIND_PROJECT,
            has_learnings=True,
        )
        assert members[0].to_json() == {
            "path": "backend",
            "abs_path": str(backend),
            "slug": "product-api",
            "role": "backend",
            "exists": True,
            "has_kitt_yml": True,
            "kitt_yml_kind": "project",
            "has_learnings": True,
        }
        assert members[1].has_kitt_yml is False
        assert members[1].kitt_yml_kind is None
        assert members[2].exists is False
        assert members[2].has_learnings is False

    @pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges")
    def test_skips_member_resolving_outside_root(self, tmp_path: Path):
        root = tmp_path / "myproduct"
        root.mkdir()
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        (root / "escape").symlink_to(outside, target_is_directory=True)
        (root / "inside").mkdir()
        info = classify_kitt_yml_data({
            "workspace": {"slug": "p", "projects": [{"path": "escape"}, {"path": "inside"}]}
        })
        assert info.workspace is not None

        members = describe_members(root, info.workspace)

        assert [m.path for m in members] == ["inside"]
