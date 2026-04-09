"""Analyze command."""

import base64
from collections.abc import Iterator
from functools import cache
from pathlib import Path

import click
import rich.console
import rich.rule
import rpp  # type: ignore[import-untyped]

from music.utils import project

_PLUGIN_TAGS = ("AU", "CLAP", "DX", "JS", "LV2", "VST")


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
        if i > 0:
            console.print()
        console.print(rich.rule.Rule(f"[bold cyan]{project_file.stem}[/bold cyan]"))
        if plugins:
            for plugin in sorted(iter_plugin_names(project_file), key=str.casefold):
                console.print(f"  {plugin}")
        else:
            for setting in iter_encoded_settings(project_file):
                console.print(f"  {setting}")


def _project_file(project_path: Path) -> Path:
    """Normalize either a project directory or an .rpp file into a file path."""
    return (
        project_path
        if project_path.is_file()
        else project_path / f"{project_path.name}.rpp"
    )


def _iter_plugins(project_files: list[Path]) -> Iterator[str]:
    """List plugin names used across the given project files."""
    for project_file in project_files:
        yield from iter_plugin_names(project_file)


def iter_encoded_settings(project_fil: Path) -> Iterator[str]:
    """Parse a Reaper project and return plugin settings encoded in base64."""
    parsed_project = _parse_project(project_fil)

    plugins = (
        plugin for tag in _PLUGIN_TAGS for plugin in parsed_project.findall(f".//{tag}")
    )
    for plugin in plugins:
        successful_decodes = (
            decode for child in plugin.children if (decode := b64_ascii(child))
        )
        yield from successful_decodes


def iter_plugin_names(project_fil: Path) -> Iterator[str]:
    """Parse a Reaper project and return plugin names."""
    parsed_project = _parse_project(project_fil)

    for tag in _PLUGIN_TAGS:
        for plugin in parsed_project.findall(f".//{tag}"):
            yield _plugin_name(plugin)


def _plugin_name(plugin: rpp.Element) -> str:
    """Render a plugin's saved RPP attributes as a display name."""
    name = str(plugin.attrib[0])
    if plugin.tag == "JS":
        return f"JS: {_jsfx_display_name(name)}"
    return name


def _jsfx_display_name(path: str) -> str:
    """Resolve a JSFX script path to a human-readable display name."""
    if jsfx_file := _jsfx_file(path):
        if desc := _jsfx_desc(jsfx_file):
            return desc

    return Path(path).stem.replace("_", " ")


@cache
def _jsfx_file(path: str) -> Path | None:
    """Find the installed JSFX file for a saved Reaper script path."""
    for root in _jsfx_search_paths():
        candidate = root / path
        if candidate.is_file():
            return candidate
    return None


def _jsfx_search_paths() -> tuple[Path, ...]:
    """Return local directories where REAPER JSFX files may be installed."""
    return (
        Path.home() / "Library/Application Support/REAPER/Effects",
        Path("/Applications/REAPER.app/Contents/InstallFiles/Effects"),
    )


def _jsfx_desc(jsfx_file: Path) -> str | None:
    """Return the last declared JSFX desc label, if present."""
    desc = None
    for line in _jsfx_lines(jsfx_file):
        if line.startswith("desc:"):
            desc = line.removeprefix("desc:").strip()
    return desc


def _jsfx_lines(jsfx_file: Path) -> list[str]:
    """Read a JSFX file, tolerating legacy REAPER effect encodings."""
    return jsfx_file.read_text(encoding="utf-8", errors="replace").splitlines()


def _parse_project(project_fil: Path) -> rpp.Element:
    """Parse a Reaper project file."""
    with open(project_fil) as fil:
        return rpp.load(fil)


def b64_ascii(s: str) -> str | None:
    """Try to decode a base64 string.

    Many VST settings are encoded in Reaper as base64. Return None if it is not
    one of those strings.
    """
    try:
        return base64.b64decode(s).decode("ascii")
    except UnicodeDecodeError:
        return None
