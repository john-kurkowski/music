"""Render progress tests."""

import asyncio
import io
import subprocess
from pathlib import Path
from unittest import mock

import pytest
import rich.console
from syrupy.assertion import SnapshotAssertion

from music.commands.render import progress


def test_progress_bar_follows_elapsed_time_and_persists(
    snapshot: SnapshotAssertion,
) -> None:
    """Keep determinate render progress visible through task completion."""
    output = io.StringIO()
    console = rich.console.Console(file=output, width=100, color_system=None)
    render_progress = progress.RenderProgress(console)
    task = render_progress.add_task('Rendering "Song"')
    render_progress.start_task(task)
    render_progress.update_task(task, 0.5)
    console.print(render_progress)
    render_progress.succeed_task(task)
    console.print(render_progress)

    assert output.getvalue() == snapshot


def test_indeterminate_progress_has_no_bar() -> None:
    """Do not imply measurable progress for tasks such as transcoding."""
    output = io.StringIO()
    console = rich.console.Console(file=output, width=100, color_system=None)
    render_progress = progress.IndeterminateProgress(console)
    task = render_progress.add_task('Transcoding "Song"')
    render_progress.start_task(task)
    console.print(render_progress)

    assert "━" not in output.getvalue()


@pytest.mark.asyncio
async def test_monitor_reports_rendered_audio_fraction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Report readable output duration as a fraction of the render bounds."""
    monkeypatch.setattr(progress, "_rendered_duration", lambda _output: 50.0)
    updated = asyncio.Event()
    reported: list[float] = []

    def update(completed: float) -> None:
        reported.append(completed)
        updated.set()

    task = asyncio.create_task(
        progress.monitor_render_progress(
            tmp_path / "render.wav",
            200.0,
            update,
        )
    )
    await asyncio.wait_for(updated.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert reported == [0.25]


def test_rendered_duration_reads_latest_packet_for_unfinalized_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Track formats whose duration remains unavailable until the file is finalized."""
    output = tmp_path / "render.flac"
    output.touch()
    ffprobe = mock.Mock(
        side_effect=[
            subprocess.CompletedProcess([], 0, "N/A\n", ""),
            subprocess.CompletedProcess([], 0, "12.0,0.5\n", ""),
        ]
    )
    monkeypatch.setattr(progress, "_ffprobe", ffprobe)

    assert progress._rendered_duration(output) == 12.5
