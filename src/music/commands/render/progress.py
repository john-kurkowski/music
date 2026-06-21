"""Custom render progress reporting."""

import asyncio
import contextlib
import math
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import override

import rich.console
import rich.progress
import rich.table


class _TaskProgress:
    """Share status behavior between determinate and indeterminate tasks."""

    def __init__(
        self,
        console: rich.console.Console,
        *columns: rich.progress.ProgressColumn,
    ) -> None:
        """Initialize `rich.progress.Progress` with the given columns."""
        self.console = console
        self._progress = rich.progress.Progress(
            *columns,
            console=self.console,
        )

    def __rich__(self) -> rich.console.RenderableType:
        """Make the progress bar renderable."""
        return self._progress.__rich__()

    def fail_task(self, task_id: rich.progress.TaskID, reason: str) -> None:
        """Finish a task, marking it failed."""
        with self._progress._lock:
            task = self._progress._tasks[task_id]
            task.fields["status"] = "failed"
            self._progress.update(
                task_id,
                description=f"{task.description} [red]({reason})",
            )
            self._progress.stop_task(task_id)

    def start_task(self, task_id: rich.progress.TaskID) -> None:
        """Start a task."""
        self._progress.start_task(task_id)

    def _mark_succeeded(self, task_id: rich.progress.TaskID) -> None:
        """Set a task's shared success status."""
        with self._progress._lock:
            task = self._progress._tasks[task_id]
            task.fields["status"] = "success"


class RenderProgress(_TaskProgress):
    """Track measurable render tasks with persistent progress bars."""

    def __init__(self, console: rich.console.Console) -> None:
        """Initialize render progress columns."""
        super().__init__(
            console,
            _SpinnerColumn(),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
            rich.progress.BarColumn(),
        )

    def add_task(self, description: str) -> rich.progress.TaskID:
        """Add a render task with fractional progress from zero to one."""
        return self._progress.add_task(description, start=False, total=1)

    def update_task(self, task_id: rich.progress.TaskID, completed: float) -> None:
        """Report a task's completion as a fraction from zero to one."""
        self._progress.update(task_id, completed=completed, total=1)

    def succeed_task(self, task_id: rich.progress.TaskID) -> None:
        """Finish a task, marking it succeeded."""
        self._mark_succeeded(task_id)
        self._progress.update(task_id, completed=1, total=1)


class IndeterminateProgress(_TaskProgress):
    """Track tasks whose intermediate completion cannot be measured."""

    def __init__(self, console: rich.console.Console) -> None:
        """Initialize indeterminate progress columns."""
        super().__init__(
            console,
            _SpinnerColumn(),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
        )

    def add_task(self, description: str) -> rich.progress.TaskID:
        """Add an indeterminate task."""
        return self._progress.add_task(description, start=False, total=None)

    def succeed_task(self, task_id: rich.progress.TaskID) -> None:
        """Finish a task, marking it succeeded."""
        self._mark_succeeded(task_id)
        self._progress.stop_task(task_id)


class _SpinnerColumn(rich.progress.SpinnerColumn):
    """Vary the "finished" text per task by providing our own text.

    Read task fields set by the progress wrappers.
    """

    @override
    def render(self, task: rich.progress.Task) -> rich.console.RenderableType:
        status = task.fields.get("status")
        if status == "success":
            return "[green]✓[/green]"
        elif status == "failed":
            return "[red]✗[/red]"

        return super().render(task)


