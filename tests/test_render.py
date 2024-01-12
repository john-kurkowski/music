"""Render tests."""

import dataclasses
import datetime
import itertools
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from click.testing import CliRunner
from music.render.command import main as render
from music.render.process import RenderResult
from music.util import SongVersion
from syrupy.assertion import SnapshotAssertion


def Track(name: str, params: list[mock.Mock] | None = None) -> mock.Mock:  # noqa: N802
    """Mock reapy's Track class."""
    rv = mock.Mock()
    rv.name = name
    rv.params = params if params else []
    return rv


@pytest.fixture
def parse_summary_stats() -> Iterator[mock.Mock]:
    """Stub parsing ffmpeg output.

    The unit test module should not run or test external commands.
    """
    with mock.patch("music.__codegen__.stats.parse_summary_stats") as parse:
        yield parse


@dataclasses.dataclass(kw_only=True)
class RenderMocks:
    """Collection of all mocked classes and functions to render a song."""

    duration_delta: mock.Mock
    get_int_config_var: mock.Mock
    project: mock.Mock
    set_int_config_var: mock.Mock
    upload: mock.Mock

    @property
    def mock_calls(self) -> dict[str, Any]:
        """A dictionary of calls, methods, magic methods, and return value mocks made for each attribute of this class.

        See also unittest.mock.Mock.mock_calls.
        """
        return {
            k.name: getattr(self, k.name).mock_calls for k in dataclasses.fields(self)
        }


@pytest.fixture
def render_mocks(
    monkeypatch: pytest.MonkeyPatch, parse_summary_stats: mock.Mock, tmp_path: Path
) -> Iterator[RenderMocks]:
    """Mock reapy's Project class and global settings functions.

    Stubs and occasionally fakes enough of a Project for coverage of this
    codebase, without actually interacting with Reaper.

    * Intercepts all the actions that would be taken by the render command.
        * Mostly returns stub output, ignoring the input.
        * The exception is after naming a render (via the "RENDER_PATTERN"
          action) and rendering, writes a fake file with the expected filename.
    * Sets up the expected FX that would be in a project.
    """
    monkeypatch.setenv("SOUNDCLOUD_OAUTH_TOKEN", "stub-fake-token")

    threshold = mock.Mock()
    threshold.name = "Threshold"
    threshold.normalized = -42.0
    threshold.functions = {"SetParamNormalized": mock.Mock()}

    with (
        mock.patch("music.util.ExtendedProject") as mock_project_class,
        mock.patch(
            "music.render.process.RenderResult.duration_delta",
            new_callable=mock.PropertyMock,
        ) as mock_duration_delta,
        mock.patch(
            "reapy.reascript_api.SNM_GetIntConfigVar", create=True
        ) as mock_get_int_config_var,
        mock.patch(
            "reapy.reascript_api.SNM_SetIntConfigVar", create=True
        ) as mock_set_int_config_var,
        mock.patch("music.upload.process.Process.process") as mock_upload,
    ):
        project = (
            mock_project_class.get_or_open.return_value
        ) = mock_project_class.return_value

        render_patterns = []

        def collect_render_patterns(key: str, value: str) -> None:
            if key == "RENDER_PATTERN":
                render_patterns.append(value)

        async def render_fake_file() -> None:
            (Path(project.path) / f"{render_patterns[-1]}.wav").touch()

        path = tmp_path / "Stub Song Title (feat. Stub Artist)"
        path.mkdir()
        project.path = str(path)

        project.master_track.fxs = [
            Track("ReaEQ"),
            Track("ReaXComp"),
            Track("Master Limiter", params=[threshold]),
        ]

        project.tracks = [Track(name="Vocals"), Track(name="Drums")]
        project.set_info_string.side_effect = collect_render_patterns
        project.render.side_effect = render_fake_file
        parse_summary_stats.side_effect = itertools.cycle(
            [
                {"duration": 1.0, "size": 42.0},
                {"duration": 250.1, "size": 1024},
            ]
        )

        mock_duration_delta.return_value = datetime.timedelta(seconds=10)

        def get_int_config_var(key: str, _: int) -> int:
            if key == "offlineinact":
                return 0
            return 999

        mock_get_int_config_var.side_effect = get_int_config_var

        yield RenderMocks(
            duration_delta=mock_duration_delta,
            get_int_config_var=mock_get_int_config_var,
            project=project,
            set_int_config_var=mock_set_int_config_var,
            upload=mock_upload,
        )


