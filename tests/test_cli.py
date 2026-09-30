"""``lrcc init`` and ``lrcc validate`` driven as a person drives them, against temporary workspaces.

These tests invoke the same Typer application the ``lrcc`` entry point runs. The environment
always removes ``LRCC_CONFIG``, so a variable set on the developer's machine never decides a
result here.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner, Result

from lrcc.views.cli.app import app, main

runner = CliRunner()

#: Terminal colour and style codes, which Typer adds to help under CI.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def lrcc(*args: str, env: dict[str, str | None] | None = None) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset unless ``env`` sets it."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None, **(env or {})})


def test_init_creates_the_layout_and_a_protocol(config_file: Path, workspace_root: Path) -> None:
    """The review gets its folder and protocol; the reported digest is the file's."""
    result = lrcc("init", "example", "--config", str(config_file))
    assert result.exit_code == 0, result.stderr
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    assert (workspace_root / "library").is_dir()
    assert protocol.is_file()
    assert hashlib.sha256(protocol.read_bytes()).hexdigest() in result.stdout
    assert "review_id: example" in protocol.read_text(encoding="utf-8")


def test_the_template_has_the_same_bytes_on_every_platform() -> None:
    """``init`` hashes a byte-for-byte copy of the template; ``.gitattributes`` pins it to LF.

    Without the pin, a fresh Windows clone had a CR on every line, and ``init`` would have
    printed a different digest there than on Linux for the same version of LRCC.
    """
    template = files("lrcc.features.init").joinpath("protocol-template.yaml").read_bytes()
    assert b"\r" not in template


def test_the_new_protocol_validates(config_file: Path) -> None:
    """Init, then validate: the synthetic template is a valid protocol as written."""
    lrcc("init", "example", "--config", str(config_file))
    result = lrcc("validate", "example", "--config", str(config_file))
    assert result.exit_code == 0, result.stderr
    assert "is valid" in result.stdout
    assert "INC1, INC2" in result.stdout
    assert "arxiv, pubmed" in result.stdout


def test_json_output_is_data(config_file: Path) -> None:
    """Both commands return machine-readable results with ``--json``, and they agree."""
    created = json.loads(lrcc("init", "example", "--config", str(config_file), "--json").stdout)
    checked = json.loads(lrcc("validate", "example", "--config", str(config_file), "--json").stdout)
    assert created["sha256"] == checked["sha256"]
    assert checked["criteria"] == {"inclusion": ["INC1", "INC2"], "exclusion": ["EXC1", "EXC2"]}
    assert checked["sources"] == ["arxiv", "pubmed"]


def test_an_existing_review_is_never_overwritten(config_file: Path, workspace_root: Path) -> None:
    """A second init of the same id fails, and the person's edits survive."""
    lrcc("init", "example", "--config", str(config_file))
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    protocol.write_text("edited by a person\n", encoding="utf-8")
    result = lrcc("init", "example", "--config", str(config_file))
    assert result.exit_code == 1
    assert "already exists" in result.stderr
    assert protocol.read_text(encoding="utf-8") == "edited by a person\n"


def test_an_invalid_review_id_creates_nothing(config_file: Path, workspace_root: Path) -> None:
    """The id is checked before anything touches the disk."""
    result = lrcc("init", "My Review", "--config", str(config_file))
    assert result.exit_code == 1
    assert "is not a valid review id" in result.stderr
    assert list(workspace_root.iterdir()) == []


def test_validate_reports_every_problem(config_file: Path, workspace_root: Path) -> None:
    """An edited protocol with two problems is reported with both, then exit code 1."""
    lrcc("init", "example", "--config", str(config_file))
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    data = yaml.safe_load(protocol.read_text(encoding="utf-8"))
    data["title"] = ""
    data["criteria"][0]["code"] = "INC-1"
    protocol.write_text(yaml.safe_dump(data), encoding="utf-8")
    result = lrcc("validate", "example", "--config", str(config_file))
    assert result.exit_code == 1
    assert "title: must not be empty" in result.stderr
    assert "criteria.0.code: must look like INC1 or EXC1" in result.stderr


def test_a_protocol_naming_another_review_is_refused(
    config_file: Path, workspace_root: Path
) -> None:
    """A protocol copied between reviews without editing its id is caught."""
    lrcc("init", "example", "--config", str(config_file))
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    text = protocol.read_text(encoding="utf-8").replace("review_id: example", "review_id: other")
    protocol.write_text(text, encoding="utf-8")
    result = lrcc("validate", "example", "--config", str(config_file))
    assert result.exit_code == 1
    assert "names the review 'other'" in result.stderr


