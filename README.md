# Project Prospector

Prospector watches the ETF universe for **structural novelty** — new baskets, fracturing
correlations, decoupling sectors — and proposes **reading, never orders**. It is a deterministic,
append-only, fully-offline-testable pipeline that turns public primary sources into a fossil record of
*leads* a human reads and adjudicates.

The organizing bet (Ben-David et al. 2023): a fund packaging a thesis is a **dated, public consensus
timestamp**, and the people who *buy* that timestamp underperform. Prospector only *reads* it —
capturing the structure early, measuring the lag between when structure appears and when it gets
packaged, and never acting. The connection to any trading system is **one human, one way**: a lead
graduates by hand.

## What it does

Two lead-spawners, a launch consensus-clock, and a set of silent corroboration streams write to an
append-only store; a deterministic fold turns each event stream into a *lead*; a cadence runner
sequences it all and pushes on state change:

- **§4a excess-correlation (`xcorr`)** — the primary live spawner. Two sector baskets that decouple
  from their trailing relationship spawn a lead (Schmitt-triggered on a departure *z*, a stress gate
  freezing crisis-day entries).
- **§4b dispersion** — a basket fracturing from within (spectral bipartition of the constituent
  correlation matrix). Wired live in shadow (§9e); the constituent-price vertical (CUSIP-keyed, with
  foreign/cash exclusion) landed with it. Starts the 90-day burn-in; promotion to paging is a human
  config flip.
- **§4c launch** — new US-listed ETFs as the consensus clock; a resolved launch's sectors are
  corroborated against live leads to measure the signed cross-stream lag.
- **§4d accretion** (`rebalance`, `mandate`, `soi`) — silent corroborations that accrete facts onto
  existing leads; they never spawn.

Everything downstream of a fact is a **verdict**, and verdicts are the human's — the code never decides
that a signal *means* something.

## Design stances (the load-bearing ones)

- **Reading, never orders.** No code reads a portfolio or places/sizes/recommends a trade. This is a
  firewall, not a preference.
- **Append-only fossil record.** Nothing under `events/` is edited or deleted; a correction (or a
  changed mind) is a *new* event that supersedes. State is never stored — a lead *is* the pure fold
  over its events, recomputed from scratch every time.
- **Freeze before parse.** Every raw response body is written to disk before anything parses it, so
  parsing is a pure function of frozen bytes and reruns are offline. Convergent-prior errors get caught
  by reading the *real* primary source (e.g. the SSGA daily file is xlsx, not CSV, and carries no
  `Sector` column for active funds — discovered only by opening one).
- **Identity on SEC series-ID.** Every fund keys on `S######`; a bare ticker is rejected at the write
  path; failed resolutions go to a retry-then-manual queue, never silently dropped.
- **Capture now, interpret later.** Payloads are captured richly even when nothing consumes them yet
  (you cannot backfill an append-only record), so later layers can thaw backward over the substrate.
- **No run-now, no auto-tune.** Record on cadence, push on state change; read-only surfaces. Thresholds
  move only by deliberate human recalibration that leaves a `config.changed` fossil.

## Architecture

The pipeline, one directory per stage. Each folder has its own `README.md`; `ARCHITECTURE.md` is the
top-level map.

```
ingest/   freeze raw bytes before parse (§3) — EDGAR, prices, holdings, prospectus, SOI
  → sensors/   deterministic writers that emit events (§4)
  → store/     append-only envelope store + WAL-SQLite index (§5/§7)
  → fold/      a lead IS the pure fold over its event stream (§5)
  → runner/    the M5 cadence driver — sequences it all, no intelligence (§9)
  → cli/ + dashboard/   read-only operator surfaces (§8c/§11)
identity/   SEC series-ID resolution + retry-then-manual queue (§2)
primitives/ vendored atomic-write / safe-backup disciplines (§1)
backtest/   offline calibration + the acceptance gate — writes only under backtest/
```

## Status

