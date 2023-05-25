"""CLI tests."""

from unittest import mock

from click.testing import CliRunner
from music.__main__ import cli


@mock.patch("reapy.Project")
def test_reaper_not_running(project: mock.Mock) -> None:
    project.side_effect = AttributeError("module doesn't have reascript_api, yo")
    result = CliRunner().invoke(cli, ["render"])
    assert result.exit_code == 1
    assert not result.output
    assert "Reaper running" in str(result.exception)
