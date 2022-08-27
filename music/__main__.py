#!/usr/bin/env python


"""CLI for this package."""

import sys

import click


@click.group()
def cli() -> None:
    """CLI entrypoint."""

    click.echo("Hello world")
    sys.exit(1)


if __name__ == "__main__":
    cli()