@pytest.fixture
def subprocess() -> Iterator[mock.Mock]:
    """Stub subprocess.run.

    The unit test module should not run or test external commands.
    """
    with mock.patch("subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def subprocess_with_output(
    snapshot: SnapshotAssertion, subprocess: mock.Mock, tmp_path: Path
) -> Iterator[mock.Mock]:
    """Stub subprocess.run and simulate subprocesses writing output files."""

    def write_out_file(*args: list[str | Path], **kwargs: Any) -> mock.Mock:
        rv = mock.Mock()
        cmd_args = args[0]

        if cmd_args[0] == "ffmpeg":
            rv.stderr = ""

            out_fil = Path(cmd_args[-1])
            out_fil.touch()

        return rv

    subprocess.side_effect = write_out_file
    yield subprocess


def test_render_result_render_speedup(
    snapshot: SnapshotAssertion, subprocess: mock.Mock, tmp_path: Path
) -> None:
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

    assert subprocess.call_count
    assert subprocess.call_args_list == snapshot


@mock.patch("reapy.reascript_api.SNM_GetIntConfigVar", create=True)
def test_main_reaper_not_configured(
    mock_get_int_config_var: mock.Mock,
    render_mocks: RenderMocks,
) -> None:
    """Test command handling when Reaper is not configured correctly for render."""
    mock_get_int_config_var.return_value = 1
    result = CliRunner().invoke(render, catch_exceptions=False)
    assert result.exit_code == 2
    assert "media items offline" in result.output


def test_main_noop(render_mocks: RenderMocks, snapshot: SnapshotAssertion) -> None:
    """Test a project with nothing to do.

    If a project has no vocals, it does not make sense to render its instrumental nor cappella.
    """
    render_mocks.project.tracks = [
        t for t in render_mocks.project.tracks if t.name != "Vocals"
    ]

    result = CliRunner(mix_stderr=False).invoke(
        render,
        ["--include-instrumental", "--include-acappella"],
        catch_exceptions=False,
    )

    assert result.exit_code == 2
    assert not result.stdout
    assert result.stderr == snapshot

    assert render_mocks.project.method_calls == snapshot


def test_main_main_version(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main with main version."""
    result = CliRunner(mix_stderr=False).invoke(
        render, ["--include-main"], catch_exceptions=False
    )

    assert not result.exception
    assert result.stdout == snapshot
    assert not result.stderr

    assert render_mocks.project.method_calls == snapshot
    assert subprocess_with_output.call_count
    assert subprocess_with_output.call_args_list == snapshot


def test_main_default_versions(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main with default versions."""
    result = CliRunner(mix_stderr=False).invoke(render, [], catch_exceptions=False)

    assert not result.exception
    assert result.stdout == snapshot
    assert not result.stderr

    assert render_mocks.project.method_calls == snapshot
    assert subprocess_with_output.call_count
    assert subprocess_with_output.call_args_list == snapshot


def test_main_all_versions(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main with all versions."""
    result = CliRunner(mix_stderr=False).invoke(
        render,
        ["--include-main", "--include-instrumental", "--include-acappella"],
        catch_exceptions=False,
    )

    assert not result.exception
    assert result.stdout == snapshot
    assert not result.stderr

    assert render_mocks.project.method_calls == snapshot
    assert subprocess_with_output.call_count
    assert subprocess_with_output.call_args_list == snapshot


def test_main_filenames_all_versions(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
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
        catch_exceptions=False,
    )

    assert not result.exception
    assert result.stdout == snapshot
    assert not result.stderr

    assert render_mocks.project.method_calls == snapshot
    assert subprocess_with_output.call_count
    assert subprocess_with_output.call_args_list == snapshot


def test_main_mocked_calls(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
    tmp_path: Path,
) -> None:
    """Test main to verify mocked calls.

    Test a maximal mix of CLI options.

    This is useful to test features that _only_ exercise mocked calls, for
    example toggling a global Reaper preference, or HTTP upload. It would be
    noisy to snapshot all mocked calls in every test case. So keep this test
    case snapshot assertion separate.
    """
    some_paths = [Path(render_mocks.project.path)]

    some_unspecified_file = SongVersion.INSTRUMENTAL.path_for_project_dir(
        Path(render_mocks.project.path)
    )
    some_unspecified_file.touch()

    result = CliRunner(mix_stderr=False).invoke(
        render,
        [
            "--include-main",
            "--upload",
            "--upload-existing",
            *[str(path.resolve()) for path in some_paths],
        ],
        catch_exceptions=False,
    )

    assert not result.exception
    assert result.stdout == snapshot
    assert not result.stderr

    assert render_mocks.mock_calls == snapshot
