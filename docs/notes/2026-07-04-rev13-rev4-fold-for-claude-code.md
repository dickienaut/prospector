# Doc fold — rev13 (spec) + rev4 (state-of-project), for the SOI slice

**For:** Claude Code.
**Where:** cut both on `claude/soi-sector-concentration-cd48yp` so the doc revs merge with the SOI code
as one unit — the way rev12 rode in with launch-corroboration. **Base the fold on the _committed_
rev12 / rev3 in the repo**, not on any draft that appeared in the design-thread chat (those diverge).
**From:** design thread, 2026-07-04.

---

## rev13 — fold the SOI decision into the spec

Add a rev13 changelog block above rev12's, and update the body sections noted at the end. The block
must carry:

- **SOI-derived sector concentration is BUILT — the resolver of `sectors_unresolved`.** `ingest/soi.py`
  isolates the target fund's block in the multi-fund NPORT-EX Schedule of Investments, parses the
  `INDUSTRY — N.N%` headers, rolls each through a **frozen 74-row GICS industry→sector table** to the
  11 canonical sector strings, and reconciles to the `COMMON STOCKS` total. `sensors/soi.py` routes the
  launch through the shared `route_corroboration`, so holdings and SOI feed **one** overlap/accrete/lag
  path with `detected_at` preserved as T2. **No ticker classifier, no third-party feed.**
- **Supersedes rev12's named next-unblock.** rev12 named "an external ticker→GICS classifier" as the
  unblock; it is **unnecessary** — the EDGAR filing carries GICS-industry groupings directly, so you
  parse the filing rather than classify tickers. (This is already recorded in
  `docs/decisions/2026-07-04-soi-derived-sector-concentration.md`; rev13 folds it into the spec.)
- **Real-data result.** The +593 now attaches on **real primary-source sectors**: Jul-2025 TEKX clears
  XLK×XLU, with **four** sectors above the 0.10 floor — Financials 10.1% (Capital Markets 4.7 +
  Financial Services 5.4), Industrials 13.9%, Information Technology ~52%, Utilities 10.7% (Electric 5.3
  + IPP 2.4 + Multi-Utilities 3.0). Jan-2026 stays **dormant** (Utilities 6.4% < 0.10). It is an
  **existence proof on real data — still n=1** (one issuer, one clearing snapshot), not a rate.
- **The rollup guard (design-thread review finding).** The reconcile-to-total check proves parsing
  completeness but is **blind to mis-mapping** (the sum is invariant to which sector bucket an industry
  rolls into). Guarded now by `tests/test_soi_config.py` — every table value ∈ the 11 canonical sector
  strings, table value-set **==** `sector_map`'s values (the overlap vocabulary), keys unique, 74 rows —
  plus the table as CONTRACT frozen reference. **Content verified 74/74** against the MSCI "GICS
  structure and definitions effective close of 2023-03-17" file (76 rows − 2 discontinued = 74 active).
- **CONTRACT re-verification trigger.** The table is verified against GICS effective 2023-03-17; **on
  any GICS revision, re-run the diff against the new MSCI structure file and update the recorded result**
  with a `config.changed` fossil. (Same doc line goes in the config comment on the table.)
- **Fetch still deferred to M5**, tied to `EdgarClient`: drop-and-freeze for tests, fetch-on-cadence for
  the runner, never conflated, fixtures never refreshed by fetch.
- **Named next unblock → the M5 runner** (where EDGAR-SOI-fetch finally has a consumer). Retire the
  ticker-classifier line.

Body edits (not just the changelog): in the §4c/§4d corroboration-sector-source text, record that the
**SOI path is the resolver of `sectors_unresolved`** (blank-sector active funds resolve via the filing's
industry grouping, not a classifier); and repoint the spec's "named next slice" from
holdings-intake/ticker-classifier to the **M5 runner**.

---

## rev4 — state-of-project bump

- **Mark the SOI slice built** (363 tests green): SOI-as-resolver of `sectors_unresolved`; the GICS
  table **verified against primary source** (MSCI 2023-03-17, 74/74); the structural test.
- **Real-data result** on the record: +593 attaches on real Jul-2025 TEKX (four sectors clear);
  Jan-2026 dormant; existence proof on real data, still n=1, not a rate.
- **§5.2 Built:** add `ingest/soi.py` + `sensors/soi.py`. **§5.2 Pending / §5.3 next steps:** the named
  next slice is now the **M5 runner** (EDGAR-SOI-fetch has its consumer there); **retire**
  "holdings-intake coverage / external ticker→GICS classifier" as the unblock.
- **Discipline note:** the fixture-provenance + primary-source-verification rule held — the GICS table
  was checked against the MSCI structure file, not against recall (the convergent-prior antidote,
  applied again).

---

## Also — the trigger-note (if not already in this commit)

Fold the CONTRACT re-verification trigger above into the config comment on the GICS table /
`sector_map` — a doc line, not code — so "who re-checks it on the next GICS revision" is a named
process, not just re-runnable in principle.
