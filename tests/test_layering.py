"""The layout of ADR-0003, checked in both directions.

Inward: every module belongs to a layer, and imports only what its layer may import. Outward: a
view decides nothing, so a function in a view that never reaches the presentation vocabulary is
logic that leaked out of a feature.

LACC checked only the inward direction for most of its life, and two writers of one file format
drifted apart inside its CLI with every test green (LACC ADR-065, ADR-066). Both directions are
checked here from the first commit, while there is nothing to retrofit.

Imports are read with ``ast``, never executed, so a module that would fail to import is still
checked.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

PACKAGE = "lrcc"
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / PACKAGE

LAYERS = ("domain", "ports", "adapters", "features", "views")

#: Which layers each layer may import from inside ``lrcc`` (ADR-0003). ``features`` is further
#: limited to its own slice, and ``views`` to ``adapters`` only in composition modules; both are
#: checked separately below. Views may import ``domain`` for the types and errors a feature
#: returns or raises (ADR-0010); that they decide nothing is the outward check's job.
ALLOWED: dict[str, frozenset[str]] = {
    "domain": frozenset({"domain"}),
    "ports": frozenset({"domain", "ports"}),
    "adapters": frozenset({"domain", "ports", "adapters"}),
    "features": frozenset({"domain", "ports", "features"}),
    "views": frozenset({"features", "views", "adapters", "domain"}),
}

#: Third-party packages the domain may import besides the standard library: Pydantic, with its
#: core, validates (ADR-0003); PyYAML's safe loader parses the documents people write (ADR-0010).
DOMAIN_THIRD_PARTY = frozenset({"pydantic", "pydantic_core", "yaml"})

#: LRCC is a sibling of LACC, coupled only through the review bundle (ADR-0001).
FORBIDDEN_EVERYWHERE = frozenset({"local_ai_control_center"})

#: A view module with this name is composition: the one place a view may build adapters.
COMPOSITION_MODULE = "composition"

#: Names that make a function part of the presentation. Extended when the first view is written,
#: never to excuse a function that decides something (ADR-0003, Consequences).
PRESENTATION_VOCABULARY = frozenset(
    {
        "typer",
        "rich",
        "Console",
        "console",
        "Table",
        "Panel",
        "Progress",
        "Prompt",
        "Confirm",
        "echo",
        "print",
    }
)

#: Functions a view may hold that touch no presentation, each exempt by name (ADR-0003):
#: the entry point. Typer commands are recognised by their decorator, and composition by its
#: module name.
EXEMPT_VIEW_FUNCTIONS = frozenset({"main"})


@dataclass(frozen=True)
class Module:
    """One source module, located in the package."""

    path: Path
    name: str
    layer: str | None
    slice: str | None
    tree: ast.Module


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _load(root: Path) -> list[Module]:
    modules = []
    for path in sorted(root.rglob("*.py")):
        name = _module_name(path, root)
        parts = name.split(".")
        layer = parts[1] if len(parts) > 1 else None
        slice_ = parts[2] if layer == "features" and len(parts) > 2 else None
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules.append(Module(path, name, layer, slice_, tree))
    return modules


def _imports(module: Module) -> list[str]:
    """Return the absolute names ``module`` imports, resolving relative imports."""
    found: list[str] = []
    is_package = module.path.name == "__init__.py"
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                anchor = module.name.split(".")
                drop = node.level - 1 if is_package else node.level
                anchor = anchor[: len(anchor) - drop]
                base = ".".join([*anchor, node.module] if node.module else anchor)
            found.append(base)
            # `from lrcc import features` names a layer through its alias.
            if base == PACKAGE:
                found.extend(f"{PACKAGE}.{alias.name}" for alias in node.names)
    return found


def layering_violations(root: Path = SOURCE_ROOT) -> list[str]:
    """Return every inward violation of ADR-0003 under ``root``, one line each."""
    problems: list[str] = []
    for module in _load(root):
        if module.layer is not None and module.layer not in LAYERS:
            problems.append(f"{module.name}: lives outside the layers {LAYERS}")
            continue
        for target in _imports(module):
            top = target.split(".")[0]
            if top in FORBIDDEN_EVERYWHERE:
                problems.append(f"{module.name} imports {target}: LACC is reached by bundle only")
                continue
            if module.layer is None:
                continue
            if top != PACKAGE:
                if (
                    module.layer == "domain"
                    and top not in sys.stdlib_module_names
                    and top not in DOMAIN_THIRD_PARTY
                ):
                    problems.append(f"{module.name} imports {target}: the domain stays pure")
                continue
            parts = target.split(".")
            if len(parts) < 2:
                problems.append(
                    f"{module.name} imports {target}: import from a layer, not the root"
                )
                continue
            layer = parts[1]
            if layer not in ALLOWED[module.layer]:
                problems.append(
                    f"{module.name} imports {target}: {module.layer} may not import {layer}"
                )
            elif (
                module.layer == "features"
                and layer == "features"
                and len(parts) > 2
                and parts[2] != module.slice
            ):
                problems.append(f"{module.name} imports {target}: a feature imports no other")
            elif (
                module.layer == "views"
                and layer == "adapters"
                and module.name.split(".")[-1] != COMPOSITION_MODULE
            ):
                problems.append(f"{module.name} imports {target}: only composition builds adapters")
    return problems


def _names_used(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _is_command(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in {"command", "callback"}:
            return True
    return False


def view_logic(root: Path = SOURCE_ROOT) -> list[str]:
    """Return every function in a view that never reaches the presentation (ADR-0003).

    A function is presentation if it uses a name from the vocabulary, or calls a function of
    the same module that is presentation, transitively. Being *called by* a presentation
    function does not count: otherwise any logic reached from a renderer would be excused. A
    pure formatter therefore has to touch the vocabulary itself, or be named in
    ``EXEMPT_VIEW_FUNCTIONS`` where a reviewer sees it.
    """
    problems: list[str] = []
    for module in _load(root):
        if module.layer != "views" or module.name.split(".")[-1] == COMPOSITION_MODULE:
            continue
        functions = {
            node.name: node
            for node in ast.walk(module.tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        used = {name: _names_used(node) for name, node in functions.items()}
        presentation = {name for name, names in used.items() if names & PRESENTATION_VOCABULARY}
        changed = True
        while changed:
            changed = False
            for name, names in used.items():
                if name not in presentation and names & presentation:
                    presentation.add(name)
                    changed = True
        for name, node in functions.items():
            if name in presentation or name in EXEMPT_VIEW_FUNCTIONS or _is_command(node):
                continue
            problems.append(f"{module.name}.{name}: touches no presentation; move it to a feature")
    return problems


def test_the_package_is_where_the_layout_test_looks() -> None:
    """A test that silently checks an empty folder would pass forever."""
    assert (SOURCE_ROOT / "__init__.py").is_file()
    assert {m.layer for m in _load(SOURCE_ROOT)} >= set(LAYERS)


def test_dependencies_point_inward() -> None:
    """Every import respects the table of ADR-0003."""
    assert layering_violations() == []


def test_no_logic_leaks_into_a_view() -> None:
    """Every function in a view is presentation, a command, composition or the entry point."""
    assert view_logic() == []


def _write(root: Path, relative: str, source: str) -> None:
    path = root / PACKAGE / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """An empty copy of the layout, to prove each rule can fail."""
    for layer in ("", *LAYERS):
        _write(tmp_path, f"{layer}/__init__.py".lstrip("/"), '"""Layer."""\n')
    return tmp_path / PACKAGE


@pytest.mark.parametrize(
    ("relative", "source", "expected"),
    [
        ("domain/rule.py", "from lrcc.adapters import x\n", "domain may not import adapters"),
        ("domain/rule.py", "import httpx\n", "the domain stays pure"),
        ("ports/source.py", "from ..features import x\n", "ports may not import features"),
        ("adapters/pubmed.py", "import lrcc.features.search\n", "adapters may not import"),
        ("features/search/use.py", "from lrcc.adapters import x\n", "features may not import"),
        ("features/search/use.py", "from lrcc.features.dedupe import x\n", "imports no other"),
        ("views/cli.py", "from lrcc.adapters import x\n", "only composition builds adapters"),
        ("views/cli.py", "from lrcc.ports import x\n", "views may not import ports"),
        ("features/search/use.py", "import local_ai_control_center\n", "reached by bundle"),
        ("extras/thing.py", "", "lives outside the layers"),
    ],
)
def test_each_inward_rule_can_fail(
    package: Path, relative: str, source: str, expected: str
) -> None:
    """A check nobody has seen fail is a check nobody has seen work."""
    _write(package.parent, relative, source)
    problems = layering_violations(package)
    assert any(expected in problem for problem in problems), problems


def test_the_allowed_imports_pass(package: Path) -> None:
    """The rules are not so strict that the intended shape fails them."""
    _write(package.parent, "domain/record.py", "import hashlib\nfrom pydantic import BaseModel\n")
    _write(package.parent, "ports/source.py", "from lrcc.domain import record\n")
    _write(package.parent, "adapters/pubmed.py", "from lrcc.ports import source\n")
    _write(package.parent, "features/search/__init__.py", '"""Search."""\n')
    _write(package.parent, "features/search/use.py", "from . import helpers\n")
    _write(package.parent, "views/composition.py", "from lrcc.adapters import pubmed\n")
    _write(
        package.parent,
        "views/cli.py",
        "from lrcc.features.search import use\nfrom lrcc.domain.errors import LrccError\n",
    )
    assert layering_violations(package) == []


def test_logic_in_a_view_is_named(package: Path) -> None:
    """Logic in a view is named even when a renderer calls it; presentation is not."""
    _write(
        package.parent,
        "views/cli.py",
        "def _show(rows):\n"
        "    console.print(_dedupe(rows))\n"
        "def _header():\n"
        "    _show(['title'])\n"
        "def _dedupe(rows):\n"
        "    return sorted(set(rows))\n"
        "@app.command()\n"
        "def search():\n"
        "    pass\n"
        "def main():\n"
        "    pass\n",
    )
    assert view_logic(package) == [
        "lrcc.views.cli._dedupe: touches no presentation; move it to a feature"
    ]
