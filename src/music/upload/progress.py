"""Custom `rich.progress.Progress`."""

from typing import cast, override

import rich.console
import rich.progress
import rich.table


class DeterminateProgress:
    """Wrap `rich.progress.Progress` with just the methods needed for this subdirectory.

    * Hardcode columns
    * Customize the success and failure indicators of individual tasks
        * Monkeypatch a runtime property `status` on `rich.progress.Task` to coordinate with `_SpinnerColumn`, below
    """

    def __init__(self, console: rich.console.Console) -> None:
        """Initialize `rich.progress.Progress` with hardcoded columns."""
        self.console = console
        self._progress = rich.progress.Progress(
            _SpinnerColumn(),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
            rich.progress.BarColumn(),
            rich.progress.DownloadColumn(),
            console=self.console,
        )

    def __rich__(self) -> rich.console.RenderableType:
        """Make the progress bar renderable."""
        return self._progress.__rich__()

    def add_task(self, description: str, total: int) -> rich.progress.TaskID:
        """Add a task to the progress bar."""
        return self._progress.add_task(description, start=False, total=total)

    def advance(self, task_id: rich.progress.TaskID, steps: int) -> None:
        """Advance task by a number of steps."""
        with self._progress._lock:
            self._progress.advance(task_id, advance=steps)
            task = self._progress._tasks[task_id]
            remaining = cast(float, task.remaining)  # this class always sets a total
            if remaining <= 0:
                task.status = "success"  # type: ignore[attr-defined]

    def fail_task(self, task_id: rich.progress.TaskID, reason: str) -> None:
        """Finish a task, marking it failed."""
        with self._progress._lock:
            task = self._progress._tasks[task_id]
            task.status = "failed"  # type: ignore[attr-defined]
            self._progress.update(
                task_id,
                description=f"{task.description} [red]({reason})",
            )
            self._progress.stop_task(task_id)

    def skip_task(self, task_id: rich.progress.TaskID, reason: str) -> None:
        """Finish a task, marking it skipped."""
        with self._progress._lock:
            task = self._progress._tasks[task_id]
            task.status = "skipped"  # type: ignore[attr-defined]
            self._progress.update(
                task_id,
                description=f"{task.description} [yellow]({reason})",
            )
            self._progress.stop_task(task_id)

    def start_task(self, task_id: rich.progress.TaskID) -> None:
        """Start a task."""
        self._progress.start_task(task_id)


class _SpinnerColumn(rich.progress.SpinnerColumn):
    """Vary the "finished" text per task by providing our own text.

    Read the monkeypatched property `status` on `rich.progress.Task` to coordinate with `Progress`, above.
    """

    @override
    def render(self, task: rich.progress.Task) -> rich.console.RenderableType:
        try:
            status = task.status  # type: ignore[attr-defined]
        except AttributeError:
            status = ""
        if status == "success":
            return "[green]✓[/green]"
        elif status == "skipped":
            return "[yellow]⚠[/yellow]"
        elif status == "failed":
            return "[red]✗[/red]"

        return super().render(task)
