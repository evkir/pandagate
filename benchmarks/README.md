# Benchmark protocol

This file fixes what is measured and how, and it was committed before the
first measurement. The results are added to this directory after the run and
are published whatever they turn out to be.

## Question

PandaGate comments on a pull request only when at least one rule reports
`ABSENT`. How often would it have commented on pull requests that maintainers
went on to merge, and how often is the fact it states wrong?

## Sample

200 merged pull requests: 20 from each of 10 repositories.

| Language | Repositories |
|---|---|
| Python | `pytest-dev/pytest`, `pandas-dev/pandas` |
| Rust | `astral-sh/ruff`, `tokio-rs/tokio` |
| TypeScript | `vitejs/vite`, `withastro/astro` |
| Go | `prometheus/prometheus`, `cli/cli` |
| C | `neovim/neovim` |
| C++ | `godotengine/godot` |

Reserve, in this order: `helix-editor/helix`, `home-assistant/core`.

From each repository the sample takes the first 20 pull requests, newest
first by creation time, that meet every condition:

- created before `2026-10-01T00:00:00Z`;
- merged (`merged_at` is set);
- the author is a user account (`user.type` is `User`), which leaves out bots;
- `author_association` is `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR` or `NONE`.

If a repository yields fewer than 20 among its 1000 most recent closed pull
requests created before the cutoff, it is replaced as a whole by the next
reserve repository. Nothing is picked or dropped by hand. The resulting list
is committed and does not change afterwards.

Only outside contributors are sampled because R1 reports `NOT_APPLICABLE` for
`OWNER`, `MEMBER` and `COLLABORATOR`, so their pull requests would not measure
it.

## Run

Every pull request is scored with the default configuration and all shipped
rules. Configuration files in the sampled repositories are not read. The
PandaGate commit used for the run is recorded next to the results.

## Metrics

**A. Comment rate.** Pull requests with at least one `ABSENT` signal, divided
by 200. This is how often PandaGate would have asked a question on a pull
request that was merged.

**B. Per-rule rate.** For each of R1, R2 and R3: `ABSENT` divided by
`PRESENT` plus `ABSENT`. The shares of `NOT_APPLICABLE` and `UNKNOWN` are
reported separately. `UNKNOWN` never counts as `ABSENT`.

**C. Factual error rate.** Every `ABSENT` signal is checked by hand against
the pull request page and labelled `correct` or `wrong`. The rate is `wrong`
divided by all `ABSENT` signals. A signal is `wrong` when:

| Rule | The signal is wrong when |
|---|---|
| R1 | the title or description references an issue, or the pull request has an issue linked in the Development sidebar |
| R2 | the diff adds or changes test code, including tests that live inside a file with logic |
| R3 | the number of areas it reports does not follow from the changed paths at the documented depth |

Every label is committed with a one-line reason.

## Criterion

C is at most 5%. A and B have no threshold: they describe how talkative the
default configuration is and feed the choice of defaults.

## Known limits

- The repositories are large, mature and popular. Smaller projects may give
  different numbers.
- `author_association` is reported as of the day the sample was taken, not as
  of the day the pull request was opened. Someone who was new then shows as
  `CONTRIBUTOR` now, and an organisation member with private membership can
  show as an outside contributor.
- Merged pull requests are a proxy for accepted work. A merge does not prove
  that the question PandaGate would have asked was pointless.
- The sample says nothing about recall. A tool that never comments scores
  zero on A and C.
