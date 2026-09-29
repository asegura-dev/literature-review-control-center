"""The installed package imports, every module of it.

On an empty package this is the path the program actually runs: the build backend has to find
``lrcc`` under ``src/`` (the distribution name differs from the import name, ADR-0007), and
every layer has to import.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import pkgutil

import lrcc


def test_every_module_imports() -> None:
    """Walking the package imports each module; a broken one fails here, by name."""
    names = [lrcc.__name__] + [
        info.name for info in pkgutil.walk_packages(lrcc.__path__, prefix=f"{lrcc.__name__}.")
    ]
    for name in names:
        importlib.import_module(name)
    assert {"lrcc.domain", "lrcc.ports", "lrcc.adapters", "lrcc.features", "lrcc.views"} <= set(
        names
    )


def test_the_distribution_is_installed_under_its_own_name() -> None:
    """The distribution is ``literature-review-control-center``, whatever the import name."""
    assert importlib.metadata.version("literature-review-control-center")
