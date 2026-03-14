"""Tests for repository static checks."""

from pathlib import Path

import pytest

from scripts.check import commands, repo_root


def test_commands_enable_autofix_when_requested(tmp_path: Path) -> None:
    """Switch Ruff into autofix mode when requested."""
    assert commands(tmp_path, fix=True)[:3] == [
        ["ruff", "check", "--fix", "."],
        ["ruff", "format", "."],
        ["mypy", "src", "tests"],
    ]


def test_repo_root_finds_project_from_nested_directory(tmp_path: Path) -> None:
    """Allow the command to run from anywhere inside the repo."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'music'\n")
    nested_dir = tmp_path / "src" / "music"
    nested_dir.mkdir(parents=True)

    assert repo_root(nested_dir) == tmp_path


def test_repo_root_errors_outside_project(tmp_path: Path) -> None:
    """Fail clearly when invoked outside a repo checkout."""
    with pytest.raises(FileNotFoundError, match="pyproject.toml"):
        repo_root(tmp_path)
