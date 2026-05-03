"""Sitala-specific analyze helpers."""

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import rpp  # type: ignore[import-untyped]

from music.commands.analyze.utils import file_refs, plugin_state

_BROKEN_LINK = "⛓️‍💥"


def is_plugin(plugin: rpp.Element) -> bool:
    """Return whether the plugin chunk belongs to Sitala."""
    return getattr(plugin, "tag", None) in {"AU", "VST"} and "Sitala" in (
        plugin_state.plugin_label(plugin)
    )


def iter_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[str]:
    """Return warnings for missing Sitala sample files."""
    for issue in _iter_sample_issues(project_dir, plugin):
        yield issue.warning(plugin_name, track_number, track_name)


def iter_plugin_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[tuple[str, str]]:
    """Return compact table warnings for missing Sitala sample files."""
    _ = track_number, track_name, plugin_name
    for issue in _iter_sample_issues(project_dir, plugin):
        yield (_BROKEN_LINK, issue.detail)


def _iter_sample_issues(
    project_dir: Path, plugin: rpp.Element
) -> Iterator[file_refs.PluginFileIssue]:
    yield from file_refs.iter_file_issues(project_dir, _iter_sample_locations(plugin))


def _iter_sample_locations(plugin: rpp.Element) -> Iterator[str]:
    decoded = plugin_state.decoded_plugin_state(plugin)
    state = plugin_state.xml_document(decoded, "sitala")
    if state is None:
        return

    try:
        root = ET.fromstring(state)
    except ET.ParseError:
        return

    seen: set[str] = set()
    for sound in root.findall(".//sound"):
        location = sound.attrib.get("location", "").strip()
        if location and location not in seen:
            seen.add(location)
            yield location
