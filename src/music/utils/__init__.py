"""Misc. utilities."""

import asyncio
import os
import shutil
from collections.abc import Callable, Iterator
from functools import wraps
from pathlib import Path
from typing import Any, NoReturn


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


def recurse_property[T](prop: str, obj: T | None) -> Iterator[T]:
    """Recursively yield the given optional, recursive property, starting with the given object."""
    while obj is not None:
        yield obj
        obj = getattr(obj, prop, None)


def rm_rf(path: Path) -> None:
    """Delete a file or directory recursively, if it exists, similarly to `rm -rf <PATH>`."""
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)
