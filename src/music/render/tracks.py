"""Helpers for Reaper tracks."""

import warnings

from music.util import recurse_property

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


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
        if not track.is_muted and bool(track.items) and not is_vocal(track)
    ]


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
        if not track.is_muted and "(vox)" in track.name.lower()
    ]


def find_stems(project: reapy.core.Project) -> list[reapy.core.Track]:
    """Find tracks to render as stems.

    Skip tracks that are already muted. Skip tracks that contain no media items
    and no FX; they're just for grouping and don't perform any processing on
    the final mix.
    """
    return [
        track
        for track in project.tracks
        if not track.is_muted and (bool(track.items) or bool(len(track.fxs)))
    ]
