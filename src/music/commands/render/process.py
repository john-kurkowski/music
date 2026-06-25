"""Render processing class and functions to handle the possible versions of a song."""

import base64
import datetime
import random
import shutil
import struct
import subprocess
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from dataclasses import dataclass
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

from music.utils import rm_rf
from music.utils.project import ExtendedProject
from music.utils.songversion import SongVersion

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
from .progress import RenderProgress, render_progress_monitor
from .result import ExistingRenderResult, RenderResult
from .tracks import find_acappella_tracks_to_mute, find_stems, find_vox_tracks_to_mute

type ProgressCallback = Callable[[float], None]


@dataclass(frozen=True)
class RenderOptions:
    """Values that vary for each invocation of a queued render."""

    keep_render_dialog_open: bool
    progress: ProgressCallback


type RenderCallable = Callable[[RenderOptions], Awaitable[RenderResult]]


@dataclass(frozen=True)
class RenderTask:
    """A song version queued for rendering and its progress display task."""

    progress_task_id: rich.progress.TaskID
    render: RenderCallable
    version: SongVersion


async def render_version(
    project: ExtendedProject,
    version: SongVersion,
    *,
    dry_run: bool,
    keep_render_dialog_open: bool,
    postprocess: Callable[[Path], None] | None = None,
    progress: Callable[[float], None],
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

    out_fil = version.path_for_project_dir(Path(project.path))
    if version == SongVersion.STEMS:
        tmp_fil = out_fil.parent / in_name

        tmp_secondary = None
        final_secondary = None
    else:
        tmp_fil = out_fil.with_stem(in_name)

        tmp_secondary = tmp_fil.with_suffix(".mp3")
        final_secondary = out_fil.with_suffix(".mp3")

    with (
        avoid_fx_tails(project),
        adjust_render_bounds(project) as render_bounds,
        adjust_render_pattern(project, Path(in_name).joinpath(*version.pattern)),
    ):
        async with render_progress_monitor(tmp_fil, render_bounds.duration, progress):
            # Time REAPER's render only. This narrower boundary is the realtime
            # performance denominator, distinct from the progress task's end-to-end
            # elapsed time that surrounds pre- and post-render application work.
            time_start = timer()
            await project.render(keep_render_dialog_open=keep_render_dialog_open)
            time_end = timer()

    final_fil = tmp_fil if dry_run else out_fil

    if postprocess is not None:
        postprocess(tmp_fil)

    result = RenderResult(
        project,
        version,
        final_fil,
        datetime.timedelta(seconds=time_end - time_start),
        cleanup_paths=(path for path in (tmp_fil, tmp_secondary) if path is not None)
        if dry_run
        else (),
        eager=dry_run,
    )

    if not dry_run:
        rm_rf(final_fil)
        shutil.move(tmp_fil, final_fil)

        if tmp_secondary and final_secondary:
            rm_rf(final_secondary)
            shutil.move(tmp_secondary, final_secondary)

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


def _encode_archival_render_format() -> str:
    """Encode maximum FLAC compression for Reaper's little-endian `RENDER_FORMAT` setting."""
    codec_tag = "flac"[::-1].encode("ascii")
    settings_flag = 0x10
    max_compression_level = 8
    payload = codec_tag + struct.pack("<II", settings_flag, max_compression_level)
    return base64.b64encode(payload).decode("ascii")


def _encode_shareable_render_format() -> str:
    """Encode LAME VBR -V2 for Reaper's little-endian `RENDER_FORMAT` setting."""
    codec_tag = "mp3l"[::-1].encode("ascii")
    settings_blob = bytes.fromhex(
        # LAME VBR -V2 (q=2) settings blob as stored by Reaper
        "20000000000000000200000000000000060000004001000000000000"
    )
    payload = codec_tag + settings_blob
    return base64.b64encode(payload).decode("ascii")


async def _render_main(
    project: ExtendedProject,
    *vocals: reapy.core.Track,
    dry_run: bool,
    keep_render_dialog_open: bool,
    progress: Callable[[float], None],
    verbose: int,
) -> RenderResult:
    for vocal in vocals:
        vocal.unsolo()
        vocal.unmute()

    with get_set_restore(
        partial(project.get_info_string, "RENDER_FORMAT2"),
        partial(project.set_info_string, "RENDER_FORMAT2"),
        _encode_shareable_render_format(),
    ):
        return await render_version(
            project,
            SongVersion.MAIN,
            dry_run=dry_run,
            keep_render_dialog_open=keep_render_dialog_open,
            progress=progress,
        )


async def _render_version_with_muted_tracks(
    version: Literal[SongVersion.INSTRUMENTAL, SongVersion.INSTRUMENTAL_DJ],
    project: ExtendedProject,
    *tracks_to_mute: reapy.core.Track,
    dry_run: bool,
    keep_render_dialog_open: bool,
    progress: Callable[[float], None],
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    with (
        adjust_master_limiter_threshold(project, vocal_loudness_worth),
        mute_tracks(tracks_to_mute),
        get_set_restore(
            partial(project.get_info_string, "RENDER_FORMAT2"),
            partial(project.set_info_string, "RENDER_FORMAT2"),
            _encode_shareable_render_format(),
        ),
    ):
        return await render_version(
            project,
            version,
            dry_run=dry_run,
            keep_render_dialog_open=keep_render_dialog_open,
            progress=progress,
        )


async def _render_a_cappella(
    project: ExtendedProject,
    *,
    dry_run: bool,
    keep_render_dialog_open: bool,
    progress: Callable[[float], None],
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    tracks_to_mute = find_acappella_tracks_to_mute(project)

    with (
        adjust_master_limiter_threshold(project, vocal_loudness_worth),
        mute_tracks(tracks_to_mute),
        get_set_restore(
            partial(project.get_info_string, "RENDER_FORMAT2"),
            partial(project.set_info_string, "RENDER_FORMAT2"),
            _encode_shareable_render_format(),
        ),
    ):
        return await render_version(
            project,
            SongVersion.ACAPPELLA,
            dry_run=dry_run,
            keep_render_dialog_open=keep_render_dialog_open,
            postprocess=trim_silence,
            progress=progress,
        )


async def _render_stems(
    project: ExtendedProject,
    *vocals: reapy.core.Track,
    dry_run: bool,
    keep_render_dialog_open: bool,
    progress: Callable[[float], None],
    verbose: int,
) -> RenderResult:
    """Set the `project` FX, track selection, and render settings for stems, render, then restore original settings.

    While there are several Reaper render presets for stems, the best one I've
    found for my conventions is "selected tracks via master": select all
    relevant tracks and process them through the "master" track.

    * Tracks are rendered through their ancestor tracks, repeatedly ascending
      all the way through the literal master track.
      * This function additionally disables FX on the master track. Its
        mastered render output is already available by requesting the main
        version of the song, rather than stems.
      * Combining all this function's output files would roughly recreate the
        master mix (albeit with some redundant sounds depending on sends and
        folder structure, and without the master FX, per the previous point).
    * Tracks are also rendered with their sends.
    * Tracks that are just sends are also rendered with all their inputs.
      * These stems are often redundant, but
        * they catch tracks that disabled master send.
        * otherwise might be a handy reference, the diff providing the input's
          original, dry signal.

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
    render_format = _encode_archival_render_format()
    render_format2 = ""

    with (
        select_tracks_only(project, find_stems(project)),
        toggle_fx_for_tracks([project.master_track], is_enabled=False),
        get_set_restore(
            partial(project.get_info_value, "RENDER_SETTINGS"),
            partial(project.set_info_value, "RENDER_SETTINGS"),
            cast(float, render_settings),
        ),
        get_set_restore(
            partial(project.get_info_string, "RENDER_FORMAT"),
            partial(project.set_info_string, "RENDER_FORMAT"),
            render_format,
        ),
        get_set_restore(
            partial(project.get_info_string, "RENDER_FORMAT2"),
            partial(project.set_info_string, "RENDER_FORMAT2"),
            render_format2,
        ),
    ):
        return await render_version(
            project,
            SongVersion.STEMS,
            dry_run=dry_run,
            keep_render_dialog_open=keep_render_dialog_open,
            progress=progress,
        )


class Process:
    """Encapsulate the state of rendering a Reaper project."""

    def __init__(
        self, console: rich.console.Console, console_err: rich.console.Console
    ) -> None:
        """Initialize."""
        self.console = console
        self.console_err = console_err
        self.progress = RenderProgress(self.console)

    async def process(
        self,
        project: ExtendedProject,
        *versions: SongVersion,
        dry_run: bool,
        exit_: bool,
        keep_render_dialog_open: bool,
        verbose: int,
        vocal_loudness_worth: float | None,
    ) -> AsyncIterator[tuple[SongVersion, RenderResult]]:
        """Render the given versions of the given Reaper project.

        Returns render results if anything was rendered. Skips versions that have
        no output. For example, if a project does not have vocals, rendering an a
        capella or instrumental version are skipped.
        """
        render_tasks = self._build_render_tasks(
            project,
            *versions,
            dry_run=dry_run,
            verbose=verbose,
            vocal_loudness_worth=self._get_vocal_loudness_worth(
                project, vocal_loudness_worth
            ),
        )

        for i, render_task in enumerate(render_tasks):
            existing_render_result = ExistingRenderResult(project, render_task.version)

            self.progress.start_task(render_task.progress_task_id)

            try:
                new_render_result = await self._render_and_print_stats(
                    existing_render_result,
                    render_task.render,
                    i=i,
                    keep_render_dialog_open=(
                        keep_render_dialog_open and i == len(render_tasks) - 1
                    ),
                    task=render_task.progress_task_id,
                    verbose=verbose,
                )
            except Exception as ex:
                self.progress.fail_task(render_task.progress_task_id, str(ex))
                raise

            self.progress.succeed_task(render_task.progress_task_id)

            yield (render_task.version, new_render_result)

        if len(render_tasks):
            # Render causes a project to have unsaved changes, no matter what. Save the user a step.
            project.save()

        if exit_:
            self._exit_daw()

    def _add_task(
        self, project: ExtendedProject, version: SongVersion, *, visible: bool = True
    ) -> rich.progress.TaskID:
        return self.progress.add_task(
            f'Rendering "{version.name_for_project_dir(Path(project.path))}"',
            visible=visible,
        )

    def _build_render_tasks(
        self,
        project: ExtendedProject,
        *versions: SongVersion,
        dry_run: bool,
        verbose: int,
        vocal_loudness_worth: float,
    ) -> list[RenderTask]:
        """Build list of render tasks based on requested versions and project content."""
        vocals = self._get_vocals(project)
        vox_tracks_to_mute = find_vox_tracks_to_mute(project)

        results: list[RenderTask] = []

        if self._should_render_main(versions):
            results.append(
                RenderTask(
                    version=SongVersion.MAIN,
                    render=lambda options: _render_main(
                        project,
                        *vocals,
                        dry_run=dry_run,
                        keep_render_dialog_open=options.keep_render_dialog_open,
                        progress=options.progress,
                        verbose=verbose,
                    ),
                    progress_task_id=self._add_task(
                        project, SongVersion.MAIN, visible=bool(results)
                    ),
                )
            )

        if self._should_render_instrumental(versions, vocals, vox_tracks_to_mute):
            results.append(
                RenderTask(
                    version=SongVersion.INSTRUMENTAL,
                    render=lambda options: _render_version_with_muted_tracks(
                        SongVersion.INSTRUMENTAL,
                        project,
                        *[track for track in [*vocals, *vox_tracks_to_mute] if track],
                        dry_run=dry_run,
                        keep_render_dialog_open=options.keep_render_dialog_open,
                        progress=options.progress,
                        vocal_loudness_worth=vocal_loudness_worth,
                        verbose=verbose,
                    ),
                    progress_task_id=self._add_task(
                        project, SongVersion.INSTRUMENTAL, visible=bool(results)
                    ),
                )
            )

        if self._should_render_instrumental_dj(versions, vocals, vox_tracks_to_mute):
            results.append(
                RenderTask(
                    version=SongVersion.INSTRUMENTAL_DJ,
                    render=lambda options: _render_version_with_muted_tracks(
                        SongVersion.INSTRUMENTAL_DJ,
                        project,
                        *vocals,
                        dry_run=dry_run,
                        keep_render_dialog_open=options.keep_render_dialog_open,
                        progress=options.progress,
                        vocal_loudness_worth=vocal_loudness_worth,
                        verbose=verbose,
                    ),
                    progress_task_id=self._add_task(
                        project, SongVersion.INSTRUMENTAL_DJ, visible=bool(results)
                    ),
                )
            )

        if self._should_render_acappella(versions, vocals):
            results.append(
                RenderTask(
                    version=SongVersion.ACAPPELLA,
                    render=lambda options: _render_a_cappella(
                        project,
                        dry_run=dry_run,
                        keep_render_dialog_open=options.keep_render_dialog_open,
                        progress=options.progress,
                        vocal_loudness_worth=vocal_loudness_worth,
                        verbose=verbose,
                    ),
                    progress_task_id=self._add_task(
                        project, SongVersion.ACAPPELLA, visible=bool(results)
                    ),
                )
            )

        if self._should_render_stems(versions):
            results.append(
                RenderTask(
                    version=SongVersion.STEMS,
                    render=lambda options: _render_stems(
                        project,
                        *vocals,
                        dry_run=dry_run,
                        keep_render_dialog_open=options.keep_render_dialog_open,
                        progress=options.progress,
                        verbose=verbose,
                    ),
                    progress_task_id=self._add_task(
                        project, SongVersion.STEMS, visible=bool(results)
                    ),
                )
            )

        return results

    def _exit_daw(self) -> None:
        """Exit the running DAW app.

        Reaper's CLI requires you close at least 1 project in order to exit the
        app. To make the UX the same whether 1 or more projects are open, this
        function closes _all_ projects.

        TODO: is there a way to gracefully exit the DAW without closing any
        projects? Maybe AppleScript? It's annoying to reopen projects on next
        DAW launch.
        """
        process = subprocess.run(
            [
                "/Applications/REAPER.app/Contents/MacOS/REAPER",
                "-closeall:exit:nosave",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if process.returncode:
            self.console_err.print(process.stdout)

    def _get_vocals(self, project: ExtendedProject) -> list[reapy.core.Track]:
        """Get vocal tracks from project."""
        return [track for track in project.tracks if track.name == "Vocals"]

    def _get_vocal_loudness_worth(
        self, project: ExtendedProject, vocal_loudness_worth: float | None
    ) -> float:
        """Get vocal loudness worth with fallback to project metadata."""
        if vocal_loudness_worth is not None:
            return vocal_loudness_worth

        return float(project.metadata.get("vocal-loudness-worth", VOCAL_LOUDNESS_WORTH))

    async def _render_and_print_stats(
        self,
        existing_render: ExistingRenderResult,
        render: RenderCallable,
        *,
        i: int,
        keep_render_dialog_open: bool,
        task: rich.progress.TaskID,
        verbose: int,
    ) -> RenderResult:
        """Collect before statistics, execute the given render, and print a before and after summary.

        Returns the rendered file.
        """
        if i > 0:
            self.console.print()

        before_stats = existing_render.summary_stats
        out = await render(
            RenderOptions(
                keep_render_dialog_open=keep_render_dialog_open,
                progress=partial(self.progress.update_task, task),
            )
        )
        after_stats = out.summary_stats

        self.console.print(f"[b default]{out.name}[/b default]")
        self.console.print(f"[default dim italic]{out.fil}[/default dim italic]")

        table = rich.table.Table(
            box=rich.box.MINIMAL,
            caption=f"Rendered at [b]{out.render_speedup:.1f}x[/b] realtime",
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

    def _should_render_acappella(
        self, versions: Collection[SongVersion], vocals: list[reapy.core.Track]
    ) -> bool:
        return SongVersion.ACAPPELLA in versions and bool(vocals)

    def _should_render_instrumental(
        self,
        versions: Collection[SongVersion],
        vocals: list[reapy.core.Track],
        vox_tracks: list[reapy.core.Track],
    ) -> bool:
        return SongVersion.INSTRUMENTAL in versions and bool(vocals or vox_tracks)

    def _should_render_instrumental_dj(
        self,
        versions: Collection[SongVersion],
        vocals: list[reapy.core.Track],
        vox_tracks: list[reapy.core.Track],
    ) -> bool:
        """Check whether to render the DJ instrumental version.

        SongVersion.INSTRUMENTAL_DJ only mutes the main vocal. However, if
        there are no other vox tracks, the version is identical to
        SongVersion.INSTRUMENTAL, and is skipped.
        """
        return (
            SongVersion.INSTRUMENTAL_DJ in versions
            and bool(vocals)
            and bool(vox_tracks)
        )

    def _should_render_main(self, versions: Collection[SongVersion]) -> bool:
        return SongVersion.MAIN in versions

    def _should_render_stems(self, versions: Collection[SongVersion]) -> bool:
        return SongVersion.STEMS in versions
