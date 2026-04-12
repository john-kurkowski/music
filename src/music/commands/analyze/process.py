"""Analyze processing for Reaper project files."""

import base64
import re
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
class PluginWarning:
    """A concise warning associated with a single plugin instance."""

    symbol: str
    detail: str = ""

    def display(self) -> str:
        """Render a compact table cell for the warning."""
        return self.symbol if not self.detail else f"{self.symbol} {self.detail}"


@dataclass(frozen=True)
class PluginRow:
    """A plugin instance together with any row-level warning indicators."""

    track_number: int
    track_name: str
    plugin_name: str
    warnings: tuple[PluginWarning, ...] = ()


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

    def iter_plugin_rows(self) -> Iterator[PluginRow]:
        """Return plugins with track locations and compact row warnings."""
        for track_number, track in enumerate(
            self.parsed_project.findall(".//TRACK"), start=1
        ):
            track_name = _track_name(track)
            for plugin in _track_plugins(track):
                yield PluginRow(
                    track_number=track_number,
                    track_name=track_name,
                    plugin_name=_plugin_name(plugin),
                    warnings=tuple(
                        _plugin_row_warnings(track_number, track_name, plugin)
                    ),
                )

    def iter_warnings(self) -> Iterator[str]:
        """Return warnings from the parsed project."""
        for track_number, track in enumerate(
            self.parsed_project.findall(".//TRACK"), start=1
        ):
            track_name = _track_name(track)
            for plugin in _track_plugins(track):
                if warning := _missing_plugin_warning(track_number, track_name, plugin):
                    yield warning
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


def _track_plugins(track: rpp.Element) -> Iterator[rpp.Element]:
    """Yield saved plugin chunks from a track in a consistent order."""
    yield from (
        plugin
        for tag in _PLUGIN_TAGS
        for plugin in track.findall(f".//{tag}")
        if hasattr(plugin, "tag")
    )


def _missing_plugin_warning(
    track_number: int, track_name: str, plugin: rpp.Element
) -> str | None:
    """Return a warning when a saved plugin cannot be located locally."""
    match plugin.tag:
        case "AU":
            if _is_builtin_apple_au(plugin):
                return None
            if _saved_plugin_basename(plugin) not in _installed_au_names():
                return _warning_message(track_number, track_name, plugin)
        case "JS":
            if _jsfx_file(str(plugin.attrib[0])) is None:
                return _warning_message(track_number, track_name, plugin)
        case "VST":
            if _is_builtin_cockos_vst(plugin):
                return None
            if _saved_plugin_basename(plugin) not in _installed_vst_names():
                return _warning_message(track_number, track_name, plugin)
    return None


def _plugin_row_warnings(
    track_number: int, track_name: str, plugin: rpp.Element
) -> Iterator[PluginWarning]:
    """Return compact warning indicators for a plugin table row."""
    if _missing_plugin_warning(track_number, track_name, plugin):
        yield PluginWarning(symbol="❌", detail="Not installed")

    if arcade.is_arcade_plugin(plugin):
        for symbol, detail in arcade.iter_plugin_warnings(
            track_number, track_name, plugin
        ):
            yield PluginWarning(symbol=symbol, detail=detail)


def _warning_message(track_number: int, track_name: str, plugin: rpp.Element) -> str:
    """Format a missing-plugin warning for user display."""
    return (
        f'Plugin "{_plugin_name(plugin)}" on track {track_number} "{track_name}" '
        "does not appear to be installed locally"
    )


def _saved_plugin_basename(plugin: rpp.Element) -> str:
    """Normalize a saved plugin label for installation lookup."""
    name = str(plugin.attrib[0])
    name = re.sub(r"^[^:]+:\s*", "", name)
    name = re.sub(r"(?:\s+\([^()]*\))+$", "", name).strip()
    return _normalize_plugin_basename(name)


def _is_builtin_apple_au(plugin: rpp.Element) -> bool:
    """Return whether a saved AU label refers to an Apple-built system effect."""
    return str(plugin.attrib[0]).endswith("(Apple)")


def _is_builtin_cockos_vst(plugin: rpp.Element) -> bool:
    """Return whether a saved VST label refers to a bundled Cockos plugin."""
    return str(plugin.attrib[0]).endswith("(Cockos)")


def _normalize_plugin_basename(name: str) -> str:
    """Normalize plugin names from saved project text and install filenames."""
    normalized = name.strip()
    normalized = re.sub(r"\.vst(?:\.dylib(?:\.rpl)?)?$", "", normalized, flags=re.I)
    normalized = re.sub(r"\.(?:component|vst3|clap)$", "", normalized, flags=re.I)
    normalized = re.sub(r"\s+(?:audio|midi)$", "", normalized, flags=re.I)
    normalized = normalized.replace("_x64", "")
    return normalized.casefold()


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


@cache
def _installed_au_names() -> frozenset[str]:
    """Return installed AU plugin basenames from standard macOS locations."""
    return frozenset(
        _normalize_plugin_basename(component.stem)
        for root in _au_search_paths()
        for component in root.glob("*.component")
    )


def _au_search_paths() -> tuple[Path, ...]:
    """Return local directories where Audio Unit plugins may be installed."""
    return (
        Path.home() / "Library/Audio/Plug-Ins/Components",
        Path("/Library/Audio/Plug-Ins/Components"),
    )


@cache
def _installed_vst_names() -> frozenset[str]:
    """Return installed VST/VST3 plugin basenames from common macOS locations."""
    names = {
        _normalize_plugin_basename(plugin.stem)
        for plugin in _installed_vst_plugins()
        if plugin.suffix.casefold() == ".vst"
    }
    names.update(
        _normalize_plugin_basename(plugin.stem)
        for plugin in _installed_vst_plugins()
        if plugin.suffix.casefold() == ".vst3"
    )
    return frozenset(names)


def _installed_vst_plugins() -> tuple[Path, ...]:
    """Return installed VST bundle paths, including nested shell layouts."""
    plugins: list[Path] = []
    for root in _vst_search_paths():
        if not root.exists():
            continue
        plugins.extend(root.rglob("*.vst"))
        plugins.extend(root.rglob("*.vst3"))
    return tuple(plugins)


def _vst_search_paths() -> tuple[Path, ...]:
    """Return local directories where VST/VST3 plugins may be installed."""
    return (
        Path.home() / "Library/Audio/Plug-Ins/VST",
        Path("/Library/Audio/Plug-Ins/VST"),
        Path.home() / "Library/Audio/Plug-Ins/VST3",
        Path("/Library/Audio/Plug-Ins/VST3"),
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
