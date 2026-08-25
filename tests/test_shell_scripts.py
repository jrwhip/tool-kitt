"""The catalog's shell scripts ship unparsed, and nothing was parsing them.

Every ``*.sh`` under ``catalog/`` is deterministic infrastructure the crew
leans on at run time (see ``catalog/crew/scripts/README.md``), yet no test
so much as fed one through a parser. That gap was not academic either:
``autorun.sh`` carried an apostrophe inside a double-quoted ``${VAR:-...}``
word that bash reads as an opening quote, so the whole file failed
``bash -n`` -- and its resume pipeline reported the trailing ``tee``'s
exit status instead of the CLI's, leaving the Ctrl+C branch dead.

Two things are checked:

a. **Every catalog shell script parses.** ``bash -n`` over each ``*.sh``.
   The scripts target zsh, but they advertise portability ("test before
   running on other shells") and bash is the parser every CI box has.
b. **autorun.sh keeps its exit-status mechanism.** The pipeline's real
   exit status is surfaced via ``set -o pipefail`` (chosen over
   ``PIPESTATUS`` because zsh spells that array differently and pipefail
   is spelled identically in both shells). Losing that line silently
   reverts EXIT_CODE to the last ``tee``'s always-zero status.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = REPO_ROOT / "catalog"

CATALOG_SHELL_SCRIPTS = sorted(CATALOG_ROOT.rglob("*.sh"))

AUTORUN = CATALOG_ROOT / "crew" / "scripts" / "autorun.sh"


def test_the_scan_is_not_vacuous():
    """The parametrized check below passes trivially on an empty list."""
    assert AUTORUN in CATALOG_SHELL_SCRIPTS, CATALOG_SHELL_SCRIPTS


@pytest.mark.parametrize(
    "script",
    CATALOG_SHELL_SCRIPTS,
    ids=lambda path: str(path.relative_to(REPO_ROOT)),
)
def test_every_catalog_shell_script_parses(script: Path):
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"bash -n rejected {script.relative_to(REPO_ROOT)}:\n{result.stderr}"
    )


def test_autorun_surfaces_the_pipeline_exit_status():
    """``set -o pipefail`` is the load-bearing line behind EXIT_CODE.

    autorun.sh captures ``$?`` after a four-element pipeline whose last
    two elements are ``tee``. Without pipefail that is always 0, the
    ``-eq 130`` Ctrl+C branch is unreachable, and every manual interrupt
    is misreported as "reason unclear".
    """
    assert "set -o pipefail" in AUTORUN.read_text(encoding="utf-8")
