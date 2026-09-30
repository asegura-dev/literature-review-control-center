"""The workspace boundary of ADR-0006: refused where it would expose content, and never escaped."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from lrcc.domain.errors import ReviewError, WorkspaceError
from lrcc.domain.workspace import SYNC_VARIABLES, open_workspace


def _link(link: Path, target: Path) -> None:
    """Make ``link`` point at the folder ``target``: a junction on Windows, a symlink elsewhere.

    A junction needs no privilege, and it is what a synchroniser or a person would create on
    Windows, so the escape is tested on every platform CI runs.
    """
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_an_existing_folder_is_accepted(workspace_root: Path) -> None:
    """The root is resolved once, when the workspace is opened."""
    assert open_workspace(workspace_root, {}).root == workspace_root.resolve()


def test_a_missing_folder_is_refused_not_created(tmp_path: Path) -> None:
    """LRCC never creates a workspace on its own."""
    with pytest.raises(WorkspaceError, match="is not an existing folder"):
        open_workspace(tmp_path / "missing", {})
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("git_is_a_file", [False, True])
def test_a_folder_inside_a_repository_is_refused(tmp_path: Path, git_is_a_file: bool) -> None:
    """``.git`` is a folder in a clone and a file in a worktree; both mark a working tree."""
    repository = tmp_path / "repository"
    workspace = repository / "nested" / "workspace"
    workspace.mkdir(parents=True)
    if git_is_a_file:
        (repository / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    else:
        (repository / ".git").mkdir()
    with pytest.raises(WorkspaceError, match="inside the git working tree") as caught:
        open_workspace(workspace, {})
    assert str(repository.resolve()) in caught.value.message


@pytest.mark.parametrize("variable", SYNC_VARIABLES)
def test_a_folder_under_a_synchronised_folder_is_refused(tmp_path: Path, variable: str) -> None:
    """A synchroniser would copy licensed PDFs to a third party."""
    synchronised = tmp_path / "OneDrive"
    workspace = synchronised / "research" / "workspace"
    workspace.mkdir(parents=True)
    with pytest.raises(WorkspaceError, match="inside the synchronised folder"):
        open_workspace(workspace, {variable: str(synchronised)})


def test_a_synchronised_folder_elsewhere_does_not_matter(
    workspace_root: Path, tmp_path: Path
) -> None:
    """Only a workspace under the synchronised folder is refused."""
    (tmp_path / "OneDrive").mkdir()
    open_workspace(workspace_root, {"OneDrive": str(tmp_path / "OneDrive")})


@pytest.mark.parametrize("relative", ["../outside", "reviews/../../outside"])
def test_a_path_that_climbs_out_is_refused(workspace_root: Path, relative: str) -> None:
    """``..`` is resolved before the check, not after."""
    workspace = open_workspace(workspace_root, {})
    with pytest.raises(WorkspaceError, match="leads outside the workspace"):
        workspace.resolve_within(relative)


def test_an_absolute_path_is_refused(workspace_root: Path, tmp_path: Path) -> None:
    """Paths inside the workspace are always relative to it."""
    workspace = open_workspace(workspace_root, {})
    with pytest.raises(WorkspaceError, match="not a path relative to the workspace"):
        workspace.resolve_within(tmp_path)


def test_a_link_that_leads_out_is_refused(workspace_root: Path, tmp_path: Path) -> None:
    """A junction or symlink inside the workspace does not carry a path outside it."""
    outside = tmp_path / "outside"
    outside.mkdir()
    _link(workspace_root / "reviews", outside)
    workspace = open_workspace(workspace_root, {})
    with pytest.raises(WorkspaceError, match="leads outside the workspace"):
        workspace.review_dir("example")


def test_an_invalid_review_id_never_becomes_a_path(workspace_root: Path) -> None:
    """Ids are validated before any path is built from them (ADR-0006)."""
    workspace = open_workspace(workspace_root, {})
    with pytest.raises(ReviewError, match="is not a valid review id"):
        workspace.review_dir("../escape")
