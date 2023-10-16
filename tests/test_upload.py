"""Upload tests."""

from pathlib import Path

import pytest
import pytest_socket  # type: ignore[import-untyped]
from click.testing import CliRunner
from music.__main__ import upload


def test_main_no_network_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that main network calls are blocked."""
    monkeypatch.setenv("SOUNDCLOUD_OAUTH_TOKEN", "stub-fake-token")
    some_paths = [
        tmp_path / "path" / "to" / "some project.wav",
        tmp_path / "path" / "to" / "another project.wav",
    ]
    for path in some_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f".wav content for {path.stem}")

    out = CliRunner(mix_stderr=False).invoke(
        upload, [str(path.resolve()) for path in some_paths]
    )

    assert isinstance(out.exception, pytest_socket.SocketBlockedError)
