#!/usr/bin/env python3
"""One-time backfill of frozen SGML SERIES/CLASS headers, for the corpus-check.

WHY
---
The corpus-check (`extraction_corpus_check.py`, section 6) models the B1 over-attribution guard from
FROZEN headers under `ingest/prospectus_headers/{accession}/header.txt`. The live store predates that
freeze (headers were introduced with the guard), so section 6 degrades to `guard=no-header` for the older
accessions and cannot prove the guard over the whole corpus. Run this ONCE to fetch + freeze a header for
every frozen prospectus accession; then the corpus-check models the guard over the whole store.

WHAT IT IS (and is not)
-----------------------
This is the ONLY networked piece of the corpus-check toolchain — the harness itself NEVER fetches (that
separation is the harness's whole safety property). It is deliberately a separate script so the harness
stays offline-only. It is SEC-polite (rate-limited by `EdgarClient`), FREEZE-ONCE (skips accessions whose
header is already frozen), and IDEMPOTENT (safe to re-run). It writes ONLY frozen substrate under
`ingest/prospectus_headers/` — no events, no registry mutation.

    uv run python tools/corpus-check/backfill_headers.py             # backfill missing headers
    uv run python tools/corpus-check/backfill_headers.py --dry-run   # list what would be fetched, fetch nothing
"""
from __future__ import annotations

import argparse
import json as _json
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _store_root(explicit: str | None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).expanduser()
    for candidate in (pathlib.Path.home() / "prospector" / "store", REPO / "store"):
        if (candidate / "ingest" / "prospectus").is_dir():
            return candidate
    raise SystemExit("no store with ingest/prospectus/ found — pass --store PATH")


def _cik_by_series(root: pathlib.Path) -> dict[str, int]:
    """series_id -> CIK from the registry index (the header fetch needs the CIK; the accession alone does
    not encode it). Reads the `cik` column if present, else parses it out of `entry_json`. Read-only."""
    conn = sqlite3.connect(f"file:{root / 'registry.sqlite'}?mode=ro", uri=True)
    try:
        out: dict[str, int] = {}
        try:
            for sid, cik in conn.execute("SELECT series_id, cik FROM funds"):
                out[str(sid)] = int(cik)
        except sqlite3.OperationalError:
            for sid, ej in conn.execute("SELECT series_id, entry_json FROM funds"):
                out[str(sid)] = int(_json.loads(ej)["cik"])
        return out
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", default=None, help="store root (default: ~/prospector/store, then ./store)")
    ap.add_argument("--config", default=None, help="config yaml (default: <repo>/config/prospector.yaml)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be fetched; fetch nothing")
    args = ap.parse_args()

    import yaml
    from prospector.ingest.edgar import EdgarClient, EdgarError
    from prospector.ingest.prospectus import ProspectusIngest
    from prospector.store.layout import StoreLayout

    root = _store_root(args.store)
    cfg_path = pathlib.Path(args.config) if args.config else REPO / "config" / "prospector.yaml"
    edgar_cfg = yaml.safe_load(cfg_path.read_text())["edgar"]
    cik_by_series = _cik_by_series(root)

    layout = StoreLayout(root)
    # persist=None: the working copy is frozen by ProspectusIngest.pull_header under prospectus_header_path
    # (what the harness reads); the raw-response edgar_path freeze is the runner's job, not this one-off.
    client = EdgarClient(edgar_cfg["user_agent"],
                         max_per_sec=float(edgar_cfg.get("max_requests_per_sec", 8)))
    prospectus = ProspectusIngest(layout, client)

    # One entry per ACCESSION (the header is series-independent, frozen once per accession).
    want: dict[str, int] = {}
    missing_cik: list[str] = []
    for body in sorted((root / "ingest" / "prospectus").glob("*/*/index.html")):
        series, acc = body.parts[-3], body.parts[-2]
        if prospectus.has_frozen_header(acc) or acc in want:
            continue
        if series not in cik_by_series:
            missing_cik.append(f"{series}/{acc}")
            continue
        want[acc] = cik_by_series[series]

    print(f"store   : {root}")
    print(f"to fetch: {len(want)} accessions with no frozen header"
          f"{f'   ({len(missing_cik)} skipped: series not in registry)' if missing_cik else ''}")
    for sa in missing_cik:
        print(f"   SKIP (no cik): {sa}")
    if args.dry_run:
        for acc, cik in sorted(want.items()):
            print(f"   would fetch CIK{cik:010d} {acc}")
        return 0

    ok = err = 0
    for acc, cik in sorted(want.items()):
        try:
            prospectus.pull_header(cik, acc)
            ok += 1
        except EdgarError as e:
            err += 1
            print(f"   ERR {acc} (CIK{cik:010d}): {e}")
    print(f"froze {ok} headers, {err} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
