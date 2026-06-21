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


class _FakeClock:
    """Drive `ProgressProjection` with explicit, controllable monotonic times."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_projection_advances_linearly_between_two_measurements() -> None:
    """Project forward at the observed render rate once two samples exist."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock)

    clock.now = 0.0
    projection.measure(10.0)
    clock.now = 1.0
    projection.measure(20.0)  # 10 rendered seconds per wall-clock second

    assert projection.fraction() == 0.20
    clock.now = 1.5
    assert projection.fraction() == 0.25  # 20 + 10 * 0.5 = 25 of 100


def test_single_measurement_does_not_interpolate() -> None:
    """Hold at the measured value until a second sample establishes a rate."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock)

    clock.now = 0.0
    projection.measure(10.0)

    assert projection.fraction() == 0.10
    clock.now = 5.0
    assert projection.fraction() == 0.10


def test_projection_never_regresses_when_measurement_trails() -> None:
    """Hold a projection that has run ahead of a slower authoritative sample."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock)

    clock.now = 0.0
    projection.measure(10.0)
    clock.now = 1.0
    projection.measure(30.0)  # rate 20/s
    clock.now = 1.5
    assert projection.fraction() == 0.40  # 30 + 20 * 0.5 = 40

    clock.now = 2.0
    projection.measure(35.0)  # behind the displayed 0.40
    assert projection.fraction() == 0.40


def test_projection_freezes_when_measurements_become_stale() -> None:
    """Stop advancing once the latest measurement passes the stale threshold."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock, stale_threshold=2.0)

    clock.now = 0.0
    projection.measure(10.0)
    clock.now = 1.0
    projection.measure(20.0)  # rate 10/s
    clock.now = 3.0
    assert projection.fraction() == 0.40  # 20 + 10 * 2 = 40, age == threshold

    clock.now = 10.0
    assert projection.fraction() == 0.40  # stale: frozen, no further advance


def test_projection_stays_below_one_until_success() -> None:
    """Cap projection below completion; exactly one is reserved for success."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock, ceiling=0.99)

    clock.now = 0.0
    projection.measure(10.0)
    clock.now = 1.0
    projection.measure(60.0)  # rate 50/s
    clock.now = 2.0

    assert projection.fraction() == 0.99  # 60 + 50 * 1 = 110 -> clamped


def test_malformed_measurement_does_not_corrupt_rate() -> None:
    """Ignore a missing measurement without disturbing the observed rate."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock)

    clock.now = 0.0
    projection.measure(10.0)
    clock.now = 1.0
    projection.measure(20.0)  # rate 10/s
    clock.now = 1.5
    projection.measure(None)
    clock.now = 2.0

    assert projection.fraction() == 0.30  # 20 + 10 * 1 = 30


def test_decreasing_measurement_does_not_corrupt_rate() -> None:
    """Ignore a sample that moves backward in rendered duration."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock)

    clock.now = 0.0
    projection.measure(10.0)
    clock.now = 1.0
    projection.measure(20.0)  # rate 10/s
    clock.now = 1.5
    projection.measure(5.0)
    clock.now = 2.0

    assert projection.fraction() == 0.30


def test_out_of_range_measurement_does_not_corrupt_rate() -> None:
    """Ignore a negative rendered-duration reading."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock)

    clock.now = 0.0
    projection.measure(10.0)
    clock.now = 1.0
    projection.measure(20.0)  # rate 10/s
    clock.now = 1.5
    projection.measure(-5.0)
    clock.now = 2.0

    assert projection.fraction() == 0.30


def test_implausible_measurement_does_not_corrupt_rate() -> None:
    """Reject a sample whose implied rate exceeds the plausibility bound."""
    clock = _FakeClock()
    projection = progress.ProgressProjection(100.0, clock=clock, max_rate=1000.0)

    clock.now = 0.0
    projection.measure(10.0)
    clock.now = 1.0
    projection.measure(20.0)  # rate 10/s
    clock.now = 1.001
    projection.measure(20000.0)  # ~2e7 rendered seconds per wall-clock second
    clock.now = 2.0

    assert projection.fraction() == 0.30


def test_succeed_task_reports_exactly_complete() -> None:
    """Mark a determinate render fully complete on success."""
    console = rich.console.Console(file=io.StringIO(), width=100, color_system=None)
    render_progress = progress.RenderProgress(console)
    task = render_progress.add_task('Rendering "Song"')
    render_progress.start_task(task)
    render_progress.update_task(task, 0.4)
    render_progress.succeed_task(task)

    completed = next(
        t.completed for t in render_progress._progress.tasks if t.id == task
    )
    assert completed == 1.0


def test_fail_task_preserves_last_displayed_progress() -> None:
    """Keep the last displayed fraction when a render fails."""
    console = rich.console.Console(file=io.StringIO(), width=100, color_system=None)
    render_progress = progress.RenderProgress(console)
    task = render_progress.add_task('Rendering "Song"')
    render_progress.start_task(task)
    render_progress.update_task(task, 0.4)
    render_progress.fail_task(task, "boom")

    completed = next(
        t.completed for t in render_progress._progress.tasks if t.id == task
    )
    assert completed == 0.4


@pytest.mark.asyncio
async def test_monitor_reports_rendered_audio_fraction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Report readable output duration as a fraction of the render bounds."""
    monkeypatch.setattr(progress, "_rendered_duration", lambda _output: 50.0)
    reached = asyncio.Event()
    reported: list[float] = []

    def update(completed: float) -> None:
        reported.append(completed)
        if completed == 0.25:
            reached.set()

    task = asyncio.create_task(
        progress.monitor_render_progress(
            tmp_path / "render.wav",
            200.0,
            update,
        )
    )
    await asyncio.wait_for(reached.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert reported[-1] == 0.25  # one sample: held at the measured value
    assert reported == sorted(reported)  # never regresses


@pytest.mark.asyncio
async def test_display_refreshes_do_not_increase_probe_frequency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep authoritative probing on the slow loop, independent of display refresh."""
    probes = 0

    def rendered_duration(_output: Path) -> float:
        nonlocal probes
        probes += 1
        return 50.0

    monkeypatch.setattr(progress, "_rendered_duration", rendered_duration)
    updates = 0

    def update(_completed: float) -> None:
        nonlocal updates
        updates += 1

    task = asyncio.create_task(
        progress.monitor_render_progress(
            tmp_path / "render.wav",
            200.0,
            update,
            poll_interval=0.1,
            refresh_interval=0.01,
        )
    )
    await asyncio.sleep(0.25)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Display refreshes ~10x as often as probes, so it must outpace probing
    # while the probe count stays bounded by the slow poll interval.
    assert updates > probes
    assert probes <= 5


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
