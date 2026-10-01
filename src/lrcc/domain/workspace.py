"""The workspace and its boundary (ADR-0006).

A workspace is a folder holding ``library/`` and ``reviews/``. LRCC refuses one inside a git
working tree, where licensed content would be one ``git add`` away from a repository. It also
refuses one under a synchronised folder it can detect, which would copy licensed PDFs to a third
party. Every path built inside it is resolved, symlinks, junctions and ``..`` included, and
checked against the root before use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from lrcc.domain.errors import WorkspaceError
from lrcc.domain.identifiers import require_review_id

LIBRARY = "library"
REVIEWS = "reviews"
PROTOCOL_FILE = "protocol.yaml"

#: Environment variables naming synchronised folders LRCC can detect. Others are covered only by
#: documentation (ADR-0006).
SYNC_VARIABLES = ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")


@dataclass(frozen=True)
class Workspace:
    """An accepted workspace. Build it with :func:`open_workspace`, which checks the root."""

    root: Path

    def resolve_within(self, relative: str | Path) -> Path:
        """Resolve a path inside the workspace, refusing any that leaves it.

        Args:
            relative: A path relative to the workspace root.

        Returns:
            The resolved absolute path.

        Raises:
            WorkspaceError: If the path is absolute, or resolves outside the root.
        """
        candidate = Path(relative)
        if candidate.anchor:
            raise WorkspaceError(f"{relative} is not a path relative to the workspace")
        resolved = (self.root / candidate).resolve()
        if not resolved.is_relative_to(self.root):
            raise WorkspaceError(
                f"{relative} leads outside the workspace {self.root}",
                ["every path LRCC uses must stay inside the workspace (ADR-0006)"],
            )
        return resolved

    def review_dir(self, review_id: str) -> Path:
        """Return the folder of a review.

        Args:
            review_id: The review's id.

        Returns:
            ``reviews/<review_id>`` inside the workspace, resolved.
        """
        return self.resolve_within(Path(REVIEWS, require_review_id(review_id)))

    def protocol_path(self, review_id: str) -> Path:
        """Return where a review's protocol lives.

        Args:
            review_id: The review's id.

        Returns:
            ``reviews/<review_id>/protocol.yaml`` inside the workspace, resolved.
        """
        return self.resolve_within(Path(REVIEWS, require_review_id(review_id), PROTOCOL_FILE))


def open_workspace(root: Path, environ: Mapping[str, str]) -> Workspace:
    """Accept ``root`` as the workspace, or refuse it with the reason.

    Args:
        root: The workspace root from the configuration.
        environ: The environment, read for synchronised folders. It is passed in rather than read
            here so that the refusal can be tested without touching the real environment.

    Returns:
        The workspace, with its root resolved.

    Raises:
        WorkspaceError: If the root is not an existing folder, lies inside a git working tree, or
            lies inside a synchronised folder named in ``environ``.
    """
    resolved = root.resolve()
    if not resolved.is_dir():
        raise WorkspaceError(
            f"workspace {root} is not an existing folder",
            ["create the folder first; LRCC never creates a workspace on its own"],
        )
    repository = _git_working_tree(resolved)
    if repository is not None:
        raise WorkspaceError(
            f"workspace {resolved} is inside the git working tree {repository}",
            [
                "licensed content must never be one `git add` away from a repository (ADR-0006)",
                "choose a folder outside every repository",
            ],
        )
    synchronised = _synchronised_folder(resolved, environ)
    if synchronised is not None:
        raise WorkspaceError(
            f"workspace {resolved} is inside the synchronised folder {synchronised}",
            [
                "a synchroniser would copy licensed PDFs to a third party (ADR-0006)",
                "choose a folder in your user profile that is not synchronised, such as"
                " C:\\Users\\you\\lrcc-workspace: other accounts cannot read it there",
            ],
        )
    return Workspace(resolved)


def _git_working_tree(path: Path) -> Path | None:
    # `.git` is a folder in a normal clone, and a file in worktrees and submodules.
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _synchronised_folder(path: Path, environ: Mapping[str, str]) -> Path | None:
    for variable in SYNC_VARIABLES:
        value = environ.get(variable, "").strip()
        if value and path.is_relative_to(Path(value).resolve()):
            return Path(value).resolve()
    return None