**Built, deployed, and self-running.** Milestones 1–6 — the sensors, the verdict layer, the SOI resolver,
the M5 cadence runner, the §10 email sender, and M6 discourse capture (built, ships-disabled) — plus the §9e
dispersion vertical, rebalance runner-wiring, the dual-HDD fossil-store backups (`pros backup`), and a CI
merge-gate on `main` are all built. The **M7 autonomy core is live**: a launchd job runs `pros run && pros
backup` daily on the Mac Mini, mirrors the fossil store to two blessed HDDs, and arms the §8a dead-man (a
weekly heartbeat; silence beyond 7 days unambiguously means broken). A real `pros run` has fired live `xcorr`
leads on the SPDR grid, dispersion runs in shadow burn-in, and the backup restores cleanly (`verify-restore`).
**v1 is build-complete and deployed.** **~660 offline tests, network-guarded**; every change lands only
through a green-CI pull request, and production is a tag-pinned worktree (`ops/deploy.sh`).

The honest caveat the docs keep front-and-center: **live ≠ validated.** The firing is n=1, the
false-discovery rate is unmeasured, and the edge question is open. **Falsifiability is demonstrated;
profitability is not.** The runner exists to convert existence-proofs into a *rate* — and that long run is
what remains now that v1 is deployed. (M6 discourse capture is **built and ships disabled** — the owner arms it via budget + provider; only the discourse *interpretation* is v2.)

## Running & testing

**Setup + the test suite** (offline — a network guard fails any test that opens a real socket):

```sh
uv sync                                     # base install
uv run pytest                               # the full offline suite (~660 tests, network-guarded)
uv run pytest -q tests/test_capture.py      # a single module
```

**The read-only CLI** (`pros` — folds of the event record; nothing here recomputes on demand):

```sh
uv run pros --help                          # all subcommands
uv run pros lead list                       # live leads (the fold over each event stream)
uv run pros lead show <lead-id>             # one lead's full fold  (pros lead --help)
uv run pros verdict <lead-id> <verdict>     # append a verdict: yes | watch | off-thesis-real | noise
uv run pros identity                        # the SEC series-ID retry-then-manual queue
uv run pros store reindex                   # rebuild the index from the fossils (repair, not run-now)
uv run pros store lock-path                 # the single-writer lockfile path
uv run pros backtest                        # replay xcorr over history → the acceptance gate (writes only under backtest/)
```

**A cadence tick + backups** (record on cadence, push on state change — `run` is NOT a recompute button):

```sh
uv run pros run                             # config-honesty → ingest → sensors → fold → push
uv run pros backup                          # mirror the fossil store to the blessed HDDs
uv run pros store verify-restore <dir>      # restore a backup to a temp store + count-check
```

Live runs need `TIINGO_API_TOKEN` (and `PROSPECTOR_SMTP_PASSWORD` if email is on) in `.env`, plus an EDGAR
user-agent (`edgar.user_agent` in config); tests need neither. Machine-local paths live in an untracked
`config/prospector.local.yaml` overlay (never in the tracked config).

**The read-only dashboard** (§11 — Streamlit; no autorefresh, no run-now):

```sh
uv sync --extra dashboard
PROSPECTOR_STORE=./store uv run streamlit run prospector/dashboard/app.py
```

To watch the **live** system, point it at the production store — safe by design (WAL mode; read-only;
concurrent with the scheduler):

```sh
cd ~/prospector/prod
PROSPECTOR_STORE=~/prospector/store uv run streamlit run prospector/dashboard/app.py
```

**Operating the deployed runner** (the Mac Mini — full runbook in [`ops/README.md`](ops/README.md)):

```sh
launchctl print gui/$(id -u)/com.prospector.run   # status · next fire · last exit code
./ops/install.sh <LOCAL_HOUR> <LOCAL_MINUTE>       # (re)install the daily schedule (local == 22:30 UTC)
./ops/uninstall.sh                                 # stop it
ops/deploy.sh <tag>                                # ship a release (tag-pinned, run from the dev repo)
```

## Where to read next

- **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — the module map and the built-vs-deferred status.
- **[`CLAUDE.md`](CLAUDE.md)** — the repo constitution (the firewall, CONTRACT-vs-DEFAULT, the
  append-only and identity rules).
- **[`docs/spec.md`](docs/spec.md)** —
  the canonical spec (rev15; rev14 and earlier revs kept as history).
- **`docs/decisions/`** — every load-bearing CONTRACT amendment, next to its `config.changed` fossil.
- **[`ops/README.md`](ops/README.md)** — the M7 autonomy core: scheduling the runner on launchd + the
  fossil-store backup, and the on-Mini activation runbook.
- Each **`prospector/<folder>/README.md`** — a per-package orientation.
