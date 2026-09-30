"""The configuration: what LRCC needs to know about this machine, validated once (ADR-0010).

It holds one field for now, the workspace. Network settings, allowed hosts and secrets arrive
with the code that reads them (v0.3.0 and v0.4.0), so no setting exists that nothing checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, ValidationError

from lrcc.domain.documents import Text, load_mapping
from lrcc.domain.errors import ConfigError, describe_validation


def _absolute(value: str) -> str:
    if not Path(value).is_absolute():
        raise ValueError(
            "must be an absolute path, such as C:\\lrcc-workspace or /home/you/lrcc-workspace"
        )
    return value


class Config(BaseModel):
    """A validated configuration. Unknown fields are errors, so a misspelt setting is caught."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace: Annotated[Text, AfterValidator(_absolute)]

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
