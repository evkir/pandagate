"""The command line: read one pull request, then print or post its comment.

The exit status says whether the run worked, never what it found. A
pull request with every question open exits with the same status as one
with none: an observation is not a verdict, and nothing here may be
wired up to fail a check.

Without --post the comment goes to standard output and nothing is
written anywhere. With --post the comment on the pull request is
created, replaced or removed, and standard output stays empty.

Notes about the run and errors go to standard error, one per line, each
behind a fixed prefix and with unprintable characters replaced, so that
text from a repository cannot drive the terminal or pass for a command
to the runner that captures the output.

The token is read from the environment and never from the arguments,
where any other process on the machine could see it.
"""

import argparse
import os
import re
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
from pandagate.publish import Change, publish
from pandagate.render import render
from pandagate.score import score

EXIT_OK = 0
EXIT_FAILURE = 1

#: Environment variables the token is read from, in order of preference.
TOKEN_VARIABLES = ("GITHUB_TOKEN", "GH_TOKEN")

#: The account a workflow token comments as.
ACTIONS_LOGIN = "github-actions[bot]"

_PREFIX = "pandagate: "
_LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}(?:\[bot\])?")

_CHANGES = {
    Change.CREATED: "comment posted",
    Change.UPDATED: "comment updated",
    Change.UNCHANGED: "comment already up to date",
    Change.DELETED: "nothing to ask about; comment removed",
    Change.NOTHING: "nothing to ask about; no comment posted",
}


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport = urllib_transport,
) -> int:
    """Run the command line and return the exit status."""
    args = _parser().parse_args(argv)
    env = os.environ if environ is None else environ
    token = _token(env)

    if args.post and token is None:
        _say("error: --post needs a token in GITHUB_TOKEN or GH_TOKEN")
        return EXIT_FAILURE

    try:
        ref = parse_pull_request_url(args.url)
        client = Client(token, transport)
        facts, config = load_pull_request(client, ref)
    except (GitHubError, ConfigError) as exc:
        _say(f"error: {exc}")
        return EXIT_FAILURE

    report = score(facts, config)
    for warning in report.warnings:
        _say(f"note: {warning}")
    comment = render(report)

    if not args.post:
        if comment is None:
            _say("nothing to ask about; no comment would be posted")
        else:
            sys.stdout.write(comment)
        return EXIT_OK

    try:
        author = args.author or _acting_login(client, env)
        change = publish(client, ref, comment, author)
    except GitHubError as exc:
        _say(f"error: {exc}")
        return EXIT_FAILURE

    _say(_CHANGES[change])
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
            "written unless --post is given. A token is read from GITHUB_TOKEN or "
            "GH_TOKEN when one is set."
        ),
    )
    check.add_argument(
        "url",
        metavar="pull-request-url",
        help="https://github.com/<owner>/<repository>/pull/<number>",
    )
    check.add_argument(
        "--post",
        action="store_true",
        help="create, replace or remove the comment on the pull request",
    )
    check.add_argument(
        "--author",
        type=_login,
        metavar="login",
        help=(
            "the account whose earlier comment is replaced; worked out from the token when omitted"
        ),
    )
    return parser


def _login(value: str) -> str:
    if not _LOGIN.fullmatch(value):
        raise argparse.ArgumentTypeError("not an account login")
    return value


def _token(environ: Mapping[str, str]) -> str | None:
    """The first token the environment offers, or None."""
    for name in TOKEN_VARIABLES:
        value = environ.get(name, "").strip()
        if value:
            return value
    return None


def _acting_login(client: Client, environ: Mapping[str, str]) -> str:
    """The account whose comments count as this action's own."""
    login = client.identity()
    if login:
        return login
    if environ.get("GITHUB_ACTIONS") == "true":
        return ACTIONS_LOGIN
    raise GitHubError("cannot tell which account the token acts as; name it with --author")


def _say(text: str) -> None:
    """Write one line to standard error."""
    shown = "".join(char if char.isprintable() else "?" for char in text)
    print(f"{_PREFIX}{shown}", file=sys.stderr)
