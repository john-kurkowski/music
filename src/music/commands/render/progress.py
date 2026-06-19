"""Custom render progress reporting."""

import asyncio
import re
import subprocess
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


async def monitor_render_progress(
    output: Path,
    total_seconds: float,
    update: Callable[[float], None],
    *,
    poll_interval: float = 0.5,
) -> None:
    """Report progress from the duration of REAPER's actively written output."""
    if total_seconds <= 0:
        return

    while True:
        duration = await asyncio.to_thread(_rendered_duration, output)
        if duration is not None:
            update(min(duration / total_seconds, 1))
        await asyncio.sleep(poll_interval)


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
