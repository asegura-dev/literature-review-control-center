"""One HTTP client for the whole program (ADR-0011; PRINCIPLES 6).

The allowlist lives in ``adapters/http.py``. It protects nothing if another module can make
requests on its own, so this test reads every module with ``ast`` and fails if a networking
library is imported anywhere else.
"""

from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "lrcc"

#: The only module that may make requests.
HTTP_CLIENT = "adapters/http.py"

#: Libraries that can open a connection. ``urllib.parse`` only splits text and is not listed.
NETWORK_LIBRARIES = frozenset(
    {
        "httpx",
        "httpcore",
        "requests",
        "urllib3",
        "aiohttp",
        "socket",
        "ssl",
        "http.client",
        "urllib.request",
        "ftplib",
        "smtplib",
        "telnetlib",
    }
)


def egress_outside_the_client(root: Path = SOURCE_ROOT) -> list[str]:
    """Return every import of a networking library outside the HTTP client, one line each."""
    problems: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == HTTP_CLIENT:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
            libraries = {
                lib
                for name in names
                for lib in NETWORK_LIBRARIES
                if name == lib or name.startswith(f"{lib}.")
            }
            problems.extend(f"{relative} imports {lib}" for lib in sorted(libraries))
    return problems


def test_only_the_http_client_can_reach_the_network() -> None:
    """No module but ``adapters/http.py`` imports a networking library."""
    assert egress_outside_the_client() == []


def test_the_http_client_is_where_the_test_expects_it() -> None:
    """If the client moved, the exemption above would silently exempt nothing."""
    assert (SOURCE_ROOT / HTTP_CLIENT).is_file()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import httpx\n", "imports httpx"),
        ("from urllib.request import urlopen\n", "imports urllib.request"),
        ("from urllib import request\n", "imports urllib.request"),
        ("import http.client\n", "imports http.client"),
        ("import socket\n", "imports socket"),
    ],
)
def test_a_second_way_out_is_caught(tmp_path: Path, source: str, expected: str) -> None:
    """A check nobody has seen fail is a check nobody has seen work."""
    package = tmp_path / "lrcc"
    (package / "adapters").mkdir(parents=True)
    (package / "adapters" / "http.py").write_text("import httpx\n", encoding="utf-8")
    (package / "adapters" / "shortcut.py").write_text(source, encoding="utf-8")
    assert egress_outside_the_client(package) == [f"adapters/shortcut.py {expected}"]


def test_parsing_an_address_is_not_egress(tmp_path: Path) -> None:
    """``urllib.parse`` only splits text; using it is not a way out."""
    package = tmp_path / "lrcc"
    package.mkdir()
    (package / "links.py").write_text("from urllib.parse import urlsplit\n", encoding="utf-8")
    assert egress_outside_the_client(package) == []


def test_the_tests_themselves_cannot_reach_the_network() -> None:
    """The autouse fixture in ``conftest.py`` makes a real connection fail."""
    with pytest.raises(AssertionError, match="real network connection"):
        socket.create_connection(("192.0.2.1", 443), timeout=0.1)
