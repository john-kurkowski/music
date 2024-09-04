"""pytest conventional file, for render helpers."""

import dataclasses
import datetime
import itertools
import warnings
from collections.abc import Collection, Iterator
from pathlib import Path
from typing import Any, cast
from unittest import mock

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

import pytest


def Fx(name: str, params: Collection[mock.Mock] = ()) -> mock.Mock:  # noqa: N802
    """Mock reapy's Fx class."""
    rv = mock.create_autospec(reapy.core.FX)
    rv.name = name
    rv.params = params
    return cast(mock.Mock, rv)


def Track(name: str, params: Collection[mock.Mock] = ()) -> mock.Mock:  # noqa: N802
    """Mock reapy's Track class."""
    rv = mock.create_autospec(reapy.core.Track)
    rv.name = name
    rv.params = params
    rv.is_muted = False
    rv.parent_track = None
    return cast(mock.Mock, rv)


@dataclasses.dataclass(kw_only=True)
class RenderMocks:
    """Collection of all mocked objects to render a song."""

    duration_delta: mock.Mock
    get_int_config_var: mock.Mock
    project: mock.Mock
    set_int_config_var: mock.Mock
    upload: mock.Mock

    @property
    def mock_calls(self) -> dict[str, Any]:
        """A dict of _all_ calls to this class's mock objects."""
        return {
            k.name: getattr(self, k.name).mock_calls for k in dataclasses.fields(self)
        }


@pytest.fixture
def render_mocks(tmp_path: Path) -> Iterator[RenderMocks]:
    """Mock reapy's Project class and global settings functions.

    Stubs and occasionally fakes enough of a Project for coverage of this
    codebase, without actually interacting with Reaper.

    * Intercepts all the actions that would be taken by the render command.
        * Mostly returns stub output, ignoring the input.
        * The exception is after naming a render (via the "RENDER_PATTERN"
          action) and rendering, writes a fake file with the expected filename.
    * Sets up the expected FX that would be in a project.
    """
    threshold = mock.create_autospec(reapy.core.FXParam)
    threshold.name = "Threshold"
    threshold.normalized = -42.0
    threshold.functions = {"SetParamNormalized": mock.Mock()}
    threshold.index = 0
    threshold.parent_list = mock.create_autospec(reapy.core.FXParamsList)

    with (
        mock.patch(
            "music.__codegen__.stats.parse_summary_stats"
        ) as mock_parse_summary_stats,
        mock.patch("music.util.ExtendedProject") as mock_project_class,
        mock.patch(
            "music.render.process.RenderResult.duration_delta",
            new_callable=mock.PropertyMock,
        ) as mock_duration_delta,
        mock.patch(
            "reapy.reascript_api.SNM_GetIntConfigVar", create=True
        ) as mock_get_int_config_var,
        mock.patch(
            "reapy.reascript_api.SNM_SetIntConfigVar", create=True
        ) as mock_set_int_config_var,
        mock.patch("music.upload.process.Process.process") as mock_upload,
    ):
        project = mock_project_class.get_or_open.return_value = (
            mock_project_class.return_value
        )

        render_patterns = []

        def collect_render_patterns(key: str, value: str) -> None:
            if key == "RENDER_PATTERN":
                render_patterns.append(value)

        async def render_fake_file() -> None:
            path = Path(project.path) / f"{render_patterns[-1]}.wav"
            path.parent.mkdir(exist_ok=True, parents=True)
            path.touch()

        path = tmp_path / "Stub Song Title (feat. Stub Artist)"
        path.mkdir()
        project.path = str(path)

        project.master_track = Track("Master Track")
        project.master_track.fxs = [
            Fx("ReaEQ"),
            Fx("ReaXComp"),
            Fx("Master Limiter", params=[threshold]),
        ]

        project.tracks = [Track(name="Vocals"), Track(name="Drums")]
        project.set_info_string.side_effect = collect_render_patterns
        project.render.side_effect = render_fake_file
        mock_parse_summary_stats.side_effect = itertools.cycle(
            [
                {"duration": 1.0, "size": 42.0},
                {"duration": 250.1, "size": 1024},
            ]
        )

        mock_duration_delta.return_value = datetime.timedelta(seconds=10)

        def get_int_config_var(key: str, _: int) -> int:
            if key == "offlineinact":
                return 0
            return 999

        mock_get_int_config_var.side_effect = get_int_config_var

        yield RenderMocks(
            duration_delta=mock_duration_delta,
            get_int_config_var=mock_get_int_config_var,
            project=project,
            set_int_config_var=mock_set_int_config_var,
            upload=mock_upload,
        )


@pytest.fixture
def subprocess() -> Iterator[mock.Mock]:
    """Stub subprocess.run.

    The unit test module should not run or test external commands.
    """
    with mock.patch("subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def subprocess_with_output(
    subprocess: mock.Mock, tmp_path: Path
) -> Iterator[mock.Mock]:
    """Stub subprocess.run and simulate subprocesses writing output files."""

    def write_out_file(*args: list[str | Path], **kwargs: Any) -> mock.Mock:
        rv = mock.Mock()
        cmd_args = args[0]

        if cmd_args[0] == "ffmpeg":
            rv.stderr = ""

            out_fil = Path(cmd_args[-1])
            out_fil.touch()

        return rv

    subprocess.side_effect = write_out_file
    yield subprocess
