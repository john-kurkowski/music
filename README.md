# music

Misc. scripts for publishing my music.

## Install

```zsh
pip install .
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
