"""Tag and encode tests."""

from pathlib import Path
from unittest import mock

from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from music.tag.command import main as tag


@mock.patch("subprocess.check_call")
def test_main(
    mock_subprocess: mock.Mock, snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test main calls the expected subprocess."""
    some_path = (
        tmp_path / "path" / "to" / "Album Title Here" / "01 - Song Title Here.wav"
    )
    some_path.parent.mkdir(parents=True, exist_ok=True)
    some_path.touch()

    result = CliRunner(mix_stderr=False).invoke(
        tag, [str(some_path)], catch_exceptions=False
    )

    assert (
        result.stderr,
        result.exception,
        result.stdout,
        mock_subprocess.mock_calls,
    ) == snapshot
