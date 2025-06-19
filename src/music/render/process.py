"""Render processing class and functions to handle the possible versions of a song."""

import datetime
import random
import shutil
import subprocess
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import partial
from pathlib import Path
from timeit import default_timer as timer
from typing import Literal, cast

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

import rich.box
import rich.console
import rich.progress
import rich.table

from music.util import (
    ExtendedProject,
    SongVersion,
    rm_rf,
)

from .consts import (
    MONO_TRACKS_TO_MONO_FILES,
    SELECTED_TRACKS_VIA_MASTER,
    VOCAL_LOUDNESS_WORTH,
)
from .contextmanagers import (
    adjust_master_limiter_threshold,
    adjust_render_bounds,
    adjust_render_pattern,
    avoid_fx_tails,
    get_set_restore,
    mute_tracks,
    select_tracks_only,
    toggle_fx_for_tracks,
)
from .progress import IndeterminateProgress
from .result import ExistingRenderResult, RenderResult
from .tracks import find_acappella_tracks_to_mute, find_stems, find_vox_tracks_to_mute


async def render_version(
    project: ExtendedProject, version: SongVersion, *, dry_run: bool
) -> RenderResult:
    """Trigger Reaper to render the current project audio. Returns the output file.

    Names the output file according to the given version. Writes to a temporary
    file first, then overwrites any existing file of the same song version.

    Adjusts some global and project preferences, then restores the original
    values after render completion.
    """
    out_name = version.name_for_project_dir(Path(project.path))

    # Avoid "Overwrite" "Render Warning" dialog, which can't be scripted, with a temporary filename
    rand_id = random.randrange(10**5, 10**6)
    in_name = f"{out_name} {rand_id}.tmp"

    with (
        avoid_fx_tails(project),
        adjust_render_bounds(project),
        adjust_render_pattern(project, Path(in_name).joinpath(*version.pattern)),
    ):
        time_start = timer()
        await project.render()
        time_end = timer()

    out_fil = version.path_for_project_dir(Path(project.path))
    if version == SongVersion.STEMS:
        tmp_fil = out_fil.parent / in_name
    else:
        tmp_fil = out_fil.with_stem(in_name)

    final_fil = tmp_fil if dry_run else out_fil
    result = RenderResult(
        project,
        version,
        final_fil,
        datetime.timedelta(seconds=time_end - time_start),
        eager=dry_run,
    )

    if dry_run:
        rm_rf(tmp_fil)
    else:
        rm_rf(final_fil)
        shutil.move(tmp_fil, final_fil)

    return result


def trim_silence(fil: Path) -> None:
    """Trim leading and trailing silence from the given audio file, in-place.

    H/T https://superuser.com/a/1715017
    """
    leading_silence_duration_s = 1.0
    trailing_silence_duration_s = 3.0

    rand_id = random.randrange(10**5, 10**6)
    tmp_fil = f"{fil} {rand_id}.tmp.wav"

    cmd: list[str | Path] = [
        "ffmpeg",
        "-i",
        fil,
        "-filter:a",
        ",".join(
            (
                "areverse",
                "atrim=start=0.2",
                f"silenceremove=start_periods=1:start_silence={trailing_silence_duration_s}:start_threshold=0.02",
                "areverse",
                "atrim=start=0.2",
                f"silenceremove=start_periods=1:start_silence={leading_silence_duration_s}:start_threshold=0.02",
            )
        ),
        tmp_fil,
    ]
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)

    shutil.move(tmp_fil, fil)


async def _render_main(
    project: ExtendedProject, *vocals: reapy.core.Track, dry_run: bool, verbose: int
) -> RenderResult:
    for vocal in vocals:
        vocal.unsolo()
        vocal.unmute()
    return await render_version(project, SongVersion.MAIN, dry_run=dry_run)


