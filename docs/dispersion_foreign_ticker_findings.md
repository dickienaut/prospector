# Dispersion vertical (§9e) — the constituent price pull is ticker-anchored, and real SSGA files break that assumption

**Branch:** `claude/dispersion-vertical-9e`
**Seat:** Claude Science (QA) → for the Claude Code (implementation) seat
**Date:** 2026-07-09
**Status of the slice otherwise:** suite green (507 passed / 1 skipped / 1 xfailed locally — the 1 skip
is `test_s3_sync.py`, gated on the optional `moto` package, unrelated to §9e; reconciles to the build
note's "508" where moto is installed). Push-collision fix (`page_worthy`), P1 guard on the constituent
pull, ticker→CUSIP re-key, and soft-fault granularity all verified correct. **This document is the one
substantive finding: it is a live-data correctness issue, not a suite failure.**

---

## TL;DR

`_run_dispersion` pulls each constituent's price series **by the SPDR file's Ticker column**
(`_build_constituent_panel` → `price_ingest.pull(_tiingo_symbol(ticker), ...)`, runner.py:503), then
re-keys the panel to the CUSIP. The re-key is correct, but it happens **after** a pull that trusts the
ticker to be a valid, unique, US-listed Tiingo symbol. Run against the **recorded-real** TEKX holdings
fixture already in the repo (`tests/fixtures/holdings/holdings-daily-us-en-tekx.xlsx`), that assumption
fails three ways inside the 0.90 coverage cut — and one of the three fails **silently and wrong** rather
than loud.

This is the §2/§5 "never anchor on a ticker" principle (the HECO lesson) reappearing one level down, at
the constituent grain. The decision record's own PRIMARY-SOURCE GATE anticipated the *dual-class* case
(`BRK.B`/`GOOG`); the real file shows two more classes it did not anticipate: **foreign listings** and
**non-equity placeholder tickers**.

---

## Evidence (real data, reproduced end-to-end)

Parsing the real TEKX xlsx through the real `parse_spdr_holdings` → `weight_covering_members(0.90)`
yields 25 constituents that will be pulled by bare ticker. Three are not clean US equity symbols:

| Ticker pulled | Real holding | CUSIP | Local ccy | Weight | In 0.90 cut? | What the pull does |
|---|---|---|---|---|---|---|
| `ENR` | **SIEMENS ENERGY AG** | ACI1RCRC2 | EUR | **6.17%** | **yes** | **succeeds with the WRONG series** |
| `-` | SSI US GOV MONEY MARKET | 924QSGII3 | (USD cash) | 4.22% | yes | 404 → dropped (coverage gap) |
| `2670549D` | EXXONMOBIL HOLDINGS CORP | 30233Q108 | (placeholder) | 1.62% | yes | 404 → dropped (coverage gap) |

(A fourth, `SU` / Schneider Electric SE, EUR, sits just below the 0.90 cut at 0.90% weight — same class,
not currently pulled, but it would be at a higher coverage target.)

### Why `ENR` is the dangerous one

In the file, `ENR` is the *foreign* local ticker for **Siemens Energy AG** (EUR-listed, CUSIP
ACI1RCRC2). But `ENR` is **also a live, US-listed NYSE symbol for a completely different company —
Energizer Holdings, Inc.** A web search returns `NYSE:ENR = Energizer Holdings` consistently across
multiple independent listing sources (TradingView, CNBC, Yahoo Finance, Simply Wall St, and SEC EDGAR
filing indexes for Energizer, CIK 1632790), one dated within the last few weeks — i.e. `ENR` is an
actively-traded US symbol *today* for a company that is not Siemens Energy. So the Tiingo-by-symbol pull
for `ENR` is expected **not to 404** — Tiingo covers NYSE equities, so it returns a real, fully-populated
price series **for Energizer**. `_build_constituent_panel` then relabels that column with Siemens
Energy's CUSIP (`frame["ticker"] = identifier`, runner.py:507), and the dispersion correlation matrix
consumes Energizer's returns as if they were Siemens Energy's — a **6.17%-weight constituent** silently
corrupted with a real-but-wrong series. This is exactly the P1-class hazard (a wrong substrate that fails
silent, not loud), but at the constituent grain and invisible to `guard_live_source` (which only vets
the *source*, not the per-name symbol resolution).

*(Provenance, stated precisely so this can be re-checked before you act on it: `ENR`=Siemens Energy in
the file is **confirmed** — read directly from the recorded fixture here. `ENR`=Energizer on NYSE is
**corroborated by a web search** across several independent listing sources (above), not by me reading a
primary SEC filing — treat it as high-confidence-but-secondary and re-confirm at the gate if you want
primary sourcing. That a bare `ENR` Tiingo pull returns Energizer's populated series rather than a 404 is
the strongly-expected **consequence** of those two facts, but I could not execute it here (no Tiingo
token in this environment) — it is the exact thing to confirm at the primary-source gate, and it is why
the two 404-drop cases below are the benign outcome and `ENR` is the malignant one. The *test* below does
not depend on any of this being live-verified: it asserts the code hands `ENR` to the price pull as a
bare symbol, which is true regardless of what that symbol resolves to.)*

The two 404 cases (`-`, `2670549D`) are much less severe — they're dropped as honest coverage gaps by
the existing per-constituent `except: continue` — but they still mean:
1. a ~6% cash/money-market line and a ~1.6% real equity (ExxonMobil, behind a placeholder ticker) are
   **silently excluded** from a basket the runner believes it covered to 90%; and
2. the reported `coverage_actual` (0.9149 here) **overstates** the priced coverage, because it's
   computed from the holdings weights *before* the price-pull drops — the sensor thinks it has more of
   the basket than it actually priced.

### One latent collision (not triggered by TEKX, but real)

`member_map = {m["ticker"]: m["identifier"] for m in members ...}` (runner.py:559) is **keyed by
ticker**. SSGA writes cash/derivative lines with ticker `-` (TEKX has two: the money-market line and
`EURO CURRENCY`). Only one is in TEKX's 0.90 cut today, so no collision fires here — but any basket
with **two `-`-ticker lines inside the cut** would collapse them to a single dict key, silently
dropping one CUSIP from the panel. A ticker-keyed dict is the wrong structure for a column that isn't
unique.

---

## Reproduction

```python
from pathlib import Path
from prospector.ingest.holdings import parse_spdr_holdings, weight_covering_members
from prospector.runner.runner import _tiingo_symbol

body = Path("tests/fixtures/holdings/holdings-daily-us-en-tekx.xlsx").read_bytes()
members, actual = weight_covering_members(parse_spdr_holdings(body, "TEKX"), 0.90)
for m in members:
    print(m["ticker"], "->", _tiingo_symbol(m["ticker"]), "|", m["identifier"], "|", m["name"])
# ENR -> ENR  (Siemens Energy, EUR)          <- pulls Energizer's series, silently
# -   -> -    (SSI money market)             <- 404, dropped
# 2670549D -> 2670549D (ExxonMobil placeholder) <- 404, dropped
```

No network needed to see the hazard — it's visible in the ticker column of the real fixture. Confirming
that `ENR` returns a *populated* (wrong) Tiingo series rather than a 404 is the part that needs the live
API and belongs in the primary-source gate (see below).

---

## Suggested handling (not prescriptive — a decision for the design/impl seats)

The file already carries what's needed to make this honest without a third-party symbol feed (which
would breach the primary-source wall): `Local Currency`, `Identifier` (CUSIP), and `SEDOL`. Options,
roughly in order of how much I'd trust them:

