"""Tests for the MCP server application factory."""

import json

import pytest

from kitt.config import ServerConfig
from kitt.context import ServerContext
from kitt.server import create_app


@pytest.fixture(autouse=True)
def _reset_server_context():
    """``create_app`` calls ``ServerContext.init()`` internally, clobbering
    the process-wide singleton. Reset on both entry and exit so this module
    doesn't leave the singleton pointed at a deleted tmp_path workspace for
    whatever test runs next, matching the pattern conftest.py's
    ``workspace``/``isolated_env`` fixtures already use elsewhere."""
    ServerContext.reset()
    yield
    ServerContext.reset()


# Every tool the server registers, pinned by name. The prior toolset
# registered 68 and gated a block of them on an ``extras`` pack lock;
# this list IS the slimming decision, so a tool appearing or vanishing
# should be a deliberate diff here rather than a silent change in
# ``create_app``.
EXPECTED_TOOLS = [
    "append_learnings",
    "check_mcp_servers_for_malware",
    "check_routing_evals",
    "create_handoff",
    "curate_learnings",
    "detect_stack",
    "get_handoff",
    "get_help",
    "get_pack_template",
    "get_workspace_info",
    "learnings_path",
    "learnings_search",
    "list_pack_templates",
    "pin_skill",
    "propose_kitt_yml",
    "resolve_crew_models",
    "scan_skill_directory",
    "seed_learnings",
    "skill_usage_report",
    "validate_scout_contract",
    "write_handoff_contract_stub",
    "write_kitt_yml",
    "write_spec_stubs",
    "write_tracking_doc_stub",
]


class TestCreateApp:
    def test_registers_exactly_the_expected_tool_set(self, tmp_path):
        config = ServerConfig(cli_type="claude")
        app = create_app(config=config, workspace=str(tmp_path))
        registered = sorted(t.name for t in app._tool_manager.list_tools())
        assert registered == EXPECTED_TOOLS

    def test_returns_fastmcp_instance(self, tmp_path):
        config = ServerConfig(cli_type="claude")
        app = create_app(config=config, workspace=str(tmp_path))
        assert app.name == "kitt"

    def test_accepts_custom_config(self, tmp_path):
        config = ServerConfig(cli_type="gemini", toggl_api_key="test-key")
        app = create_app(config=config, workspace=str(tmp_path))
        assert app is not None
        assert ServerContext.get().cli_type == "gemini"

    def test_multiple_instances(self, tmp_path):
        """Verify factory creates independent instances."""
        config = ServerConfig(cli_type="claude")
        app1 = create_app(config=config, workspace=str(tmp_path))
        app2 = create_app(config=config, workspace=str(tmp_path))
        assert app1 is not app2

    def test_every_ctx_parameter_receives_context_injection(self, tmp_path):
        """Every registered tool with a ``ctx`` param must be injectable.

        The ``ToolContext`` alias in ``context.py`` must resolve, at
        runtime, to something FastMCP's ``find_context_parameter()``
        recognizes — otherwise detection returns None, ctx silently
        arrives as None in every tool, and workspace resolution degrades
        with no error anywhere. This pins the wiring end-to-end against
        both alias changes and SDK detection changes.
        """
        import inspect

        config = ServerConfig(cli_type="claude")
        app = create_app(config=config, workspace=str(tmp_path))
        tools = app._tool_manager.list_tools()
        assert tools, "no tools registered"
        ctx_tools = [
            t for t in tools if "ctx" in inspect.signature(t.fn).parameters
        ]
        assert ctx_tools, "no ctx-taking tools found; detection is broken"
        not_injected = [t.name for t in ctx_tools if t.context_kwarg != "ctx"]
        assert not_injected == []


class TestGetWorkspaceInfo:
    """The reported surface must describe tools and CLIs that exist.

    ``get_workspace_info`` used to count ``~/.gemini/{skills,commands}``
    and ``~/.copilot/{skills,agents}`` and to report on
    ``time-tracking.json`` / ``notes.json``. Those counters could only
    ever return zero here, and a zero next to a real number reads as
    "installed but empty" rather than "not a thing". Both the CLI list
    and the file list are pinned so re-adding one is a deliberate diff.
    """

    @staticmethod
    async def _info(tmp_path):
        config = ServerConfig(cli_type="claude")
        app = create_app(config=config, workspace=str(tmp_path))
        tool = next(
            t for t in app._tool_manager.list_tools()
            if t.name == "get_workspace_info"
        )
        return json.loads(await tool.fn(str(tmp_path)))

    async def test_reports_claude_as_the_only_global_target(self, tmp_path):
        payload = await self._info(tmp_path)
        assert list(payload["resources"]["global"]) == ["claude"]
        assert sorted(payload["resources"]["global"]["claude"]) == [
            "agents",
            "commands",
            "skills",
        ]

    async def test_reports_only_files_a_surviving_tool_touches(self, tmp_path):
        payload = await self._info(tmp_path)
        assert sorted(payload["files"]) == [
            "agents_md",
            "claude_md",
            "handoff",
            "kitt_yml",
            "learnings",
            "todos",
        ]

    async def test_still_reports_workspace_and_local_counters(self, tmp_path):
        (tmp_path / "LEARNINGS.md").write_text("x", encoding="utf-8")
        payload = await self._info(tmp_path)
        assert payload["workspace"] == str(tmp_path)
        assert payload["workspace_source"] == "explicit"
        assert payload["cli_type"] == "claude"
        assert payload["files"]["learnings"] is True
        assert payload["files"]["todos"] is False
        assert sorted(payload["resources"]["local"]) == [
            "agents",
            "commands",
            "context_docs",
            "skills",
        ]


class TestGetWorkspaceInfoKind:
    """``kitt_yml_kind`` and the member list a workspace root declares."""

    @staticmethod
    async def _info(root):
        config = ServerConfig(cli_type="claude")
        app = create_app(config=config, workspace=str(root))
        tool = next(
            t for t in app._tool_manager.list_tools()
            if t.name == "get_workspace_info"
        )
        return json.loads(await tool.fn(str(root)))

    async def test_reports_workspace_kind_and_members(self, tmp_path):
        (tmp_path / "kitt.yml").write_text(
            "workspace:\n  slug: myproduct\n  name: My Product\n  projects:\n"
            "    - path: backend\n      role: backend\n"
            "    - path: frontend\n      role: frontend\n",
            encoding="utf-8",
        )
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "kitt.yml").write_text(
            "project:\n  slug: api\n", encoding="utf-8"
        )
        payload = await self._info(tmp_path)
        assert payload["kitt_yml_kind"] == "workspace"
        assert payload["files"]["kitt_yml"] is True
        assert payload["workspace_config"]["slug"] == "myproduct"
        assert payload["workspace_config"]["name"] == "My Product"
        members = {m["path"]: m for m in payload["workspace_config"]["members"]}
        assert list(members) == ["backend", "frontend"]
        assert members["backend"]["has_kitt_yml"] is True
        assert members["backend"]["kitt_yml_kind"] == "project"
        assert members["frontend"]["exists"] is False

    async def test_reports_project_kind_without_members(self, tmp_path):
        (tmp_path / "kitt.yml").write_text("project:\n  slug: api\n", encoding="utf-8")
        payload = await self._info(tmp_path)
        assert payload["kitt_yml_kind"] == "project"
        assert payload["workspace_config"] is None

    async def test_reports_none_when_no_kitt_yml(self, tmp_path):
        payload = await self._info(tmp_path)
        assert payload["kitt_yml_kind"] is None
        assert payload["workspace_config"] is None
