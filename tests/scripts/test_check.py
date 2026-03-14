"""Tests for repository static checks."""

from pathlib import Path

import pytest

from scripts.check import commands, repo_root, shellcheck_targets


def test_shellcheck_targets_include_scripts_dir(tmp_path: Path) -> None:
    """Discover checked shell files while skipping tool caches."""
    script = tmp_path / "scripts" / "check.sh"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env bash\n")

    ignored_script = tmp_path / ".venv" / "bin" / "ignored.sh"
    ignored_script.parent.mkdir(parents=True)
    ignored_script.write_text("#!/usr/bin/env bash\n")

    assert shellcheck_targets(tmp_path) == [script]


def test_commands_include_shellcheck_when_shell_files_exist(tmp_path: Path) -> None:
    """Run shellcheck as part of the static checks when needed."""
    script = tmp_path / "scripts" / "check.sh"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env bash\n")

    assert commands(tmp_path, fix=False) == [
        ["ruff", "check", "."],
        ["ruff", "format", "--check", "."],
        ["mypy", "src", "tests"],
        ["shellcheck", "scripts/check.sh"],
    ]


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
