"""Misc. utilities."""

from typing import NoReturn


def assert_exhaustiveness(no_return: NoReturn) -> NoReturn:
    """Provide an assertion at type-check time that this function is never called."""
    raise AssertionError(f"Invalid value: {no_return!r}")