def test_validating_a_missing_review(config_file: Path) -> None:
    """A review that was never created says how to create it."""
    result = lrcc("validate", "missing", "--config", str(config_file))
    assert result.exit_code == 1
    assert "has no protocol" in result.stderr
    assert "lrcc init missing" in result.stderr


def test_no_configuration_is_an_error_not_a_default() -> None:
    """Without --config or LRCC_CONFIG there is no hidden fallback location."""
    result = lrcc("init", "example")
    assert result.exit_code == 1
    assert "no configuration file was given" in result.stderr
    assert "LRCC_CONFIG" in result.stderr


def test_a_configuration_file_that_is_not_there(tmp_path: Path) -> None:
    """A mistyped path is named as missing, not treated as an empty configuration."""
    result = lrcc("init", "example", "--config", str(tmp_path / "typo.yaml"))
    assert result.exit_code == 1
    assert "does not exist" in result.stderr


def test_a_configuration_path_that_is_a_folder(tmp_path: Path) -> None:
    """A folder cannot be read as a file; the reason is passed on as a detail."""
    result = lrcc("init", "example", "--config", str(tmp_path))
    assert result.exit_code == 1
    assert "cannot read configuration file" in result.stderr


def test_the_configuration_can_come_from_the_environment(config_file: Path) -> None:
    """``LRCC_CONFIG`` names the file when --config does not."""
    result = lrcc("init", "example", env={"LRCC_CONFIG": str(config_file)})
    assert result.exit_code == 0, result.stderr


def test_an_empty_workspace_setting_is_a_clear_error(
    make_config: Callable[[object], Path],
) -> None:
    """The roadmap's criterion, end to end: an empty required value is named, not defaulted."""
    result = lrcc("init", "example", "--config", str(make_config("")))
    assert result.exit_code == 1
    assert "workspace: must not be empty" in result.stderr


def test_a_workspace_inside_a_repository_is_refused_before_writing(
    make_config: Callable[[object], Path], tmp_path: Path
) -> None:
    """Nothing is written when the workspace itself is refused."""
    workspace = tmp_path / "repository" / "workspace"
    workspace.mkdir(parents=True)
    (tmp_path / "repository" / ".git").mkdir()
    result = lrcc("init", "example", "--config", str(make_config(workspace)))
    assert result.exit_code == 1
    assert "inside the git working tree" in result.stderr
    assert list(workspace.iterdir()) == []


def test_a_workspace_under_onedrive_is_refused(
    make_config: Callable[[object], Path], tmp_path: Path
) -> None:
    """The real environment variable, as Windows sets it, is what the command reads."""
    workspace = tmp_path / "OneDrive" / "workspace"
    workspace.mkdir(parents=True)
    result = lrcc(
        "init",
        "example",
        "--config",
        str(make_config(workspace)),
        env={"OneDrive": str(tmp_path / "OneDrive")},
    )
    assert result.exit_code == 1
    assert "inside the synchronised folder" in result.stderr


def test_errors_are_data_with_json(config_file: Path) -> None:
    """A script gets the error as JSON on stdout, with exit code 1."""
    result = lrcc("validate", "missing", "--config", str(config_file), "--json")
    assert result.exit_code == 1
    error = json.loads(result.stdout)
    assert "has no protocol" in error["error"]
    assert error["details"] == ["create the review first with: lrcc init missing"]


def test_markup_in_a_title_is_printed_as_written(config_file: Path, workspace_root: Path) -> None:
    """Content from files is data: Rich markup inside it is shown, never interpreted."""
    lrcc("init", "example", "--config", str(config_file))
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    data = yaml.safe_load(protocol.read_text(encoding="utf-8"))
    data["title"] = "[bold]Not bold[/bold]"
    protocol.write_text(yaml.safe_dump(data), encoding="utf-8")
    result = lrcc("validate", "example", "--config", str(config_file))
    assert "[bold]Not bold[/bold]" in result.stdout


def test_the_lrcc_command_runs_this_application() -> None:
    """The installed ``lrcc`` entry point is ``main``, which runs the app tested here."""
    (entry_point,) = importlib.metadata.entry_points(group="console_scripts", name="lrcc")
    assert entry_point.load() is main


@pytest.mark.parametrize("command", ["init", "validate"])
def test_each_command_explains_itself(command: str) -> None:
    """``--help`` works without a configuration: help is not a command that needs one.

    Typer colours its help when it detects GitHub Actions, and the colour codes land inside
    ``--config``. They are stripped before the text is checked: CI failed on exactly this.
    """
    result = lrcc(command, "--help")
    assert result.exit_code == 0
    text = ANSI_ESCAPE.sub("", result.stdout)
    assert "--config" in text
    assert "--json" in text
