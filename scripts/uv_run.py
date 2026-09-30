"""Run uv with the project environment kept outside the checkout.

``run.ps1`` does this for a person at a Windows terminal. pre-commit hooks do not pass through
it, and a bare ``uv run`` inside a hook would create a ``.venv`` in the checkout: inside a
synchronised folder, exactly where ADR-0002 says the environment must not be. This launcher uses
only the standard library, so pre-commit can run it on any platform.

``tests/test_environment.py`` checks that this file and ``run.ps1`` name the same environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

#: Folder under the user's home that holds the environment, shared with ``run.ps1``.
ENVIRONMENT_PARTS: tuple[str, ...] = (".venvs", "lrcc")


def environment_path() -> Path:
    """Return where the project environment lives.

    Returns:
        The environment folder under the current user's home directory.
    """
    return Path.home().joinpath(*ENVIRONMENT_PARTS)


def main(argv: list[str]) -> int:
    """Run uv with ``argv``, pointing it at the environment outside the checkout.

    Args:
        argv: Arguments passed to uv, for example ``["run", "mypy"]``.

    Returns:
        uv's exit code.
    """
    uv = shutil.which("uv")
    if uv is None:
        print(
            "uv was not found on PATH; install it from https://docs.astral.sh/uv/", file=sys.stderr
        )
        return 127
    env = dict(os.environ)
    # An inherited VIRTUAL_ENV would be reported as a mismatch on every command.
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT_ENVIRONMENT"] = str(environment_path())
    return subprocess.run([uv, *argv], env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
