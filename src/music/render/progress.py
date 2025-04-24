"""Custom `rich.progress.Progress`."""

from typing import override

import rich.console
import rich.progress
import rich.table


class Progress:
    """Wrap `rich.progress.Progress` with just the methods needed for render.

    * Hardcode columns
    * Customize the success and failure indicators of individual tasks
        * Set a runtime property on `rich.progress.Task`, `status`, to coordinate with `_SpinnerColumn`, below
    * Simplify the "amount" of progress to use `rich.progress.Progress`
        * The Reaper API does not expose render progress, so to use `rich.progress.Progress`, it's only 0 or 1
    """

    def __init__(self) -> None:
        """Initialize `rich.progress.Progress` with hardcoded columns."""
        self._progress = rich.progress.Progress(
            _SpinnerColumn(),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
        )

    def __rich__(self) -> rich.console.RenderableType:
        """Make the progress bar renderable."""
        return self._progress.__rich__()

    def add_task(self, description: str) -> rich.progress.TaskID:
        """Add a task to the progress bar."""
        return self._progress.add_task(description, start=False, total=1)

    def fail_task(self, task_id: rich.progress.TaskID) -> None:
        """Finish a task, marking it failed."""
        with self._progress._lock:
            task = self._progress._tasks[task_id]
            task.status = "failed"  # type: ignore[attr-defined]

        self._progress.update(task_id, advance=1)

    def start_task(self, task_id: rich.progress.TaskID) -> None:
        """Start a task."""
        self._progress.start_task(task_id)

    def succeed_task(self, task_id: rich.progress.TaskID) -> None:
        """Finish a task, marking it succeeded."""
        with self._progress._lock:
            task = self._progress._tasks[task_id]
            task.status = "success"  # type: ignore[attr-defined]

        self._progress.update(task_id, advance=1)


class _SpinnerColumn(rich.progress.SpinnerColumn):
    """Vary the "finished" text per task by providing our own text."""

    @override
    def render(self, task: rich.progress.Task) -> rich.console.RenderableType:
        try:
            status = task.status  # type: ignore[attr-defined]
        except AttributeError:
            status = ""
        if status == "success":
            return "[green]✓[/green]"
        elif status:
            return "[red]✗[/red]"

        return super().render(task)
