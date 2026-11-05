# PandaGate

[![CI](https://github.com/evkir/pandagate/actions/workflows/ci.yml/badge.svg)](https://github.com/evkir/pandagate/actions/workflows/ci.yml)

Gate incoming pull requests on **contribution evidence**, not on guesses
about who or what wrote them.

Standard library only - no runtime dependencies, no language model, no
network calls other than the GitHub API.

## What it reports

For each incoming pull request PandaGate records observable facts:

- is an issue linked
- did tests change alongside logic
- how far the diff is spread across the tree
- does the description carry reproduction steps
- description substance relative to diff size
- author's prior pull requests in this repository

It then posts a single comment with those facts and the questions a
maintainer would otherwise type by hand.

## What it does not do

- It does **not** classify authorship. There is no "written by AI" verdict,
  flag, score or label anywhere in the output, and none is planned.
- It does **not** close, reject or request changes by default. The default
  mode is `warn`: one comment, no state change.
- It does **not** check out or execute pull request code.

## Status

v0.0.1 - scaffold. No evidence rules are implemented yet.
Do not read the sections above as a description of working behaviour.

## License

Apache-2.0
