"""Analyze processing for Reaper project files."""

import base64
import binascii
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, cast

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
    architecture: str = ""
    mute: bool = False
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
        for track_number, track, track_muted in _iter_tracks_with_mute_state(
            self.parsed_project
        ):
            track_name = _track_name(track)
            for plugin, plugin_bypassed in _track_plugins_with_bypass(track):
                architecture = _plugin_architecture(plugin)
                yield PluginRow(
                    track_number=track_number,
                    track_name=track_name,
                    plugin_name=_plugin_name(plugin),
                    architecture=architecture,
                    mute=track_muted or plugin_bypassed,
                    warnings=tuple(
                        _plugin_row_warnings(
                            track_number, track_name, plugin, architecture
                        )
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
    name = _plugin_label(plugin)
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


def _track_plugins_with_bypass(
    track: rpp.Element,
) -> Iterator[tuple[rpp.Element, bool]]:
    """Yield each saved plugin chunk together with its hard bypass state."""
    for child in track.children:
        if not hasattr(child, "tag") or child.tag != "FXCHAIN":
            continue
        yield from _fxchain_plugins_with_bypass(child)


def _fxchain_plugins_with_bypass(
    fxchain: rpp.Element,
) -> Iterator[tuple[rpp.Element, bool]]:
    """Yield FX chain plugins with the saved bypass flag that precedes them."""
    bypassed = False
    for child in fxchain.children:
        if isinstance(child, list) and child and child[0] == "BYPASS":
            bypassed = _bypass_enabled(child)
            continue
        if hasattr(child, "tag") and child.tag in _PLUGIN_TAGS:
            yield child, bypassed
            bypassed = False


def _iter_tracks_with_mute_state(
    project: rpp.Element,
) -> Iterator[tuple[int, rpp.Element, bool]]:
    """Yield tracks in document order together with inherited mute state."""
    track_number = 0

    def visit(
        track: rpp.Element, parent_muted: bool
    ) -> Iterator[tuple[int, rpp.Element, bool]]:
        nonlocal track_number
        track_number += 1
        track_muted = parent_muted or _track_is_muted(track)
        yield track_number, track, track_muted
        for child in track.children:
            if hasattr(child, "tag") and child.tag == "TRACK":
                yield from visit(child, track_muted)

    for child in project.children:
        if hasattr(child, "tag") and child.tag == "TRACK":
            yield from visit(child, False)


def _track_is_muted(track: rpp.Element) -> bool:
    """Return whether a parsed Reaper track is muted in the saved project state."""
    for child in track.children:
        if isinstance(child, list) and child and child[0] == "MUTESOLO":
            return bool(int(child[1]))
    return False


def _bypass_enabled(bypass: list[str]) -> bool:
    """Return whether a parsed FXCHAIN BYPASS entry hard-disables the next plugin."""
    return len(bypass) > 1 and bool(int(bypass[1]))


def _missing_plugin_warning(
    track_number: int, track_name: str, plugin: rpp.Element
) -> str | None:
    """Return a warning when a saved plugin cannot be located locally."""
    match plugin.tag:
        case "AU":
            if not _audio_units_supported():
                return None
            if _is_builtin_apple_au(plugin):
                return None
            if _saved_plugin_basename(plugin) not in _installed_au_names():
                return _warning_message(track_number, track_name, plugin)
        case "JS":
            if _jsfx_file(_plugin_label(plugin)) is None:
                return _warning_message(track_number, track_name, plugin)
        case "VST":
            if _is_builtin_cockos_vst(plugin):
                return None
            if _saved_plugin_basename(plugin) not in _installed_vst_names():
                return _warning_message(track_number, track_name, plugin)
    return None


def _plugin_row_warnings(
    track_number: int, track_name: str, plugin: rpp.Element, architecture: str
) -> Iterator[PluginWarning]:
    """Return compact warning indicators for a plugin table row."""
    if _missing_plugin_warning(track_number, track_name, plugin):
        yield PluginWarning(symbol="❌", detail="Not installed")

    if architecture == "Intel-only":
        yield PluginWarning(symbol="⚠️", detail="Intel-only")

    if arcade.is_arcade_plugin(plugin):
        for symbol, detail in arcade.iter_plugin_warnings(
            track_number, track_name, plugin
        ):
            yield PluginWarning(symbol=symbol, detail=detail)


def _plugin_architecture(plugin: rpp.Element) -> str:
    """Return a concise CPU architecture label for an installed plugin bundle."""
    bundle = _installed_plugin_bundle(plugin)
    if bundle is None:
        return ""

    binary = _bundle_binary(bundle)
    if binary is None:
        return ""

    archs = _binary_architectures(binary)
    if not archs:
        return ""
    if archs == frozenset({"x86_64"}):
        return "Intel-only"
    if archs == frozenset({"arm64"}):
        return "Apple Silicon"
    if {"x86_64", "arm64"}.issubset(archs):
        return "Universal"
    return ", ".join(sorted(archs))


def _warning_message(track_number: int, track_name: str, plugin: rpp.Element) -> str:
    """Format a missing-plugin warning for user display."""
    return (
        f'Plugin "{_plugin_name(plugin)}" on track {track_number} "{track_name}" '
        "does not appear to be installed locally"
    )


def _saved_plugin_basename(plugin: rpp.Element) -> str:
    """Normalize a saved plugin label for installation lookup."""
    name = _plugin_label(plugin)
    name = re.sub(r"^[^:]+:\s*", "", name)
    name = re.sub(r"(?:\s+\([^()]*\))+$", "", name).strip()
    return _normalize_plugin_basename(name)


def _is_builtin_apple_au(plugin: rpp.Element) -> bool:
    """Return whether a saved AU label refers to an Apple-built system effect."""
    return _plugin_label(plugin).endswith("(Apple)")


def _is_builtin_cockos_vst(plugin: rpp.Element) -> bool:
    """Return whether a saved VST label refers to a bundled Cockos plugin."""
    return _plugin_label(plugin).endswith("(Cockos)")


def _plugin_label(plugin: rpp.Element) -> str:
    """Return the saved plugin label from a parsed Reaper plugin chunk."""
    return str(cast(tuple[Any, ...], plugin.attrib)[0])


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


def _audio_units_supported() -> bool:
    """Return whether this platform can install Audio Unit plugins."""
    return sys.platform == "darwin"


@cache
def _installed_au_names() -> frozenset[str]:
    """Return installed AU plugin basenames from standard macOS locations."""
    return frozenset(
        _normalize_plugin_basename(component.stem)
        for root in _au_search_paths()
        for component in root.glob("*.component")
    )


@cache
def _installed_au_plugins() -> dict[str, Path]:
    """Return installed AU bundles keyed by normalized basename."""
    plugins: dict[str, Path] = {}
    for root in _au_search_paths():
        if not root.exists():
            continue
        for component in root.glob("*.component"):
            plugins.setdefault(_normalize_plugin_basename(component.stem), component)
    return plugins


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


@cache
def _installed_vst_plugins_by_name() -> dict[str, Path]:
    """Return installed VST bundle paths keyed by normalized basename."""
    plugins: dict[str, Path] = {}
    for plugin in _installed_vst_plugins():
        plugins.setdefault(_normalize_plugin_basename(plugin.stem), plugin)
    return plugins


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


def _installed_plugin_bundle(plugin: rpp.Element) -> Path | None:
    """Return the installed bundle path that matches a saved plugin entry."""
    basename = _saved_plugin_basename(plugin)
    match plugin.tag:
        case "AU":
            return _installed_au_plugins().get(basename)
        case "VST":
            return _installed_vst_plugins_by_name().get(basename)
        case _:
            return None


def _bundle_binary(bundle: Path) -> Path | None:
    """Return the executable binary inside a macOS audio plugin bundle."""
    info_plist = bundle / "Contents/Info.plist"
    if info_plist.is_file():
        try:
            import plistlib

            executable = plistlib.loads(info_plist.read_bytes()).get(
                "CFBundleExecutable"
            )
        except (OSError, ValueError):
            executable = None
        if isinstance(executable, str):
            binary = bundle / "Contents/MacOS" / executable
            if binary.is_file():
                return binary

    macos_dir = bundle / "Contents/MacOS"
    for binary in sorted(macos_dir.glob("*")):
        if binary.is_file():
            return binary
    return None


@cache
def _binary_architectures(binary: Path) -> frozenset[str]:
    """Return Mach-O CPU architectures reported for a plugin executable."""
    try:
        completed = subprocess.run(
            ["lipo", "-archs", str(binary)],
            capture_output=True,
            check=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return frozenset()

    return frozenset(completed.stdout.strip().split())


def b64_ascii(s: str) -> str | None:
    """Try to decode a base64 string from a Reaper plugin chunk."""
    try:
        return base64.b64decode(s).decode("ascii")
    except (binascii.Error, UnicodeDecodeError):
        return None
