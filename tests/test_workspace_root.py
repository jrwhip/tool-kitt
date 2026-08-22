"""Workspace-root resolution, and the multi-package repo it was broken on.

Three layers:

1. :func:`wopr.tools._workspace_root.find_workspace_root` as a pure
   function: markers, nearest-match-wins, and the git-toplevel boundary.
2. The learnings tools end to end on the exact shape that exposed the
   defect -- a repo whose ``wopr.yml`` files live in subpackages while
   the corpus lives at the repo root. ``seed_learnings`` wrote the root
   file, ``append_learnings`` sent the next entries to
   ``~/.wopr/LEARNINGS.md``, and the read path could reach neither, so
   the root corpus was an orphan that looked correct.
3. Status messages that describe what happened rather than what the
   happy path would have done.

Fixtures are built in ``tmp_path``. The real multi-package repo that
produced the bug report is not touched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from wopr.tools import learnings
from wopr.tools._workspace_root import (
    WorkspaceRoot,
    find_git_toplevel,
    find_workspace_root,
)
from wopr.tools.learnings import (
    _ensure_workspace_registered,
    _registration_note,
    append_learnings,
    curate_learnings,
    learnings_path,
    learnings_search,
    seed_learnings,
)

# ``isolated_env`` lives in tests/conftest.py: it isolates WOPR_HOME so
# nothing here can touch the operator's real ``~/.wopr``.

REPO_ROOT = Path(__file__).resolve().parents[1]


def _today() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def _entry(letter: str = "a", title: str = "A lesson", stack: str = "fastapi") -> str:
    """A LEARNINGS entry dated today so the recency prefilter keeps it."""
    return (
        f"## LRN-{_today()}-{letter}: {title}\n"
        "\n"
        "```meta\n"
        f"date: {_today()}\n"
        "project: sample\n"
        f"stack: [{stack}]\n"
        "req: []\n"
        "```\n"
        "\n"
        "**What happened.** Test fixture body.\n"
    )


def _shape(result: WorkspaceRoot) -> tuple[bool, int]:
    """Comparable shape of a resolution: did it find a root, after how many hops."""
    return (result.found, len(result.searched))


def _mkrepo(root: Path) -> Path:
    """Create a directory that looks like a git repository root."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir()
    return root


def _mkpackage(parent: Path, name: str) -> Path:
    """Create a subpackage carrying its own ``wopr.yml``."""
    package = parent / name
    package.mkdir(parents=True, exist_ok=True)
    (package / "wopr.yml").write_text("project:\n  slug: pkg\n", encoding="utf-8")
    return package


@pytest.fixture
def arcade(tmp_path: Path) -> tuple[Path, Path, Path]:
    """The shape from the bug report, minus the corpus.

    ``<root>/.git`` plus ``backend/wopr.yml`` and ``frontend/wopr.yml``,
    and deliberately NO ``LEARNINGS.md`` at the root yet: that file is
    what ``seed_learnings`` is supposed to establish.
    """
    root = _mkrepo(tmp_path / "arcade")
    backend = _mkpackage(root, "backend")
    frontend = _mkpackage(root, "frontend")
    return root, backend, frontend


