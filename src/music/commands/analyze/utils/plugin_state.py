"""Helpers for reading saved plugin state from Reaper project chunks."""

import base64
import binascii
import re
from collections.abc import Iterator
from typing import Any, cast

import rpp  # type: ignore[import-untyped]

_MEDIA_PATH_RE = re.compile(
    r"(?:(?:/Users|/Volumes|/Library|/private|/tmp|~|\.\.?/)[^\x00\r\n<>\"']+?"
    r"\.(?:wav|aif|aiff|flac|mp3|ogg|rex|rx2|sfz|nki|sitala|mid|midi)"
    r"|(?:[A-Za-z0-9_.,()#+&-]+/)+[A-Za-z0-9 _.,()#+&-]+"
    r"\.(?:wav|aif|aiff|flac|mp3|ogg|rex|rx2|sfz|nki|sitala|mid|midi))",
    re.IGNORECASE,
)


def plugin_label(plugin: rpp.Element) -> str:
    """Return the saved plugin label from a parsed Reaper plugin chunk."""
    attrib = cast(tuple[Any, ...], getattr(plugin, "attrib", ()))
    return str(attrib[0]) if attrib else ""


def decoded_plugin_state(plugin: rpp.Element) -> bytes:
    """Decode base64 text chunks from a saved plugin state."""
    decoded = bytearray()
    for child in plugin.children:
        if not isinstance(child, str):
            continue
        chunk = "".join(child.split())
        if not chunk:
            continue
        try:
            decoded.extend(base64.b64decode(chunk))
        except (binascii.Error, ValueError):
            continue
    return bytes(decoded)


def iter_path_like_references(data: bytes) -> Iterator[str]:
    """Yield conservative path-like media references from decoded plugin data."""
    text = data.decode("utf-8", errors="ignore")
    seen: set[str] = set()
    for match in _MEDIA_PATH_RE.finditer(text):
        ref = match.group(0).strip()
        if ref not in seen:
            seen.add(ref)
            yield ref


def xml_document(data: bytes, root_name: str) -> bytes | None:
    """Extract a complete XML document containing the requested root tag."""
    root_start = data.find(f"<{root_name}".encode())
    if root_start == -1:
        return None

    xml_start = data.rfind(b"<?xml", 0, root_start)
    if xml_start == -1:
        xml_start = root_start

    closing = f"</{root_name}>".encode()
    xml_end = data.find(closing, root_start)
    if xml_end == -1:
        return None
    return data[xml_start : xml_end + len(closing)]
