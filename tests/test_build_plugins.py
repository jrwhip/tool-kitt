"""Tests for ``wopr build-plugins``: the marketplace generator.

Four things have to hold, and each one has a class below:

1. **Safety.** The generator wipes its output directory. The marker
   file is the only thing standing between ``--out ~/Work`` and a very
   bad afternoon, so its absence must be fatal.
2. **Shape.** The manifests have to match the documented plugin and
   marketplace schemas, because a shape error surfaces to the user as
   a silently missing plugin rather than an error.
3. **No drift.** The emitted tree is the catalog, byte for byte, minus
   an explicit exclusion list. A test that only checked "some files
   were written" would not notice a converter quietly rewriting
   content or a pack silently dropping out.
4. **A working server bundle.** The bundle is the runtime projection
   of the package: dependencies pinned to what the server imports,
   no dev-time files, and a shim that actually runs.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from wopr import __version__
from wopr.build_plugins import (
    BUNDLED_RESOURCES,
    EXCLUDED_FILE_NAMES,
    MARKER_NAME,
    MARKETPLACE_NAME,
    SERVER_DEPENDENCIES,
    SERVER_ENTRY_POINT,
    BuildResult,
    PluginCollisionError,
    PluginPlan,
    UnsafeOutputDirError,
    build_plugins,
    check_collisions,
    check_skill_descriptions,
    find_repo_root,
    format_build_report,
    plan_plugins,
    plugin_name_for_pack,
    to_semver,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = REPO_ROOT / "catalog"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> BuildResult:
    """Generate the real marketplace once for the whole module.

    Module-scoped on purpose: the tree is ~300 files and every shape
    assertion below reads the same tree. Nothing here mutates it.
    """
    out = tmp_path_factory.mktemp("marketplace") / "wopr-plugins"
    return build_plugins(out, REPO_ROOT)


@pytest.fixture(scope="module")
def out_dir(built: BuildResult) -> Path:
    return built.out_dir


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _plugin_dirs(out_dir: Path) -> list[Path]:
    """Plugin directories only: skip the marketplace's own .claude-plugin."""
    return sorted(
        p for p in out_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
    )


class TestOutputDirSafety:
    """The wipe-and-rewrite contract must never touch a foreign directory."""

    def test_creates_a_missing_directory(self, tmp_path: Path):
        out = tmp_path / "nested" / "wopr-plugins"
        build_plugins(out, REPO_ROOT)
        assert (out / MARKER_NAME).is_file()

    def test_accepts_an_existing_empty_directory(self, tmp_path: Path):
        out = tmp_path / "empty"
        out.mkdir()
        build_plugins(out, REPO_ROOT)
        assert (out / MARKER_NAME).is_file()

    def test_refuses_a_non_empty_directory_without_the_marker(self, tmp_path: Path):
        out = tmp_path / "someones-repo"
        out.mkdir()
        precious = out / "precious.txt"
        precious.write_text("do not delete", encoding="utf-8")

        with pytest.raises(UnsafeOutputDirError) as excinfo:
            build_plugins(out, REPO_ROOT)

        assert MARKER_NAME in str(excinfo.value)
        assert str(out) in str(excinfo.value)
        assert precious.read_text(encoding="utf-8") == "do not delete"

    def test_refuses_when_the_path_is_a_file(self, tmp_path: Path):
        out = tmp_path / "a-file"
        out.write_text("", encoding="utf-8")
        with pytest.raises(UnsafeOutputDirError):
            build_plugins(out, REPO_ROOT)

    def test_rewrites_a_marked_directory_and_drops_stale_files(self, tmp_path: Path):
        out = tmp_path / "wopr-plugins"
        build_plugins(out, REPO_ROOT)
        stale_file = out / "wopr-core" / "commands" / "gone-from-catalog.md"
        stale_file.write_text("stale", encoding="utf-8")
        stale_dir = out / "wopr-obsolete"
        stale_dir.mkdir()

        build_plugins(out, REPO_ROOT)

        assert not stale_file.exists()
        assert not stale_dir.exists()
        assert (out / MARKER_NAME).is_file()

    def test_regeneration_is_byte_identical(self, tmp_path: Path):
        """Determinism is what makes the drift test above meaningful."""
        first = tmp_path / "first"
        second = tmp_path / "second"
        build_plugins(first, REPO_ROOT)
        build_plugins(second, REPO_ROOT)

        first_files = {
            p.relative_to(first): p.read_bytes()
            for p in sorted(first.rglob("*"))
            if p.is_file()
        }
        second_files = {
            p.relative_to(second): p.read_bytes()
            for p in sorted(second.rglob("*"))
            if p.is_file()
        }
        assert first_files.keys() == second_files.keys()
        assert first_files == second_files


