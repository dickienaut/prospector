#!/usr/bin/env python3
"""Re-run prospectus extraction over EVERY frozen blob and diff the outcome, per document,
against a baseline git ref. The standing answer to: *"what else did my parser change touch?"*

WHY THIS EXISTS
---------------
On 2026-07-19 a mandate-extraction fix was verified against the four filings it was aimed at, all
of which it fixed. Run against the whole frozen corpus, the same change turned out to also
reclassify **11 genuine 497 stickers** as full prospectuses — which would have re-created exactly
the advisory noise the 2026-07-18 supplement cut had removed. The break was nowhere near the
failing filings; it was in the population that was **already passing**.

    A fix verified only on the documents it targeted is verified on a biased sample.

That check was a throwaway script. This is it, kept. See
`docs/decisions/2026-07-19-mandate-extraction-structural-lines.md`.

WHY IT IS A TOOL AND NOT A TEST
-------------------------------
The suite is hermetic and offline — it runs on fixtures committed to the repo, in CI, with no
store. This reads the **live frozen store** (`ingest/prospectus/`), which is machine-local, grows
over time, and is not in the repo. So it cannot be a test; it is a **pre-merge check you run by
hand** on any change to `prospector/ingest/prospectus.py`. The two are complements: the fixtures
pin known cases forever, this one asks what happened to everything else.

IT COMPUTES NOTHING INTO THE RECORD. Read-only: it opens frozen bytes, re-derives extraction in
memory, prints a report. No network (it never touches EDGAR — it reads blobs already frozen), no
writes, no events. That is what makes it safe to run whenever, and it is deliberately NOT wired to
a `pros` subcommand: the CLI is the operator's product surface, and this is a build-seat
instrument. (Extraction being a pure function of frozen bytes — `ProspectusIngest.load_frozen` —
is what makes any of this possible: a later, better extractor re-reads old filings with no stored
staleness.)

WHAT IT REPORTS — and why each column earned its place
------------------------------------------------------
  1. SUPPLEMENT/SAI CLASSIFICATION FLIPS. A document changing *kind* between baseline and HEAD.
     This is the one that caught the 11-sticker regression, and note that it is a category the
     change was not supposed to touch **at all** — which is precisely why it must be reported
     rather than assumed. Expect zero unless you meant to change the classifier.
  2. RELIABILITY MATRIX + REGRESSIONS. Documents that extracted before and do not now. Read every
     one: sometimes a "regression" is the fix (on 2026-07-19 one was a false-reliable extraction
     of risk prose that correctly began to fault instead) — but that is a judgment for a human,
     never an assumption for this script.
  3. NEWLY RELIABLE. What the change bought, per document.
  4. SECTION TEXT CHANGED. Documents reliable both ways whose extracted section MOVED. Usually
     the most interesting section: it means the same filing would now diff differently.
  5. REMAINING UNRELIABLE, BY REASON. The residual work, grouped — the shape, not the row count.
  6. PAIRS — WHAT THE SENSOR WOULD ACTUALLY DO. Sections 1-5 judge documents ONE AT A TIME. The
     sensor does not: it diffs a PAIR (prior frozen filing, current filing) and emits
     `mandate.changed` from the comparison. A change can improve every document individually and
     still make the sensor emit garbage — which is not a hypothetical. On 2026-07-19 a candidate
     fix scored "6 newly reliable, 0 regressions, 0 flips" here and would have emitted **3 false
     `mandate.changed` events**, because the two accessions being compared were the prospectuses of
     two DIFFERENT FUNDS (bug B1 — the prospectus resolves at trust level, so several series point
     at one filing). Per-document metrics are blind to that by construction. This section closes it,
     and flags the B1 smell directly: an accession frozen under more than one series.

USAGE
-----
    uv run python tools/corpus-check/extraction_corpus_check.py
    uv run python tools/corpus-check/extraction_corpus_check.py --baseline HEAD~1 --verbose
    uv run python tools/corpus-check/extraction_corpus_check.py --json report.json

Exit status is 0 unless --strict is passed, in which case any regression or classification flip
exits 1 (for wiring into a personal pre-push hook — never CI, which has no store).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _norm(s: str | None) -> str | None:
    """Whitespace-insensitive comparison, matching `diff_mandate`'s own change decision — so this
    report never disagrees with what the sensor would actually call a change."""
    return re.sub(r"\s+", " ", s).strip() if s else s


def _load_baseline(ref: str):
    """Exec the baseline revision's `prospectus.py` in an isolated namespace.

    Deliberately crude, and deliberately not an import: we need TWO versions of the same module
    live in one process, which the import system will not give us. The module is self-contained
    (stdlib + bs4 + one atomic-write helper), so exec'ing it is safe and keeps the harness to a
    single file with no build step. If it ever grows real intra-package imports, switch to a
    temporary worktree (`git worktree add`) instead.
    """
    src = subprocess.run(["git", "show", f"{ref}:prospector/ingest/prospectus.py"],
                         cwd=REPO, capture_output=True, text=True)
    if src.returncode != 0:
        raise SystemExit(f"cannot read prospectus.py at {ref!r}: {src.stderr.strip()}")
    ns: dict = {}
    exec(compile(src.stdout, f"<{ref}:prospectus.py>", "exec"), ns)  # noqa: S102 - see docstring
    if "extract_mandate" not in ns:
        raise SystemExit(f"{ref} has no extract_mandate — baseline too old to compare")
    return ns


def _store_root(explicit: str | None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).expanduser()
    # The production store, then the repo-local one. Never guesses a third place: an empty report
    # because it read the wrong (empty) store is the failure mode this ordering avoids.
    for candidate in (pathlib.Path.home() / "prospector" / "store", REPO / "store"):
        if (candidate / "ingest" / "prospectus").is_dir():
            return candidate
    raise SystemExit("no store with ingest/prospectus/ found — pass --store PATH")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--baseline", default="origin/main",
                    help="git ref to compare HEAD's extractor against (default: origin/main)")
    ap.add_argument("--store", default=None, help="store root (default: ~/prospector/store, then ./store)")
    ap.add_argument("--config", default=None, help="config yaml (default: <repo>/config/prospector.yaml)")
    ap.add_argument("--json", dest="json_out", default=None, help="also write the full report as JSON")
    ap.add_argument("--verbose", action="store_true", help="list every document, not just the deltas")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any regression or classification flip")
    args = ap.parse_args()

    import yaml
    from prospector.ingest.prospectus import extract_mandate as extract_head
    from prospector.ingest.prospectus import is_prospectus_supplement as is_supp_head

    cfg_path = pathlib.Path(args.config) if args.config else REPO / "config" / "prospector.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())["mandate"]

    base = _load_baseline(args.baseline)
    extract_base, is_supp_base = base["extract_mandate"], base.get("is_prospectus_supplement")

    root = _store_root(args.store)
    blobs = sorted((root / "ingest" / "prospectus").glob("*/*/index.html"))
    if not blobs:
        raise SystemExit(f"no frozen prospectus blobs under {root}")

    print(f"store    : {root}")
    print(f"baseline : {args.baseline}   vs   HEAD (working tree)")
    print(f"blobs    : {len(blobs)} across {len({b.parts[-3] for b in blobs})} series\n")

    flips, matrix, regressions, newly, textdiff, remaining, rows = [], collections.Counter(), [], [], [], [], []

    for p in blobs:
        series, acc = p.parts[-3], p.parts[-2]
        body = p.read_bytes()

        sup_head = is_supp_head(body)
        sup_base = is_supp_base(body) if is_supp_base else sup_head
        if sup_base != sup_head:
            flips.append(dict(series=series, accession=acc, baseline=sup_base, head=sup_head))

        # A document classified as a supplement/SAI is never extracted, so comparing extraction on
        # it would report noise. Its *classification* flip is the finding, reported above.
        if sup_head:
            rows.append(dict(series=series, accession=acc, kind="supplement/SAI"))
            continue

        b, h = extract_base(body, cfg), extract_head(body, cfg)
        matrix[(bool(b["reliable"]), bool(h["reliable"]))] += 1
        row = dict(series=series, accession=acc, kind="prospectus",
                   baseline_reliable=bool(b["reliable"]), head_reliable=bool(h["reliable"]),
                   baseline_reason=b["reason"], head_reason=h["reason"],
                   baseline_heading=b["heading"], head_heading=h["heading"])
        rows.append(row)

        if b["reliable"] and not h["reliable"]:
            regressions.append(row)
        elif not b["reliable"] and h["reliable"]:
            newly.append(row)
        elif b["reliable"] and h["reliable"] and _norm(b["section"]) != _norm(h["section"]):
            textdiff.append({**row, "baseline_chars": len(_norm(b["section"]) or ""),
                             "head_chars": len(_norm(h["section"]) or "")})
        if not h["reliable"]:
            remaining.append(row)

    # 1 — the category a parser change is not supposed to touch at all.
    print("=" * 100)
    print(f"1. SUPPLEMENT/SAI CLASSIFICATION FLIPS: {len(flips)}"
          f"{'   <- expect 0 unless you changed the classifier' if flips else ''}")
    for f in flips:
        print(f"     {f['series']} {f['accession']}   {f['baseline']} -> {f['head']}")

    print("\n2. RELIABILITY (non-supplement documents)")
    total = sum(matrix.values())
    base_ok = sum(c for (bb, _), c in matrix.items() if bb)
    head_ok = sum(c for (_, hh), c in matrix.items() if hh)
    print(f"     baseline {base_ok}/{total}   ->   HEAD {head_ok}/{total}")
    print(f"\n   REGRESSIONS (reliable at baseline, not at HEAD): {len(regressions)}")
    for r in regressions:
        print(f"     {r['series']} {r['accession']}")
        print(f"         was ok, heading={r['baseline_heading']!r}")
        print(f"         now {r['head_reason']!r}, heading={r['head_heading']!r}")
    if regressions:
        print("     ^ read each one: a 'regression' is sometimes the fix (a false-reliable extraction")
        print("       that correctly begins to fault). That call is yours, not this script's.")

    print(f"\n3. NEWLY RELIABLE: {len(newly)}")
    for r in newly:
        print(f"     {r['series']} {r['accession']}   was {r['baseline_reason']!r}"
              f"   now heading={r['head_heading']!r}")

    print(f"\n4. SECTION TEXT CHANGED (reliable both ways): {len(textdiff)}")
    for r in textdiff:
        print(f"     {r['series']} {r['accession']}   {r['baseline_chars']} -> {r['head_chars']} ch")
        if r["baseline_heading"] != r["head_heading"]:
            print(f"         heading {r['baseline_heading']!r} -> {r['head_heading']!r}")

    print(f"\n5. REMAINING UNRELIABLE AT HEAD: {len(remaining)}")
    for reason, c in collections.Counter(r["head_reason"] for r in remaining).most_common():
        print(f"     {c:4}  {reason}")
    if args.verbose:
        for r in remaining:
            print(f"         {r['series']} {r['accession']}  {r['head_reason']}"
                  f"  (candidate heading: {r['head_heading']!r})")
    print("=" * 100)

    # 6 — the pair the sensor actually diffs. See the module docstring: per-document metrics are
    # structurally blind to a change that makes the sensor emit a FALSE corroboration.
    diff_head = __import__("prospector.ingest.prospectus", fromlist=["diff_mandate"]).diff_mandate
    diff_base = base.get("diff_mandate")
    # HEAD's B1 over-attribution guard: the SGML SERIES/CLASS header says which series a filing covers.
    # Modeled from FROZEN headers only (offline — no fetch); accessions with no frozen header degrade to
    # "unknown" and are reported, so a partial run never reads as a clean full-corpus proof. Backfill the
    # headers first (tools/corpus-check/backfill_headers.py) to exercise this over the whole store.
    parse_series_classes = __import__(
        "prospector.ingest.prospectus", fromlist=["parse_series_classes"]).parse_series_classes

    def _guard(series: str, accession: str) -> str:
        """The mandate over-attribution verdict for (series, current accession) from its frozen header:
        'covered' | 'not_covered' | 'review' (truncated) | 'no-series-block' | 'no-header' (not backfilled)."""
        hp = root / "ingest" / "prospectus_headers" / accession / "header.txt"
        if not hp.exists():
            return "no-header"
        cov = parse_series_classes(hp.read_bytes())
        if not cov["complete"]:
            return "review"
        if cov["has_series_block"]:
            return "covered" if series in cov["series"] else "not_covered"
        return "no-series-block"

    print("\n6. PAIRS — WHAT THE SENSOR WOULD ACTUALLY DO   (accession ordering approximated by"
          " freeze time;\n   the runner walks EDGAR submission order, which is unavailable offline)")

    # The B1 smell: one accession frozen under several series means those series share a document,
    # so at most one of them legitimately owns it. Any change fired off such a pair is suspect.
    acc_series: dict[str, set] = collections.defaultdict(set)
    for p in blobs:
        acc_series[p.parts[-2]].add(p.parts[-3])
    shared = {a for a, ss in acc_series.items() if len(ss) > 1}
    headers_have = sum(1 for a in acc_series if (root / "ingest" / "prospectus_headers" / a / "header.txt").exists())

    pair_rows, newly_firing, guard_skips = [], [], []
    for series in sorted({b.parts[-3] for b in blobs}):
        # Model `_last_frozen_prospectus`: newest first, skipping supplements/SAI (not diff baselines).
        docs = sorted((root / "ingest" / "prospectus" / series).glob("*/index.html"),
                      key=lambda q: q.stat().st_mtime, reverse=True)
        full = [q for q in docs if not is_supp_head(q.read_bytes())]
        if len(full) < 2:
            continue
        cur_p, prior_p = full[0], full[1]
        cur_b, prior_b = cur_p.read_bytes(), prior_p.read_bytes()
        h = diff_head(prior_b, cur_b, cfg)
        b = diff_base(prior_b, cur_b, cfg) if diff_base else None

        def verdict(d):
            if d is None:
                return "n/a"
            return "fault" if not d["reliable"] else ("CHANGED" if d["changed"] else "unchanged")

        vb, vh = verdict(b), verdict(h)
        guard = _guard(series, cur_p.parts[-2])
        # The guard runs BEFORE the diff: not_covered -> the pair is skipped (nothing emitted); a truncated
        # header -> review advisory. Both mean HEAD does NOT fire mandate.changed, whatever the diff says.
        effective = "skipped" if guard == "not_covered" else ("review" if guard == "review" else vh)
        row = dict(series=series, prior=prior_p.parts[-2], current=cur_p.parts[-2],
                   baseline=vb, head=vh, guard=guard, effective=effective,
                   shared_accession=bool({prior_p.parts[-2], cur_p.parts[-2]} & shared))
        pair_rows.append(row)
        if guard in ("not_covered", "review") and vh == "CHANGED":
            guard_skips.append(row)   # a diff the guard now prevents from firing (Shape-A over-attribution)
        if effective == "CHANGED" and vb != "CHANGED":
            newly_firing.append(row)

    fires = sum(1 for r in pair_rows if r["effective"] == "CHANGED")
    print(f"     {len(pair_rows)} diffable pairs · would emit mandate.changed at HEAD: {fires}"
          f" (baseline: {sum(1 for r in pair_rows if r['baseline'] == 'CHANGED')})")
    print(f"     coverage guard modeled from frozen headers for {headers_have}/{len(acc_series)} accessions"
          f"{'   <- run backfill_headers.py; missing headers are unmodeled (guard=no-header)' if headers_have < len(acc_series) else ''}")

    print(f"\n   GUARD SKIPS — a diff the B1 guard now PREVENTS from firing: {len(guard_skips)}")
    for r in guard_skips:
        print(f"     {r['series']}  {r['head']} -> {r['effective']} ({r['guard']})   {r['prior']} -> {r['current']}")
    if guard_skips:
        print("     ^ these are the Shape-A over-attribution firings the header guard removes.")

    print(f"\n   NEWLY FIRING `mandate.changed` (read every one): {len(newly_firing)}")
    for r in newly_firing:
        warn = "  ⚠ SHARED ACCESSION (B1: several series point at one filing —" \
               " this diff may be comparing two different funds)" if r["shared_accession"] else ""
        gw = f"  [guard={r['guard']}]" if r["guard"] not in ("covered",) else ""
        print(f"     {r['series']}  {r['baseline']} -> {r['head']}   {r['prior']} -> {r['current']}{warn}{gw}")
    if any(r["shared_accession"] for r in newly_firing):
        print("     ^ a shared accession that the guard did NOT skip (covered, or header not backfilled).")
        print("       If guard=no-header, backfill and re-run before trusting this as a real firing.")
    if args.verbose:
        print("\n   all pairs:")
        for r in pair_rows:
            print(f"     {r['series']}  {r['baseline']:>9} -> {r['effective']:<9} (guard={r['guard']})"
                  f"{'  [shared accession]' if r['shared_accession'] else ''}")
    print("=" * 100)

    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps(
            dict(store=str(root), baseline=args.baseline, blobs=len(blobs), flips=flips,
                 regressions=regressions, newly_reliable=newly, section_changed=textdiff,
                 remaining=remaining, documents=rows, headers_modeled=headers_have,
                 pairs=pair_rows, guard_skips=guard_skips, newly_firing=newly_firing), indent=2))
        print(f"\nJSON report -> {args.json_out}")

    # A shared-accession firing the guard did NOT resolve is suspect. Once headers are backfilled the guard
    # should skip the over-attributed ones; a residual suspect (covered, or still no-header) needs a human.
    suspect = [r for r in newly_firing if r["shared_accession"]]
    if args.strict and (flips or regressions or suspect):
        print("\nSTRICT: regressions, classification flips, or suspect new firings -> exit 1")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
