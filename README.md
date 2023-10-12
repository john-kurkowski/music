# music

Miscellaneous tasks for publishing my music.

The code is idiosyncratic with my music project conventions and therefore
applicable mainly to me. However, the code may be a useful example for using
[Reaper](https://reaper.fm)'s Python API.

## Prerequisites

1. A Python install _with framework_. For example, with
   [pyenv](https://github.com/pyenv/pyenv):
   ```zsh
   PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install <VERSION>
   ```
1. [SWS Extension](https://www.sws-extension.org/)

## Install

1.  ```zsh
    pip install .
    ```
1.  Open Reaper
1.  Configure Reaper for Python (per
    [reapy's README](https://github.com/RomeoDespres/reapy/blob/0.10.0/README.md#installation))
    ```zsh
    python -c "import reapy; reapy.configure_reaper()"
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
