"""Shared fixtures: temporary workspaces and configuration files, never a real review."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    """An empty folder outside any repository, which LRCC accepts as a workspace."""
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[[object], Path]:
    """Write a configuration file holding ``{"workspace": value}`` and return its path."""

    def write(workspace: object) -> Path:
        path = tmp_path / "config.yaml"
        value = str(workspace) if isinstance(workspace, Path) else workspace
        path.write_text(yaml.safe_dump({"workspace": value}), encoding="utf-8")
        return path

    return write


@pytest.fixture
def config_file(make_config: Callable[[object], Path], workspace_root: Path) -> Path:
    """A configuration file naming ``workspace_root``."""
    return make_config(workspace_root)
