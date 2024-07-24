"""Render processing class and functions to handle the possible versions of a song."""

import datetime
import random
import shutil
import subprocess
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from functools import cached_property
from pathlib import Path
from timeit import default_timer as timer

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

import rich.box
import rich.console
import rich.progress
import rich.table

from music.__codegen__ import stats
from music.util import (
    ExtendedProject,
    SongVersion,
    rm_rf,
)

from .consts import VOCAL_LOUDNESS_WORTH
from .contextmanagers import (
    adjust_master_limiter_threshold,
    adjust_render_pattern,
    adjust_render_settings,
    avoid_fx_tails,
    mute_tracks,
    normalize_tempo,
    toggle_fx_for_tracks,
)
from .result import RenderResult
from .tracks import find_acappella_tracks_to_mute, find_stems, find_vox_tracks_to_mute


def summary_stats_for_file(fil: Path, verbose: int = 0) -> dict[str, float | str]:
    """Print statistics for the given audio file, like LUFS-I and LRA."""
    cmd = _cmd_for_stats(fil)
    proc = subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)
    proc_output = proc.stderr
    return stats.parse_summary_stats(proc_output)


def _cmd_for_stats(fil: Path) -> list[str | Path]:
    return [
        "ffmpeg",
        "-i",
        fil,
        "-filter:a",
        ",".join(("volumedetect", "ebur128=framelog=verbose")),
        "-hide_banner",
        "-nostats",
        "-f",
        "null",
        "/dev/null",
    ]


async def render_version(
    project: ExtendedProject, version: SongVersion
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
        adjust_render_settings(project, version),
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

    rm_rf(out_fil)
    shutil.move(tmp_fil, out_fil)

    return RenderResult(out_fil, datetime.timedelta(seconds=time_end - time_start))


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
    project: ExtendedProject, vocals: reapy.core.Track | None, verbose: int
) -> RenderResult:
    if vocals:
        vocals.unsolo()
        vocals.unmute()
    return await render_version(project, SongVersion.MAIN)


