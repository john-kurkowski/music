"""Stat command tests."""

from pathlib import Path
from unittest import mock

from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from music.commands.stat.command import main as stat


@mock.patch("music.commands.render.result.summary_stats_for_file")
def test_main_files(
    mock_stats_for_file: mock.Mock, snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test main calls the expected subprocess per file."""
    mock_stats_for_file.return_value = {"some": "stat"}

    some_paths = [
        tmp_path / "path" / "to" / "Album Title Here" / "01 - Song Title Here.wav",
        tmp_path / "path" / "to" / "Album Title Here" / "02 - Song Title Here.wav",
    ]
    for path in some_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    result = CliRunner(catch_exceptions=False).invoke(
        stat, [str(path) for path in some_paths]
    )

    assert (
        result.stderr,
        result.exception,
        result.stdout,
        mock_stats_for_file.mock_calls,
    ) == snapshot


@mock.patch("music.commands.render.result.summary_stats_for_file")
@mock.patch("music.utils.project.ExtendedProject", autospec=True)
def test_main_no_args(
    mock_project: mock.Mock,
    mock_stats_for_file: mock.Mock,
    snapshot: SnapshotAssertion,
    tmp_path: Path,
) -> None:
    """Test main calls the expected subprocess per project directory file."""
    mock_stats_for_file.return_value = {"some": "stat"}

    project_name = "Song Title Here"
    project_dir = tmp_path / "path" / "to" / project_name
    mock_project.return_value.path = project_dir

    some_paths = [
        project_dir / f"{project_name}.wav",
        project_dir / f"{project_name} (A Cappella).wav",
        project_dir / "another file.wav",
    ]
    for path in some_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    result = CliRunner(catch_exceptions=False).invoke(stat)

    assert (
        result.stderr,
        result.exception,
        result.stdout,
        mock_project.mock_calls,
        mock_stats_for_file.mock_calls,
    ) == snapshot
