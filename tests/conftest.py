"""pytest conventional configuration file."""

import dataclasses
import io
import re
from collections.abc import AsyncIterable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import aiohttp
import pytest
import syrupy
from syrupy.assertion import SnapshotAssertion


@dataclasses.dataclass(kw_only=True)
class RequestsMocks:
    """Collection of all mocked HTTP requests."""

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


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Block all external socket connections by default.

    Allows asyncio, local socket connections. H/T https://github.com/pytest-dev/pytest-asyncio/issues/160
    """
    for item in items:
        item.add_marker(pytest.mark.allow_hosts(["127.0.0.1", "::1"]))


@pytest.fixture
def snapshot(
    monkeypatch: pytest.MonkeyPatch, snapshot: SnapshotAssertion, tmp_path: Path
) -> SnapshotAssertion:
    """Override. Make syrupy's snapshot fixture strip verbose class `__repr__`s, temporary paths, and temporary tokens from any paths within a snapshot.

    Verbose class `__repr__`s can change between library versions, and we
    usually don't care about 3rd party internals.

    Temporary paths can change between test runs.

    In the case of console output, ensure no text wrapping occurs, so the
    regular expression matches.
    """
    monkeypatch.setattr("music.render.command._CONSOLE_WIDTH", 999)

    tmp_path_str = str(tmp_path)
    tmp_id_re = re.compile(r"(?P<tmp_id>\s*\d+)(?P<ext>\.tmp)")

    def matcher(data: Any, path: Any) -> Any:
        if isinstance(data, aiohttp.ClientSession):
            return "CLIENT_SESSION_HERE"
        elif isinstance(data, AsyncIterable):
            return "ASYNC_ITERABLE_HERE"
        elif isinstance(data, Path) or isinstance(data, io.IOBase):
            return str(data).replace(tmp_path_str, "TMP_PATH_HERE")
        elif isinstance(data, str):
            without_tmp_id = tmp_id_re.sub(r"\g<ext>", data)
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
        return mock.AsyncMock(return_value=mock.Mock(spec=aiohttp.ClientResponse))

    with (
        mock.patch("aiohttp.ClientSession.get", new_callable=request_mock) as get,
        mock.patch("aiohttp.ClientSession.post", new_callable=request_mock) as post,
        mock.patch("aiohttp.ClientSession.put", new_callable=request_mock) as put,
    ):
        yield RequestsMocks(get=get, post=post, put=put)