class TestFindWorkspaceRoot:
    def test_wopr_yml_in_the_start_directory_wins_immediately(self, tmp_path: Path):
        package = _mkpackage(tmp_path, "pkg")
        result = find_workspace_root(package)
        assert result.found
        assert result.root == package
        assert result.searched == (package,)

    def test_learnings_md_is_a_marker_too(self, tmp_path: Path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "LEARNINGS.md").write_text("", encoding="utf-8")
        assert find_workspace_root(corpus).root == corpus

    def test_walks_up_from_a_directory_with_no_marker(self, tmp_path: Path):
        package = _mkpackage(tmp_path, "pkg")
        deep = package / "src" / "app" / "routers"
        deep.mkdir(parents=True)
        result = find_workspace_root(deep)
        assert result.root == package
        assert result.searched[0] == deep  # nearest first
        assert package in result.searched

    def test_nearest_match_wins_over_an_outer_one(self, tmp_path: Path):
        outer = _mkrepo(tmp_path / "outer")
        (outer / "LEARNINGS.md").write_text("", encoding="utf-8")
        inner = _mkpackage(outer, "inner")
        assert find_workspace_root(inner).root == inner

    def test_stops_at_the_git_toplevel(self, tmp_path: Path):
        """A marker outside the repository is not this repository's corpus."""
        (tmp_path / "wopr.yml").write_text("project:\n  slug: outside\n", encoding="utf-8")
        repo = _mkrepo(tmp_path / "repo")
        sub = repo / "sub"
        sub.mkdir()

        result = find_workspace_root(sub)

        assert not result.found
        assert result.root is None
        assert result.git_toplevel == repo
        assert result.searched == (sub, repo)  # walk stopped AT the toplevel
        assert tmp_path not in result.searched

    def test_the_git_toplevel_itself_is_searched(self, tmp_path: Path):
        repo = _mkrepo(tmp_path / "repo")
        (repo / "LEARNINGS.md").write_text("", encoding="utf-8")
        sub = repo / "sub"
        sub.mkdir()
        assert find_workspace_root(sub).root == repo

    def test_no_repo_and_no_marker_walks_to_the_filesystem_root(self, tmp_path: Path):
        loose = tmp_path / "loose"
        loose.mkdir()
        result = find_workspace_root(loose)
        assert not result.found
        assert result.git_toplevel is None
        assert result.searched[-1] == Path(loose.anchor)

    def test_a_git_file_marks_a_linked_worktree_toplevel(self, tmp_path: Path):
        """Worktrees and submodules carry ``.git`` as a file, not a directory."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        sub = worktree / "sub"
        sub.mkdir()
        assert find_git_toplevel(sub) == worktree
        assert find_workspace_root(sub).searched == (sub, worktree)

    def test_a_nonexistent_start_path_resolves_through_its_parents(self, tmp_path: Path):
        package = _mkpackage(tmp_path, "pkg")
        assert find_workspace_root(package / "not" / "created").root == package


class TestExplainAFailedSearch:
    def test_names_every_searched_path_and_the_git_boundary(self, tmp_path: Path):
        repo = _mkrepo(tmp_path / "repo")
        sub = repo / "sub"
        sub.mkdir()

        text = find_workspace_root(sub).explain()

        assert "wopr.yml or LEARNINGS.md" in text
        assert str(sub) in text
        assert str(repo) in text
        assert "git toplevel" in text

    def test_names_the_filesystem_boundary_outside_a_repo(self, tmp_path: Path):
        loose = tmp_path / "loose"
        loose.mkdir()
        assert "filesystem root" in find_workspace_root(loose).explain()


class TestArcadeShapeEndToEnd:
    """The multi-package repo the defect was found on."""

    def test_before_seeding_the_repo_root_belongs_to_no_workspace(self, arcade):
        root, _backend, _frontend = arcade
        result = find_workspace_root(root)
        assert not result.found
        assert result.git_toplevel == root

    async def test_before_seeding_append_at_the_root_refuses_and_writes_nothing(
        self, arcade, isolated_env
    ):
        """The defect: this used to land in ~/.wopr/LEARNINGS.md."""
        root, _backend, _frontend = arcade
        _ws, home = isolated_env

        result = await append_learnings(str(root), entry_markdown=_entry())

        assert result.startswith("Error")
        assert "no workspace root found" in result
        assert str(root) in result
        assert not (root / "LEARNINGS.md").exists()
        assert not (home / "LEARNINGS.md").exists()

    def test_seeding_the_root_establishes_the_corpus_and_the_marker(
        self, arcade, isolated_env
    ):
        root, _backend, _frontend = arcade
        _ws, home = isolated_env

        result = seed_learnings(str(root), ["fastapi", "angular"])

        assert result.startswith("Seeded ")
        assert "Workspace registered." in result
        assert (root / "LEARNINGS.md").is_file()
        # The seeded file is itself the marker that makes the root resolvable.
        assert find_workspace_root(root).root == root
        assert str(root) in (home / "workspaces.txt").read_text(encoding="utf-8")

    async def test_append_from_the_root_lands_in_the_root_corpus(
        self, arcade, isolated_env
    ):
        root, _backend, _frontend = arcade
        _ws, home = isolated_env
        seed_learnings(str(root), ["fastapi"])

        result = await append_learnings(str(root), entry_markdown=_entry(title="Root"))

        assert result == f"Appended entry to {root / 'LEARNINGS.md'}"
        assert "Root" in (root / "LEARNINGS.md").read_text(encoding="utf-8")
        assert not (home / "LEARNINGS.md").exists()

    async def test_append_from_a_subpackage_uses_that_subpackage(
        self, arcade, isolated_env
    ):
        """Nearest match wins: a subpackage with its own wopr.yml is its own root.

        The point of the assertion is not which of the two files wins,
        it is that the entry lands in a file the read path can reach --
        never in ``~/.wopr`` behind the caller's back.
        """
        root, backend, _frontend = arcade
        _ws, home = isolated_env
        seed_learnings(str(root), ["fastapi"])

        result = await append_learnings(
            str(backend), entry_markdown=_entry(title="Backend")
        )

        assert result == f"Appended entry to {backend / 'LEARNINGS.md'}"
        assert "Backend" in (backend / "LEARNINGS.md").read_text(encoding="utf-8")
        assert "Backend" not in (root / "LEARNINGS.md").read_text(encoding="utf-8")
        assert not (home / "LEARNINGS.md").exists()

    async def test_append_from_deep_inside_a_subpackage_resolves_up_to_it(
        self, arcade, isolated_env
    ):
        root, backend, _frontend = arcade
        seed_learnings(str(root), ["fastapi"])
        deep = backend / "src" / "arcade_api" / "routers"
        deep.mkdir(parents=True)

        result = await append_learnings(str(deep), entry_markdown=_entry(title="Deep"))

        assert result == f"Appended entry to {backend / 'LEARNINGS.md'}"

    async def test_the_root_corpus_is_reachable_by_search(self, arcade, isolated_env):
        """The orphan-file case: written by seed, read by nothing."""
        root, _backend, _frontend = arcade
        seed_learnings(str(root), ["fastapi"])
        await append_learnings(
            str(root), entry_markdown=_entry(title="Postgres 18 moved its volume")
        )

        result = await learnings_search(
            stack_tags=["fastapi"], target_workspace_path=str(root)
        )

        assert "Postgres 18 moved its volume" in result

    async def test_search_from_a_subpackage_reads_that_subpackage_only(
        self, arcade, isolated_env
    ):
        root, backend, _frontend = arcade
        seed_learnings(str(root), ["fastapi"])
        await append_learnings(str(root), entry_markdown=_entry(letter="a", title="Root only"))
        await append_learnings(
            str(backend), entry_markdown=_entry(letter="b", title="Backend only")
        )

        from_backend = await learnings_search(
            stack_tags=["fastapi"], target_workspace_path=str(backend)
        )
        from_root = await learnings_search(
            stack_tags=["fastapi"], target_workspace_path=str(root)
        )

        assert "Backend only" in from_backend
        assert "Root only" not in from_backend
        assert "Root only" in from_root
        assert "Backend only" not in from_root

    async def test_learnings_path_reports_the_resolved_root(self, arcade, isolated_env):
        root, backend, _frontend = arcade
        seed_learnings(str(root), ["fastapi"])
        deep = backend / "src"
        deep.mkdir(parents=True)

        result = await learnings_path(str(deep))

        assert f"workspace: {deep}" in result
        assert f"workspace_root: {backend}" in result
        assert "in_workspace: True" in result

    async def test_learnings_path_reports_an_unresolved_target_honestly(
        self, arcade, isolated_env
    ):
        root, _backend, _frontend = arcade

        result = await learnings_path(str(root))

        assert "workspace_root: (none found)" in result
        assert "in_workspace: False" in result
        assert "write_path: (unresolved)" in result
        assert f"searched: {root}" in result
        assert f"search_boundary: git toplevel {root}" in result

    async def test_curate_refuses_an_unresolved_root(self, arcade, isolated_env):
        root, _backend, _frontend = arcade
        result = await curate_learnings(str(root))
        assert result.startswith("Error")
        assert "no workspace root found" in result


class TestHonestStatusMessages:
    def test_seed_claims_registration_only_on_the_call_that_registers(
        self, tmp_path: Path, isolated_env
    ):
        workspace = _mkpackage(tmp_path, "pkg")

        first = seed_learnings(str(workspace), ["angular"])
        second = seed_learnings(str(workspace), ["angular"])

        assert "Workspace registered." in first
        assert "Workspace already registered." in second
        # The false claim the field notes caught: "registered" asserted on a
        # call that registered nothing.
        assert "already" in second

    def test_registration_of_a_directory_with_no_marker_is_reported_as_skipped(
        self, tmp_path: Path, isolated_env
    ):
        bare = tmp_path / "bare"
        bare.mkdir()

        result = _ensure_workspace_registered(bare)

        assert result == "not-a-workspace"
        note = _registration_note(result, bare)
        assert note.startswith("Registration skipped")
        assert str(bare) in note

    def test_registration_reports_failure_when_the_registry_cannot_be_written(
        self, tmp_path: Path, isolated_env
    ):
        workspace = _mkpackage(tmp_path, "pkg")
        _ws, home = isolated_env
        # A directory where the registry file belongs: every open("a")
        # raises IsADirectoryError, an OSError.
        (home / learnings.WORKSPACES_REGISTRY_FILENAME).mkdir()

        result = _ensure_workspace_registered(workspace)

        assert result == "failed"
        assert _registration_note(result, workspace).startswith("Registration failed")

    def test_seed_reports_the_registration_failure_rather_than_success(
        self, tmp_path: Path, isolated_env
    ):
        workspace = _mkpackage(tmp_path, "pkg")
        _ws, home = isolated_env
        (home / learnings.WORKSPACES_REGISTRY_FILENAME).mkdir()

        result = seed_learnings(str(workspace), ["angular"])

        assert result.startswith("Seeded ")
        assert "Registration failed" in result
        assert "Workspace registered." not in result


class TestGoldenFixtureResolutionIsUnchanged:
    """The single-package shape must resolve exactly as it always did.

    Both golden-req fixtures carry ``wopr.yml`` at their root, which is
    the case the old ``wopr.yml``-at-the-root rule handled. Resolution
    must terminate on the fixture directory itself without walking, so
    the new walk-up costs these projects nothing and changes nothing.
    """

    @pytest.mark.parametrize("name", ["golden-req", "golden-req-2"])
    def test_resolution_terminates_on_the_fixture_directory(self, name: str):
        fixture = REPO_ROOT / "evals" / name / "fixture"
        assert (fixture / "wopr.yml").is_file(), "fixture precondition"

        result = find_workspace_root(fixture)

        assert result.root == fixture
        assert result.searched == (fixture,)  # no walking at all

    @pytest.mark.parametrize("name", ["golden-req", "golden-req-2"])
    async def test_a_copy_of_the_fixture_writes_and_reads_its_own_corpus(
        self, name: str, tmp_path: Path, isolated_env
    ):
        """End to end on a copy, so the checked-in fixtures stay untouched."""
        fixture = REPO_ROOT / "evals" / name / "fixture"
        replica = tmp_path / name
        replica.mkdir()
        (replica / "wopr.yml").write_text(
            (fixture / "wopr.yml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        _ws, home = isolated_env

        appended = await append_learnings(
            str(replica), entry_markdown=_entry(title="Golden")
        )
        found = await learnings_search(
            stack_tags=["fastapi"], target_workspace_path=str(replica)
        )

        assert appended == f"Appended entry to {replica / 'LEARNINGS.md'}"
        assert "Golden" in found
        assert not (home / "LEARNINGS.md").exists()

    def test_a_single_package_workspace_resolves_identically_to_a_golden_fixture(
        self, tmp_path: Path
    ):
        fixture = REPO_ROOT / "evals" / "golden-req" / "fixture"
        plain = _mkpackage(tmp_path, "plain")

        assert _shape(find_workspace_root(fixture)) == _shape(find_workspace_root(plain))


