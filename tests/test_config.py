"""The configuration: an empty required value is a clear error, never a silent default."""

from __future__ import annotations

from pathlib import Path

import pytest

from lrcc.domain.config import parse_config
from lrcc.domain.errors import ConfigError


def _problems(text: str) -> tuple[str, tuple[str, ...]]:
    with pytest.raises(ConfigError) as caught:
        parse_config(text, source="config.yaml")
    return caught.value.message, caught.value.details


def test_a_valid_configuration(tmp_path: Path) -> None:
    """The workspace is read as written, as an absolute path."""
    config = parse_config(f"workspace: '{tmp_path}'\n", source="config.yaml")
    assert config.workspace_path == tmp_path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("workspace: ''\n", "workspace: must not be empty"),
        ("workspace: '   '\n", "workspace: must not be empty"),
        ("workspace:\n", "workspace: must not be empty"),
        ("other: 1\n", "workspace: is required"),
        ("workspace: relative/folder\n", "workspace: must be an absolute path"),
    ],
)
def test_invalid_values_are_named(text: str, expected: str) -> None:
    """Each problem names its field and says what is wrong."""
    message, details = _problems(text)
    assert message == "config.yaml is not a valid configuration"
    assert any(detail.startswith(expected) for detail in details), details


def test_a_misspelt_field_is_an_error_not_ignored(tmp_path: Path) -> None:
    """``extra="forbid"``: a typo in a setting's name is reported, never silently skipped."""
    _, details = _problems(f"workspace: '{tmp_path}'\nworkspce: x\n")
    assert "workspce: is not a known field" in details


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "config.yaml is empty"),
        ("- a\n- b\n", "config.yaml must be a mapping of fields, not a list"),
        ("workspace: [unclosed\n", "config.yaml is not valid YAML"),
    ],
)
def test_documents_that_are_not_a_configuration(text: str, expected: str) -> None:
    """Empty files, lists and broken YAML are refused before any field is read."""
    message, _ = _problems(text)
    assert message == expected
