#!/usr/bin/env python

"""Static checks for local development and CI."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse CLI flags."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply fixes with tools that support autofixing.",
    )
    return parser.parse_args()


def repo_root(cwd: Path) -> Path:
    """Find the repository root from the current working directory."""
    for path in [cwd, *cwd.parents]:
        if (path / "pyproject.toml").is_file():
            return path

    msg = "Could not find pyproject.toml from the current directory"
    raise FileNotFoundError(msg)


def commands(root: Path, *, fix: bool) -> list[list[str]]:
    """Build the static check commands for the repo."""
    return [
        ["ruff", "check", "--fix", "."] if fix else ["ruff", "check", "."],
        ["ruff", "format", "."] if fix else ["ruff", "format", "--check", "."],
        ["mypy", "src", "tests"],
        ["ty", "check", "src", "tests"],
    ]


def run_commands(root: Path, checks: Iterable[Sequence[str]]) -> None:
    """Run each check from the repository root."""
    for command in checks:
        print("+", " ".join(command))
        subprocess.run(command, check=True, cwd=root)


def main() -> None:
    """Run all static checks."""
    args = parse_args()
    root = repo_root(Path.cwd())
    run_commands(root, commands(root, fix=args.fix))


if __name__ == "__main__":  # pragma: no cover
    main()