1. **Restrict the constituent price universe to priceable US equity lines, at the membership boundary.**
   Filter out (a) non-USD `Local Currency` rows and (b) cash/derivative rows (ticker `-`/blank, or a
   money-market/currency name) *before* building `member_map`. This is the honest "coverage gap, never
   a guess" move: the basket is priced on the US-listed core, the excluded weight is reported as a gap,
   and nothing is silently wrong. It does mean carrying `Local Currency` through `MEMBER_COLUMNS`
   (holdings.py:60) — a small, additive parser change.
   - **Trade-off:** for a fund with heavy foreign weight this shrinks the priced universe. That should
     be *surfaced* (a large coverage gap is a signal), which the build note already names as a deferred
     observability refinement.

2. **Make `member_map` collision-safe regardless.** Even with (1), key the re-key structure so a
   non-unique ticker can't silently drop a CUSIP — e.g. build the panel keyed on CUSIP from the start,
   or detect a duplicate/blank ticker and skip-with-a-fault rather than dict-collapse.

3. **A CUSIP/SEDOL→symbol resolution for foreign lines** is the "complete" fix but needs a mapping
   source. Anything third-party breaches the primary-source wall; if SSGA/EDGAR exposes the US-listing
   symbol for a foreign holding anywhere in a primary file, that would be the clean bridge. Absent that,
   **exclusion (option 1) is the honest default** and foreign coverage becomes a named gap, not a guess.

I would **not** rely on the bare-ticker pull 404-ing for the bad cases — `ENR` proves it won't.

---

## Test target (RED against current branch, GREEN after a fix — matches the house convention)

A `test_dispersion_foreign_and_cash_tickers.py` that drives the **real** TEKX fixture through the
membership → `member_map` path (no network) and asserts the price universe is clean:

- **`test_foreign_listing_is_not_pulled_by_a_colliding_us_ticker`** — assert `ENR` (Siemens Energy,
  EUR) is **not** in the set of symbols handed to the price pull (its US-ticker collision makes a
  bare-symbol pull unsafe). RED today: `ENR` is pulled. Fix-agnostic: satisfied by excluding the
  foreign line *or* by resolving it to its true US symbol.
- **`test_cash_and_placeholder_lines_are_excluded_from_the_price_universe`** — assert the `-`
  money-market line and the `2670549D` placeholder are not treated as priceable equities. RED today
  (they enter `member_map` and are only dropped downstream by a 404). Guards against the coverage
  overstatement.
- **`test_member_map_does_not_collapse_duplicate_tickers`** — construct a membership with two `-`-ticker
  cash lines in the cut; assert no CUSIP is silently lost (either both survive keyed by CUSIP, or the
  collision faults). RED today (dict-key collapse).

I can draft these as runnable RED tests + a reference patch (option 1 + option 2) on request, the same
RED/GREEN + reference-fix shape as the N1–N10 set — say the word and I'll produce them against this
branch.

---

## Note on the decision record's PRIMARY-SOURCE GATE

The §9e decision record already flags the dual-class symbol mapping (`BRK.B`/`GOOG`/`FOX`) as the "one
genuine primary-source unknown," to be checked against real XLF/XLC/XLY files before the live run. This
finding **widens that gate**: the pre-live check should also confirm, on real files, that

- foreign-listed holdings (non-USD) are handled (excluded or correctly symbol-mapped), and
- cash / money-market / placeholder-ticker lines are excluded from the price universe,

and specifically that **`ENR` does not silently return a US security's series**. The dual-class check
alone would not have caught the `ENR` collision, because `ENR` needs no dot/dash transform — it's a
clean-looking symbol that happens to point at the wrong company.
