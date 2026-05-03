"""Output Arcade-specific analyze helpers."""

import base64
import os
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import rpp  # type: ignore[import-untyped]

from music.commands.analyze.utils import plugin_state


def is_arcade_plugin(plugin: rpp.Element) -> bool:
    """Return whether the plugin chunk belongs to Output Arcade."""
    return _is_arcade_plugin(plugin)


def is_plugin(plugin: rpp.Element) -> bool:
    """Return whether the plugin chunk belongs to Output Arcade."""
    return _is_arcade_plugin(plugin)


def iter_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[str]:
    """Inspect an Arcade state blob for missing-content issues.

    Arcade saves different preset families under distinct XML sections. This
    analyzer currently recognizes looper presets, which reference kit installs
    via ``Looper_Preset``, and Hyperion presets, which reference instrument
    source installs via ``Hyperion_Preset``.
    """
    _ = project_dir, plugin_name
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


def iter_plugin_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[tuple[str, str]]:
    """Return compact warning indicators for plugin-table rows."""
    _ = project_dir, track_number, track_name, plugin_name
    state = arcade_state_xml(plugin)
    if state is None:
        return

    root = ET.fromstring(state)
    hyperion_preset = root.find("./Hyperion_Preset/info")
    looper_preset = root.find("./Looper_Preset/info")

    if looper_preset is not None:
        yield from _iter_arcade_looper_plugin_warnings(looper_preset)
    if hyperion_preset is not None:
        yield from _iter_arcade_hyperion_plugin_warnings(root, hyperion_preset)


def arcade_state_xml(plugin: rpp.Element) -> bytes | None:
    """Extract Arcade's nested state XML from a saved plugin chunk."""
    if not _is_arcade_plugin(plugin):
        return None

    chunks = [child.strip() for child in plugin.children if isinstance(child, str)]
    if not chunks:
        return None

    try:
        decoded = b"".join(base64.b64decode(chunk) for chunk in chunks)
    except ValueError:
        return None

    if plugin.tag == "AU":
        try:
            plist_start = decoded.index(b"<?xml")
            plist_end = decoded.index(b"</plist>") + len(b"</plist>")
            outer_plist = decoded[plist_start:plist_end]
            juce_state = rpp_plist_value(outer_plist, "jucePluginState")
            if not isinstance(juce_state, bytes):
                return None
            decoded = juce_state
        except (ValueError, KeyError):
            return None

    try:
        state_start = decoded.index(b"<?xml")
        state_end = decoded.index(b"</state_info>") + len(b"</state_info>")
    except ValueError:
        return None
    return decoded[state_start:state_end]


def decoded_setting(plugin: rpp.Element) -> bytes | None:
    """Return Arcade's nested state XML for raw analyze output."""
    return arcade_state_xml(plugin)


def _is_arcade_plugin(plugin: rpp.Element) -> bool:
    """Return whether the plugin chunk belongs to Output Arcade in a supported format."""
    return getattr(plugin, "tag", None) in {"AU", "VST"} and "Arcade" in str(
        plugin_state.plugin_label(plugin)
    )


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


def _iter_arcade_looper_plugin_warnings(
    preset: ET.Element,
) -> Iterator[tuple[str, str]]:
    """Return compact plugin-table warnings for missing looper kits."""
    preset_name = preset.attrib.get("name", "Unknown Arcade preset")
    preset_uuid = preset.attrib.get("uuid", "")
    if preset_uuid and preset_uuid not in _arcade_installed_kit_uuids():
        yield ("⛓️‍💥", preset_name)


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


def _iter_arcade_hyperion_plugin_warnings(
    root: ET.Element,
    preset: ET.Element,
) -> Iterator[tuple[str, str]]:
    """Return compact plugin-table warnings for missing Hyperion content."""
    installed_sources = _arcade_installed_source_uuids()
    source_names = _hyperion_source_names_by_uuid(root)
    preset_name = preset.attrib.get("name", "Unknown Arcade preset")
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
    if missing_sources:
        display_names = [
            name
            for source_uuid in missing_sources
            if (name := source_names.get(source_uuid))
        ]
        if not display_names:
            display_names = [preset_name]
        yield ("⛓️‍💥", ", ".join(display_names))


def _hyperion_source_names_by_uuid(root: ET.Element) -> dict[str, str]:
    """Return friendly Hyperion source names from state XML or local metadata."""
    source_names: dict[str, str] = {}
    for elem in root.findall(".//HyperionLoadedSource"):
        source_uuid = elem.attrib.get("LoadedSourceUuid", "")
        source_name = (
            elem.attrib.get("LoadedSourceName")
            or elem.attrib.get("SourceName")
            or elem.attrib.get("Name")
            or elem.attrib.get("name")
            or ""
        ).strip()
        if source_uuid and source_name:
            source_names[source_uuid] = source_name

    if source_names:
        return source_names

    return _arcade_source_names_by_uuid()


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


def _arcade_source_names_by_uuid() -> dict[str, str]:
    """Return friendly source names keyed by UUID when Arcade metadata has them."""
    db_path = _arcade_db_path()
    if not db_path.exists():
        return {}

    with closing(sqlite3.connect(db_path)) as con:
        columns = {row[1] for row in con.execute("pragma table_info(sound_sources)")}
        if "uuid" not in columns:
            return {}

        name_column = next(
            (
                column
                for column in ("name", "title", "display_name")
                if column in columns
            ),
            None,
        )
        if name_column is None:
            return {}

        return dict(
            con.execute(
                f"select uuid, {name_column} from sound_sources where {name_column} is not null and {name_column} != ''"
            )
        )


def rpp_plist_value(plist_xml: bytes, key: str) -> object:
    """Look up a plist value by key from a parsed Arcade AU state blob."""
    import plistlib

    return plistlib.loads(plist_xml)[key]
