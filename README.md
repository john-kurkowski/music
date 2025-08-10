# music

CLI to automate music render and upload, using [Reaper](https://reaper.fm) and
Python.

This app demonstrates how to programmatically control Reaper, from checking and
temporarily changing global settings, un/muting tracks, to triggering renders of
tracks. While built for personal music publishing workflows and assumes certain
Reaper project conventions, the app serves as an example of integrating with
Reaper's Python API.

## Usage

The following are the most common commands.

### Render

```sh
music render
```

Serially render the given list of Reaper projects, defaulting to the currently
open project. Prints statistics comparing any previous render with the new
output file.

The output looks like the following.

[![asciicast](https://asciinema.org/a/630914.svg)](https://asciinema.org/a/630914)

The command accepts many options, for example to render only 1 version of the
song, or to [upload](#upload) asynchronously in addition to render.

### Upload

```sh
music upload
```

Serially upload to a streaming service the renders of the given list of Reaper
projects, defaulting to the currently open project.

### Open

```sh
music open
```

Reveal the current project folder.

### Help

```sh
music --help                    # list all commands
music command-name-here --help  # list options for a specific command
```

## Prerequisites

1. A Python install [_with framework_](#reaper-compatible-python). For example,
   with [pyenv](https://github.com/pyenv/pyenv):
   ```sh
   PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install <VERSION>
   ```
1. [SWS Extension](https://www.sws-extension.org/)

## Install

1.  ```sh
    path/to/framework/enabled/python -m pip install .
    ```
1.  Open Reaper
1.  Configure Reaper for Python (per
    [reapy's README](https://github.com/RomeoDespres/reapy/blob/0.10.0/README.md#installation))
    ```sh
    path/to/framework/enabled/python -c "import reapy; reapy.configure_reaper()"
    ```
1.  Restart Reaper

## Contribute

Install for local development:

```sh
pip install --editable '.[testing]'
pre-commit install
```

### Tests

```sh
pytest
```

Besides tests, checks are run on commit, after installing the pre-commit hook
above, and on push. You can also run them manually.

```sh
pre-commit run --all-files
```

### Debug

When using `breakpoint()`, to make the Python interactive debugger easier to
see, you'll probably want to disable [rich](https://github.com/Textualize/rich)
output, via the `TERM` environment variable. For example:

```sh
TERM=dumb music render
```

## FAQ

### Why Python with Reaper?

_Coming soon: Conceptual overview of when and why to automate Reaper workflows._

- Reaper's Python API capabilities and limitations
- When automation makes sense vs. manual workflows
- Architecture decisions in this project
- Alternative approaches to Reaper automation

### Reaper-compatible Python

Reaper's Python API uses embedded Python that requires framework bindings to
communicate between the DAW and Python scripts. Some Python installations lack
this by default, like when installing Python via mise, pyenv, or uv. If Reaper
is set to these incompatible Python versions, any commands sent from this
project will exit with a stacktrace and may crash Reaper.

Running reapy's setup command from a compatible Python install will set the
correct version in Reaper's preferences, without needing to use Reaper's GUI.

From then on, technically, this project can use a different Python version, even
one without framework, as long as you **don't re-run reapy's setup command**,
which will reset Reaper's Python version.
