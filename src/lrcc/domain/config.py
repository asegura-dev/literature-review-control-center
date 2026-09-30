"""The configuration: what LRCC needs to know about this machine, validated once.

It names the workspace (ADR-0010) and, when searching is wanted, the network settings: whether
requests are allowed at all, and the only hosts that may be contacted, each with the pause to
leave between two requests to it (ADR-0011). The network is off unless the file turns it on.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, field_validator

from lrcc.domain.documents import Text, load_mapping
from lrcc.domain.errors import ConfigError, describe_validation

_HOST = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")


def _absolute(value: str) -> str:
    if not Path(value).is_absolute():
        raise ValueError(
            "must be an absolute path, such as C:\\lrcc-workspace or /home/you/lrcc-workspace"
        )
    return value


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HostConfig(_Frozen):
    """One allowed host, and the seconds to leave between two requests to it."""

    min_interval: Annotated[float, Field(ge=0)]


class NetworkConfig(_Frozen):
    """Whether requests are allowed, and the only hosts that may be contacted."""

    enabled: bool = False
    hosts: dict[str, HostConfig] = Field(default_factory=dict)

    @field_validator("hosts")
    @classmethod
    def _hosts_are_bare_names(cls, hosts: dict[str, HostConfig]) -> dict[str, HostConfig]:
        bad = sorted(host for host in hosts if not _HOST.fullmatch(host))
        if bad:
            raise ValueError(
                f"{', '.join(bad)}: a host is a lowercase name such as export.arxiv.org,"
                " without a scheme, a port or a path"
            )
        return hosts


class Config(_Frozen):
    """A validated configuration. Unknown fields are errors, so a misspelt setting is caught."""

    workspace: Annotated[Text, AfterValidator(_absolute)]
    network: NetworkConfig = Field(default_factory=NetworkConfig)

    @property
    def workspace_path(self) -> Path:
        """The workspace root, as written in the configuration."""
        return Path(self.workspace)


def parse_config(text: str, source: str) -> Config:
    """Parse and validate a configuration document.

    Args:
        text: The YAML document.
        source: Where it came from, named in any error.

    Returns:
        The validated configuration.

    Raises:
        ConfigError: If the document is not valid YAML or not a valid configuration.
    """
    data = load_mapping(text, source, ConfigError)
    try:
        return Config.model_validate(data)
    except ValidationError as error:
        raise ConfigError(
            f"{source} is not a valid configuration", describe_validation(error)
        ) from None
