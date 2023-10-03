"""Render tests."""

import datetime
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import syrupy
from click.testing import CliRunner
from music.__main__ import render
from music.render import RENDER_CMD_ID, RenderResult


def Track(name: str, params: list[mock.Mock] | None = None) -> mock.Mock:  # noqa: N802
    """Mock reapy's Track class."""
    rv = mock.Mock()
    rv.name = name
    rv.params = params if params else []
    return rv


@pytest.fixture
def parse_summary_stats() -> Iterator[mock.Mock]:
    """Stub parsing ffmpeg output. The test module does not run or test external commands."""
    with mock.patch("music.__codegen__.stats.parse_summary_stats") as parse:
        yield parse


@pytest.fixture
def project(
    parse_summary_stats: mock.Mock, snapshot: syrupy.SnapshotAssertion, tmp_path: Path
) -> Iterator[mock.Mock]:
    """Mock reapy's Project class.

    Stubs and occasionally fakes enough of a Project for coverage of this
    codebase, without actually interacting with Reaper.

    * Intercepts all the actions that would be taken by the render command.
        * Mostly returns stub output, ignoring the input.
        * The exception is after naming a render (via the "RENDER_PATTERN"
          action) and rendering, writes a fake file with the expected filename.
    * Sets up the expected FX that would be in a project.


    """
    threshold = mock.Mock()
    threshold.name = "Threshold"
    threshold.normalized = -42.0
    threshold.functions = {"SetParamNormalized": mock.Mock()}

    with (
        mock.patch("reapy.open_project") as mock_open_project,
        mock.patch("reapy.Project") as mock_project_class,
        mock.patch(
            "music.render.RenderResult.duration_delta", new_callable=mock.PropertyMock
        ) as mock_duration_delta,
    ):
        project = mock_open_project.return_value = mock_project_class.return_value

        render_patterns = []

        def collect_render_patterns(key: str, value: str) -> None:
            if key == "RENDER_PATTERN":
                render_patterns.append(value)

        def render_fake_file(cmd_id: int) -> None:
            if cmd_id == RENDER_CMD_ID:
                (project.path / f"{render_patterns[-1]}.wav").touch()

        project.name = "Stub Song Title"
        project.path = tmp_path

        project.master_track.fxs = [
            Track("ReaEQ"),
            Track("ReaXComp"),
            Track("Master Limiter", params=[threshold]),
        ]

        project.tracks = [Track(name="Vocals"), Track(name="Drums")]
        project.set_info_string.side_effect = collect_render_patterns
        project.perform_action.side_effect = render_fake_file
        parse_summary_stats.return_value = {"duration": 1.0, "size": 42.0}

        mock_duration_delta.return_value = datetime.timedelta(seconds=10)

        yield project

        assert mock_open_project.call_args_list == snapshot


@pytest.fixture
def subprocess(
    snapshot: syrupy.SnapshotAssertion, tmp_path: Path
) -> Iterator[mock.Mock]:
    """Stub subprocess.run.

    During unit tests, we don't want to actually run subprocesses. But we do
    want to check that the arguments passed are expected, and simulate
    subprocesses writing output files.
    """

    def write_out_file(*args: list[str | Path], **kwargs: Any) -> mock.Mock:
        rv = mock.Mock()
        cmd_args = args[0]

        if cmd_args[0] == "ffmpeg":
            rv.stderr = ""

            out_fil = Path(cmd_args[-1])
            out_fil.touch()

        return rv

    with mock.patch("subprocess.run") as mock_run:
        mock_run.side_effect = write_out_file
        yield mock_run

        assert mock_run.call_count
        assert mock_run.call_args_list == snapshot


@mock.patch("subprocess.run")
def test_render_result_render_speedup(subprocess: mock.Mock, tmp_path: Path) -> None:
    """Test RenderResult.render_speedup."""
    proc = mock.Mock()
    proc.stdout = """
    [FORMAT]
    duration=23.209501
    [/FORMAT]
    """
    subprocess.return_value = proc

    obj1 = RenderResult(tmp_path, datetime.timedelta(seconds=4.5))
    obj2 = RenderResult(tmp_path, datetime.timedelta(seconds=0.1))

    assert obj1.render_speedup == 5.75
    assert obj2.render_speedup == math.inf


def test_main_noop(project: mock.Mock, snapshot: syrupy.SnapshotAssertion) -> None:
    """Test a project with nothing to do.

    If a project has no vocals, it does not make sense to render its instrumental nor cappella.
    """
    project.tracks = [t for t in project.tracks if t.name != "Vocals"]

    result = CliRunner(mix_stderr=False).invoke(
        render, ["--include-instrumental", "--include-acappella"]
    )

    assert result.exit_code == 2
    assert not result.stdout
    assert result.stderr == snapshot

    assert project.method_calls == snapshot


def test_main_main_version(
    project: mock.Mock,
    snapshot: syrupy.SnapshotAssertion,
    subprocess: mock.Mock,
) -> None:
    """Test main with main version."""
    result = CliRunner(mix_stderr=False).invoke(render, ["--include-main"])

    assert result.stdout == snapshot
    assert not result.stderr

    assert project.method_calls == snapshot


def test_main_default_versions(
    project: mock.Mock,
    snapshot: syrupy.SnapshotAssertion,
    subprocess: mock.Mock,
) -> None:
    """Test main with default versions."""
    result = CliRunner(mix_stderr=False).invoke(render, [])

    assert result.stdout == snapshot
    assert not result.stderr

    assert project.method_calls == snapshot


def test_main_all_versions(
    project: mock.Mock,
    snapshot: syrupy.SnapshotAssertion,
    subprocess: mock.Mock,
) -> None:
    """Test main with all versions."""
    result = CliRunner(mix_stderr=False).invoke(
        render, ["--include-main", "--include-instrumental", "--include-acappella"]
    )

    assert result.stdout == snapshot
    assert not result.stderr

    assert project.method_calls == snapshot


def test_main_filenames_all_versions(
    project: mock.Mock,
    snapshot: syrupy.SnapshotAssertion,
    subprocess: mock.Mock,
    tmp_path: Path,
) -> None:
    """Test main with filenames and versions."""
    some_paths = [
        tmp_path / "path" / "to" / "some project",
        tmp_path / "path" / "to" / "another project",
    ]
    for path in some_paths:
        path.mkdir(parents=True)

    result = CliRunner(mix_stderr=False).invoke(
        render,
        [
            "--include-main",
            "--include-instrumental",
            "--include-acappella",
            *[str(path.resolve()) for path in some_paths],
        ],
    )

    assert result.stdout == snapshot
    assert not result.stderr

    assert project.method_calls == snapshot
