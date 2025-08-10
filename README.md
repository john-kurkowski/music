# music

Tasks for publishing my music.

The code is idiosyncratic with my music project conventions and therefore
applicable mainly to me. However, the code may be a useful example for using
[Reaper](https://reaper.fm)'s Python API.

## Prerequisites

1. A Python install [_with framework_](#reaper-compatible-python). For example,
   with [pyenv](https://github.com/pyenv/pyenv):
   ```zsh
   PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install <VERSION>
   ```
1. [SWS Extension](https://www.sws-extension.org/)

## Install

1.  ```zsh
    path/to/framework/enabled/python -m pip install .
    ```
1.  Open Reaper
1.  Configure Reaper for Python (per
    [reapy's README](https://github.com/RomeoDespres/reapy/blob/0.10.0/README.md#installation))
    ```zsh
    path/to/framework/enabled/python -c "import reapy; reapy.configure_reaper()"
    ```
1.  Restart Reaper

## Usage

```zsh
music --help
```

For example:

```zsh
music render
```

Which renders the current project in Reaper, with terminal output like the
following.

[![asciicast](https://asciinema.org/a/630914.svg)](https://asciinema.org/a/630914)

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

When using `breakpoint()`, you'll probably want to disable
[rich](https://github.com/Textualize/rich) output, via the `TERM=dumb`
environment variable. That will make the Python interactive debugger easier to
see.

## FAQ

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
