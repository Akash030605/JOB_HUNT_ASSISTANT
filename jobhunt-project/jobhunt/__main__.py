"""Entry point: this file runs when you type `python -m jobhunt`.

Python looks for __main__.py inside a package when you use the -m flag.
All it does is hand control over to the Typer app defined in cli.py.
"""

from jobhunt.cli import app

if __name__ == "__main__":
    app()
