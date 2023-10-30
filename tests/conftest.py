"""pytest conventional configuration file."""

import io
import re
from pathlib import Path
from typing import Any

import pytest
import syrupy
from syrupy.assertion import SnapshotAssertion


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
    """Override. Make syrupy's snapshot fixture strip temporary paths and tokens from any paths within a snapshot.

    In the case of console output, ensure no text wrapping occurs, so the
    regular expression matches.
    """
    monkeypatch.setattr("music.render._CONSOLE_WIDTH", 999)

    tmp_path_str = str(tmp_path)
    tmp_id_re = re.compile(r"(?P<tmp_id>\s*\d+)(?P<ext>\.tmp)")

    def without_tmp_path(data: Any, path: Any) -> Any:
        if isinstance(data, Path) or isinstance(data, io.IOBase):
            return str(data).replace(tmp_path_str, "TMP_PATH_HERE")
        elif isinstance(data, str):
            without_tmp_id = tmp_id_re.sub(r"\g<ext>", data)
            without_path = without_tmp_id.replace(tmp_path_str, "TMP_PATH_HERE")
            return without_path
        return data

    class WithoutTmpPathExtension(syrupy.extensions.amber.AmberSnapshotExtension):
        def serialize(self, data: syrupy.types.SerializableData, **kwargs: Any) -> str:
            """Override."""
            new_kwargs = kwargs | {"matcher": without_tmp_path}
            return super().serialize(data, **new_kwargs)

    return snapshot.use_extension(WithoutTmpPathExtension)
