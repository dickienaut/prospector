# Real holdings: xlsx, not CSV — and no file sectors for active funds

**Status:** primary-source finding, recorded 2026-07-04, from freezing TEKX's real daily holdings file
as a golden fixture (`tests/fixtures/holdings/holdings-daily-us-en-tekx.xlsx`, provenance in the
`.source.txt` sidecar) to close the fixture-provenance gap on the launch corroboration slice (§4c).
The synthetic CSV fixture that carried the M4 green hid two facts a real file forces. Both change what
the live cross-stream lag *means* on real data. Anti-fitting CONTRACT invoked (below). Folds into the
next spec rev.

## Two facts the synthetic CSV hid

1. **SSGA serves the daily holdings file as XLSX, not CSV.** `parse_spdr_holdings` did
   `body.decode()` + `csv.reader` — it could not read the real file *at all*. Since holdings ingest is
   the keystone under dispersion, rebalance, and corroboration, the entire holdings pipeline had only
   ever been tested against fabricated CSVs and would have failed on the first real download.
   **Fixed now:** the ingest detects xlsx (zip magic `PK\x03\x04`) and reads it via `openpyxl` (pinned,
   infrastructure-not-intelligence, like `beautifulsoup4`) → the same tidy `[name, identifier, weight,
   sector]` frame; the URL template is corrected to `.xlsx`. Verified on the real file: 35 holdings,
   weights parse, sum ≈ 100%.

2. **The real file carries NO GICS sectors for an active fund.** TEKX's daily file leaves the `Sector`
   column `-` on *every* security row (blank on cash rows). SSGA discloses holdings but not sectors for
   an active/thematic ETF. So the corroboration's "holdings-derived sectors" — reading the file's
   `Sector` column — yields the **empty set** for real TEKX. rev12 expected "~8% Utilities, below the
   0.10 floor → undetermined"; the reality is deeper: **there are no file sectors to derive from.**

## The empirical outcome — real TEKX resolves DORMANT

`sector_concentration(real_TEKX) == frozenset()` → a new first-class disposition
**`sectors_unresolved`** (holdings parsed, but the file gives no sectors → cannot compute overlap →
flag, never guess; the launch-side twin of `holdings_unavailable`, one level in). So real TEKX against
a live XLK×XLU lead → **dormant**, no accretion, no lag.

**The +593 lag was reachable only on the *synthetic* fixture's fabricated sectors.** On the real book,
the first live derivation is dormant. The mechanism is code-correct — proven on synthetic sectors and
on a populated-sector synthetic xlsx — but its *input*, file-provided sectors, is absent for the active
thematic funds that are the actual launch targets. So the honest status of the live cross-stream lag,
deflated once more:

> The mechanism works and derives correctly when sectors are present, but **the real SSGA daily file
> provides no sectors for active funds**, so the first real-data derivation is `sectors_unresolved →
> dormant`. The live lag is therefore **not yet reachable on real data even for TEKX** — it remains an
> existence proof on synthetic input, not a measured number on the real book.

## Anti-fitting (CONTRACT) — the threshold is frozen

Real TEKX landing dormant is **not** a reason to touch `corroboration.sector_min_weight` (nor to loosen
`sector_concentration`). The dormant outcome is the honest disposition, recorded as the truth; the
frozen-threshold discipline (§4a/§8a) forbids nudging a knob to rescue a known case. The golden test
records the outcome; it does not chase it.

## The deeper named unblock (updates the "next slice")

The unblock for a *representative* live lag is no longer just "widen holdings intake / handle xlsx" —
xlsx is handled. It is **an external ticker→GICS-sector classifier**: the file gives holdings (names,
CUSIPs, weights) but not sectors, so deriving a launch's sectors requires mapping each constituent to a
GICS sector from a source other than the daily file. Until that exists, real active-fund launches
resolve `sectors_unresolved → dormant`. This is the real frontier between existence-proof and rate —
recorded honestly rather than papered over.

## Method note (why this matters beyond the code)

Primary-source contact — actually downloading the file — broke a **convergent** blind spot that neither
thread's cross-review caught: both the code *and* the synthetic fixture assumed CSV-with-sectors,
because both instances shared the same wrong prior. Divergent-error review (a mapping bug vs a hook bug)
can't catch a shared default. The antidote is primary-source verification, and it is now standing
practice: **every test fixture is either recorded-real (with a provenance header/sidecar) or declared
synthetic in-band** — fixtures were the last input class exempt from freeze-the-substrate; no longer.

## What shipped
xlsx support in `ingest/holdings.py` (`_rows_from_body`, `openpyxl` pinned, URL → `.xlsx`);
`sectors_unresolved` disposition + `-`/blank-as-unresolved in `sensors/launch_corroboration.py`; the
real golden fixture + `.source.txt` provenance sidecar; `tests/test_holdings_real_tekx.py` (real file
parses; real TEKX → `sectors_unresolved` dormant; a populated-sector synthetic xlsx proves the parse
path); the fixture-provenance discipline in CLAUDE.md. 344 tests green. **Not built:** the ticker→GICS
classifier (the deeper unblock); broader per-issuer intake / NPORT-P.