class TestVersionMapping:
    """``plugin.json`` documents semver; the package uses PEP 440."""

    @pytest.mark.parametrize(
        ("pep440", "semver"),
        [
            ("1.0.0.dev0", "1.0.0-dev.0"),
            ("1.0.0.dev12", "1.0.0-dev.12"),
            ("2.3.4", "2.3.4"),
            ("1.2.0rc1", "1.2.0-rc.1"),
            ("1.2.0a3", "1.2.0-alpha.3"),
            ("1.2.0b2", "1.2.0-beta.2"),
            ("weird-thing", "weird-thing"),
        ],
    )
    def test_maps_pep440_onto_semver(self, pep440: str, semver: str):
        assert to_semver(pep440) == semver

    def test_the_emitted_version_tracks_the_package_version(self, built: BuildResult):
        assert built.version == to_semver(__version__)


class TestPluginNaming:
    def test_core_pack_becomes_wopr_core(self):
        assert plugin_name_for_pack("_core") == "wopr-core"

    def test_meta_authoring_pack_becomes_wopr_meta(self):
        assert plugin_name_for_pack("meta-authoring") == "wopr-meta"

    def test_other_packs_take_the_default_rule(self):
        assert plugin_name_for_pack("angular") == "wopr-angular"
        assert plugin_name_for_pack("crew") == "wopr-crew"


class TestMarketplaceManifest:
    def test_required_fields_are_present(self, out_dir: Path):
        manifest = _read_json(out_dir / ".claude-plugin" / "marketplace.json")
        assert manifest["name"] == MARKETPLACE_NAME
        assert manifest["owner"]["name"] == "Jerry"
        assert isinstance(manifest["plugins"], list)
        assert manifest["plugins"]

    def test_every_entry_has_a_name_and_a_resolvable_relative_source(
        self, out_dir: Path
    ):
        manifest = _read_json(out_dir / ".claude-plugin" / "marketplace.json")
        for entry in manifest["plugins"]:
            assert entry["name"], entry
            # Relative sources must start with ./ and resolve from the
            # marketplace root, NOT from .claude-plugin/.
            assert entry["source"].startswith("./"), entry
            assert (out_dir / entry["source"][2:]).is_dir(), entry
            assert entry["description"].strip(), entry
            assert entry["version"] == to_semver(__version__), entry

    def test_lists_every_emitted_plugin_and_nothing_else(
        self, out_dir: Path, built: BuildResult
    ):
        manifest = _read_json(out_dir / ".claude-plugin" / "marketplace.json")
        listed = [entry["name"] for entry in manifest["plugins"]]
        on_disk = [p.name for p in _plugin_dirs(out_dir)]
        assert sorted(listed) == on_disk
        assert listed == [plan.name for plan in built.plugins]

    def test_the_expected_six_plugins_are_emitted(self, built: BuildResult):
        assert [plan.name for plan in built.plugins] == [
            "wopr-core",
            "wopr-angular",
            "wopr-auditors",
            "wopr-crew",
            "wopr-meta",
            "wopr-python",
        ]


class TestPluginManifests:
    def test_each_plugin_has_a_manifest_matching_its_directory(self, out_dir: Path):
        for plugin_dir in _plugin_dirs(out_dir):
            manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
            assert manifest_path.is_file(), plugin_dir
            manifest = _read_json(manifest_path)
            assert manifest["name"] == plugin_dir.name
            assert manifest["description"].strip()
            assert manifest["version"] == to_semver(__version__)
            assert manifest["author"]["name"] == "Jerry"
            assert manifest["license"] == "MIT"

    def test_components_sit_at_the_plugin_root_not_under_claude_plugin(
        self, out_dir: Path
    ):
        """Claude Code only scans components at the plugin root."""
        for plugin_dir in _plugin_dirs(out_dir):
            manifest_dir = plugin_dir / ".claude-plugin"
            assert sorted(p.name for p in manifest_dir.iterdir()) == ["plugin.json"]

    def test_only_wopr_core_declares_an_mcp_server(self, out_dir: Path):
        with_mcp = [
            p.name for p in _plugin_dirs(out_dir) if (p / ".mcp.json").is_file()
        ]
        assert with_mcp == ["wopr-core"]

    def test_mcp_config_launches_the_shim_with_the_plugin_root_in_env(
        self, out_dir: Path
    ):
        config = _read_json(out_dir / "wopr-core" / ".mcp.json")
        server = config["mcpServers"]["wopr"]
        assert server["command"] == (
            "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap-serve.sh"
        )
        assert server["env"] == {"WOPR_PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}"}
        assert (out_dir / "wopr-core" / "scripts" / "bootstrap-serve.sh").is_file()


