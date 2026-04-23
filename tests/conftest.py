"""pytest conventional configuration file."""

import dataclasses
import io
import re
import types
from collections.abc import AsyncIterable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import syrupy
from syrupy.assertion import SnapshotAssertion

from music.utils.http import ClientSession


@dataclasses.dataclass(kw_only=True)
class RequestsMocks:
    """Collection of all mocked HTTP requests."""

    get: mock.Mock
    post: mock.Mock
    put: mock.Mock
    put_file: mock.Mock

    @property
    def mock_calls(self) -> dict[str, Any]:
        """A dict of _all_ calls to this class's mock objects."""
        return {
            k.name: getattr(self, k.name).mock_calls for k in dataclasses.fields(self)
        }


def _is_dataclass_instance(data: Any) -> bool:
    return dataclasses.is_dataclass(data) and not isinstance(data, type)


@pytest.fixture(autouse=True)
def envvars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub environment variables, to avoid snapshotting secrets."""
    monkeypatch.setenv("SOUNDCLOUD_ADDITIONAL_HEADERS", "X-Test-Additional-Header: 1")
    monkeypatch.setenv("SOUNDCLOUD_OAUTH_TOKEN", "stub-fake-token")


@pytest.fixture
def snapshot(
    monkeypatch: pytest.MonkeyPatch, snapshot: SnapshotAssertion, tmp_path: Path
) -> SnapshotAssertion:
    """Override syrupy's snapshot fixture to be more deterministic.

    * Verbose class `__repr__`s can change between library versions, and we
      usually don't care about 3rd party internals.
    * Temporary paths can change between test runs.
    * In the case of console output, ensure no text wrapping occurs, so the
      regular expression matches.
    """
    monkeypatch.setattr("music.commands.render.command._CONSOLE_WIDTH", 999)

    tmp_path_str = str(tmp_path)
    tmp_id_re = re.compile(r"(?P<tmp_id>\s*\d+)(?P<ext>\.tmp)")

    def matcher(data: Any, path: Any) -> Any:
        if isinstance(data, ClientSession):
            return "CLIENT_SESSION_HERE"
        elif _is_dataclass_instance(data):
            return dataclasses.asdict(data)
        elif isinstance(data, AsyncIterable):
            return "ASYNC_ITERABLE_HERE"
        elif isinstance(data, types.FunctionType):
            return "CALLABLE_HERE"
        elif isinstance(data, Path | io.IOBase | str):
            without_tmp_id = tmp_id_re.sub(r"\g<ext>", str(data))
            without_path = without_tmp_id.replace(tmp_path_str, "TMP_PATH_HERE")
            return without_path
        return data

    class WithoutVerboseAndTmpPathExtension(
        syrupy.extensions.amber.AmberSnapshotExtension
    ):
        def serialize(self, data: syrupy.types.SerializableData, **kwargs: Any) -> str:
            """Override."""
            new_kwargs = kwargs | {"matcher": matcher}
            return super().serialize(data, **new_kwargs)

    return snapshot.use_extension(WithoutVerboseAndTmpPathExtension)


@pytest.fixture
def requests_mocks() -> Iterator[RequestsMocks]:
    """Fake the network calls made during upload."""

    def request_mock() -> mock.Mock:
        return mock.AsyncMock(return_value=mock.Mock(status_code=200))

    async def put_file(_url: str, fil: Path, *args: Any, **kwargs: Any) -> mock.Mock:
        progress = kwargs.get("progress")
        if progress:
            progress(fil.stat().st_size)
        return mock.Mock(status_code=200)

    with (
        mock.patch(
            "music.utils.http.ClientSession.get", new_callable=request_mock
        ) as get,
        mock.patch(
            "music.utils.http.ClientSession.post", new_callable=request_mock
        ) as post,
        mock.patch(
            "music.utils.http.ClientSession.put", new_callable=request_mock
        ) as put,
        mock.patch(
            "music.utils.http.ClientSession.put_file",
            new=mock.AsyncMock(side_effect=put_file),
        ) as put_file,
    ):
        yield RequestsMocks(get=get, post=post, put=put, put_file=put_file)
