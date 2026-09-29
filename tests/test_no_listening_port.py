"""LRCC opens no listening port, in any mode (ADR-0005; PRINCIPLES 6).

The check reads the source with ``ast`` and fails on server-side networking: modules that exist
to serve, and the calls that bind or listen. A client socket, which the HTTP client will open,
is not a listening port and is not flagged.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "lrcc"

#: Modules whose purpose is to serve requests.
SERVER_MODULES = frozenset(
    {
        "http.server",
        "socketserver",
        "xmlrpc.server",
        "wsgiref.simple_server",
        "flask",
        "fastapi",
        "starlette",
        "aiohttp.web",
        "uvicorn",
        "hypercorn",
        "waitress",
        "tornado.web",
    }
)

#: Calls that bind a port or accept connections.
SERVER_CALLS = frozenset({"bind", "listen", "start_server", "create_server", "serve_forever"})


def listening_code(root: Path = SOURCE_ROOT) -> list[str]:
    """Return every server-side import or call under ``root``, one line each."""
    problems: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        where = path.relative_to(root.parent)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                else:
                    module = node.module or ""
                    names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
                for name in names:
                    if any(name == m or name.startswith(f"{m}.") for m in SERVER_MODULES):
                        problems.append(f"{where}:{node.lineno} imports {name}")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in SERVER_CALLS
            ):
                problems.append(f"{where}:{node.lineno} calls {node.func.attr}()")
    return problems


def test_nothing_listens() -> None:
    """The package contains no server-side networking."""
    assert listening_code() == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import http.server\n", "imports http.server"),
        ("from socketserver import TCPServer\n", "imports socketserver"),
        ("from aiohttp import web\n", "imports aiohttp.web"),
        ("import socket\nsocket.socket().bind(('', 80))\n", "calls bind()"),
        ("import asyncio\nasyncio.start_server(None)\n", "calls start_server()"),
    ],
)
def test_each_kind_of_listening_is_caught(tmp_path: Path, source: str, expected: str) -> None:
    """A check nobody has seen fail is a check nobody has seen work."""
    package = tmp_path / "lrcc"
    package.mkdir()
    (package / "server.py").write_text(source, encoding="utf-8")
    problems = listening_code(package)
    assert any(expected in problem for problem in problems), problems


def test_a_client_socket_is_not_a_listening_port(tmp_path: Path) -> None:
    """Outbound connections are the HTTP client's job and are not flagged."""
    package = tmp_path / "lrcc"
    package.mkdir()
    (package / "client.py").write_text(
        "import socket\nsocket.create_connection(('example.org', 443))\n", encoding="utf-8"
    )
    assert listening_code(package) == []
