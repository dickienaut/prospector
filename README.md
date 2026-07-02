# Project Prospector

The offensive twin of the thesis smoke detector: watches the ETF universe for structural novelty
and proposes **reading, never orders**. v1 is the deterministic core — three lead-spawners
(intra-basket dispersion, inter-basket excess-correlation, ETF launches), a rebalance accretion
stream, discourse capture, and an append-only fossil record.

Canonical spec: [docs/prospector-v1-spec-rev5-2026-07-02.md](docs/prospector-v1-spec-rev5-2026-07-02.md)
(rev5; earlier revs kept as history).
Repo rules: [CLAUDE.md](CLAUDE.md).

## Setup

```sh
uv sync
uv run pytest          # offline — a network guard blocks live sockets in tests
uv run pros --help
```

## Layout

- `prospector/primitives/` — record-keeping disciplines vendored from the sibling repo's LTEE
  archive (atomic write + SHA, safe SQLite backup, forensic query shapes), envelope-shaped.
- `prospector/store/` — five-field envelope, WAL SQLite index, append-only event store, S3 sync.
- `prospector/fold/` — the pure fold (a lead *is* the fold over its events) + reactive snapshots.
- `prospector/identity/`, `prospector/ingest/` — SEC series-ID resolution, EDGAR/price ingest.
- `prospector/sensors/` — the deterministic writers.
- `prospector/backtest/` — calibration and the milestone-3 acceptance gate. Writes only under
  `backtest/`.
