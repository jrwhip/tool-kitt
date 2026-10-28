"""Stack detection on a workspace root: a container of sibling repos.

The shape under test::

    myproduct/              <- no .git, maybe a workspace kitt.yml
      backend/   .git, pyproject.toml (fastapi), kitt.yml
      frontend/  .git, package.json (angular), kitt.yml
      tests/     .git only

Without a root file the scan calls this a ``container`` and lists the
children it can recognize. With a workspace-kind root file the scan
calls it a ``workspace`` and the targets are exactly the declared
members, recognized or not.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from kitt.tools.stack_detect import detect_stack

WORKSPACE_YML = (
    "workspace:\n"
    "  slug: myproduct\n"
    "  name: My Product\n"
    "  projects:\n"
    "    - path: backend\n"
    "      role: backend\n"
    "    - path: frontend\n"
    "      role: frontend\n"
    "    - path: tests\n"
    "      role: tests\n"
)


def _mk_fastapi(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / "pyproject.toml").write_text(
        '[project]\nname = "api"\nversion = "0.1.0"\ndependencies = ["fastapi>=0.110"]\n',
        encoding="utf-8",
    )
    (path / "kitt.yml").write_text("project:\n  slug: api\n", encoding="utf-8")


def _mk_angular(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / "package.json").write_text(
        json.dumps({
            "name": "ui",
            "dependencies": {"@angular/core": "^21.0.0"},
            "devDependencies": {"vitest": "^1.0.0"},
        }),
        encoding="utf-8",
    )
    (path / "kitt.yml").write_text("project:\n  slug: ui\n", encoding="utf-8")
    (path / "LEARNINGS.md").write_text("", encoding="utf-8")


def _mk_bare_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)


def _mk_product(root: Path, *, root_yml: bool) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _mk_fastapi(root / "backend")
    _mk_angular(root / "frontend")
    _mk_bare_repo(root / "tests")
    if root_yml:
        (root / "kitt.yml").write_text(WORKSPACE_YML, encoding="utf-8")
    return root


def _detect(root: Path) -> dict[str, Any]:
    result = json.loads(detect_stack(str(root)))
    assert "error" not in result, result
    return result


@pytest.fixture
def container(tmp_path: Path) -> Path:
    return _mk_product(tmp_path / "myproduct", root_yml=False)


@pytest.fixture
def product(tmp_path: Path) -> Path:
    return _mk_product(tmp_path / "myproduct", root_yml=True)


class TestContainerWithoutRootFile:
    def test_is_container_without_a_workspace_block(self, container: Path):
        result = _detect(container)
        assert result["project_type"] == "container"
        assert result["monorepo_type"] is None
        assert result["workspace"] is None

    def test_bare_git_child_is_a_container_target(self, container: Path):
        """``tests/`` has ``.git`` and nothing else: the repo IS the signal."""
        result = _detect(container)
        targets = {t["target_path"]: t for t in result["targets"]}
        assert list(targets) == ["backend", "frontend", "tests"]
        assert targets["backend"]["framework"] == "fastapi"
        assert targets["tests"]["language"] is None
        assert targets["tests"]["framework"] is None

    def test_plain_child_without_git_or_markers_is_not_a_target(self, container: Path):
        (container / "notes").mkdir()
        result = _detect(container)
        assert "notes" not in [t["target_path"] for t in result["targets"]]

    def test_inventory_lists_child_files_with_kind(self, container: Path):
        result = _detect(container)
        kinds = {e["path"]: e["summary"]["kind"] for e in result["kitt_yml_inventory"]}
        assert kinds == {"backend/kitt.yml": "project", "frontend/kitt.yml": "project"}


class TestWorkspaceRoot:
    def test_root_workspace_yml_makes_project_type_workspace(self, product: Path):
        result = _detect(product)
        assert result["project_type"] == "workspace"
        assert result["monorepo_type"] is None
        assert result["workspace"]["slug"] == "myproduct"
        assert result["workspace"]["name"] == "My Product"

    def test_targets_are_declared_members_in_declared_order(self, product: Path):
        result = _detect(product)
        targets = {t["target_path"]: t for t in result["targets"]}
        assert list(targets) == ["backend", "frontend", "tests"]
        assert targets["backend"]["framework"] == "fastapi"
        assert targets["frontend"]["framework"] == "angular"
        # A declared member nothing recognizes still gets a bare profile.
        assert targets["tests"]["language"] is None
        assert targets["tests"]["framework"] is None

    def test_member_flags_report_kitt_yml_and_learnings(self, product: Path):
        result = _detect(product)
        members = {m["path"]: m for m in result["workspace"]["members"]}
        assert members["backend"] == {
            "path": "backend",
            "abs_path": str(product / "backend"),
            "slug": "backend",
            "role": "backend",
            "exists": True,
            "has_kitt_yml": True,
            "kitt_yml_kind": "project",
            "has_learnings": False,
            "detected": True,
        }
        assert members["frontend"]["has_learnings"] is True
        assert members["tests"]["has_kitt_yml"] is False
        assert members["tests"]["detected"] is False
        assert result["workspace"]["missing_children"] == []
        assert result["workspace"]["undeclared_children"] == []

    def test_undeclared_child_is_reported(self, product: Path):
        docs = product / "docs-site"
        docs.mkdir()
        (docs / "package.json").write_text(json.dumps({"name": "docs"}), encoding="utf-8")
        result = _detect(product)
        assert result["workspace"]["undeclared_children"] == ["docs-site"]
        # Undeclared children are NOT targets; the operator decides.
        assert "docs-site" not in [t["target_path"] for t in result["targets"]]

    def test_missing_declared_child_is_reported(self, product: Path):
        shutil.rmtree(product / "tests")
        result = _detect(product)
        assert result["workspace"]["missing_children"] == ["tests"]
        members = {m["path"]: m for m in result["workspace"]["members"]}
        assert members["tests"]["exists"] is False
        assert [t["target_path"] for t in result["targets"]] == ["backend", "frontend"]

    def test_inventory_marks_root_as_workspace_and_children_as_project(
        self, product: Path
    ):
        result = _detect(product)
        kinds = {e["path"]: e["summary"]["kind"] for e in result["kitt_yml_inventory"]}
        assert kinds == {
            "kitt.yml": "workspace",
            "backend/kitt.yml": "project",
            "frontend/kitt.yml": "project",
        }
        root_entry = next(
            e for e in result["kitt_yml_inventory"] if e["path"] == "kitt.yml"
        )
        assert root_entry["summary"]["workspace"]["projects"][0] == {
            "path": "backend",
            "slug": "backend",
            "role": "backend",
        }

    def test_nested_member_path_is_a_target_and_not_undeclared(self, tmp_path: Path):
        root = tmp_path / "myproduct"
        root.mkdir()
        _mk_fastapi(root / "apps" / "api")
        (root / "kitt.yml").write_text(
            "workspace:\n  slug: p\n  projects:\n    - path: apps/api\n",
            encoding="utf-8",
        )
        result = _detect(root)
        assert [t["target_path"] for t in result["targets"]] == ["apps/api"]
        assert result["workspace"]["undeclared_children"] == []


class TestWorkspaceIgnoresMonorepoMarkers:
    def test_nx_json_at_a_workspace_root_does_not_make_it_a_monorepo(self, product: Path):
        (product / "nx.json").write_text("{}", encoding="utf-8")
        result = _detect(product)
        assert result["project_type"] == "workspace"
        assert result["monorepo_type"] is None


class TestInvalidRootFile:
    def test_falls_back_to_container_and_inventory_says_invalid(self, container: Path):
        (container / "kitt.yml").write_text(
            "project: {slug: a}\nworkspace: {slug: b, projects: [{path: backend}]}\n",
            encoding="utf-8",
        )
        result = _detect(container)
        assert result["project_type"] == "container"
        assert result["workspace"] is None
        root_entry = next(
            e for e in result["kitt_yml_inventory"] if e["path"] == "kitt.yml"
        )
        assert root_entry["parse_ok"] is True
        assert root_entry["summary"]["kind"] == "invalid"
        assert "both" in root_entry["summary"]["error"]


class TestInventorySkipFilter:
    def test_workspace_under_a_skip_named_folder_still_inventories(self, tmp_path: Path):
        """The skip set applies inside the workspace, not to its absolute path."""
        root = _mk_product(tmp_path / "build" / "myproduct", root_yml=True)
        result = _detect(root)
        paths = sorted(e["path"] for e in result["kitt_yml_inventory"])
        assert paths == ["backend/kitt.yml", "frontend/kitt.yml", "kitt.yml"]

    def test_noise_dirs_inside_the_workspace_are_still_skipped(self, product: Path):
        noise = product / "frontend" / "node_modules" / "dep"
        noise.mkdir(parents=True)
        (noise / "kitt.yml").write_text("project:\n  slug: dep\n", encoding="utf-8")
        result = _detect(product)
        assert "frontend/node_modules/dep/kitt.yml" not in [
            e["path"] for e in result["kitt_yml_inventory"]
        ]
