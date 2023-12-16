"""CLI entry point tests."""

from click.testing import CliRunner
from music.__main__ import cli
from syrupy.assertion import SnapshotAssertion


def test_help(snapshot: SnapshotAssertion) -> None:
    """Test help message lists available commands."""
    result = CliRunner(mix_stderr=False).invoke(cli, catch_exceptions=False)

    assert not result.stderr
    assert not result.exception
    assert result.stdout == snapshot
