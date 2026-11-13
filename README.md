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

## What it reports

Three rules. Each one states a fact, and asks a question only when the
fact is missing.

| Rule | Fact | Asks when |
|---|---|---|
| `R1` Linked issue | Does the title or body reference an issue? | The author is not a maintainer, at least 5 lines of logic changed, and there is no reference. |
| `R2` Tests alongside logic | Did test files change together with logic? | At least 5 lines of logic changed and no test changed. |
| `R3` Diff cohesion | How many areas of the tree does the logic change touch? | Logic changed in more than 3 areas. |

**Logic** means source code outside test paths. Documentation,
manifests, lock files and CI configuration are not logic. Changed lines
are additions plus deletions; a file that was only renamed counts as
zero.

**R1** reads the title and the body. `#12`, `GH-12`, `owner/repo#12` and
issue or pull request URLs all count as a reference. Text inside code
spans and fenced code blocks is ignored, so a `fixes #123` left over
from a pull request template does not count. Authors whose association
with the repository is owner, member or collaborator are not asked.

**R2** applies to every author, maintainers included. A test file is
recognised by its path: directories such as `tests/`, `spec/` or
`__tests__/`, and names such as `test_x.py`, `x_test.go`, `x.test.ts` or
`x.spec.js`. In Rust, a test added inside a source file counts too.

**R3** applies to every author and has no size threshold. An area is the
first two directories of a path, for example `src/demo`; files in the
repository root form one area.

Each rule ends in one of four outcomes: present, absent, not applicable
or unknown. Only absent carries a question. Unknown means PandaGate
could not see enough to state the fact, for example when GitHub returns
an incomplete file list for a very large pull request. It says so
instead of guessing.

The identifiers `R1`, `R2` and `R3` are stable. The configuration file
refers to rules by them.

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