class TestCatalogDrift:
    """The emitted tree IS the catalog, minus a declared exclusion list."""

    def _expected_pairs(self, out_dir: Path) -> list[tuple[Path, Path]]:
        pairs: list[tuple[Path, Path]] = []
        for pack_dir in sorted(CATALOG_ROOT.iterdir()):
            if not pack_dir.is_dir():
                continue
            plugin_dir = out_dir / plugin_name_for_pack(pack_dir.name)
            if not plugin_dir.is_dir():
                continue
            for dirname in ("commands", "agents", "skills", "hooks", "scripts",
                            "templates", "data"):
                source_dir = pack_dir / dirname
                if not source_dir.is_dir():
                    continue
                for source in sorted(source_dir.rglob("*")):
                    rel = source.relative_to(pack_dir)
                    if not source.is_file():
                        continue
                    if source.name in EXCLUDED_FILE_NAMES:
                        continue
                    if any(part.startswith(".") for part in rel.parts):
                        continue
                    if "__pycache__" in rel.parts:
                        continue
                    pairs.append((source, plugin_dir / rel))
        return pairs

    def test_every_catalog_file_is_emitted_byte_identical(self, out_dir: Path):
        pairs = self._expected_pairs(out_dir)
        assert len(pairs) > 200, "catalog scan found suspiciously little"
        missing = [str(dest) for _src, dest in pairs if not dest.is_file()]
        assert not missing, f"not emitted: {missing[:5]}"
        differing = [
            str(dest)
            for src, dest in pairs
            if dest.read_bytes() != src.read_bytes()
        ]
        assert not differing, f"content drift: {differing[:5]}"

    def test_no_emitted_component_file_is_unaccounted_for(self, out_dir: Path):
        """Nothing appears in a plugin that did not come from the catalog."""
        expected = {dest for _src, dest in self._expected_pairs(out_dir)}
        generated = {
            out_dir / "README.md",
            out_dir / MARKER_NAME,
            out_dir / ".claude-plugin" / "marketplace.json",
            out_dir / "wopr-core" / ".mcp.json",
        }
        for plugin_dir in _plugin_dirs(out_dir):
            generated.add(plugin_dir / ".claude-plugin" / "plugin.json")
        server_dir = out_dir / "wopr-core" / "server"

        unaccounted = [
            str(path)
            for path in out_dir.rglob("*")
            if path.is_file()
            and path not in expected
            and path not in generated
            and server_dir not in path.parents
            and path != out_dir / "wopr-core" / "scripts" / "bootstrap-serve.sh"
        ]
        assert not unaccounted, unaccounted[:5]

    def test_routing_eval_fixtures_are_never_shipped(self, out_dir: Path):
        """Dev-time fixtures for the slimming gate; useless to an install."""
        assert list(CATALOG_ROOT.rglob("routing-eval.jsonl")), (
            "catalog has no routing fixtures; this test would be vacuous"
        )
        assert not list(out_dir.rglob("routing-eval.jsonl"))

    def test_pack_readmes_are_not_shipped(self, out_dir: Path):
        """Pack-root READMEs document the retired `wopr add` install path."""
        assert (CATALOG_ROOT / "crew" / "README.md").is_file()
        assert not (out_dir / "wopr-crew" / "README.md").exists()

    def test_core_context_docs_are_not_shipped(self, out_dir: Path):
        """`get_shared_context` retired in P1; nothing reads these now."""
        assert (CATALOG_ROOT / "_core" / "context").is_dir()
        assert not (out_dir / "wopr-core" / "context").exists()

    def test_skills_keep_their_kebab_case_directory_names(self, out_dir: Path):
        names = sorted(p.name for p in (out_dir / "wopr-core" / "skills").iterdir())
        assert "wopr-create-agent-skills" in names
        assert all(
            re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) for name in names
        ), names

    def test_every_emitted_skill_dir_holds_a_skill_md(self, out_dir: Path):
        for skills_dir in out_dir.glob("*/skills"):
            for skill_dir in skills_dir.iterdir():
                assert (skill_dir / "SKILL.md").is_file(), skill_dir


