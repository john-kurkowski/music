"""Helpers for Reaper tracks."""

import warnings
from collections.abc import Callable
from typing import Any, cast

from music.utils import recurse_property

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

_reapy_dynamic = cast(Any, reapy)


def _inside_reaper[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Run a function inside Reaper while preserving its Python signature."""
    return cast(Callable[P, R], _reapy_dynamic.inside_reaper()(func))


@_inside_reaper
def find_acappella_tracks_to_mute(
    project: reapy.core.Project,
) -> list[reapy.core.Track]:
    """Find tracks to mute when rendering the a cappella version of the song.

    reapy.core.Track.solo() doesn't work as expected, so we have to mute
    multiple tracks by hand. Skip tracks that are already muted (wouldn't want
    to ultimately unmute them). Skip tracks that contain no media items
    themselves and still might contribute to the vocal, e.g. sends with FX.
    """

    def is_vocal(track: reapy.Track) -> bool:
        return any(
            track.name == "Vocals" for track in recurse_property("parent_track", track)
        )

    return [
        track
        for track in project.tracks
        if not is_muted(track) and bool(track.items) and not is_vocal(track)
    ]


@_inside_reaper
def find_vox_tracks_to_mute(
    project: reapy.core.Project,
) -> list[reapy.core.Track]:
    """Find vox tracks to mute when rendering the instrumental version of the song.

    Skip tracks that are already muted (wouldn't want to ultimately unmute
    them).
    """
    return [
        track
        for track in project.tracks
        if not is_muted(track) and "(vox)" in track.name.lower()
    ]


@_inside_reaper
def find_stems(project: reapy.core.Project) -> list[reapy.core.Track]:
    """Find tracks to render as stems.

    Skip tracks that are already muted. Skip tracks that contain no media items
    and no FX; they're just for grouping and don't perform any processing on
    the final mix.
    """
    return [
        track
        for track in project.tracks
        if not is_muted(track) and (bool(track.items) or bool(len(track.fxs)))
    ]


@_inside_reaper
def is_muted(track: reapy.core.Track) -> bool:
    """Check whether a track is muted more robustly than `reapy.core.Track.is_muted`."""
    return track.is_muted or any(
        parent_track.is_muted
        for parent_track in recurse_property("parent_track", track)
    )
