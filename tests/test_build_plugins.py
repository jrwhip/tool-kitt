"""Tests for ``wopr build-plugins``: the marketplace generator.

Four things have to hold, and each one has a class below:

1. **Safety.** The generator wipes its output directory. The marker
   file is the only thing standing between ``--out ~/Work`` and a very
   bad afternoon, so its absence must be fatal.
2. **Shape.** The manifests have to match the documented plugin and
   marketplace schemas, because a shape error surfaces to the user as
   a silently missing plugin rather than an error.
3. **No drift.** The emitted tree is the catalog, minus an explicit
   exclusion list and modulo exactly one declared transformation (the
   MCP tool-name rewrite). A test that only checked "some files were
   written" would not notice a converter quietly rewriting content or a
   pack silently dropping out.
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
    CLI_PROG,
    EXCLUDED_FILE_NAMES,
    MARKER_NAME,
    MARKETPLACE_NAME,
    MCP_SERVER_KEY,
    REWRITTEN_SUFFIXES,
    SERVER_DEPENDENCIES,
    SERVER_ENTRY_POINT,
    SOURCE_TOOL_PREFIX,
    BuildPluginsError,
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
    rewrite_tool_names,
    runtime_tool_prefix,
    server_plugin_name,
    to_semver,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = REPO_ROOT / "catalog"


def _expected_bytes(source: Path) -> bytes:
    """What ``source`` must look like once emitted.

    Everything is copied verbatim except markdown, which carries the
    declared MCP tool-name rewrite. Encoding the expectation once, here,
    keeps the drift tests honest without letting them ignore content.
    """
    if source.suffix.lower() not in REWRITTEN_SUFFIXES:
        return source.read_bytes()
    text = rewrite_tool_names(source.read_text(encoding="utf-8"))
    return text.encode("utf-8")


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
    """The emitted tree IS the catalog, minus a declared exclusion list
    and modulo the declared tool-name rewrite."""

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

    def test_every_catalog_file_is_emitted_with_only_the_declared_rewrite(
        self, out_dir: Path
    ):
        pairs = self._expected_pairs(out_dir)
        assert len(pairs) > 200, "catalog scan found suspiciously little"
        missing = [str(dest) for _src, dest in pairs if not dest.is_file()]
        assert not missing, f"not emitted: {missing[:5]}"
        differing = [
            str(dest)
            for src, dest in pairs
            if dest.read_bytes() != _expected_bytes(src)
        ]
        assert not differing, f"content drift: {differing[:5]}"

    def test_non_markdown_is_emitted_byte_identical(self, out_dir: Path):
        """The rewrite must not reach scripts, YAML or data fixtures."""
        pairs = [
            (src, dest)
            for src, dest in self._expected_pairs(out_dir)
            if src.suffix.lower() not in REWRITTEN_SUFFIXES
        ]
        assert pairs, "no non-markdown catalog files found; test is vacuous"
        differing = [
            str(dest)
            for src, dest in pairs
            if dest.read_bytes() != src.read_bytes()
        ]
        assert not differing, f"non-markdown drift: {differing[:5]}"

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


class TestToolNameRewrite:
    """The catalog spells tools ``mcp__wopr__x``; the runtime does not.

    A plugin-provided MCP server is namespaced
    ``mcp__plugin_<plugin>_<server-key>__<tool>``. An agent ``tools:``
    grant that does not match the runtime name grants nothing, silently:
    the tool is never offered and the agent reports success having
    written nothing. That is how the crew auditor's ``append_learnings``
    grant died, taking the CRAG write path with it. These tests pin the
    generator as the single place that knows the runtime name.
    """

    def test_prefix_is_derived_from_the_plugin_and_the_server_key(self):
        assert server_plugin_name() == "wopr-core"
        assert runtime_tool_prefix() == "mcp__plugin_wopr-core_wopr__"
        assert runtime_tool_prefix("wopr-elsewhere") == (
            "mcp__plugin_wopr-elsewhere_wopr__"
        )
        assert runtime_tool_prefix("p", "srv") == "mcp__plugin_p_srv__"

    def test_prefix_agrees_with_the_emitted_mcp_config(self, out_dir: Path):
        """The generator must not learn the server key in two places."""
        config = _read_json(out_dir / "wopr-core" / ".mcp.json")
        (server_key,) = config["mcpServers"].keys()
        assert server_key == MCP_SERVER_KEY
        assert runtime_tool_prefix() == f"mcp__plugin_wopr-core_{server_key}__"

    def test_rewrites_a_frontmatter_tools_list(self):
        source = (
            "---\nname: crew-auditor\ntools:\n  - Read\n"
            "  - mcp__wopr__append_learnings\n---\n"
        )
        assert rewrite_tool_names(source) == (
            "---\nname: crew-auditor\ntools:\n  - Read\n"
            "  - mcp__plugin_wopr-core_wopr__append_learnings\n---\n"
        )

    def test_rewrites_prose_including_backticked_and_bare_mentions(self):
        source = (
            "Call `mcp__wopr__detect_stack`, then mcp__wopr__write_wopr_yml.\n"
        )
        assert rewrite_tool_names(source) == (
            "Call `mcp__plugin_wopr-core_wopr__detect_stack`, then "
            "mcp__plugin_wopr-core_wopr__write_wopr_yml.\n"
        )

    def test_leaves_other_servers_alone(self):
        source = (
            '"matcher": "mcp__memory__.*"\n'
            "mcp__context7__resolve-library-id\n"
            "mcp__plugin_atlassian_atlassian__getJiraIssue\n"
            "mcp__ag-mcp__*\n"
        )
        assert rewrite_tool_names(source) == source

    def test_a_bare_prefix_mention_is_not_rewritten(self):
        """Prose about the naming scheme is not a tool reference."""
        source = "tools are named `mcp__wopr__` plus the tool name\n"
        assert rewrite_tool_names(source) == source

    def test_is_idempotent(self):
        once = rewrite_tool_names("`mcp__wopr__seed_learnings`")
        assert rewrite_tool_names(once) == once

    def test_no_source_form_survives_anywhere_in_the_emitted_tree(
        self, out_dir: Path
    ):
        """The end-to-end assertion: nothing ships the dead name.

        The bundled server SOURCE is exempt: ``build_plugins.py`` and
        ``converters.py`` discuss the source form in comments, and
        rewriting Python would be the generator editing itself.
        """
        server_src = out_dir / "wopr-core" / "server" / "src"
        offenders = [
            f"{path.relative_to(out_dir)}"
            for path in sorted(out_dir.rglob("*.md"))
            if server_src not in path.parents
            and SOURCE_TOOL_PREFIX in path.read_text(encoding="utf-8")
        ]
        assert not offenders, offenders

    def test_the_rewrite_actually_fired_on_the_real_catalog(self, out_dir: Path):
        """Guards the test above from passing because nothing matched."""
        prefix = runtime_tool_prefix()
        hits = [
            path.relative_to(out_dir)
            for path in sorted(out_dir.rglob("*.md"))
            if prefix in path.read_text(encoding="utf-8")
        ]
        assert len(hits) >= 5, hits

    def test_the_auditors_learnings_grant_is_live(self, out_dir: Path):
        """The specific grant whose silence killed the CRAG write path."""
        auditor = out_dir / "wopr-crew" / "agents" / "wopr-crew-auditor.md"
        text = auditor.read_text(encoding="utf-8")
        frontmatter = text.split("---")[1]
        assert (
            f"  - {runtime_tool_prefix()}append_learnings" in frontmatter
        ), frontmatter

    def test_non_core_plugins_get_the_core_plugins_prefix(self, out_dir: Path):
        """`wopr` is the marketplace's only server; every plugin calls it."""
        crew = out_dir / "wopr-crew"
        assert not (crew / ".mcp.json").exists()
        text = (crew / "agents" / "wopr-crew-auditor.md").read_text(
            encoding="utf-8"
        )
        assert "mcp__plugin_wopr-core_wopr__" in text
        assert "mcp__plugin_wopr-crew_wopr__" not in text


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
        # The embeddings deps ship deliberately (Phase 1): the local
        # semantic-search provider is the default and must work out of
        # the box.
        assert "fastembed" in text
        assert "numpy" in text
        # The dev extra is dev-time weight; a plugin install must not
        # resolve pytest or mypy. The bedrock extra is opt-in; boto3
        # must not ship either.
        assert "pytest" not in text
        assert "mypy" not in text
        assert "boto3" not in text

    def test_bundled_dependencies_match_the_source_project(self):
        """The bundle's deps are a hand-maintained copy; catch the drift.

        The bundle ships the base runtime dependencies PLUS the
        ``embeddings`` extra's pins (Phase 1 decision: the local
        semantic-search provider works out of the box), so the
        lockstep shape is base + embeddings, exactly and in order.
        """
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        base_block = re.search(r"^dependencies = \[(.*?)^\]", text, re.S | re.M)
        assert base_block, "could not find the dependencies block in pyproject.toml"
        embeddings_block = re.search(r"^embeddings = \[(.*?)^\]", text, re.S | re.M)
        assert embeddings_block, (
            "could not find the embeddings extra block in pyproject.toml"
        )
        declared = re.findall(r'"([^"]+)"', base_block.group(1)) + re.findall(
            r'"([^"]+)"', embeddings_block.group(1)
        )
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
                # Markdown here reaches a model through
                # ``get_pack_template``, so it carries the same rewrite
                # as the component tree.
                assert dest.read_bytes() == _expected_bytes(source), dest


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


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` keyed by POSIX relative path."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture(scope="module")
def hosted(tmp_path_factory: pytest.TempPathFactory) -> BuildResult:
    """One hosted build for the whole module, like ``built`` above."""
    root = tmp_path_factory.mktemp("hosted-repo")
    return build_plugins(root / "plugins", REPO_ROOT, marketplace_root=root)


class TestHostedLayout:
    """``marketplace_root`` hosts the manifest above the plugin tree.

    A marketplace served from git needs ``.claude-plugin/marketplace.json``
    at the repo root with sources that point down into the generated
    tree. The tree itself must not change shape, or the self-contained
    tests above would be testing something nobody installs.
    """

    def test_manifest_lands_under_the_root_not_inside_the_tree(
        self, hosted: BuildResult
    ):
        root = hosted.out_dir.parent
        assert hosted.manifest_path == root / ".claude-plugin" / "marketplace.json"
        assert hosted.manifest_path.is_file()
        assert not (hosted.out_dir / ".claude-plugin").exists()

    def test_sources_resolve_from_the_root_into_the_tree(self, hosted: BuildResult):
        assert hosted.manifest_path is not None
        root = hosted.manifest_path.parents[1]
        manifest = _read_json(hosted.manifest_path)
        assert manifest["name"] == MARKETPLACE_NAME
        for entry in manifest["plugins"]:
            assert entry["source"] == f"./plugins/{entry['name']}"
            assert (root / entry["source"] / ".claude-plugin" / "plugin.json").is_file()

    def test_the_tree_is_byte_identical_to_a_self_contained_build(
        self, hosted: BuildResult, built: BuildResult
    ):
        manifest_rel = ".claude-plugin/marketplace.json"
        self_contained = _tree_bytes(built.out_dir)
        self_contained.pop(manifest_rel)
        assert _tree_bytes(hosted.out_dir) == self_contained

    def test_only_the_manifest_is_written_outside_the_tree(self, hosted: BuildResult):
        root = hosted.out_dir.parent
        assert sorted(p.name for p in root.iterdir()) == [".claude-plugin", "plugins"]
        assert [p.name for p in (root / ".claude-plugin").iterdir()] == [
            "marketplace.json"
        ]

    def test_refuses_an_out_dir_outside_the_root(self, tmp_path: Path):
        with pytest.raises(BuildPluginsError, match="must sit inside"):
            build_plugins(
                tmp_path / "elsewhere", REPO_ROOT, marketplace_root=tmp_path / "root"
            )
        assert not (tmp_path / "elsewhere").exists()

    def test_a_root_equal_to_out_is_the_self_contained_layout(self, tmp_path: Path):
        out = tmp_path / "marketplace"
        result = build_plugins(out, REPO_ROOT, marketplace_root=out)
        assert result.manifest_path == out / ".claude-plugin" / "marketplace.json"
        manifest = _read_json(result.manifest_path)
        assert all(e["source"] == f"./{e['name']}" for e in manifest["plugins"])

    def test_report_names_the_manifest_only_when_it_is_outside_the_tree(
        self, hosted: BuildResult, built: BuildResult
    ):
        assert str(hosted.manifest_path) in format_build_report(hosted)
        assert "marketplace manifest:" not in format_build_report(built)


class TestCommittedTreeIsCurrent:
    """A committed ``plugins/`` tree must never lag the catalog.

    Hosting the marketplace from git means the generated tree is checked
    in. This test is the drift gate: it rebuilds into a scratch root and
    demands byte equality with what is committed. It skips, rather than
    passes, in a checkout that hosts nothing.
    """

    def test_committed_plugins_match_a_fresh_build(self, tmp_path: Path):
        committed = REPO_ROOT / "plugins"
        committed_manifest = REPO_ROOT / ".claude-plugin" / "marketplace.json"
        if not (committed / MARKER_NAME).is_file():
            pytest.skip("this checkout does not host a committed plugins/ tree")

        root = tmp_path / "repo"
        result = build_plugins(root / "plugins", REPO_ROOT, marketplace_root=root)

        fresh = _tree_bytes(result.out_dir)
        stale = _tree_bytes(committed)
        assert sorted(fresh) == sorted(stale), (
            "committed plugins/ has a different file set than a fresh build; "
            f"rerun `{CLI_PROG} build-plugins --out plugins --marketplace-root .`"
        )
        changed = [rel for rel in fresh if fresh[rel] != stale[rel]]
        assert not changed, f"committed plugins/ is stale: {changed[:10]}"
        assert result.manifest_path is not None
        assert result.manifest_path.read_bytes() == committed_manifest.read_bytes()