class TestCollisionDetection:
    def _plan(self, name: str, **kwargs: list[str]) -> PluginPlan:
        return PluginPlan(
            pack=name,
            name=name,
            description="d",
            keywords=[],
            commands=kwargs.get("commands", []),
            agents=kwargs.get("agents", []),
            skills=kwargs.get("skills", []),
        )

    def test_the_real_catalog_has_no_collisions(self):
        plans = plan_plugins(CATALOG_ROOT, REPO_ROOT / "catalog.yaml")
        check_collisions(plans)
        check_skill_descriptions(CATALOG_ROOT, plans)

    @pytest.mark.parametrize("kind", ["commands", "agents", "skills"])
    def test_a_shared_component_name_fails_generation(self, kind: str):
        plans = [
            self._plan("wopr-a", **{kind: ["wopr-thing"]}),
            self._plan("wopr-b", **{kind: ["wopr-thing"]}),
        ]
        with pytest.raises(PluginCollisionError) as excinfo:
            check_collisions(plans)
        message = str(excinfo.value)
        assert "wopr-thing" in message
        assert "wopr-a" in message and "wopr-b" in message
        assert kind[:-1] in message

    def test_distinct_names_pass(self):
        check_collisions(
            [
                self._plan("wopr-a", commands=["one"], skills=["s1"]),
                self._plan("wopr-b", commands=["two"], skills=["s2"]),
            ]
        )

    def test_duplicate_skill_descriptions_fail_generation(self, tmp_path: Path):
        catalog = tmp_path / "catalog"
        for pack, skill in (("a", "skill-one"), ("b", "skill-two")):
            skill_dir = catalog / pack / "skills" / skill
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {skill}\ndescription: Do the exact same thing\n---\n",
                encoding="utf-8",
            )
        plans = [
            self._plan("wopr-a", skills=["skill-one"]),
            self._plan("wopr-b", skills=["skill-two"]),
        ]
        with pytest.raises(PluginCollisionError) as excinfo:
            check_skill_descriptions(catalog, plans)
        assert "skill-one" in str(excinfo.value)


class TestPackSelection:
    def test_a_pack_with_no_components_is_skipped(self, tmp_path: Path):
        catalog = tmp_path / "catalog"
        (catalog / "empty-pack" / "templates").mkdir(parents=True)
        (catalog / "empty-pack" / "templates" / "t.md").write_text("x", "utf-8")
        real = catalog / "real-pack" / "commands"
        real.mkdir(parents=True)
        (real / "cmd.md").write_text("x", encoding="utf-8")

        plans = plan_plugins(catalog, tmp_path / "catalog.yaml")

        assert [plan.name for plan in plans] == ["wopr-real-pack"]


