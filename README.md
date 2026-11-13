# PandaGate

[![CI](https://github.com/evkir/pandagate/actions/workflows/ci.yml/badge.svg)](https://github.com/evkir/pandagate/actions/workflows/ci.yml)

One comment on an incoming pull request: what can be observed about it,
and the questions a maintainer would ask anyway.

A pull request arrives from someone you do not know. Before reading the
code you check the same things every time: is there an issue behind it,
did tests change with the logic, is the diff about one thing. Then you
type the same questions. PandaGate does that first pass and leaves it as
a single comment.

- **No authorship verdict.** It never says or implies "this was written
  by AI". It states facts anyone can verify from the pull request.
- **It changes nothing.** No closing, no labels, no review state, no
  failing check. One comment, or none.
- **One workflow file.** No dependencies, nothing installed on the
  runner, and the pull request's code is never checked out or run.
- **Quiet by default.** The issue and test questions are only asked from
  five changed lines of logic up. Documentation-only pull requests and
  manifest or lock file updates, such as Dependabot's, get no comment.

## What the comment looks like

This is the comment PandaGate left on a pull request opened from a fork,
[evkir/pandagate-live#2](https://github.com/evkir/pandagate-live/pull/2):

> ### Observations on this pull request
>
> - **Linked issue** (` R1 `): ` no issue reference in the title or body `
>   - Which issue does this address? If there is none, what did you observe that made this change necessary?
> - **Tests alongside logic** (` R2 `): ` 1 logic file(s) changed, 9 line(s), no test file changed `
>   - Which test fails before this change and passes after it?
> - **Diff cohesion** (` R3 `): ` 1 area(s) of logic touched: src/demo `
>
> <sub>[PandaGate](https://github.com/evkir/pandagate) reports what it can observe and changes nothing about this pull request. Rules are set in ` .pandagate.toml ` on the base branch.</sub>

Every fact is listed. A fact that is missing carries one question under
it; a fact that is present carries none.

PandaGate comments only when it has at least one question. It keeps a
single comment per pull request, edits that comment in place when the
pull request changes, and deletes it once there is nothing left to ask.

## What it does not do

- It does not classify authorship. There is no "written by AI" verdict,
  flag, score or label anywhere in the output, and none is planned.
- It does not close, reject, label or request changes. There are two
  modes, `warn` (one comment) and `off`. There is no mode that changes
  the state of a pull request.
- It does not fail the job because of what it found. The job is red only
  when the run itself broke, for example on a GitHub API error or an
  invalid configuration file.
- It does not check out or execute pull request code.
- It does not call a language model or any service other than the
  GitHub API. It is Python standard library only.

## License

Apache-2.0
