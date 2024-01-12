"""Misc. utilities."""

import asyncio
import enum
import warnings
from collections.abc import Callable, Iterator
from functools import wraps
from pathlib import Path
from typing import Any, NoReturn, TypeVar

import aiohttp

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

T = TypeVar("T")

# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230


class SongVersion(enum.Enum):
    """Different versions of a song to render."""

    MAIN = enum.auto()
    INSTRUMENTAL = enum.auto()
    ACAPPELLA = enum.auto()

    def name_for_project_dir(self, project_dir: Path) -> str:
        """Name of the project for the given song version."""
        project_name = project_dir.name
        if self is SongVersion.MAIN:
            return project_name
        elif self is SongVersion.INSTRUMENTAL:
            return f"{project_name} (Instrumental)"
        elif self is SongVersion.ACAPPELLA:
            return f"{project_name} (A Cappella)"
        else:  # pragma: no cover
            assert_exhaustiveness(self)

    def path_for_project_dir(self, project_dir: Path) -> Path:
        """Path of the rendered file for the given song version."""
        return project_dir / f"{self.name_for_project_dir(project_dir)}.wav"


class ExtendedProject(reapy.core.Project):
    """Extend reapy.core.Project with additional properties."""

    def __init__(self) -> None:
        """Wrap common error in a more helpful message."""
        try:
            super().__init__()
        except AttributeError as aterr:
            if "module" in str(aterr) and "reascript_api" in str(aterr):
                raise Exception(
                    "Error while loading Reaper project. Is Reaper running?"
                ) from aterr
            raise  # pragma: no cover

    @classmethod
    def get_or_open(cls, project_dir: Path) -> "ExtendedProject":
        """Open the target Reaper project if it is not already open."""
        project = cls()
        if project_dir is None or str(project_dir.resolve()) == project.path:
            return project

        project_file = (
            project_dir
            if project_dir.suffix == ".rpp"
            else project_dir / f"{project_dir.name}.rpp"
        )
        reapy.RPR.Main_openProject(str(project_file))  # type: ignore[attr-defined]
        return cls()

    async def render(self) -> None:
        """Trigger Reaper to render the currently open project.

        Unlike sending a command via Reaper's Python API
        (`project.perform_action(action_id)`), this method uses Reaper's HTTP
        API, to work async.
        """
        port = reapy.config.WEB_INTERFACE_PORT

        async with aiohttp.ClientSession() as client:
            resp = await client.get(
                f"http://localhost:{port}/_/{RENDER_CMD_ID}",
            )
            resp.raise_for_status()

    @property
    def path(self) -> str:
        """Override. Get the path containing the project.

        Works around a bug in reapy 0.10.0's implementation of `Project.path`,
        which actually gets the _recording_ path of the project.
        """
        filename = str(reapy.RPR.EnumProjects(-1, None, 999)[2])  # type: ignore[attr-defined]
        return str(Path(filename).parent)


def assert_exhaustiveness(no_return: NoReturn) -> NoReturn:  # pragma: no cover
    """Provide an assertion at type-check time that this function is never called."""
    raise AssertionError(f"Invalid value: {no_return!r}")


def coro(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate Click commands as coroutines.

    H/T https://github.com/pallets/click/issues/85
    """

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))

    return wrapper


def recurse_property(prop: str, obj: T | None) -> Iterator[T]:
    """Recursively yield the given optional, recursive property, starting with the given object."""
    while obj is not None:
        yield obj
        obj = getattr(obj, prop, None)


def set_param_value(param: reapy.core.FXParam, value: float) -> None:
    """Set a parameter's value.

    Works around bug with reapy 0.10's setter.
    """
    parent_fx = param.parent_list.parent_fx
    parent = parent_fx.parent
    param.functions["SetParamNormalized"](  # type: ignore[operator]
        parent.id, parent_fx.index, param.index, value
    )
