# music

Miscellaneous tasks for publishing my music.

## Prerequisites

1. A Python install _with framework_. For example, with
   [pyenv](https://github.com/pyenv/pyenv):
   ```zsh
   PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install <VERSION>
   ```

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
1. Restart Reaper

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
pip install --editable .
pip install --editable '.[testing]'
pre-commit install
```

### Tests

Checks are run on commit, after installing the pre-commit hook above, and on
push. You can also run them manually.

```sh
pre-commit run --all-files
```