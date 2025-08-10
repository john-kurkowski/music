"""Utilities for working with Reaper's FX."""

import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


def set_param_value(param: reapy.core.FXParam, value: float) -> None:
    """Set a parameter's value.

    Works around bug with reapy 0.10's setter.
    """
    parent_fx = param.parent_list.parent_fx
    parent = parent_fx.parent
    param.functions["SetParamNormalized"](  # type: ignore[operator]
        parent.id, parent_fx.index, param.index, value
    )
