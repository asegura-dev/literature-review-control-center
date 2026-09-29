"""``run.ps1`` and ``scripts/uv_run.py`` keep the environment in the same place (ADR-0002).

Two launchers exist because pre-commit hooks do not pass through ``run.ps1``. Two copies of one
path can drift; this test is where the drift would show.
"""

from __future__ import annotations

from pathlib import Path

import uv_run

ROOT = Path(__file__).resolve().parents[1]


def test_both_launchers_name_the_same_environment() -> None:
    """The PowerShell wrapper and the Python launcher point uv at one folder."""
    wrapper = (ROOT / "run.ps1").read_text(encoding="utf-8")
    assert '".venvs\\lrcc"' in wrapper
    assert uv_run.ENVIRONMENT_PARTS == (".venvs", "lrcc")


def test_the_environment_is_outside_the_checkout() -> None:
    """The whole point: nothing of the environment lives in the repository."""
    assert not uv_run.environment_path().is_relative_to(ROOT)
