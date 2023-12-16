"""Tag and encode tests."""

from pathlib import Path
from unittest import mock

from click.testing import CliRunner
from music.tag.command import main as tag
from syrupy.assertion import SnapshotAssertion


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

    assert not result.stderr
    assert not result.exception
    assert result.stdout == snapshot

    assert mock_subprocess.call_args == snapshot
