"""Analyze processing for Reaper project files."""

import base64
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import rpp  # type: ignore[import-untyped]

from .output import arcade

_PLUGIN_TAGS = ("AU", "CLAP", "DX", "JS", "LV2", "VST")


@dataclass(frozen=True)
class PluginInstance:
    """A plugin instance and the track it belongs to."""

    track_number: int
    track_name: str
    plugin_name: str


@dataclass(frozen=True)
class AnalyzeProject:
    """A parsed Reaper project file with analyze-oriented query methods."""

    project_file: Path
    parsed_project: rpp.Element

    @classmethod
    def from_project_file(cls, project_file: Path) -> "AnalyzeProject":
        """Parse a Reaper `.rpp` project file once for repeated analysis."""
        with open(project_file) as fil:
            parsed_project = rpp.load(fil)
        return cls(project_file=project_file, parsed_project=parsed_project)

    def iter_encoded_settings(self) -> Iterator[str]:
        """Return plugin settings encoded in base64 from the parsed project."""
        plugins = (
            plugin
            for tag in _PLUGIN_TAGS
            for plugin in self.parsed_project.findall(f".//{tag}")
        )
        for plugin in plugins:
            if arcade_state := arcade.arcade_state_xml(plugin):
                yield arcade_state.decode("utf-8")
                continue

            raw = "".join(
                child.strip() for child in plugin.children if isinstance(child, str)
            )
            if decode := b64_ascii(raw):
                yield decode

    def iter_plugin_names(self) -> Iterator[str]:
        """Return plugin names from the parsed project."""
        yield from (plugin.plugin_name for plugin in self.iter_plugin_instances())

    def iter_plugin_instances(self) -> Iterator[PluginInstance]:
        """Return plugins with their track locations from the parsed project."""
        for track_number, track in enumerate(
            self.parsed_project.findall(".//TRACK"), start=1
        ):
            track_name = _track_name(track)
            for tag in _PLUGIN_TAGS:
                for plugin in track.findall(f".//{tag}"):
                    yield PluginInstance(
                        track_number=track_number,
                        track_name=track_name,
                        plugin_name=_plugin_name(plugin),
                    )

    def iter_warnings(self) -> Iterator[str]:
        """Return plugin warnings from the parsed project."""
        for track_number, track in enumerate(
            self.parsed_project.findall(".//TRACK"), start=1
        ):
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
                if arcade.is_arcade_plugin(plugin):
                    yield from arcade.iter_warnings(track_number, track_name, plugin)


def _plugin_name(plugin: rpp.Element) -> str:
    """Render a plugin's saved Reaper plugin chunk attributes as a display name."""
    name = str(plugin.attrib[0])
    if plugin.tag == "JS":
        return f"JS: {_jsfx_display_name(name)}"
    return name


def _track_name(track: rpp.Element) -> str:
    """Return a track's saved Reaper name, if present."""
    for child in track.children:
        if isinstance(child, list) and child and child[0] == "NAME":
            return str(child[1])
    return ""


def _jsfx_display_name(path: str) -> str:
    """Resolve a Reaper JSFX script path to a human-readable display name."""
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


def b64_ascii(s: str) -> str | None:
    """Try to decode a base64 string from a Reaper plugin chunk."""
    try:
        return base64.b64decode(s).decode("ascii")
    except UnicodeDecodeError:
        return None
