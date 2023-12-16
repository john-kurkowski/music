"""Upload tests."""

import dataclasses
import datetime
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import pytest_socket  # type: ignore[import-untyped]
from click.testing import CliRunner
from music.upload.command import main as upload
from syrupy.assertion import SnapshotAssertion


@dataclasses.dataclass(kw_only=True)
class RequestsMocks:
    """Collection of all mocked python-requests functions to upload a song."""

    get: mock.Mock
    post: mock.Mock
    put: mock.Mock

    @property
    def mock_calls(self) -> dict[str, Any]:
        """A dictionary of calls, methods, magic methods, and return value mocks made for each attribute of this class.

        See also unittest.mock.Mock.mock_calls.
        """
        return {
            k.name: getattr(self, k.name).mock_calls for k in dataclasses.fields(self)
        }


@pytest.fixture
def requests_mocks() -> Iterator[RequestsMocks]:
    """Fake the network calls made during upload."""
    with (
        mock.patch("aiohttp.ClientSession.get", new_callable=mock.AsyncMock) as get,
        mock.patch("aiohttp.ClientSession.post", new_callable=mock.AsyncMock) as post,
        mock.patch("aiohttp.ClientSession.put", new_callable=mock.AsyncMock) as put,
    ):
        yield RequestsMocks(get=get, post=post, put=put)


@pytest.fixture
def some_paths(tmp_path: Path) -> list[Path]:
    """Create some files to upload."""
    some_paths = [
        tmp_path / "path" / "to" / "some project" / "some project.wav",
        tmp_path / "path" / "to" / "another project" / "another project.wav",
    ]
    for path in some_paths:
        path.parent.mkdir(parents=True)
        path.write_text(f".wav content for {path.stem}")

    return some_paths


@pytest.fixture(autouse=True)
def envvars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub environment variables, to avoid snapshotting secrets."""
    monkeypatch.setenv("SOUNDCLOUD_OAUTH_TOKEN", "stub-fake-token")


def test_main_no_network_calls(some_paths: list[Path]) -> None:
    """Test that main network calls are blocked."""
    with pytest.raises(pytest_socket.SocketConnectBlockedError):
        CliRunner(mix_stderr=False).invoke(
            upload,
            [str(path.parent.resolve()) for path in some_paths],
            catch_exceptions=False,
        )


def test_main_tracks_not_found(
    requests_mocks: RequestsMocks, snapshot: SnapshotAssertion, some_paths: list[Path]
) -> None:
    """Test main when tracks are not found/matched in the upstream database."""
    result = CliRunner(mix_stderr=False).invoke(
        upload,
        [str(path.parent.resolve()) for path in some_paths],
    )

    assert result.exception == snapshot
    assert not result.stdout
    assert not result.stderr

    assert requests_mocks.mock_calls == snapshot


def test_main_tracks_newer(
    requests_mocks: RequestsMocks,
    snapshot: SnapshotAssertion,
    some_paths: list[Path],
) -> None:
    """Test main when tracks are newer in the upstream database, and skipped.

    Stubs enough of the local filesystem and upstream responses for timestamps
    to be checked.
    """
    old_timestamp = "2020-10-01T00:00:00Z"
    new_timestamp = "2021-10-01T00:00:00Z"

    original_stat = Path.stat

    def mock_stat(self: Path, *args: Any, **kwargs: Any) -> Any:
        """Mock `Path.stat()` to return a timestamp for some paths under test.

        Other paths use `Path.stat()`'s default implementation.
        """
        if self in some_paths:
            return mock.Mock(
                st_mtime=datetime.datetime.fromisoformat(old_timestamp).timestamp()
            )

        return original_stat(self, *args, **kwargs)

    def mock_get(url: str, *args: Any, **kwargs: Any) -> mock.Mock:
        if re.search(r"^https://api-v2.soundcloud.com/users/.*/tracks", url):
            return mock.Mock(
                json=mock.AsyncMock(
                    return_value={
                        "collection": [
                            {
                                "id": 1,
                                "last_modified": new_timestamp,
                                "title": "some project",
                                "permalink_url": "https://soundcloud.com/1",
                            },
                            {
                                "id": 2,
                                "last_modified": new_timestamp,
                                "title": "another project",
                                "permalink_url": "https://soundcloud.com/2",
                            },
                        ]
                    }
                )
            )

        return mock.Mock()

    requests_mocks.get.side_effect = mock_get
    with mock.patch.object(Path, "stat", autospec=True, side_effect=mock_stat):
        result = CliRunner(mix_stderr=False).invoke(
            upload,
            [str(path.parent.resolve()) for path in some_paths],
            catch_exceptions=False,
        )

    assert not result.exception
    assert result.stdout == snapshot
    assert not result.stderr

    assert requests_mocks.mock_calls == snapshot


def test_main_success(
    requests_mocks: RequestsMocks, snapshot: SnapshotAssertion, some_paths: list[Path]
) -> None:
    """Test main with multiple files succeeds.

    Stubs enough of responses for the sequence of API requests to complete.
    """
    new_timestamp = "2021-10-01T00:00:00Z"

    def mock_get(url: str, *args: Any, **kwargs: Any) -> mock.Mock:
        if re.search(r"^https://api-v2.soundcloud.com/users/.*/tracks", url):
            return mock.Mock(
                json=mock.AsyncMock(
                    return_value={
                        "collection": [
                            {
                                "id": 1,
                                "last_modified": new_timestamp,
                                "title": "some project",
                                "permalink_url": "https://soundcloud.com/1",
                            },
                            {
                                "id": 2,
                                "last_modified": new_timestamp,
                                "title": "another project",
                                "permalink_url": "https://soundcloud.com/2",
                            },
                        ]
                    }
                )
            )
        elif re.search(
            r"^https://api-v2.soundcloud.com/uploads/.*/track-transcoding", url
        ):
            return mock.Mock(
                json=mock.AsyncMock(
                    return_value={
                        "status": "finished",
                    }
                )
            )

        return mock.Mock()

    def mock_post(url: str, *args: Any, **kwargs: Any) -> mock.Mock:
        if re.search(
            r"^https://api-v2.soundcloud.com/uploads/track-upload-policy", url
        ):
            return mock.Mock(
                json=mock.AsyncMock(
                    return_value={
                        "headers": {"some-uploader-id": "some-uploader-value"},
                        "url": "https://some-url",
                        "uid": "stub-uid",
                    }
                )
            )

        return mock.Mock()

    requests_mocks.get.side_effect = mock_get
    requests_mocks.post.side_effect = mock_post

    result = CliRunner(mix_stderr=False).invoke(
        upload,
        [str(path.parent.resolve()) for path in some_paths],
        catch_exceptions=False,
    )

    assert not result.exception
    assert result.stdout == snapshot
    assert not result.stderr

    assert requests_mocks.mock_calls == snapshot