async def _render_instrumental(
    project: ExtendedProject,
    vocals: reapy.core.Track,
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    tracks_to_mute = (vocals,)

    with (
        adjust_master_limiter_threshold(project, vocal_loudness_worth),
        mute_tracks(tracks_to_mute),
    ):
        return await render_version(project, SongVersion.INSTRUMENTAL)


async def _render_instrumental_dj(
    project: ExtendedProject,
    tracks_to_mute: list[reapy.core.Track],
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    with (
        adjust_master_limiter_threshold(project, vocal_loudness_worth),
        mute_tracks(tracks_to_mute),
        normalize_tempo(project),
    ):
        return await render_version(project, SongVersion.INSTRUMENTAL_DJ)


async def _render_a_cappella(
    project: ExtendedProject,
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    tracks_to_mute = find_acappella_tracks_to_mute(project)

    with (
        adjust_master_limiter_threshold(project, vocal_loudness_worth),
        mute_tracks(tracks_to_mute),
    ):
        out = await render_version(project, SongVersion.ACAPPELLA)

    trim_silence(out.fil)
    return out


async def _render_stems(
    project: ExtendedProject,
    vocals: reapy.core.Track | None,
    verbose: int,
) -> RenderResult:
    if vocals:
        vocals.unsolo()
        vocals.unmute()
    for track in project.tracks:
        track.unselect()
    for track in find_stems(project):
        track.select()
    with toggle_fx_for_tracks([project.master_track], is_enabled=False):
        return await render_version(project, SongVersion.STEMS)


def _has_instrumental_dj_difference(project: ExtendedProject) -> bool:
    return bool(find_vox_tracks_to_mute(project)) or project.n_tempo_markers > 1


class Process:
    """Encapsulate the state of rendering a Reaper project."""

    def __init__(self, console: rich.console.Console) -> None:
        """Initialize."""
        self.console = console

    async def process(
        self,
        project: ExtendedProject,
        versions: Collection[SongVersion],
        vocal_loudness_worth: float | None,
        verbose: int,
    ) -> AsyncIterator[tuple[SongVersion, RenderResult]]:
        """Render the given versions of the given Reaper project.

        Returns render results if anything was rendered. Skips versions that have
        no output. For example, if a project does not have vocals, rendering an a
        capella or instrumental version are skipped.
        """
        vocals = next(
            (track for track in project.tracks if track.name == "Vocals"), None
        )

        if vocal_loudness_worth is None:
            vocal_loudness_worth = float(
                project.metadata.get("vocal-loudness-worth") or VOCAL_LOUDNESS_WORTH
            )

        results = []

        if SongVersion.MAIN in versions:
            results.append(
                (
                    SongVersion.MAIN,
                    lambda: _render_main(project, vocals, verbose),
                    self._add_task(project, SongVersion.MAIN),
                )
            )

        if SongVersion.INSTRUMENTAL in versions and vocals:
            results.append(
                (
                    SongVersion.INSTRUMENTAL,
                    lambda: _render_instrumental(
                        project,
                        vocals,
                        vocal_loudness_worth,
                        verbose,
                    ),
                    self._add_task(project, SongVersion.INSTRUMENTAL),
                )
            )

        if SongVersion.INSTRUMENTAL_DJ in versions and _has_instrumental_dj_difference(
            project
        ):
            results.append(
                (
                    SongVersion.INSTRUMENTAL_DJ,
                    lambda: _render_instrumental_dj(
                        project,
                        [
                            track
                            for track in [vocals, *find_vox_tracks_to_mute(project)]
                            if track
                        ],
                        vocal_loudness_worth,
                        verbose,
                    ),
                    self._add_task(project, SongVersion.INSTRUMENTAL_DJ),
                )
            )

        if SongVersion.ACAPPELLA in versions and vocals:
            results.append(
                (
                    SongVersion.ACAPPELLA,
                    lambda: _render_a_cappella(project, vocal_loudness_worth, verbose),
                    self._add_task(project, SongVersion.ACAPPELLA),
                )
            )

        if SongVersion.STEMS in versions:
            results.append(
                (
                    SongVersion.STEMS,
                    lambda: _render_stems(project, vocals, verbose),
                    self._add_task(project, SongVersion.STEMS),
                )
            )

        for i, (version, render, task) in enumerate(results):
            if i > 0:
                self.console.print()

            self.progress.start_task(task)

            yield (
                version,
                await self._print_stats_for_render(project, version, verbose, render),
            )

            self.progress.update(task, advance=1)

        # TODO: REVERT ME. Avoiding saves while developing experimental feature.
        # if len(results):
        #     # Render causes a project to have unsaved changes, no matter what. Save the user a step.
        #     project.save()

    @cached_property
    def progress(self) -> rich.progress.Progress:
        """Rich progress bar."""
        return rich.progress.Progress(
            rich.progress.SpinnerColumn(finished_text="[green]✓[/green]"),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
        )

    def _add_task(
        self, project: ExtendedProject, version: SongVersion
    ) -> rich.progress.TaskID:
        return self.progress.add_task(
            f'Rendering "{version.name_for_project_dir(Path(project.path))}"',
            start=False,
            total=1,
        )

    async def _print_stats_for_render(
        self,
        project: ExtendedProject,
        version: SongVersion,
        verbose: int,
        render: Callable[[], Awaitable[RenderResult]],
    ) -> RenderResult:
        """Collect and print before and after summary statistics for the given project version render.

        Returns the rendered file, after pretty printing itsprogress and metadata.
        """
        name = version.name_for_project_dir(Path(project.path))
        out_fil = version.path_for_project_dir(Path(project.path))

        before_stats = summary_stats_for_file(out_fil) if out_fil.is_file() else {}
        out = await render()
        after_stats = (
            summary_stats_for_file(out_fil, verbose) if out_fil.is_file() else {}
        )

        self.console.print(f"[b default]{name}[/b default]")
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
