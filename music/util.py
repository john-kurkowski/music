"""Misc. utilities."""

from collections.abc import Iterator
from typing import NoReturn, TypeVar

import reapy

T = TypeVar("T")


def assert_exhaustiveness(no_return: NoReturn) -> NoReturn:
    """Provide an assertion at type-check time that this function is never called."""
    raise AssertionError(f"Invalid value: {no_return!r}")


def find_project() -> reapy.core.Project:
    """Find the target Reaper project."""
    try:
        return reapy.Project()
    except AttributeError as aterr:
        if "module" in str(aterr) and "reascript_api" in str(aterr):
            raise Exception(
                "Error while loading Reaper project. Is Reaper running?"
            ) from aterr
        raise


def recurse_property(prop: str, obj: T | None) -> Iterator[T]:
    """Recursively yield the given optional, recursive property, starting with the given object."""
    while obj is not None:
        yield obj
        obj = getattr(obj, prop, None)


def set_param_value(param: reapy.core.FXParam, value: float) -> None:
    """Set a parameter's value. Work around bug with reapy 0.10's setter."""
    parent_fx = param.parent_list.parent_fx
    parent = parent_fx.parent
    param.functions["SetParamNormalized"](  # type: ignore[operator]
        parent.id, parent_fx.index, param.index, value
    )
