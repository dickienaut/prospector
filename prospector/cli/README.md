# `prospector/cli/` — the `pros` command tree (read-only operator surface)

This package is the `pros` CLI: the human's terminal-side window onto the fossil record
plus the four write paths that are allowed to touch it. It implements the operator surface
of spec §8c — read the record, record a verdict, work the identity queue, repair the index,
and invoke one cadence tick. **Built.** The command tree itself is pinned by test.

## Modules

- **`main.py`** — the whole Click command tree (`cli`). Read surfaces: `pros lead list` /
  `lead show` (folds of a lead's events), `pros identity queue`. Write paths (only four):
  `pros verdict <lead> <value>` (appends a `verdict` event; a changed mind *supersedes* via
  `superseded_by`, never edits), `pros identity resolve <ticker> --series-id S######` (the
  §2 manual queue's human path — EDGAR-verified, no bypass), `pros store reindex` (rebuilds
  `registry.sqlite` from the `events/`+`snapshots/` trees), and `pros run` (one cadence
  tick). `pros backtest` replays frozen history and writes **only** under `backtest/`.
  Also holds `_load_dotenv` — the one place a secret (`TIINGO_API_TOKEN`) enters the process
  env; it rides the Authorization header, never config.

## Important to know

- **No run-now surface (CONTRACT, CLAUDE.md).** `pros store reindex` recomputes *nothing* —
  it rebuilds the index from the fossil record, so it is **repair, not run-now**. `pros run`
  is **one tick invoked by cron** (scheduling itself is M7), not an on-demand recompute; there
  is deliberately no flag to recompute or capture on demand.
- **Firewall (CONTRACT).** Nothing here reads a portfolio or `portfolio.yaml`, and no command
  places, sizes, or recommends a trade. The human records a *verdict* (`yes` · `watch` ·
  `off-thesis-real` · `noise`); a lead graduates to the portfolio system by hand, one-way.
- The module docstring says "three writers" — that predates `pros run`, which is a fourth
  (heavy) writer. `ARCHITECTURE.md` §7 is authoritative: read-only **except four writers**.

## See also

- Spec §8c (operator surface), §9 (the `run` tick), §2 (identity), §10 test 5 (backtest) in
  `docs/prospector-v1-spec-rev15-2026-07-16.md`.
- `ARCHITECTURE.md` §7 (the CLI table) and §9 (built vs deferred).
- `docs/decisions/2026-07-02-crash-flags-guidance-rev2.md` §8.4 (the verdict vocabulary).
