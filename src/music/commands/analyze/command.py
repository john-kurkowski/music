"""Analyze command."""

from pathlib import Path

import click
import rich.console
import rich.rule
import rich.table

from music.commands.analyze import process
from music.utils import project

_MAX_SETTING_PREVIEW_CHARS = 240


@click.command("analyze")
@click.argument(
    "project_paths",
    nargs=-1,
    type=click.Path(dir_okay=True, exists=True, file_okay=True, path_type=Path),
)
@click.option(
    "--plugins",
    is_flag=True,
    help="List plugin names used by the given projects instead of decoded settings.",
)
def main(project_paths: list[Path], plugins: bool) -> None:
    """(alpha) Analyze projects for problems.

    Prints out a project's plugin settings encoded in base64 for human review.
    Sometimes these contain unwanted settings, which are not possible to see by
    looking at a Reaper .rpp file's XML directly.

    Accepts 0 or more PROJECT_PATHS projects. Defaults to the currently open
    project.
    """
    if not project_paths:
        project_paths = [Path(project.ExtendedProject().path)]

    project_files = [_project_file(project_path) for project_path in project_paths]
    console = rich.console.Console()

    for i, project_file in enumerate(project_files):
        analyzed_project = process.AnalyzeProject.from_project_file(project_file)
        if i > 0:
            console.print()
        console.print(rich.rule.Rule(f"[bold cyan]{project_file.stem}[/bold cyan]"))
        for warning in analyzed_project.iter_warnings():
            console.print(f"  [yellow]Warning:[/yellow] {warning}")
        if plugins:
            console.print(_plugins_table(analyzed_project))
        else:
            for setting in analyzed_project.iter_encoded_settings():
                console.print(f"  {_display_setting(setting)}")


def _project_file(project_path: Path) -> Path:
    """Normalize either a project directory or an `.rpp` file into a file path."""
    return (
        project_path
        if project_path.is_file()
        else project_path / f"{project_path.name}.rpp"
    )


def _plugins_table(analyzed_project: process.AnalyzeProject) -> rich.table.Table:
    """Render plugin instances for a project as a table."""
    table = rich.table.Table(show_header=True)
    table.add_column("Plugin")
    table.add_column("Track #", justify="right")
    table.add_column("Track Name")

    plugins = sorted(
        analyzed_project.iter_plugin_instances(),
        key=lambda plugin: (
            plugin.plugin_name.casefold(),
            plugin.track_number,
            plugin.track_name.casefold(),
        ),
    )
    for plugin in plugins:
        table.add_row(
            plugin.plugin_name,
            str(plugin.track_number),
            plugin.track_name or "(unnamed)",
        )

    return table


def _display_setting(setting: str) -> str:
    """Render plugin settings as compact one-line previews."""
    single_line = " ".join(setting.split())
    if len(single_line) <= _MAX_SETTING_PREVIEW_CHARS:
        return single_line

    preview = single_line[:_MAX_SETTING_PREVIEW_CHARS].rstrip()
    truncated = len(single_line) - len(preview)
    return f"{preview}... [{truncated} more chars]"
