"""Analyze command."""

import base64
import os
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import click
import rich.console
import rich.rule
import rich.table
import rpp  # type: ignore[import-untyped]

from music.utils import project

_PLUGIN_TAGS = ("AU", "CLAP", "DX", "JS", "LV2", "VST")
_MAX_SETTING_PREVIEW_CHARS = 240


@dataclass(frozen=True)
class PluginInstance:
    """A plugin instance and the track it belongs to."""

    track_number: int
    track_name: str
    plugin_name: str


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
        for warning in iter_warnings(project_file):
            console.print(f"  [yellow]Warning:[/yellow] {warning}")
        if plugins:
            console.print(_plugins_table(project_file))
        else:
            for setting in iter_encoded_settings(project_file):
                console.print(f"  {_display_setting(setting)}")


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


def _plugins_table(project_file: Path) -> rich.table.Table:
    """Render plugin instances for a project as a table."""
    table = rich.table.Table(show_header=True)
    table.add_column("Plugin")
    table.add_column("Track #", justify="right")
    table.add_column("Track Name")

    plugins = sorted(
        iter_plugin_instances(project_file),
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


def iter_encoded_settings(project_fil: Path) -> Iterator[str]:
    """Parse a Reaper project and return plugin settings encoded in base64."""
    parsed_project = _parse_project(project_fil)

    plugins = (
        plugin for tag in _PLUGIN_TAGS for plugin in parsed_project.findall(f".//{tag}")
    )
    for plugin in plugins:
        if arcade_state := _arcade_state_xml(plugin):
            yield arcade_state.decode("utf-8")
            continue

        raw = "".join(
            child.strip() for child in plugin.children if isinstance(child, str)
        )
        if decode := b64_ascii(raw):
            yield decode


def iter_plugin_names(project_fil: Path) -> Iterator[str]:
    """Parse a Reaper project and return plugin names."""
    yield from (plugin.plugin_name for plugin in iter_plugin_instances(project_fil))


def iter_plugin_instances(project_fil: Path) -> Iterator[PluginInstance]:
    """Parse a Reaper project and return plugins with their track locations."""
    parsed_project = _parse_project(project_fil)

    for track_number, track in enumerate(parsed_project.findall(".//TRACK"), start=1):
        track_name = _track_name(track)
        for tag in _PLUGIN_TAGS:
            for plugin in track.findall(f".//{tag}"):
                yield PluginInstance(
                    track_number=track_number,
                    track_name=track_name,
                    plugin_name=_plugin_name(plugin),
                )


def _plugin_name(plugin: rpp.Element) -> str:
    """Render a plugin's saved RPP attributes as a display name."""
    name = str(plugin.attrib[0])
    if plugin.tag == "JS":
        return f"JS: {_jsfx_display_name(name)}"
    return name


def _track_name(track: rpp.Element) -> str:
    """Return a track's saved name, if present."""
    for child in track.children:
        if isinstance(child, list) and child and child[0] == "NAME":
            return str(child[1])
    return ""


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


def _display_setting(setting: str) -> str:
    """Render plugin settings as compact one-line previews."""
    single_line = " ".join(setting.split())
    if len(single_line) <= _MAX_SETTING_PREVIEW_CHARS:
        return single_line

    preview = single_line[:_MAX_SETTING_PREVIEW_CHARS].rstrip()
    truncated = len(single_line) - len(preview)
    return f"{preview}... [{truncated} more chars]"


def iter_warnings(project_fil: Path) -> Iterator[str]:
    """Parse a Reaper project and return plugin warnings."""
    parsed_project = _parse_project(project_fil)

    for track in parsed_project.findall(".//TRACK"):
        track_name = _track_name(track)
        fxchain = next(
            (
                child
                for child in track.children
                if getattr(child, "tag", None) == "FXCHAIN"
            ),
            None,
        )
        if fxchain is None:
            continue

        for plugin in fxchain.children:
            if getattr(plugin, "tag", None) != "AU":
                continue
            if "Arcade" not in str(plugin.attrib[0]):
                continue
            yield from _iter_arcade_warnings(track_name, plugin)


def _parse_project(project_fil: Path) -> rpp.Element:
    """Parse a Reaper project file."""
    with open(project_fil) as fil:
        return rpp.load(fil)


def _iter_arcade_warnings(track_name: str, plugin: rpp.Element) -> Iterator[str]:
    """Inspect an Arcade AU state blob for detectable missing content issues."""
    state = _arcade_state_xml(plugin)
    if state is None:
        return

    root = ET.fromstring(state)
    hyperion_preset = root.find("./Hyperion_Preset/info")
    looper_preset = root.find("./Looper_Preset/info")

    if looper_preset is not None:
        yield from _iter_arcade_looper_warnings(track_name, looper_preset)
    if hyperion_preset is not None:
        yield from _iter_arcade_hyperion_warnings(track_name, root, hyperion_preset)


def _iter_arcade_looper_warnings(track_name: str, preset: ET.Element) -> Iterator[str]:
    """Warn when a sampler/looper Arcade kit is not installed locally."""
    preset_name = preset.attrib.get("name", "Unknown Arcade preset")
    preset_uuid = preset.attrib.get("uuid", "")
    if preset_uuid and preset_uuid not in _arcade_installed_kit_uuids():
        yield (
            f'Arcade sampler "{preset_name}" on track "{track_name}" is not '
            f"installed locally (kit UUID: {preset_uuid})"
        )


def _iter_arcade_hyperion_warnings(
    track_name: str, root: ET.Element, preset: ET.Element
) -> Iterator[str]:
    """Warn when a Hyperion Arcade preset is missing installed source content."""
    preset_name = preset.attrib.get("name", "Unknown Arcade preset")
    installed_sources = _arcade_installed_source_uuids()
    missing_sources = sorted(
        {
            source_uuid
            for source_uuid in (
                elem.attrib.get("LoadedSourceUuid", "")
                for elem in root.findall(".//HyperionLoadedSource")
            )
            if source_uuid and source_uuid not in installed_sources
        }
    )
    has_internal_error = (
        root.find('.//HyperionFxBusSettings[@Name="error"]') is not None
    )

    if missing_sources or has_internal_error:
        detail = f'Arcade instrument "{preset_name}" on track "{track_name}"'
        if missing_sources:
            sources = ", ".join(missing_sources)
            yield f"{detail} references missing source content: {sources}"
        if has_internal_error and missing_sources:
            yield f'{detail} has an internal "error" state in its saved plugin data'


def _arcade_state_xml(plugin: rpp.Element) -> bytes | None:
    """Extract Arcade's nested JUCE state XML from an AU plugin chunk."""
    if "Arcade" not in str(plugin.attrib[0]):
        return None

    raw = "".join(child.strip() for child in plugin.children if isinstance(child, str))
    if not raw:
        return None

    try:
        outer = base64.b64decode(raw)
        plist_start = outer.index(b"<?xml")
        plist_end = outer.index(b"</plist>") + len(b"</plist>")
        outer_plist = outer[plist_start:plist_end]
        juce_state = rpp_plist_value(outer_plist, "jucePluginState")
        if not isinstance(juce_state, bytes):
            return None

        state_start = juce_state.index(b"<?xml")
        state_end = juce_state.index(b"</state_info>") + len(b"</state_info>")
    except (ValueError, KeyError):
        return None
    return juce_state[state_start:state_end]


def _arcade_content_root() -> Path:
    """Return Arcade's content install root, overridable for tests."""
    return Path(
        os.environ.get(
            "ARCADE_CONTENT_ROOT",
            "/Library/Application Support/Output/Arcade/Arcade Content",
        )
    )


def _arcade_db_path() -> Path:
    """Return Arcade's local metadata database, overridable for tests."""
    return Path(
        os.environ.get(
            "ARCADE_DB_PATH",
            "/Library/Application Support/Output/Arcade/local.db",
        )
    )


def _arcade_installed_kit_uuids() -> set[str]:
    """Return the set of Arcade kit UUIDs installed in the local metadata DB."""
    db_path = _arcade_db_path()
    if not db_path.exists():
        return set()

    with closing(sqlite3.connect(db_path)) as con:
        return {uuid for (uuid,) in con.execute("select uuid from kits")}


def _arcade_installed_source_uuids() -> set[str]:
    """Return the set of Arcade instrument source UUIDs in the local metadata DB."""
    db_path = _arcade_db_path()
    if not db_path.exists():
        return set()

    with closing(sqlite3.connect(db_path)) as con:
        return {uuid for (uuid,) in con.execute("select uuid from sound_sources")}


def rpp_plist_value(plist_xml: bytes, key: str) -> object:
    """Look up a plist value by key from a parsed Arcade AU state blob."""
    import plistlib

    return plistlib.loads(plist_xml)[key]


def b64_ascii(s: str) -> str | None:
    """Try to decode a base64 string.

    Many VST settings are encoded in Reaper as base64. Return None if it is not
    one of those strings.
    """
    try:
        return base64.b64decode(s).decode("ascii")
    except UnicodeDecodeError:
        return None
