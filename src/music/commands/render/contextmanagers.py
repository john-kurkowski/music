"""Context managers for before and after Reaper renders."""

import contextlib
import warnings
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, TypeVar, cast

from music.utils.project import ExtendedProject

from .consts import SWS_ERROR_SENTINEL
from .tracks import is_muted

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


T = TypeVar("T")
_reapy_dynamic = cast(Any, reapy)


@dataclass(frozen=True)
class RenderBounds:
    """Start, end, and duration of the audio included in a render."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        """Return the number of seconds between the render bounds."""
        return self.end - self.start


def adjust_render_pattern(
    project: ExtendedProject, pattern: Path
) -> contextlib.AbstractContextManager[None]:
    """Set the `project` RENDER_PATTERN, then restore the original value."""
    return get_set_restore(
        partial(project.get_info_string, "RENDER_PATTERN"),
        partial(project.set_info_string, "RENDER_PATTERN"),
        str(pattern),
    )


@contextlib.contextmanager
def adjust_render_bounds(project: ExtendedProject) -> Iterator[RenderBounds]:
    """Set `project` render bounds, then restore the original values.

    This sets the render start and end times to contain all unmuted media
    items. Different song versions may therefore have different starts and ends
    and durations. This is more flexible than a human remembering to set fixed,
    custom times in the Reaper GUI, per song version.

    Yields the active render bounds for consumers that need their duration.
    """
    custom_time_bounds = 0

    with _reapy_dynamic.inside_reaper():
        items = sorted(
            (
                item
                for track in project.tracks
                if not is_muted(track)
                for item in track.items
                if not item.get_info_value("B_MUTE_ACTUAL")
            ),
            key=lambda item: item.position,
        )

        startpos = items[0].position if items else 0.0
        endpos = max(
            (item.position + item.length for item in items),
            default=0.0,
        )

    with (
        get_set_restore(
            partial(project.get_info_value, "RENDER_BOUNDSFLAG"),
            partial(project.set_info_value, "RENDER_BOUNDSFLAG"),
            cast(float, custom_time_bounds),
        ),
        get_set_restore(
            partial(project.get_info_value, "RENDER_STARTPOS"),
            partial(project.set_info_value, "RENDER_STARTPOS"),
            startpos,
        ),
        get_set_restore(
            partial(project.get_info_value, "RENDER_ENDPOS"),
            partial(project.set_info_value, "RENDER_ENDPOS"),
            endpos,
        ),
    ):
        yield RenderBounds(start=startpos, end=endpos)


@contextlib.contextmanager
def avoid_fx_tails(project: ExtendedProject) -> Iterator[None]:
    """Change global settings to avoid FX tails at the beginning of the render, then restore the global settings' original values."""
    off = 0
    start_time = 0.0

    with (
        get_set_restore(
            partial(
                _reapy_dynamic.reascript_api.SNM_GetIntConfigVar,
                "runallonstop",
                SWS_ERROR_SENTINEL,
            ),
            partial(_reapy_dynamic.reascript_api.SNM_SetIntConfigVar, "runallonstop"),
            off,
        ),
        get_set_restore(
            partial(
                _reapy_dynamic.reascript_api.SNM_GetIntConfigVar,
                "runafterstop",
                SWS_ERROR_SENTINEL,
            ),
            partial(_reapy_dynamic.reascript_api.SNM_SetIntConfigVar, "runafterstop"),
            off,
        ),
        get_set_restore(
            partial(getattr, project, "cursor_position"),
            partial(setattr, project, "cursor_position"),
            start_time,
        ),
    ):
        yield


@contextlib.contextmanager
def get_set_restore[T](
    getter: Callable[[], T], setter: Callable[[T], None], during_value: T
) -> Iterator[None]:
    """Get the previous value from `getter`, set `during_value` with the `setter`, then restore the original value."""
    prev_value = getter()
    try:
        setter(during_value)
        yield
    finally:
        setter(prev_value)


@contextlib.contextmanager
def mute_tracks(tracks: Collection[reapy.core.Track]) -> Iterator[None]:
    """Mute all tracks in the given collection, then unmute them."""
    for track in tracks:
        track.mute()
    try:
        yield
    finally:
        for track in tracks:
            track.unmute()


@contextlib.contextmanager
def select_tracks_only(
    project: ExtendedProject, tracks: Collection[reapy.core.Track]
) -> Iterator[None]:
    """Select only the tracks in the given collection, unselecting all other tracks, then restore track selection."""
    tracks_to_select = {track.id: track for track in tracks}

    with _reapy_dynamic.inside_reaper():
        original_selection = {track.id: track.is_selected for track in project.tracks}

        for track in project.tracks:
            should_be_selected = track.id in tracks_to_select
            if track.is_selected != should_be_selected:
                if should_be_selected:
                    track.select()
                else:
                    track.unselect()

    try:
        yield
    finally:
        with _reapy_dynamic.inside_reaper():
            for track in project.tracks:
                if track.is_selected != original_selection[track.id]:
                    if original_selection[track.id]:
                        track.select()
                    else:
                        track.unselect()


@contextlib.contextmanager
def toggle_fx_for_tracks(
    tracks: Collection[reapy.core.Track], is_enabled: bool
) -> Iterator[None]:
    """Toggle all effects in the given collection of tracks, then toggle them back."""
    fxs = [
        fx
        for track in tracks
        for i in range(len(track.fxs))
        if (fx := track.fxs[i]) and fx.is_enabled != is_enabled
    ]
    for fx in fxs:
        fx.is_enabled = is_enabled

    try:
        yield
    finally:
        for fx in fxs:
            fx.is_enabled = not is_enabled