class ProgressProjection:
    """Smooth display progress between authoritative render measurements.

    Authoritative measurements (rendered-audio duration) arrive only every probe
    interval. To move the bar near the console refresh rate, this state derives a
    render rate from the two most recent valid measurements and projects forward
    from the latest one. It is deliberately independent from Rich and takes an
    injectable monotonic clock so projection is deterministic under test.

    Projected values are display-only: real measurements stay authoritative, but
    displayed progress never moves backward, stays below one, and stops advancing
    once measurements go stale. Reaching exactly one and preserving progress on
    failure are the Rich layer's responsibility, not this state's.
    """

    def __init__(
        self,
        total_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        stale_threshold: float = 2.0,
        ceiling: float = 0.99,
        max_rate: float = 1000.0,
    ) -> None:
        """Initialize projection bounds and the two-sample measurement window."""
        self._total = total_seconds
        self._clock = clock
        self._stale_threshold = stale_threshold
        self._ceiling = ceiling
        self._max_rate = max_rate
        # The two most recent valid (rendered duration, observation time) samples.
        self._samples: list[tuple[float, float]] = []
        self._last_displayed = 0.0

    def measure(self, duration: float | None) -> None:
        """Record an authoritative rendered-duration measurement, if usable.

        Malformed, out-of-range, decreasing, or implausibly fast samples are
        ignored so they cannot corrupt the observed rate.
        """
        if duration is None or not math.isfinite(duration) or duration < 0:
            return

        now = self._clock()
        if self._samples:
            prev_duration, prev_time = self._samples[-1]
            delta_duration = duration - prev_duration
            delta_time = now - prev_time
            if delta_duration < 0 or delta_time <= 0:
                return
            if delta_duration / delta_time > self._max_rate:
                return

        self._samples.append((duration, now))
        self._samples = self._samples[-2:]

    def fraction(self) -> float:
        """Return the current display fraction in the range zero through one.

        Monotonic across calls: a projection that has run ahead of a trailing
        measurement holds its position rather than regressing.
        """
        clamped = min(max(self._project(), 0.0), self._ceiling)
        self._last_displayed = max(self._last_displayed, clamped)
        return self._last_displayed

    def _project(self) -> float:
        if not self._samples:
            return 0.0

        latest_duration, latest_time = self._samples[-1]
        if len(self._samples) < 2:
            return latest_duration / self._total

        prev_duration, prev_time = self._samples[-2]
        age = self._clock() - latest_time
        if age > self._stale_threshold:
            return latest_duration / self._total

        rate = (latest_duration - prev_duration) / (latest_time - prev_time)
        return (latest_duration + rate * age) / self._total


async def monitor_render_progress(
    output: Path,
    total_seconds: float,
    update: Callable[[float], None],
    *,
    poll_interval: float = 0.5,
    refresh_interval: float = 0.1,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Report progress from the duration of REAPER's actively written output.

    A measurement loop probes the authoritative output duration every
    `poll_interval`. A separate display loop projects between measurements and
    invokes `update` near the console refresh rate without probing more often.
    """
    if total_seconds <= 0:
        return

    projection = ProgressProjection(total_seconds, clock=clock)

    async def measure_loop() -> None:
        while True:
            duration = await asyncio.to_thread(_rendered_duration, output)
            projection.measure(duration)
            await asyncio.sleep(poll_interval)

    async def display_loop() -> None:
        while True:
            update(projection.fraction())
            await asyncio.sleep(refresh_interval)

    measure = asyncio.create_task(measure_loop())
    display = asyncio.create_task(display_loop())
    try:
        await asyncio.gather(measure, display)
    finally:
        for task in (measure, display):
            task.cancel()
        for task in (measure, display):
            with contextlib.suppress(asyncio.CancelledError):
                await task


def _rendered_duration(output: Path) -> float | None:
    """Return the readable duration of one current render output, if available."""
    candidates = [output] if output.is_file() else list(output.glob("**/*"))
    fil = next((candidate for candidate in candidates if candidate.is_file()), None)
    if fil is None:
        return None

    process = _ffprobe(
        [
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
        ],
        fil,
    )
    if process.returncode:
        return None

    match = re.search(r"\d+(?:\.\d+)?", process.stdout)
    if match:
        return float(match.group())

    # FLAC does not publish its total duration until REAPER finalizes the file.
    # The latest readable packet timestamp still tracks the rendered timeline.
    process = _ffprobe(
        [
            "-select_streams",
            "a:0",
            "-show_entries",
            "packet=pts_time,duration_time",
            "-of",
            "csv=p=0",
        ],
        fil,
    )
    if process.returncode:
        return None

    last_line = next(
        (line for line in reversed(process.stdout.splitlines()) if line), None
    )
    if last_line is None:
        return None

    try:
        timestamp, duration = (float(value) for value in last_line.split(","))
    except ValueError:
        return None
    return timestamp + duration


def _ffprobe(args: list[str], fil: Path) -> subprocess.CompletedProcess[str]:
    """Run a quiet ffprobe query against a render output."""
    return subprocess.run(
        ["ffprobe", "-v", "error", *args, fil],
        capture_output=True,
        text=True,
    )
