# Writing a command

Commands are discovered in subfolders that contain a `command.py` module with a
`@click.command`-decorated function `main`. Argument parsing is done in these
`command.py` modules. Actually processing the task (e.g. making Reaper API
calls) is conventionally done in a `process.py` colocated in the same subfolder.
