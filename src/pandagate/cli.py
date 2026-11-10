"""The command line: read one pull request and print what would be posted.

The exit status says whether the run worked, never what it found. A
pull request with every question open exits with the same status as one
with none: an observation is not a verdict, and nothing here may be
wired up to fail a check.

The comment goes to standard output and nothing else does. Notes about
the run and errors go to standard error, one per line, each behind a
fixed prefix and with unprintable characters replaced, so that text
from a repository cannot drive the terminal or pass for a command to
the runner that captures the output.

The token is read from the environment and never from the arguments,
where any other process on the machine could see it.
"""

import argparse
import os
import sys
from collections.abc import Mapping, Sequence

from pandagate import __version__
from pandagate.config import ConfigError
from pandagate.github import (
    Client,
    GitHubError,
    Transport,
    load_pull_request,
    parse_pull_request_url,
    urllib_transport,
)
from pandagate.render import render
from pandagate.score import score

EXIT_OK = 0
EXIT_FAILURE = 1

#: Environment variables the token is read from, in order of preference.
TOKEN_VARIABLES = ("GITHUB_TOKEN", "GH_TOKEN")

_PREFIX = "pandagate: "


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport = urllib_transport,
) -> int:
    """Run the command line and return the exit status."""
    args = _parser().parse_args(argv)
    env = os.environ if environ is None else environ

    try:
        ref = parse_pull_request_url(args.url)
        client = Client(_token(env), transport)
        facts, config = load_pull_request(client, ref)
    except (GitHubError, ConfigError) as exc:
        _say(f"error: {exc}")
        return EXIT_FAILURE

    report = score(facts, config)
    for warning in report.warnings:
        _say(f"note: {warning}")

    comment = render(report)
    if comment is None:
        _say("nothing to ask about; no comment would be posted")
    else:
        sys.stdout.write(comment)
    return EXIT_OK


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pandagate",
        description="Report what can be observed about a pull request.",
    )
    parser.add_argument("--version", action="version", version=f"pandagate {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    check = commands.add_parser(
        "check",
        help="read one pull request and print the comment it would get",
        description=(
            "Read one pull request and print the comment it would get. Nothing is "
            "posted and nothing about the pull request is changed. A token is read "
            "from GITHUB_TOKEN or GH_TOKEN when one is set."
        ),
    )
    check.add_argument(
        "url",
        metavar="pull-request-url",
        help="https://github.com/<owner>/<repository>/pull/<number>",
    )
    return parser


def _token(environ: Mapping[str, str]) -> str | None:
    """The first token the environment offers, or None."""
    for name in TOKEN_VARIABLES:
        value = environ.get(name, "").strip()
        if value:
            return value
    return None


def _say(text: str) -> None:
    """Write one line to standard error."""
    shown = "".join(char if char.isprintable() else "?" for char in text)
    print(f"{_PREFIX}{shown}", file=sys.stderr)
