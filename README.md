# music

Miscellaneous tasks for publishing my music.

## Prerequisites

1. A Python install _with framework_. For example, with
   [pyenv](https://github.com/pyenv/pyenv):
   ```zsh
   PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install <VERSION>
   ```
1. Enable Python scripting in Reaper
   1. Open Reaper
   1. Open Preferences > Plug-Ins > ReaScript
   1. Check "Enable Python." The dialog will initially warn that Python is not
      detected.
   1. Input "Custom path to Python" to something like
      `/Users/alice/.pyenv/versions/<VERSION>/Library/Frameworks/Python.framework/Versions/3.10/lib`
      (depending where you installed Python and which version in the earlier
      step)
   1. Input "Force ReaScript to use specific Python" `libpython3.10`. The dialog
      should now say Python is installed.
   1. Click OK
   1. Restart Reaper

## Install

1.  ```zsh
    pip install .
    ```

## Usage

### Reaper Tasks

1. Open Reaper
1. Show action list...
1. Select "ReaScript: Run ReaScript"
1. Navigate to this project's source code folder, `music/`
1. Select the desired script to run

You may also like the Reaper action "ReaScript: Run _last_ ReaScript."

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
