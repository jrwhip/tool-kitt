"""Tests for catalog and lock file operations."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from kitt import __version__
from kitt.catalog import read_lock_file, resolve_packs, write_lock_file

CATALOG_ROOT = Path(__file__).resolve().parents[1] / "catalog"


def _catalog_yaml_files() -> list[Path]:
    return sorted(
        {
            *CATALOG_ROOT.rglob("*.yml"),
            *CATALOG_ROOT.rglob("*.yaml"),
        }
    )


def _rel_id(path: Path) -> str:
    return str(path.relative_to(CATALOG_ROOT))


class TestLockFile:
    def test_write_and_read(self, tmp_path: Path):
        write_lock_file(tmp_path, ["_core", "angular"])
        result = read_lock_file(tmp_path)

        assert result is not None
        assert result["installed_packs"] == ["_core", "angular"]
        # Pin to whatever the current package version is. Hardcoding a
        # specific version string here was a known staleness trap: the
        # version bumps on every release, and the assertion fell out of
        # sync with the package version after 0.2.0.
        assert result["version"] == __version__
        assert result["installed_at"] != ""

    def test_read_nonexistent(self, tmp_path: Path):
        assert read_lock_file(tmp_path) is None

    def test_write_with_catalog_source(self, tmp_path: Path):
        write_lock_file(tmp_path, ["_core"], catalog_source="/path/to/catalog")
        result = read_lock_file(tmp_path)

        assert result is not None
        assert result["catalog_source"] == "/path/to/catalog"

    def test_packs_sorted(self, tmp_path: Path):
        write_lock_file(tmp_path, ["python", "_core", "angular"])
        result = read_lock_file(tmp_path)

        assert result is not None
        assert result["installed_packs"] == ["_core", "angular", "python"]

    def test_creates_directory(self, tmp_path: Path):
        """The nested directory must be created BEFORE the lock file
        is written. Pin both halves so a future refactor cannot satisfy
        the assertion by writing the file at the wrong (already
        existing) path.
        """
        lock_dir = tmp_path / "nested" / "dir"
        assert not lock_dir.exists()  # Confirms the dir is the missing piece.
        write_lock_file(lock_dir, ["_core"])
        assert lock_dir.is_dir()
        assert (lock_dir / "kitt.lock.yaml").is_file()


class TestResolvePacks:
    def test_explicit_packs(self):
        result = resolve_packs(cli_packs=["angular", "python"])
        assert "_core" in result
        assert "angular" in result
        assert "python" in result

    def test_core_always_included(self):
        result = resolve_packs(cli_packs=[])
        assert "_core" in result

    def test_profile_resolution(self):
        catalog: dict[str, Any] = {
            "profiles": {
                "web": {"packs": ["angular", "auditors"]},
            }
        }
        result = resolve_packs(cli_profile="web", catalog=catalog)
        assert "angular" in result
        assert "auditors" in result
        assert "_core" in result

    def test_unknown_profile(self):
        catalog: dict[str, Any] = {"profiles": {}}
        result = resolve_packs(cli_profile="nonexistent", catalog=catalog)
        assert result == ["_core"]

    def test_no_input_returns_core_only(self):
        result = resolve_packs()
        assert result == ["_core"]


class TestCatalogYamlExamplesParse:
    """Every YAML file shipped under ``catalog/`` must parse.

    `catalog/crew/templates/kitt.example.yml` previously had a broken
    example: a bracketed scrub placeholder directly against a bare
    scalar (``slug: [placeholder]-api``) parses as a flow sequence
    followed by a trailing scalar, which YAML rejects outright. Nothing
    caught it because nothing loaded the example files. This guards the
    whole catalog, not just that one file, against the same mistake.
    """

    def test_discovery_is_not_empty(self):
        assert _catalog_yaml_files(), "no *.yml / *.yaml files found under catalog/"

    @pytest.mark.parametrize("yaml_path", _catalog_yaml_files(), ids=_rel_id)
    def test_yaml_file_parses(self, yaml_path: Path):
        text = yaml_path.read_text(encoding="utf-8")
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as e:
            pytest.fail(f"{_rel_id(yaml_path)} failed to parse: {e}")
