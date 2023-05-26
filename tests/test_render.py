"""Render tests."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import click
import pytest
import syrupy
from music.render import RENDER_CMD_ID, SongVersion, main


@pytest.fixture
def parse_summary_stats() -> Iterator[mock.Mock]:
    with mock.patch("music.__codegen__.stats.parse_summary_stats") as parse:
        yield parse


@pytest.fixture
def project(tmp_path: Path) -> Iterator[mock.Mock]:
    with mock.patch("reapy.Project") as mock_project_class:
        project = mock_project_class.return_value
        project.name = "Song of Myself"
        project.path = tmp_path
        yield project


@pytest.fixture
def subprocess(
    snapshot: syrupy.SnapshotAssertion, tmp_path: Path
) -> Iterator[mock.Mock]:
    """Stub subprocess.run.

    During unit tests, we don't want to actually run subprocesses. But we do
    want to check that the arguments passed are expected.
    """
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value.stderr = ""
        yield mock_run

        assert mock_run.call_count
        assert mock_run.call_args_list == snapshot(matcher=without_tmp_path(tmp_path))


def without_tmp_path(tmp_path: Path) -> syrupy.types.PropertyMatcher:
    """Strip temporary paths and tokens from any paths in the snapshot."""
    tmp_path_str = str(tmp_path)
    tmp_id_re = re.compile(r"(?P<tmp_id>\s*\d+)(?P<ext>\.tmp)")

    def matcher(data: Any, path: Any) -> Any:
        if isinstance(data, Path):
            return str(data).replace(tmp_path_str, "TMP_PATH_HERE")
        elif isinstance(data, str):
            without_tmp_id = tmp_id_re.sub(r"\g<ext>", data)
            without_path = without_tmp_id.replace(tmp_path_str, "TMP_PATH_HERE")
            return without_path
        return data

    return matcher


def test_main_noop(project: mock.Mock) -> None:
    with pytest.raises(click.UsageError, match="nothing"):
        main({})


def test_main_main_version(
    capsys: pytest.CaptureFixture,
    parse_summary_stats: mock.Mock,
    project: mock.Mock,
    snapshot: syrupy.SnapshotAssertion,
    subprocess: mock.Mock,
    tmp_path: Path,
) -> None:
    render_patterns = []

    def collect_render_patterns(key: str, value: str) -> None:
        if key == "RENDER_PATTERN":
            render_patterns.append(value)

    def render_fake_file(cmd_id: int) -> None:
        if cmd_id == RENDER_CMD_ID:
            (project.path / f"{render_patterns[0]}.wav").touch()

    project.set_info_string.side_effect = collect_render_patterns
    project.perform_action.side_effect = render_fake_file
    parse_summary_stats.return_value = {"duration": 1.0, "size": 42.0}

    main({SongVersion.MAIN})

    out, err = capsys.readouterr()

    assert out == snapshot(matcher=without_tmp_path(tmp_path))
    assert not err

    assert project.method_calls == snapshot(matcher=without_tmp_path(tmp_path))