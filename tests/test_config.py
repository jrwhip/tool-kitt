"""Tests for ServerConfig."""

import dataclasses
import os
from unittest.mock import patch

import pytest

from kitt.config import ServerConfig, _detect_cli_type


class TestDetectCliType:
    def test_explicit_claude(self):
        assert _detect_cli_type("claude", None, None, None) == "claude"

    def test_explicit_gemini(self):
        assert _detect_cli_type("gemini", None, None, None) == "gemini"

    def test_explicit_copilot(self):
        assert _detect_cli_type("copilot", None, None, None) == "copilot"

    def test_claude_entrypoint(self):
        assert _detect_cli_type("", "some-entrypoint", None, None) == "claude"

    def test_copilot_token(self):
        assert _detect_cli_type("", None, "token-value", None) == "copilot"

    def test_gemini_key(self):
        assert _detect_cli_type("", None, None, "key-value") == "gemini"

    def test_unknown_default(self):
        assert _detect_cli_type("", None, None, None) == "unknown"

    def test_explicit_takes_priority(self):
        assert _detect_cli_type("gemini", "entrypoint", "token", "key") == "gemini"


class TestServerConfig:
    def test_frozen(self):
        """Assignment to a field on a frozen dataclass raises.

        Tests the observable behavior, not the
        ``__dataclass_params__.frozen`` internal attribute, so this
        contract survives a future Python release that renames the
        attribute or changes the dataclass machinery.
        """
        config = ServerConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.cli_type = "claude"  # type: ignore[misc]

    def test_defaults(self):
        config = ServerConfig()
        assert config.ai_cli_workspace is None
        assert config.kitt_workspace is None
        assert config.cli_type == "unknown"
        assert config.catalog_path is None
        assert config.toggl_api_key is None

    def test_from_env_reads_environment(self):
        env = {
            "AI_CLI_WORKSPACE": "/test/workspace",
            "KITT_WORKSPACE": "/test/kitt",
            "AI_CLI_TYPE": "claude",
            "KITT_CATALOG": "/test/catalog",
            "TOGGL_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False):
            config = ServerConfig.from_env()

        assert config.ai_cli_workspace == "/test/workspace"
        assert config.kitt_workspace == "/test/kitt"
        assert config.cli_type == "claude"
        assert config.catalog_path == "/test/catalog"
        assert config.toggl_api_key == "test-key"

    def test_from_env_empty_environment(self):
        env_keys = [
            "AI_CLI_WORKSPACE", "KITT_WORKSPACE", "TOOL_KITT_WORKSPACE",
            "AI_CLI_TYPE", "CLAUDE_CODE_ENTRYPOINT", "GITHUB_COPILOT_TOKEN",
            "GH_COPILOT_TOKEN", "GEMINI_API_KEY", "KITT_CATALOG", "TOGGL_API_KEY",
        ]
        clean_env = {k: v for k, v in os.environ.items() if k not in env_keys}
        with patch.dict(os.environ, clean_env, clear=True):
            config = ServerConfig.from_env()

        assert config.cli_type == "unknown"
        assert config.ai_cli_workspace is None

    def test_legacy_tool_kitt_workspace(self):
        env = {"TOOL_KITT_WORKSPACE": "/old/path"}
        env_keys = ["KITT_WORKSPACE"]
        clean = {k: v for k, v in os.environ.items() if k not in env_keys}
        clean.update(env)
        with patch.dict(os.environ, clean, clear=True):
            config = ServerConfig.from_env()

        assert config.kitt_workspace == "/old/path"
