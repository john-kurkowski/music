"""Spitfire LABS-specific analyze helpers."""

import json
import os
import plistlib
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import rpp  # type: ignore[import-untyped]

from music.commands.analyze.utils import plugin_state

_BROKEN_LINK = "⛓️‍💥"


@dataclass(frozen=True)
class LabsContentIssue:
    """A saved LABS preset whose installed content cannot be found."""

    family: str
    preset_name: str

    @property
    def detail(self) -> str:
        """Return a compact display label for table warnings."""
        return self.preset_name or self.family

    def warning(self, plugin_name: str, track_number: int, track_name: str) -> str:
        """Render the full stdout warning for missing LABS content."""
        preset = f' preset "{self.preset_name}"' if self.preset_name else ""
        return (
            f'Plugin "{plugin_name}" on track {track_number} "{track_name}" '
            f'references missing LABS library "{self.family}"{preset}'
        )


def is_plugin(plugin: rpp.Element) -> bool:
    """Return whether the plugin chunk belongs to Spitfire LABS."""
    return getattr(plugin, "tag", None) in {"AU", "VST"} and "LABS" in (
        plugin_state.plugin_label(plugin)
    )


def iter_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[str]:
    """Return warnings for missing LABS library content."""
    _ = project_dir
    for issue in _iter_content_issues(plugin):
        yield issue.warning(plugin_name, track_number, track_name)


def iter_plugin_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[tuple[str, str]]:
    """Return compact table warnings for missing LABS library content."""
    _ = project_dir, track_number, track_name, plugin_name
    for issue in _iter_content_issues(plugin):
        yield (_BROKEN_LINK, issue.detail)


def _iter_content_issues(plugin: rpp.Element) -> Iterator[LabsContentIssue]:
    seen: set[str] = set()
    installed_families = _installed_labs_families()
    for metadata in _iter_labs_metadata(plugin):
        family = metadata.attrib.get("family", "").strip()
        preset_name = metadata.attrib.get("name", "").strip()
        if not family or family in seen:
            continue
        seen.add(family)
        if family not in installed_families:
            yield LabsContentIssue(family=family, preset_name=preset_name)


def _iter_labs_metadata(plugin: rpp.Element) -> Iterator[ET.Element]:
    decoded = plugin_state.decoded_plugin_state(plugin)
    for state in _iter_labs_xml(decoded, plugin.tag == "AU"):
        try:
            root = ET.fromstring(state)
        except ET.ParseError:
            continue
        metadata = root.find("./META")
        if metadata is not None:
            yield metadata


def _iter_labs_xml(decoded: bytes, is_au: bool) -> Iterator[bytes]:
    if is_au:
        if juce_state := _juce_plugin_state(decoded):
            if labs_state := plugin_state.xml_document(juce_state, "Labs"):
                yield labs_state

    if labs_state := plugin_state.xml_document(decoded, "Labs"):
        yield labs_state


def _juce_plugin_state(decoded: bytes) -> bytes | None:
    plist_start = decoded.find(b"<?xml")
    plist_end = decoded.find(b"</plist>")
    if plist_start == -1 or plist_end == -1:
        return None

    try:
        plist = plistlib.loads(decoded[plist_start : plist_end + len(b"</plist>")])
    except (plistlib.InvalidFileException, ValueError):
        return None

    juce_state = plist.get("jucePluginState")
    return juce_state if isinstance(juce_state, bytes) else None


@cache
def _installed_labs_families() -> frozenset[str]:
    """Return LABS families listed in Spitfire's local install metadata."""
    metadata = _spitfire_properties()
    labs = metadata.get("Labs")
    if not isinstance(labs, dict):
        return frozenset()

    families: set[str] = set()
    for paths in labs.values():
        if not isinstance(paths, list):
            continue
        for path in paths:
            if not isinstance(path, str):
                continue
            if family := _labs_family_from_path(Path(path)):
                families.add(family)
    return frozenset(families)


def _spitfire_properties() -> dict[str, Any]:
    path = Path(
        os.environ.get(
            "SPITFIRE_PROPERTIES_PATH",
            str(Path.home() / "Music/Spitfire Audio/Settings/Spitfire.properties"),
        )
    )
    if not path.is_file():
        return {}

    try:
        properties = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return properties if isinstance(properties, dict) else {}


def _labs_family_from_path(path: Path) -> str:
    for part in reversed(path.parts):
        if part.startswith("LABS ") and part != "LABS Common":
            return part.removeprefix("LABS ").strip()
    return ""
