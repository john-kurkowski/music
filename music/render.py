"""Render vocal and instrumental versions of the current Reaper project."""

import sys

sys.path.append("/Applications/REAPER.app/Contents/Plugins/")

# pylint: disable-next=import-error,wrong-import-position
import reaper_python  # type: ignore[import] # noqa: E402


def main() -> None:
    """Module entrypoint."""
    # some_str = reaper_python.RPR_GetSetProjectInfo_String(0, "RENDER_FILE", None, None)
    some_str = "hello world"
    reaper_python.RPR_ShowConsoleMsg(some_str)


if __name__ == "__main__":
    main()
