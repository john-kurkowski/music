"""Upload tests."""

import datetime
import re
from pathlib import Path
from typing import Any
from unittest import mock

import aiohttp
import multidict
import pytest
import pytest_socket  # type: ignore[import-untyped]
import yarl
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from music.upload.command import main as upload

from .conftest import RequestsMocks

ST_MODE_IS_FILE = 33188


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


def test_main_no_network_calls(some_paths: list[Path]) -> None:
    """Test that main network calls are blocked."""
    with pytest.raises(pytest_socket.SocketBlockedError):
        CliRunner(catch_exceptions=False).invoke(
            upload,
            [str(path.parent.resolve()) for path in some_paths],
        )


def test_main_tracks_not_found(
    requests_mocks: RequestsMocks, snapshot: SnapshotAssertion, some_paths: list[Path]
) -> None:
    """Test main when tracks are not found/matched in the upstream database."""
    result = CliRunner(catch_exceptions=False).invoke(
        upload,
        [str(path.parent.resolve()) for path in some_paths],
    )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        requests_mocks.mock_calls,
    ) == snapshot


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
                st_mode=ST_MODE_IS_FILE,
                st_mtime=datetime.datetime.fromisoformat(old_timestamp).timestamp(),
                st_size=1_234_567,
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
        result = CliRunner(catch_exceptions=False).invoke(
            upload,
            [str(path.parent.resolve()) for path in some_paths],
        )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        requests_mocks.mock_calls,
    ) == snapshot


def test_main_success(
    requests_mocks: RequestsMocks, snapshot: SnapshotAssertion, some_paths: list[Path]
) -> None:
    """Test main with multiple files succeeds.

    Stubs enough of responses for the sequence of API requests to complete (in success).
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

    result = CliRunner(catch_exceptions=False).invoke(
        upload,
        [str(path.parent.resolve()) for path in some_paths],
    )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        requests_mocks.mock_calls,
    ) == snapshot


def test_main_transcode_failure(
    requests_mocks: RequestsMocks, snapshot: SnapshotAssertion, some_paths: list[Path]
) -> None:
    """Test main with transcode failure shows error in progress indicator.

    Stubs enough of responses for the sequence of API requests to complete (in failure).
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
                        ]
                    }
                )
            )
        elif re.search(
            r"^https://api-v2.soundcloud.com/uploads/.*/track-transcoding", url
        ):
            # Simulate transcode failure with an HTTP error
            request_info = aiohttp.RequestInfo(
                url=yarl.URL(url),
                method="GET",
                headers=multidict.CIMultiDictProxy(multidict.CIMultiDict()),
                real_url=yarl.URL(url),
            )

            error_response = mock.Mock()
            error_response.ok = False
            error_response.status = 422
            error_response.text = mock.AsyncMock(
                return_value="Transcoding failed: Invalid audio format"
            )
            error_response.raise_for_status = mock.Mock(
                side_effect=aiohttp.ClientResponseError(
                    request_info=request_info,
                    history=(),
                    status=422,
                    message="Unprocessable Entity",
                )
            )
            return error_response

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

    result = CliRunner(catch_exceptions=True).invoke(
        upload,
        [str(some_paths[0].parent.resolve())],
    )

    assert (
        result.exception,
        result.stdout,
        result.stderr,
        requests_mocks.mock_calls,
    ) == snapshot
