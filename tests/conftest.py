"""Shared fixtures: temporary workspaces and configuration files, never a real review.

No test touches the network. ``no_real_network`` makes any real connection fail, for every test,
so a request that escapes the mocked transport is an error and not a slow, flaky pass.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every real connection attempt fail (PRINCIPLES: tests never touch the network)."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def fixture_bytes() -> Callable[[str], bytes]:
    """Read a synthetic fixture from ``tests/fixtures`` as bytes."""

    def read(name: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    return read


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    """An empty folder outside any repository, which LRCC accepts as a workspace."""
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., Path]:
    """Write a configuration file holding ``workspace`` and any extra sections; return its path."""

    def write(workspace: object, **sections: object) -> Path:
        path = tmp_path / "config.yaml"
        value = str(workspace) if isinstance(workspace, Path) else workspace
        path.write_text(yaml.safe_dump({"workspace": value, **sections}), encoding="utf-8")
        return path

    return write


@pytest.fixture
def config_file(make_config: Callable[..., Path], workspace_root: Path) -> Path:
    """A configuration file naming ``workspace_root``, with the network off."""
    return make_config(workspace_root)
