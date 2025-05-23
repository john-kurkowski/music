"""Render tests."""

import datetime
import math
from pathlib import Path
from typing import Any
from unittest import mock

from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from music.render.command import main as render
from music.render.result import RenderResult
from music.util import SongVersion

from .conftest import RenderMocks


def test_render_result_render_speedup(
    snapshot: SnapshotAssertion, subprocess: mock.Mock, tmp_path: Path
) -> None:
    """Test RenderResult.render_speedup."""
    subprocess.return_value.stdout = """
    [FORMAT]
    duration=23.209501
    [/FORMAT]
    """
    project = mock.Mock(path="some/path")
    version = mock.Mock()

    some_file = tmp_path / "foo.wav"
    some_file.touch()

    obj1 = RenderResult(project, version, some_file, datetime.timedelta(seconds=4.5))
    obj2 = RenderResult(project, version, some_file, datetime.timedelta(seconds=0.1))

    assert obj1.render_speedup == 5.75
    assert obj2.render_speedup == math.inf

    assert subprocess.mock_calls
    assert subprocess.mock_calls == snapshot


def test_main_reaper_not_configured(
    render_mocks: RenderMocks,
) -> None:
    """Test command handling when Reaper is not configured correctly for render."""
    render_mocks.get_int_config_var.reset_mock(return_value=True, side_effect=True)
    render_mocks.get_int_config_var.return_value = 1
    result = CliRunner(catch_exceptions=False).invoke(render)
    assert result.exit_code == 2
    assert "media items offline" in result.output


def test_main_noop(render_mocks: RenderMocks, snapshot: SnapshotAssertion) -> None:
    """Test a project with nothing to do.

    If a project has no vocals, it does not make sense to render its instrumental nor cappella.
    """
    render_mocks.project.tracks = [
        t
        for t in render_mocks.project.tracks
        if t.name != "Vocals" and "(vox)" not in t.name.lower()
    ]

    result = CliRunner(catch_exceptions=False).invoke(
        render,
        ["--include-instrumental", "--include-instrumental-dj", "--include-acappella"],
    )

    assert (
        result.exit_code,
        result.stdout,
        result.stderr,
        render_mocks.project.mock_calls,
    ) == snapshot


def test_main_main_version(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main with main version."""
    result = CliRunner(catch_exceptions=False).invoke(
        render,
        ["--include-main"],
    )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        render_mocks.project.mock_calls,
        subprocess_with_output.mock_calls,
    ) == snapshot


def test_main_default_versions(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main with default versions."""
    result = CliRunner(catch_exceptions=False).invoke(render, [])

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        render_mocks.project.mock_calls,
        subprocess_with_output.mock_calls,
    ) == snapshot


def test_main_default_versions_dry_run(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main dry run, with default versions."""
    result = CliRunner(catch_exceptions=False).invoke(
        render,
        ["--dry-run"],
    )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        render_mocks.project.mock_calls,
        subprocess_with_output.mock_calls,
    ) == snapshot


def test_main_instrumental_versions_only_main_vocals(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main with 2 instrumental versions.

    With only a main vocal track, only 1 instrumental version should render.
    Otherwise the versions would be identical.

    Other tests in this suite cover rendering 2 instrumental versions.
    """
    render_mocks.project.tracks = [
        t for t in render_mocks.project.tracks if "(vox)" not in t.name.lower()
    ]

    result = CliRunner(catch_exceptions=False).invoke(
        render,
        ["--include-instrumental", "--include-instrumental-dj"],
    )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        render_mocks.project.mock_calls,
        subprocess_with_output.mock_calls,
    ) == snapshot


def test_main_all_versions(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main with all versions."""
    result = CliRunner(catch_exceptions=False).invoke(
        render,
        [
            "--include-main",
            "--include-instrumental",
            "--include-instrumental-dj",
            "--include-acappella",
            "--include-stems",
        ],
    )

    assert not result.exception
    assert result.stdout == snapshot
    assert not result.stderr

    assert render_mocks.project.mock_calls == snapshot
    assert subprocess_with_output.mock_calls
    assert subprocess_with_output.mock_calls == snapshot


def test_main_mixed_errors(
    render_mocks: RenderMocks,
    snapshot: SnapshotAssertion,
    subprocess_with_output: mock.Mock,
) -> None:
    """Test main with the first 2 versions succeeding and the last 1 failing."""
    original_render = render_mocks.project.render.side_effect
    render_count = 0

    async def render_with_error(*args: Any, **kwargs: Any) -> Any:
        nonlocal render_count
        render_count += 1
        if render_count >= 3:
            raise RuntimeError("some error")

        return await original_render(*args, **kwargs)

    render_mocks.project.render.side_effect = render_with_error

    result = CliRunner(catch_exceptions=True).invoke(
        render,
        [
            "--include-main",
            "--include-instrumental",
            "--include-acappella",
        ],
    )

    assert result.exception == snapshot
    assert result.stdout == snapshot
    assert not result.stderr

    assert render_mocks.project.mock_calls == snapshot
    assert subprocess_with_output.mock_calls
    assert subprocess_with_output.mock_calls == snapshot


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

    result = CliRunner(catch_exceptions=False).invoke(
        render,
        [
            "--include-main",
            "--include-instrumental",
            "--include-instrumental-dj",
            "--include-acappella",
            "--include-stems",
            *[str(path.resolve()) for path in some_paths],
        ],
    )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        render_mocks.project.mock_calls,
        subprocess_with_output.mock_calls,
    ) == snapshot


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

    result = CliRunner(catch_exceptions=False).invoke(
        render,
        [
            "--exit",
            "--include-main",
            "--upload",
            "--upload-existing",
            *[str(path.resolve()) for path in some_paths],
        ],
    )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        render_mocks.mock_calls,
    ) == snapshot