class TestServerBundle:
    def test_package_source_is_present(self, out_dir: Path):
        package = out_dir / "wopr-core" / "server" / "src" / "wopr"
        assert (package / "server.py").is_file()
        assert (package / "cli.py").is_file()
        assert (package / "tools" / "learnings.py").is_file()

    def test_no_dev_time_files_ride_along(self, out_dir: Path):
        server_dir = out_dir / "wopr-core" / "server"
        offenders = [
            str(path)
            for path in server_dir.rglob("*")
            if path.is_file()
            and (
                path.name.startswith("test_")
                or path.suffix in {".pyc", ".pyo"}
                or path.name == "routing-eval.jsonl"
                or "__pycache__" in path.parts
                or "evals" in path.parts
                or "tests" in path.parts
            )
        ]
        assert not offenders, offenders[:5]

    def test_pyproject_declares_runtime_deps_and_the_serve_entry_point(
        self, out_dir: Path
    ):
        text = (out_dir / "wopr-core" / "server" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        for dep in SERVER_DEPENDENCIES:
            assert f'"{dep}"' in text
        assert f'{SERVER_ENTRY_POINT} = "wopr.cli:serve"' in text
        assert to_semver(__version__) in text
        # The dev and embeddings extras are dev-time weight; a plugin
        # install must not resolve pytest or onnxruntime.
        assert "pytest" not in text
        assert "fastembed" not in text
        assert "mypy" not in text

    def test_bundled_dependencies_match_the_source_project(self):
        """The bundle's deps are a hand-maintained copy; catch the drift."""
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        block = re.search(r"^dependencies = \[(.*?)^\]", text, re.S | re.M)
        assert block, "could not find the dependencies block in pyproject.toml"
        declared = re.findall(r'"([^"]+)"', block.group(1))
        assert list(SERVER_DEPENDENCIES) == declared

    def test_runtime_resources_are_bundled(self, out_dir: Path):
        resources = out_dir / "wopr-core" / "server" / "resources"
        assert (resources / "catalog.yaml").is_file()
        for parts in BUNDLED_RESOURCES:
            assert resources.joinpath(*parts).is_dir()
        assert (
            resources / "crew" / "templates" / "by-stack" / "fastapi" / "coder-spec.md"
        ).is_file()
        assert (
            resources / "crew" / "data" / "learnings-seed" / "fastapi.md"
        ).is_file()

    def test_bundled_resources_match_the_catalog(self, out_dir: Path):
        resources = out_dir / "wopr-core" / "server" / "resources"
        for parts in BUNDLED_RESOURCES:
            source_dir = CATALOG_ROOT.joinpath(*parts)
            for source in sorted(source_dir.rglob("*")):
                if not source.is_file():
                    continue
                dest = resources.joinpath(*parts, *source.relative_to(source_dir).parts)
                assert dest.is_file(), dest
                assert dest.read_bytes() == source.read_bytes(), dest


@pytest.fixture(scope="module")
def shim(out_dir: Path) -> Path:
    return out_dir / "wopr-core" / "scripts" / "bootstrap-serve.sh"


class TestBootstrapShim:
    def test_is_executable(self, shim: Path):
        assert shim.stat().st_mode & 0o111, "shim must be executable"

    def test_is_valid_bash(self, shim: Path):
        result = subprocess.run(
            ["bash", "-n", str(shim)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr

    def test_execs_uv_against_the_bundled_server(self, shim: Path):
        text = shim.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash\n")
        assert f'exec uv run --project "$plugin_root/server" {SERVER_ENTRY_POINT}' in text

    def test_prints_per_os_install_lines_when_uv_is_missing(self, shim: Path):
        text = shim.read_text(encoding="utf-8")
        assert "astral.sh/uv/install.ps1" in text
        assert "winget install astral-sh.uv" in text
        assert "brew install uv" in text
        assert "astral.sh/uv/install.sh" in text
        assert "exit 1" in text

    def test_missing_uv_exits_nonzero_with_guidance(self, shim: Path, tmp_path: Path):
        """Run the real shim with a PATH that has bash but no uv."""
        result = subprocess.run(
            [str(shim)],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        )
        assert result.returncode == 1
        assert "uv was not found" in result.stderr
        assert "brew install uv" in result.stderr


class TestMarkerFile:
    def test_marker_records_the_generator_and_version(self, out_dir: Path):
        marker = _read_json(out_dir / MARKER_NAME)
        assert marker["generator"] == "wopr build-plugins"
        assert marker["generator_version"] == to_semver(__version__)
        assert marker["marketplace"] == MARKETPLACE_NAME

    def test_marker_carries_no_timestamp(self, out_dir: Path):
        """A timestamp would make every regeneration a diff."""
        assert "date" not in (out_dir / MARKER_NAME).read_text(encoding="utf-8")


class TestReporting:
    def test_report_names_every_plugin_and_the_server(self, built: BuildResult):
        report = format_build_report(built)
        for plan in built.plugins:
            assert plan.name in report
        assert "bundled MCP server" in report
        assert str(built.file_count) in report

    def test_singular_counts_read_correctly(self, built: BuildResult):
        assert "1 skills" not in format_build_report(built)


class TestRepoRootDiscovery:
    def test_finds_the_repo_root_from_the_installed_module(self):
        assert find_repo_root() == REPO_ROOT
