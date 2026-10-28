"""Tests for the scout-contract validator.

Covers the gate behavior the orchestrator skill relies on:

* Valid contracts return ``ok: true`` with parsed frontmatter and no
  errors.
* Missing required keys, malformed YAML, missing frontmatter
  delimiters, empty critical fields, and non-absolute / non-existent
  paths each surface specific errors so the operator can fix exactly
  the gap.
* Warnings (empty class inventory for a non-class REQ, very short
  body) do not flip ``ok`` to False; that decision belongs to the
  orchestrator's gate, not this helper.
* Self-consistency: a contract that contradicts itself or the
  filesystem is caught rather than waved through. Path scope is an
  error; missing files, body/frontmatter basename drift, and
  out-of-scope inventory entries are warnings. The last group also
  has to stay quiet on a coherent contract, which is what
  ``TestNoNoiseOnConsistentContracts`` is for: a check that fires on
  clean input is a check operators learn to ignore.
"""

from __future__ import annotations

import json
from pathlib import Path

from kitt.tools import crew_contracts
from kitt.tools.crew_contracts import validate_scout_contract

# ``fake_mcp`` fixture lives in tests/conftest.py.


def _write_contract(
    contracts_dir: Path,
    req_id: str = "REQ-001",
    *,
    frontmatter_lines: list[str] | None = None,
    body: str = (
        "## Discovery notes\n\n"
        "The scout walked apps/billing/ and identified the invoice domain.\n"
        "Three entities are in scope: Invoice, LineItem, Customer.\n"
    ),
    include_frontmatter_delimiters: bool = True,
) -> Path:
    """Build a scout contract on disk and return its path.

    ``frontmatter_lines`` is the body of the frontmatter block (without
    the ``---`` delimiters). Defaults to a fully-populated contract.
    """
    if frontmatter_lines is None:
        frontmatter_lines = [
            f"req_id: {req_id}",
            "generated_at: 2026-05-18T14:00:00Z",
            "files_touched:",
            "  - apps/billing/src/main/java/com/example/Invoice.java",
            "  - apps/billing/src/main/java/com/example/InvoiceRepository.java",
            "class_inventory:",
            "  - name: Invoice",
            "    file: apps/billing/src/main/java/com/example/Invoice.java",
            "    signature: \"public class Invoice { ... }\"",
            "package_structure: |",
            "  com.example.billing",
            "    .Invoice",
            "    .InvoiceRepository",
        ]
    target_dir = contracts_dir / req_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "scout.md"
    parts: list[str] = []
    if include_frontmatter_delimiters:
        parts.append("---\n")
    parts.extend(line + "\n" for line in frontmatter_lines)
    if include_frontmatter_delimiters:
        parts.append("---\n")
    parts.append("\n")
    parts.append(body)
    path.write_text("".join(parts), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestValidContract:
    def test_fully_populated_contract_is_ok(self, tmp_path: Path) -> None:
        path = _write_contract(tmp_path / "crew-contracts")
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert result["errors"] == []
        assert result["frontmatter"]["req_id"] == "REQ-001"
        assert len(result["frontmatter"]["files_touched"]) == 2
        assert result["body_length"] > 0

    def test_returns_absolute_resolved_path(self, tmp_path: Path) -> None:
        """``path`` in the result is the resolved absolute path so the
        operator and orchestrator can copy-paste it from the report."""
        path = _write_contract(tmp_path / "crew-contracts")
        result = json.loads(validate_scout_contract(str(path)))
        assert Path(result["path"]) == path.resolve()


# ---------------------------------------------------------------------------
# Path / I/O failures
# ---------------------------------------------------------------------------


class TestPathFailures:
    def test_relative_path_rejected(self) -> None:
        result = json.loads(validate_scout_contract("relative/scout.md"))
        assert result["ok"] is False
        assert any("not absolute" in e for e in result["errors"])

    def test_nonexistent_path_rejected(self, tmp_path: Path) -> None:
        missing = tmp_path / "crew-contracts" / "REQ-099" / "scout.md"
        result = json.loads(validate_scout_contract(str(missing)))
        assert result["ok"] is False
        assert any("does not exist" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Frontmatter shape failures
# ---------------------------------------------------------------------------


class TestFrontmatterFailures:
    def test_missing_frontmatter_delimiters_rejected(self, tmp_path: Path) -> None:
        """A markdown file with no ``---`` block at top is rejected;
        the orchestrator must not silently treat a body-only contract
        as valid."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            include_frontmatter_delimiters=False,
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])

    def test_malformed_yaml_in_frontmatter(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "files_touched: [unterminated",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("yaml" in e.lower() for e in result["errors"])

    def test_frontmatter_must_be_mapping(self, tmp_path: Path) -> None:
        """A YAML scalar or list at top level is not acceptable."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=["- just-a-list"],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("mapping" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# Required-key failures
# ---------------------------------------------------------------------------


class TestRequiredKeys:
    def test_missing_req_id(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - x.java",
                "class_inventory: []",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("`req_id`" in e for e in result["errors"])

    def test_empty_req_id_rejected(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: \"\"",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - x.java",
                "class_inventory: []",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("`req_id`" in e and "non-empty" in e for e in result["errors"])

    def test_empty_files_touched_rejected(self, tmp_path: Path) -> None:
        """files_touched is the load-bearing field for the downstream
        agents; an empty list means scout under-populated and the
        coder/tester would have nothing to consult."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched: []",
                "class_inventory: []",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any(
            "`files_touched` is empty" in e for e in result["errors"]
        )

    def test_files_touched_must_be_list_of_strings(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - 42",
                "class_inventory: []",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any(
            "`files_touched`" in e and "non-empty strings" in e
            for e in result["errors"]
        )

    def test_class_inventory_entry_missing_subkeys(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - x.java",
                "class_inventory:",
                "  - name: Invoice",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any(
            "`class_inventory[0]`" in e and "file" in e and "signature" in e
            for e in result["errors"]
        )

    def test_empty_package_structure_rejected(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - x.java",
                "class_inventory: []",
                "package_structure: \"\"",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("`package_structure`" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Warnings (do not flip ok)
# ---------------------------------------------------------------------------


class TestAdvisoryWarnings:
    def test_empty_class_inventory_is_warning_not_error(
        self, tmp_path: Path
    ) -> None:
        """A REQ that is genuinely not class-shaped (a config edit, a
        documentation REQ) can legitimately have an empty class
        inventory. Surface as advisory; do not block."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-002",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - README.md",
                "class_inventory: []",
                "package_structure: docs only",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert any("class_inventory" in w for w in result["warnings"])

    def test_very_short_body_is_warning(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            body="ok\n",
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert any("body" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Self-consistency: path scope (errors)
# ---------------------------------------------------------------------------


def _frontmatter(
    *,
    files_touched: list[str],
    inventory: list[tuple[str, str]] | None = None,
    req_id: str = "REQ-001",
) -> list[str]:
    """Frontmatter lines with a chosen ``files_touched`` / inventory pair.

    The consistency checks are all about the relationship between those
    two lists and the body, so every test below varies exactly them and
    leaves the required-key shape alone.
    """
    lines = [
        f"req_id: {req_id}",
        "generated_at: 2026-05-18T14:00:00Z",
        "files_touched:",
    ]
    lines.extend(f"  - {path}" for path in files_touched)
    if inventory:
        lines.append("class_inventory:")
        for name, file in inventory:
            lines.extend([
                f"  - name: {name}",
                f"    file: {file}",
                f"    signature: \"class {name}: ...\"",
            ])
    else:
        lines.append("class_inventory: []")
    lines.append("package_structure: app/")
    return lines


class TestPathScope:
    """``files_touched`` is an edit allowlist, so scope is an error."""

    def test_absolute_entry_is_rejected(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(files_touched=["/etc/passwd"]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any(
            "/etc/passwd" in e and "absolute" in e for e in result["errors"]
        )

    def test_parent_traversal_is_rejected(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(files_touched=["../elsewhere/app.py"]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("`..`" in e for e in result["errors"])

    def test_symlink_that_escapes_the_workspace_is_rejected(
        self, tmp_path: Path
    ) -> None:
        """No ``..`` anywhere in the string, and still outside the tree."""
        workspace = tmp_path
        outside = tmp_path.parent / "outside-the-workspace"
        outside.mkdir(exist_ok=True)
        (outside / "app.py").write_text("x\n", encoding="utf-8")
        (workspace / "link").symlink_to(outside, target_is_directory=True)

        path = _write_contract(
            workspace / "crew-contracts",
            frontmatter_lines=_frontmatter(files_touched=["link/app.py"]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("outside the contract's workspace" in e for e in result["errors"])

    def test_ordinary_relative_entry_is_not_an_error(self, tmp_path: Path) -> None:
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "game.py").write_text("x\n", encoding="utf-8")
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(files_touched=["app/game.py"]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Self-consistency: on-disk existence (warning, never an error)
# ---------------------------------------------------------------------------


class TestMissingFilesAreAdvisory:
    def test_absent_files_produce_exactly_one_warning(self, tmp_path: Path) -> None:
        """One warning listing every absent path, not one warning each."""
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_text("x\n", encoding="utf-8")
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(
                files_touched=["app/main.py", "app/game.py", "tests/test_game.py"]
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        missing_warnings = [w for w in result["warnings"] if "assumed net-new" in w]
        assert len(missing_warnings) == 1
        assert "app/game.py" in missing_warnings[0]
        assert "tests/test_game.py" in missing_warnings[0]
        assert "app/main.py" not in missing_warnings[0]

    def test_planned_new_files_never_flip_ok(self, tmp_path: Path) -> None:
        """The scout enumerating files the coder will create is normal."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(files_touched=["app/game.py"]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert result["errors"] == []

    def test_files_that_exist_produce_no_warning(self, tmp_path: Path) -> None:
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_text("x\n", encoding="utf-8")
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(files_touched=["app/main.py"]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert not any("assumed net-new" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Self-consistency: body vs frontmatter basename drift (warning)
# ---------------------------------------------------------------------------


class TestBasenameDrift:
    def test_reproduces_the_observed_test_queue_defect(self, tmp_path: Path) -> None:
        """Defect (a) from live use, verbatim.

        Frontmatter said ``tests/api/test_queue.py``; the body told the
        tester ``tests/test_queue.py``. Both documents read fine alone.
        """
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(
                files_touched=["app/queue.py", "tests/api/test_queue.py"]
            ),
            body=(
                "## Discovery notes\n\n"
                "The queue endpoints live in `app/queue.py`. The tester adds "
                "cases to `tests/test_queue.py` covering enqueue and dequeue.\n"
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        drift = [w for w in result["warnings"] if "path drift" in w]
        assert len(drift) == 1
        assert "tests/api/test_queue.py" in drift[0]
        assert "tests/test_queue.py" in drift[0]
        assert result["ok"] is True  # advisory, the operator decides

    def test_reproduces_the_arcade_req_arc_1_prefix_drift(
        self, tmp_path: Path
    ) -> None:
        """Defect (b) from live use: the Arcade build's REQ-ARC-1 contract.

        Frontmatter declared ``backend/tests/services/test_auth.py``;
        body line 110 told the tester the unit tests live in
        ``tests/services/test_auth.py`` — same basename, missing the
        ``backend/`` prefix. Two agents following the two halves would
        write to two different trees. Regression pin per remediation
        plan 3.2.
        """
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(
                files_touched=[
                    "backend/app/services/auth.py",
                    "backend/tests/services/test_auth.py",
                ]
            ),
            body=(
                "## Discovery notes\n\n"
                "Unit tests of the service live in "
                "`tests/services/test_auth.py`; extend them for the "
                "join_player flow.\n"
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        drift = [w for w in result["warnings"] if "path drift" in w]
        assert len(drift) == 1
        assert "backend/tests/services/test_auth.py" in drift[0]
        assert "tests/services/test_auth.py" in drift[0]
        assert result["ok"] is True  # advisory, the operator decides

    def test_body_agreeing_with_frontmatter_does_not_warn(
        self, tmp_path: Path
    ) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(
                files_touched=["app/queue.py", "tests/api/test_queue.py"]
            ),
            body=(
                "## Discovery notes\n\n"
                "The queue endpoints live in `app/queue.py`. The tester adds "
                "cases to `tests/api/test_queue.py` and to `./app/queue.py`.\n"
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert not any("path drift" in w for w in result["warnings"])

    def test_prose_and_unrelated_paths_do_not_false_positive(
        self, tmp_path: Path
    ) -> None:
        """The matcher has to stay quiet on everything that is not a path."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(files_touched=["app/queue.py"]),
            body=(
                "## Discovery notes\n\n"
                "Run `pytest -q` against `app.main:app`. The `Invoice` class "
                "and its `createrEmail` field are out of scope. See "
                "`docs/adr/0004-queue.md` and `vendor/other/broker.py` for "
                "background; neither is edited by this REQ.\n"
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert not any("path drift" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Self-consistency: inventory scope (warning)
# ---------------------------------------------------------------------------


class TestInventoryScope:
    def test_inventory_file_outside_files_touched_warns(
        self, tmp_path: Path
    ) -> None:
        """Defect (b): the inventory describes a module nobody will build."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(
                files_touched=["app/main.py"],
                inventory=[("GameEngine", "app/engine.py")],
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        scope = [w for w in result["warnings"] if "class_inventory` entry" in w]
        assert len(scope) == 1
        assert "app/engine.py" in scope[0]
        assert "GameEngine" in scope[0]
        assert result["ok"] is True

    def test_inventory_file_inside_files_touched_does_not_warn(
        self, tmp_path: Path
    ) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=_frontmatter(
                files_touched=["app/main.py", "app/engine.py"],
                inventory=[("GameEngine", "./app/engine.py")],
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert not any("class_inventory` entry" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# No noise on a coherent contract
# ---------------------------------------------------------------------------


def _golden_shaped_workspace(tmp_path: Path) -> Path:
    """A tmp tree shaped like ``evals/golden-req-2/fixture``.

    Same layout the golden REQ runs against (``kitt.yml`` at the root,
    ``app/`` and ``tests/`` packages), built in tmp so the checked-in
    fixture is never read from or written to by this test.
    """
    root = tmp_path / "golden-shaped"
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "kitt.yml").write_text("project: golden\n", encoding="utf-8")
    for relative in (
        "app/__init__.py",
        "app/main.py",
        "app/game.py",
        "tests/__init__.py",
        "tests/test_health.py",
        "tests/test_game.py",
    ):
        (root / relative).write_text("x\n", encoding="utf-8")
    return root


class TestNoNoiseOnConsistentContracts:
    def test_coherent_golden_shaped_contract_warns_about_nothing(
        self, tmp_path: Path
    ) -> None:
        """A contract that agrees with itself and with disk is silent.

        The point of the assertion is the empty list, not a substring: a
        check that fires on clean input is a check the operator learns
        to scroll past, and then the checks that matter go unread too.
        """
        root = _golden_shaped_workspace(tmp_path)
        path = _write_contract(
            root / "crew-contracts",
            req_id="REQ-GOLD-2",
            frontmatter_lines=_frontmatter(
                files_touched=["app/main.py", "app/game.py", "tests/test_game.py"],
                inventory=[("Game", "app/game.py")],
                req_id="REQ-GOLD-2",
            ),
            body=(
                "## Discovery notes\n\n"
                "The FastAPI app is `app/main.py`; the health route already "
                "has coverage in `tests/test_health.py`. The engine lands in "
                "`app/game.py` with its suite at `tests/test_game.py`.\n"
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert result["warnings"] == []

    def test_planned_new_file_is_the_only_warning(self, tmp_path: Path) -> None:
        """Same contract, one file not written yet: one warning, still ok."""
        root = _golden_shaped_workspace(tmp_path)
        (root / "app" / "game.py").unlink()
        path = _write_contract(
            root / "crew-contracts",
            req_id="REQ-GOLD-2",
            frontmatter_lines=_frontmatter(
                files_touched=["app/main.py", "app/game.py", "tests/test_game.py"],
                inventory=[("Game", "app/game.py")],
                req_id="REQ-GOLD-2",
            ),
            body=(
                "## Discovery notes\n\n"
                "The FastAPI app is `app/main.py`; the engine lands in "
                "`app/game.py` with its suite at `tests/test_game.py`.\n"
            ),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert len(result["warnings"]) == 1
        assert "assumed net-new" in result["warnings"][0]
        assert "app/game.py" in result["warnings"][0]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_registers_expected_tools(self, fake_mcp) -> None:
        crew_contracts.register(fake_mcp)
        assert sorted(fake_mcp.registered) == ["validate_scout_contract"]


# ---------------------------------------------------------------------------
# Workspace mode: the ``also_writes`` exception
# ---------------------------------------------------------------------------


def _also_writes_frontmatter(entries_yaml: list[str]) -> list[str]:
    lines = _frontmatter(files_touched=["app/game.py"])
    lines.append("also_writes:")
    lines.extend(entries_yaml)
    return lines


class TestAlsoWrites:
    """``files_touched`` stays home-relative; other members go here."""

    def _home_and_sibling(self, tmp_path: Path, *, declare: bool = True) -> tuple[Path, Path]:
        """``frontend`` (home) and ``backend`` under a workspace root.

        ``declare=False`` leaves the root without a workspace ``kitt.yml``
        so the membership requirement can be exercised.
        """
        home = tmp_path / "frontend"
        (home / "app").mkdir(parents=True)
        (home / "app" / "game.py").write_text("x\n", encoding="utf-8")
        sibling = tmp_path / "backend"
        (sibling / "app").mkdir(parents=True)
        (sibling / "app" / "routes.py").write_text("x\n", encoding="utf-8")
        if declare:
            (tmp_path / "kitt.yml").write_text(
                "workspace:\n  slug: p\n  projects:\n"
                "    - path: frontend\n    - path: backend\n",
                encoding="utf-8",
            )
        return home, sibling

    def test_valid_entry_is_ok(self, tmp_path: Path) -> None:
        home, sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: backend",
                f"    root: {sibling}",
                "    files_touched:",
                "      - app/routes.py",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True, result["errors"]
        assert result["errors"] == []

    def test_root_that_is_not_a_declared_member_is_rejected(self, tmp_path: Path) -> None:
        home, _sibling = self._home_and_sibling(tmp_path)
        stranger = tmp_path / "stranger"
        (stranger / "app").mkdir(parents=True)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: stranger",
                f"    root: {stranger}",
                "    files_touched: [app/x.py]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("not a declared member" in e for e in result["errors"])

    def test_root_anywhere_on_disk_is_rejected(self, tmp_path: Path) -> None:
        """The hole the review found: ``/`` used to pass with zero errors."""
        home, _sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: x",
                "    root: /",
                "    files_touched: [etc/hostname]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("not a declared member" in e for e in result["errors"])

    def test_requires_an_enclosing_workspace_root(self, tmp_path: Path) -> None:
        home, sibling = self._home_and_sibling(tmp_path, declare=False)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: backend",
                f"    root: {sibling}",
                "    files_touched: [app/routes.py]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("workspace root" in e and "no ancestor" in e for e in result["errors"])

    def test_home_must_be_a_declared_member_too(self, tmp_path: Path) -> None:
        home, sibling = self._home_and_sibling(tmp_path)
        (tmp_path / "kitt.yml").write_text(
            "workspace:\n  slug: p\n  projects:\n    - path: backend\n", encoding="utf-8"
        )
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: backend",
                f"    root: {sibling}",
                "    files_touched: [app/routes.py]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("and it is not" in e for e in result["errors"])

    def test_missing_member_files_are_an_advisory_warning(self, tmp_path: Path) -> None:
        home, sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: backend",
                f"    root: {sibling}",
                "    files_touched: [app/routes.py, app/new_module.py]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True, result["errors"]
        assert any(
            "also_writes" in w and "app/new_module.py" in w for w in result["warnings"]
        )

    def test_member_scope_messages_name_the_member(self, tmp_path: Path) -> None:
        home, sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: backend",
                f"    root: {sibling}",
                "    files_touched: [/etc/passwd]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("member `backend`'s root" in e for e in result["errors"])

    def test_absent_key_changes_nothing(self, tmp_path: Path) -> None:
        home, _sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_frontmatter(files_touched=["app/game.py"]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True

    def test_entry_file_escaping_its_member_root_is_rejected(self, tmp_path: Path) -> None:
        home, sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: backend",
                f"    root: {sibling}",
                "    files_touched:",
                "      - ../frontend/app/game.py",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("(backend)" in e and "`..`" in e for e in result["errors"])

    def test_relative_root_is_rejected(self, tmp_path: Path) -> None:
        home, _sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: backend",
                "    root: ../backend",
                "    files_touched: [app/routes.py]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("not absolute" in e for e in result["errors"])

    def test_missing_root_directory_is_rejected(self, tmp_path: Path) -> None:
        home, _sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: gone",
                f"    root: {tmp_path / 'gone'}",
                "    files_touched: [a.py]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("not an existing directory" in e for e in result["errors"])

    def test_home_member_listed_under_also_writes_is_rejected(self, tmp_path: Path) -> None:
        home, _sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: frontend",
                f"    root: {home}",
                "    files_touched: [app/other.py]",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("home member" in e for e in result["errors"])

    def test_shape_problems_are_named(self, tmp_path: Path) -> None:
        home, sibling = self._home_and_sibling(tmp_path)
        path = _write_contract(
            home / "crew-contracts",
            frontmatter_lines=_also_writes_frontmatter([
                "  - member: backend",
                f"    root: {sibling}",
                "    files_touched: []",
                "  - just-a-string",
            ]),
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("non-empty list" in e for e in result["errors"])
        assert any("`also_writes[1]`" in e and "mapping" in e for e in result["errors"])

    def test_not_a_list_is_rejected(self, tmp_path: Path) -> None:
        home, _sibling = self._home_and_sibling(tmp_path)
        lines = _frontmatter(files_touched=["app/game.py"])
        lines.append("also_writes: backend")
        path = _write_contract(home / "crew-contracts", frontmatter_lines=lines)
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("must be a list" in e for e in result["errors"])
