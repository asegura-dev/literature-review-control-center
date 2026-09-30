"""API keys: read from a ``.env`` beside the configuration, and never shown (ADR-0015).

Only the four variables LRCC knows are kept. A key already set in the environment wins over the
file. Nothing here ever returns a value inside a message: errors name the variable and the file,
and the object's printed form lists names only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from lrcc.domain.errors import ConfigError

DOTENV = ".env"

#: The variables LRCC reads. Nothing else in a ``.env`` is kept.
KNOWN = ("SCOPUS_API_KEY", "SCOPUS_INSTTOKEN", "IEEE_API_KEY", "NCBI_API_KEY")

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse_dotenv(text: str) -> dict[str, str]:
    """Read ``NAME=value`` lines, ignoring blanks, ``#`` comments and an optional ``export``.

    The same rules as LACC's parser, so the two programs read one file alike. Matching quotes
    around a value are removed. A malformed line is skipped rather than reported: reporting it
    would mean printing it, and it may hold a key.

    Args:
        text: The file's contents.

    Returns:
        Every well-formed variable, by name.
    """
    found: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = stripped.removeprefix("export ").lstrip()
        name, separator, value = stripped.partition("=")
        name = name.strip()
        if not separator or not _NAME.fullmatch(name):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[name] = value
    return found


@dataclass(frozen=True, repr=False)
class Secrets:
    """The keys available to this run, and where they would have come from."""

    values: Mapping[str, str] = field(default_factory=dict)
    origin: str = "the .env beside the configuration file"

    def get(self, name: str) -> str | None:
        """Return the key ``name``, or None if it is not set."""
        return self.values.get(name) or None

    def require(self, name: str, purpose: str) -> str:
        """Return the key ``name``, or explain which file should hold it.

        Args:
            name: One of :data:`KNOWN`.
            purpose: What needs it, such as "IEEE Xplore", named in the error.

        Returns:
            The key.

        Raises:
            ConfigError: If the key is not set. The message names the variable and the file,
                never a value.
        """
        value = self.get(name)
        if value is None:
            raise ConfigError(
                f"{purpose} needs {name}, and it is not set",
                [
                    f"add a line {name}=... to {self.origin}",
                    "each line has the shape NAME=value, with no spaces around the value",
                ],
            )
        return value

    def __repr__(self) -> str:
        """Name the keys that are set, never their values."""
        return f"Secrets(set: {', '.join(sorted(self.values)) or 'none'})"


#: No keys at all: what a source gets when nothing was loaded, as in most tests.
NO_SECRETS = Secrets()


def load_secrets(directory: Path, environ: Mapping[str, str]) -> Secrets:
    """Read the keys LRCC knows from ``directory/.env``, letting the environment win.

    Args:
        directory: The folder holding the configuration file. Nowhere else is looked at.
        environ: The environment. A known variable set there replaces the file's value.

    Returns:
        The keys that are set. A missing file means no keys, not an error.

    Raises:
        ConfigError: If the file exists but cannot be read.
    """
    path = directory / DOTENV
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        text = ""
    except (OSError, UnicodeDecodeError) as problem:
        raise ConfigError(f"cannot read {path}", [type(problem).__name__]) from None
    parsed = parse_dotenv(text)
    values = {name: parsed[name] for name in KNOWN if parsed.get(name)}
    values.update({name: environ[name] for name in KNOWN if environ.get(name)})
    return Secrets(values, origin=str(path))