async def _render_version_with_muted_tracks(
    version: Literal[SongVersion.INSTRUMENTAL, SongVersion.INSTRUMENTAL_DJ],
    project: ExtendedProject,
    *tracks_to_mute: reapy.core.Track,
    dry_run: bool,
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    with (
        adjust_master_limiter_threshold(project, vocal_loudness_worth),
        mute_tracks(tracks_to_mute),
    ):
        return await render_version(project, version, dry_run=dry_run)


async def _render_a_cappella(
    project: ExtendedProject,
    *,
    dry_run: bool,
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    tracks_to_mute = find_acappella_tracks_to_mute(project)

    with (
        adjust_master_limiter_threshold(project, vocal_loudness_worth),
        mute_tracks(tracks_to_mute),
    ):
        out = await render_version(project, SongVersion.ACAPPELLA, dry_run=dry_run)

    trim_silence(out.fil)
    return out


async def _render_stems(
    project: ExtendedProject,
    *vocals: reapy.core.Track,
    dry_run: bool,
    verbose: int,
) -> RenderResult:
    """Set the `project` FX, track selection, and render settings for stems, render, then restore original settings.

    While there are several Reaper render presets for stems, the best one I've
    found for my conventions is "selected tracks via master": select all
    relevant tracks and process them through the "master" track.

    * Tracks are rendered through their parent, ancestor tracks, ascending all
      the way through the literal master track.
      * This function additionally disables FX on the master track. Its
        mastered render output is already available by requesting the main
        version of the song, rather than stems.
      * Combining all this function's output files would roughly recreate the
        master mix, albeit with some redundant sounds depending on sends and
        folder structure (and sans the master FX, per the previous point).
    * Tracks are also rendered with their sends.
    * Tracks that are just sends are also rendered with all their inputs.
      * These stems are often redundant, but
        * they catch tracks that disabled master send.
        * otherwise might be a handy reference, the diff providing the input's
          original dry signal.

    A disadvantage of "selected tracks via master" is, there is no stem
    containing a track's dry signal if any of its ancestors has FX. A
    workaround could be to select only tracks with some ancestor with FX
    (besides master), and perform a 2nd render with the setting "selected
    tracks (stems)". The files would need a different name pattern and to be
    manually merged with the folder structure of the first render, vs.
    overwriting the entire folder. Then there would be both dry and
    parent-and-send-included stems available.

    As a slight time and space efficiency, keep mono files in mono.
    """
    for vocal in vocals:
        vocal.unsolo()
        vocal.unmute()

    render_settings = MONO_TRACKS_TO_MONO_FILES | SELECTED_TRACKS_VIA_MASTER

    with (
        select_tracks_only(project, find_stems(project)),
        toggle_fx_for_tracks([project.master_track], is_enabled=False),
        get_set_restore(
            partial(project.get_info_value, "RENDER_SETTINGS"),
            partial(project.set_info_value, "RENDER_SETTINGS"),
            cast(float, render_settings),
        ),
    ):
        return await render_version(project, SongVersion.STEMS, dry_run=dry_run)


class Process:
    """Encapsulate the state of rendering a Reaper project."""

    def __init__(
        self, console: rich.console.Console, console_err: rich.console.Console
    ) -> None:
        """Initialize."""
        self.console = console
        self.console_err = console_err
        self.progress = IndeterminateProgress(self.console)

    async def process(  # noqa: C901
        self,
        project: ExtendedProject,
        *versions: SongVersion,
        dry_run: bool,
        exit_: bool,
        verbose: int,
        vocal_loudness_worth: float | None,
    ) -> AsyncIterator[tuple[SongVersion, RenderResult]]:
        """Render the given versions of the given Reaper project.

        Returns render results if anything was rendered. Skips versions that have
        no output. For example, if a project does not have vocals, rendering an a
        capella or instrumental version are skipped.
        """
        vocals = [track for track in project.tracks if track.name == "Vocals"]

        if vocal_loudness_worth is None:
            vocal_loudness_worth = float(
                project.metadata.get("vocal-loudness-worth", VOCAL_LOUDNESS_WORTH)
            )

        results = []

        if SongVersion.MAIN in versions:
            results.append(
                (
                    SongVersion.MAIN,
                    lambda: _render_main(
                        project, *vocals, dry_run=dry_run, verbose=verbose
                    ),
                    self._add_task(project, SongVersion.MAIN),
                )
            )

        if SongVersion.INSTRUMENTAL in versions and (
            vocals or find_vox_tracks_to_mute(project)
        ):
            results.append(
                (
                    SongVersion.INSTRUMENTAL,
                    lambda: _render_version_with_muted_tracks(
                        SongVersion.INSTRUMENTAL,
                        project,
                        *[
                            track
                            for track in [*vocals, *find_vox_tracks_to_mute(project)]
                            if track
                        ],
                        dry_run=dry_run,
                        vocal_loudness_worth=vocal_loudness_worth,
                        verbose=verbose,
                    ),
                    self._add_task(project, SongVersion.INSTRUMENTAL),
                )
            )

        # SongVersion.INSTRUMENTAL_DJ only mutes the main vocal. However, if
        # there are no other vox tracks, the version is identical to
        # SongVersion.INSTRUMENTAL, and is skipped.
        if (
            SongVersion.INSTRUMENTAL_DJ in versions
            and vocals
            and find_vox_tracks_to_mute(project)
        ):
            results.append(
                (
                    SongVersion.INSTRUMENTAL_DJ,
                    lambda: _render_version_with_muted_tracks(
                        SongVersion.INSTRUMENTAL_DJ,
                        project,
                        *vocals,
                        dry_run=dry_run,
                        vocal_loudness_worth=vocal_loudness_worth,
                        verbose=verbose,
                    ),
                    self._add_task(project, SongVersion.INSTRUMENTAL_DJ),
                )
            )

        if SongVersion.ACAPPELLA in versions and vocals:
            results.append(
                (
                    SongVersion.ACAPPELLA,
                    lambda: _render_a_cappella(
                        project,
                        dry_run=dry_run,
                        vocal_loudness_worth=vocal_loudness_worth,
                        verbose=verbose,
                    ),
                    self._add_task(project, SongVersion.ACAPPELLA),
                )
            )

        if SongVersion.STEMS in versions:
            results.append(
                (
                    SongVersion.STEMS,
                    lambda: _render_stems(
                        project, *vocals, dry_run=dry_run, verbose=verbose
                    ),
                    self._add_task(project, SongVersion.STEMS),
                )
            )

        for i, (version, render, task) in enumerate(results):
            if i > 0:
                self.console.print()

            self.progress.start_task(task)

            try:
                result = await self._render_and_print_stats(
                    ExistingRenderResult(project, version), render, verbose=verbose
                )
            except Exception as ex:
                self.progress.fail_task(task, str(ex))
                raise

            self.progress.succeed_task(task)

            yield (version, result)

        if len(results):
            # Render causes a project to have unsaved changes, no matter what. Save the user a step.
            project.save()

        if exit_:
            self._exit_daw()

    def _add_task(
        self, project: ExtendedProject, version: SongVersion
    ) -> rich.progress.TaskID:
        return self.progress.add_task(
            f'Rendering "{version.name_for_project_dir(Path(project.path))}"',
        )

    def _exit_daw(self) -> None:
        process = subprocess.run(
            [
                "/Applications/REAPER.app/Contents/MacOS/REAPER",
                "-close:exit:nosave",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if process.returncode:
            self.console_err.print(process.stdout)

    async def _render_and_print_stats(
        self,
        existing_render: ExistingRenderResult,
        render: Callable[[], Awaitable[RenderResult]],
        *,
        verbose: int,
    ) -> RenderResult:
        """Collect before statistics, execute the given render, and print a before and after summary.

        Returns the rendered file.
        """
        before_stats = existing_render.summary_stats
        out = await render()
        after_stats = out.summary_stats

        self.console.print(f"[b default]{out.name}[/b default]")
        self.console.print(f"[default dim italic]{out.fil}[/default dim italic]")

        table = rich.table.Table(
            box=rich.box.MINIMAL,
            caption=(
                f"Rendered in [b]{out.render_delta}[/b], a"
                f" [b]{out.render_speedup:.1f}x[/b] speedup"
            ),
        )
        table.add_column("", style="blue")
        table.add_column("Before", header_style="bold blue")
        table.add_column("After", header_style="bold blue")

        keys = sorted({k for di in (before_stats, after_stats) for k in di})
        for k in keys:
            table.add_row(
                k, *[str(di.get(k, "")) for di in (before_stats, after_stats)]
            )

        self.console.print(table)

        return out
