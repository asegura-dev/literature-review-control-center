"""Load the configuration and open its workspace: the first step of every command (ADR-0010).

There is no default location for the configuration. A person names it with ``--config`` or with
the ``LRCC_CONFIG`` environment variable; with neither, LRCC stops and says so.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from lrcc.domain.config import Config, parse_config
from lrcc.domain.errors import ConfigError
from lrcc.domain.workspace import Workspace, open_workspace

#: The environment variable that may name the configuration file.
CONFIG_ENV = "LRCC_CONFIG"


def load_configuration(config_path: Path | None) -> Config:
    """Read and validate the configuration file.

    Args:
        config_path: The configuration file, or None if the person named none.

    Returns:
        The validated configuration.

    Raises:
        ConfigError: If no file was named, or it cannot be read, or it is not valid.
    """
    if config_path is None:
        raise ConfigError(
            "no configuration file was given",
            [f"pass --config PATH, or set {CONFIG_ENV} to the path of your configuration file"],
        )
    try:
        text = config_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise ConfigError(f"configuration file {config_path} does not exist") from None
    except (OSError, UnicodeDecodeError) as problem:
        raise ConfigError(f"cannot read configuration file {config_path}", [str(problem)]) from None
    return parse_config(text, source=str(config_path))


def workspace_of(config: Config, environ: Mapping[str, str]) -> Workspace:
    """Open the workspace a configuration names.

    Args:
        config: The validated configuration.
        environ: The environment, passed on to the workspace checks.

    Returns:
        The accepted workspace.

    Raises:
        WorkspaceError: If the workspace is refused.
    """
    return open_workspace(config.workspace_path, environ)


def open_configured_workspace(config_path: Path | None, environ: Mapping[str, str]) -> Workspace:
    """Read the configuration file and open the workspace it names.

    Args:
        config_path: The configuration file, or None if the person named none.
        environ: The environment, passed on to the workspace checks.

    Returns:
        The accepted workspace.

    Raises:
        ConfigError: If no file was named, or it cannot be read, or it is not valid.
        WorkspaceError: If the workspace it names is refused.
    """
    return workspace_of(load_configuration(config_path), environ)
