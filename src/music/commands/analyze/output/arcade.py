"""Output Arcade-specific analyze helpers."""

import base64
import os
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import rpp  # type: ignore[import-untyped]


def is_arcade_plugin(plugin: rpp.Element) -> bool:
    """Return whether the plugin chunk belongs to Output Arcade."""
    return getattr(plugin, "tag", None) == "AU" and "Arcade" in str(plugin.attrib[0])


def iter_warnings(
    track_number: int, track_name: str, plugin: rpp.Element
) -> Iterator[str]:
    """Inspect an Arcade AU state blob for missing-content issues.

    Arcade saves different preset families under distinct XML sections. This
    analyzer currently recognizes looper presets, which reference kit installs
    via ``Looper_Preset``, and Hyperion presets, which reference instrument
    source installs via ``Hyperion_Preset``.
    """
    state = arcade_state_xml(plugin)
    if state is None:
        return

    root = ET.fromstring(state)
    hyperion_preset = root.find("./Hyperion_Preset/info")
    looper_preset = root.find("./Looper_Preset/info")

    if looper_preset is not None:
        yield from _iter_arcade_looper_warnings(track_number, track_name, looper_preset)
    if hyperion_preset is not None:
        yield from _iter_arcade_hyperion_warnings(
            track_number, track_name, root, hyperion_preset
        )


def arcade_state_xml(plugin: rpp.Element) -> bytes | None:
    """Extract Arcade's nested JUCE state XML from an AU plugin chunk."""
    if not is_arcade_plugin(plugin):
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


def _iter_arcade_looper_warnings(
    track_number: int, track_name: str, preset: ET.Element
) -> Iterator[str]:
    """Warn when a looper-style Arcade preset references a missing kit install."""
    preset_name = preset.attrib.get("name", "Unknown Arcade preset")
    preset_uuid = preset.attrib.get("uuid", "")
    if preset_uuid and preset_uuid not in _arcade_installed_kit_uuids():
        yield (
            f'Arcade sampler "{preset_name}" on track {track_number} "{track_name}" '
            f"is not "
            f"installed locally (kit UUID: {preset_uuid})"
        )


def _iter_arcade_hyperion_warnings(
    track_number: int, track_name: str, root: ET.Element, preset: ET.Element
) -> Iterator[str]:
    """Warn when a Hyperion Arcade preset references missing source content."""
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
        detail = (
            f'Arcade instrument "{preset_name}" on track {track_number} "{track_name}"'
        )
        if missing_sources:
            sources = ", ".join(missing_sources)
            yield f"{detail} references missing source content: {sources}"
        if has_internal_error and missing_sources:
            yield f'{detail} has an internal "error" state in its saved plugin data'


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
