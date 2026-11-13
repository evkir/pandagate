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

## Install

Add one file, `.github/workflows/pandagate.yml`, to the default branch:

```yaml
name: PandaGate

on:
  pull_request_target:
    types: [opened, edited, synchronize, reopened]

permissions: {}

concurrency:
  group: pandagate-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  report:
    name: Report on the pull request
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      pull-requests: write
    steps:
      # No checkout: the pull request's code is never fetched or run.
      - uses: evkir/pandagate@v0.1.0
```

That is the whole installation. The action needs `python3` 3.12 or newer
on the runner, which `ubuntu-latest` provides, and installs nothing.

To pin the action to a commit instead of a tag, replace `v0.1.0` with
the full commit SHA shown on the
[releases page](https://github.com/evkir/pandagate/releases).

The workflow uses `pull_request_target` so that pull requests from forks
get a token that is allowed to comment. That trigger is dangerous when a
workflow checks out and runs the fork's code. This one has no checkout
step, and the action reads the pull request only through the GitHub API.

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

## Configuration

Configuration is optional. Without a file the defaults below apply. To
change them, add `.pandagate.toml` to the root of the repository. The
file is read from the base branch, never from the pull request, so a
contributor cannot switch the rules off in their own pull request.

All keys with their default values:

```toml
mode = "warn"
enabled_rules = ["R1", "R2", "R3"]

[rules.R1]
min_logic_lines = 5
require_closing_keyword = false
maintainer_associations = ["OWNER", "MEMBER", "COLLABORATOR"]

[rules.R2]
min_logic_lines = 5

[rules.R3]
max_areas = 3
area_depth = 2
```

- `mode`: `warn` posts the comment, `off` posts nothing.
- `enabled_rules`: the rules that run.
- `min_logic_lines`: the rule stays silent below this many changed lines
  of logic.
- `require_closing_keyword`: when `true`, only a reference behind a
  closing keyword, such as `Fixes #12`, counts for `R1`.
- `maintainer_associations`: authors with one of these associations are
  not asked for an issue. An empty list means everyone is asked.
- `max_areas`: `R3` asks above this many areas.
- `area_depth`: how many leading directories make an area.

A project that does not keep tests next to the code will get the test
question on most pull requests. Turn that rule off:

```toml
enabled_rules = ["R1", "R3"]
```

To ask for an issue on every change to logic, however small:

```toml
[rules.R1]
min_logic_lines = 0
```

An invalid configuration file fails the job and posts nothing.

## Benchmark

PandaGate was run on 200 pull requests that maintainers merged: the 20
most recent ones from outside contributors, created before 2026-10-01,
in each of pytest, pandas, ruff, tokio, vite, astro, prometheus,
GitHub CLI, neovim and godot. The
[protocol](benchmarks/README.md) was committed before the first run, and
every run is published as it came out in
[benchmarks/RESULTS.md](benchmarks/RESULTS.md).

Two things were measured: how often PandaGate would have commented, and
how often the fact it stated was wrong. For the second, every signal
that carried a question was checked by hand against the pull request.

| Run | Would have commented | Stated fact was wrong |
|---|---|---|
| 1. First version of the rules | 100 of 200 (50.0%) | 17 of 119 (14.3%) |
| 2. After fixing the wrong facts | 90 of 200 (45.0%) | 0 of 101 |
| 3. With the 5 line threshold on `R1`, the current default | 50 of 200 (25.0%) | 0 of 61 |

What these numbers do and do not show:

- **The rules were tuned on this sample.** The fixes after run 1 were
  made by looking at its 17 errors, and the threshold was chosen by
  looking at where run 2 asked its questions. So 0 of 61 and 25% are
  results on pull requests the rules have already seen. Performance on
  unseen pull requests has not been measured; that needs a fresh sample.
- **The drop from 45% to 25% comes from asking less, not from being more
  accurate.** Run 3 no longer asks 40 questions that were checked and
  found correct in run 2. Each of them is listed in the results.
- **Every pull request in the sample was merged.** The comment rate is
  how often PandaGate speaks up on work that maintainers accepted. How
  many low-effort pull requests it would catch has not been measured.
- **`R3` never asked.** It applied to 162 pull requests and found none
  spread over more than 3 areas.
- **The rate depends on the project.** In run 3 it ranges from 0 of 20
  in pytest to 13 of 20 in godot, where engine changes are routinely
  merged without a test in the same pull request. For a project like
  that, turn `R2` off as shown above.

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
