#!/usr/bin/env python3
"""Does the submissions-pagination guard fire for any watched fund TODAY? Answer it over the frozen
store, offline, in seconds. The standing answer to: *"is this tripwire guarding a live silence, or a
state that cannot yet occur?"*

WHY THIS EXISTS
---------------
`latest_prospectus` raises `SubmissionsIncompleteError` when a fund has filings but no prospectus in the
readable `filings.recent` window WHILE `filings.files[]` (the SEC older-pages pointer) is non-empty — the
prospectus may sit in a page we deliberately do not paginate (B2). That is the pagination third-state
(Design 2026-07-22), the F1 shape-drift split one condition further along. The runner surfaces it as a
per-fund REVIEW-ADVISORY.

A guard on a state you believe unreachable is worth nothing if you cannot say whether it is unreachable.
Every submissions dict we ever fetched is frozen per-CIK in the store, so this is decidable for THIS
fleet with no network: for each watched CIK, read its newest frozen submissions and ask the real guard.
If it fires for some CIK today, you have found a LIVE silent-dormancy, not a hypothetical. If it fires for
none, the guard sits there costing nothing and never firing — the correct shape for a tripwire on a state
that is present in substrate but not yet in trigger.

    Measured on 2026-07-22: 0 fire / 30 CIKs — but 17 of 30 already carry a non-empty files[]. The
    pagination substrate is live across 57% of the fleet; only the trigger (a prospectus aged past the
    ~1000-filing window) is dormant. The guard watches a real surface, not a hypothetical.

WHY IT IS A TOOL AND NOT A TEST
-------------------------------
It reads the **live frozen store** (`ingest/edgar/`), which is machine-local, grows over time, and is not
in the repo — so it cannot be a hermetic offline test. It is a build-seat instrument (B-M2): read frozen
bytes, ask the guard in memory, print a table. No network, no writes, no events; deliberately NOT a `pros`
subcommand. Re-run it on any change to the submissions helpers or when the fleet grows.

The submissions blobs are date-partitioned (`ingest/edgar/{YYYY-MM-DD}/CIK{cik:010d}.json`, one copy each
tick that fetched them), so "current" per CIK is the newest date dir — the same newest-date-wins glob the
runner's `_load_prior_mf_snapshot` uses over the same tree.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from prospector.ingest.edgar import (  # noqa: E402 - after sys.path insert
    latest_prospectus, SubmissionsShapeError, SubmissionsIncompleteError)

CIK_RE = re.compile(r"^CIK(\d{10})\.json$")


def _store_root(explicit: str | None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).expanduser()
    # Production store, then the repo-local one. Never guesses a third place: an empty report because it
    # read the wrong (empty) store is the failure mode this ordering avoids.
    for candidate in (pathlib.Path.home() / "prospector" / "store", REPO / "store"):
        if (candidate / "ingest" / "edgar").is_dir():
            return candidate
    raise SystemExit("no store with ingest/edgar/ found — pass --store PATH")


def _watched_ciks(root: pathlib.Path) -> dict[int, int]:
    """{cik: fund_count} from the registry fund objects on disk (each carries `cik`). Read the JSON
    directly rather than open the SQLite index — no side effects, fully offline."""
    funds_dir = root / "registry" / "funds"
    if not funds_dir.is_dir():
        raise SystemExit(f"no registry/funds/ under {root}")
    counts: dict[int, int] = {}
    for f in sorted(funds_dir.glob("*.json")):
        cik = int(json.loads(f.read_bytes())["cik"])
        counts[cik] = counts.get(cik, 0) + 1
    return counts


def _newest_submissions(root: pathlib.Path) -> dict[int, tuple[str, pathlib.Path]]:
    """{cik: (date, path)} — the newest frozen submissions blob per CIK across the date-partitioned
    ingest/edgar tree (newest date wins), mirroring runner._load_prior_mf_snapshot."""
    edgar = root / "ingest" / "edgar"
    newest: dict[int, tuple[str, pathlib.Path]] = {}
    for d in sorted(p for p in edgar.iterdir() if p.is_dir()):
        for blob in d.glob("CIK*.json"):
            m = CIK_RE.match(blob.name)
            if not m:
                continue
            cik = int(m.group(1))
            if cik not in newest or d.name > newest[cik][0]:
                newest[cik] = (d.name, blob)
    return newest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", default=None, help="store root (default: ~/prospector/store, then ./store)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if the guard would fire for any watched fund (a live silent-dormancy)")
    args = ap.parse_args()

    root = _store_root(args.store)
    watched = _watched_ciks(root)
    newest = _newest_submissions(root)
    print(f"store   : {root}")
    print(f"watched : {sum(watched.values())} funds across {len(watched)} distinct CIKs")
    print(f"frozen  : {len(newest)} CIKs have a frozen submissions blob (newest date wins)\n")

    fire, has_pros, has_pros_paginated, absent, drift, never = [], 0, 0, 0, [], []
    for cik in sorted(watched):
        if cik not in newest:
            never.append(cik)   # never fetched on the runner path — a distinct third outcome, not fire/absence
            continue
        date, path = newest[cik]
        subs = json.loads(path.read_bytes())
        files_n = len(subs.get("filings", {}).get("files") or [])
        try:
            cur = latest_prospectus(subs)
        except SubmissionsIncompleteError:
            fire.append((cik, date, files_n))          # the guard fires: UNDETERMINED, a live silence
            continue
        except SubmissionsShapeError:
            drift.append((cik, date))                  # a shape drift (the F1 case), not pagination
            continue
        if cur is not None:
            has_pros += 1
            has_pros_paginated += 1 if files_n else 0
        else:
            absent += 1                                # clean absence: no prospectus, no older pages

    print("=== RESULT ===")
    print(f"WOULD FIRE (pagination-undetermined — no prospectus in recent + files[] non-empty): {len(fire)}")
    for cik, date, n in fire:
        print(f"    CIK{cik:010d}  (blob {date}, files pages={n})  <- LIVE silent-dormancy")
    print(f"has prospectus in recent (normal)      : {has_pros}"
          f"   [of these, files[] non-empty: {has_pros_paginated}]")
    print(f"clean absence (no prospectus, no files): {absent}")
    print(f"shape drift (F1 case, raises)          : {len(drift)}  {drift if drift else ''}")
    print(f"never fetched on runner path (no blob) : {len(never)}  {never if never else ''}")
    return 1 if (args.strict and fire) else 0


if __name__ == "__main__":
    raise SystemExit(main())
