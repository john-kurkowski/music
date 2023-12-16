"""Misc. utilities."""

import asyncio
import warnings
from collections.abc import Callable, Iterator
from functools import wraps
from pathlib import Path
from typing import Any, NoReturn, TypeVar

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

T = TypeVar("T")

# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230


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

        This method is actually synchronous as it uses Reaper's Python API,
        which is synchronous. Maybe one day an async version will be available.
        """
        self.perform_action(RENDER_CMD_ID)

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
