# Project Prospector — Full Review

*Fresh-eyes review by Claude Science, acting as the QA/research seat in a three-tool workflow
(ideation in Claude Desktop, implementation in Claude Code, QA here). Prepared 2026-07-05.*

This document collects everything from two review passes plus my own thoughts and suggestions:

- **Part I — Code-level review** of the `prospector/` package (~5,390 LOC, excluding tests, macOS
  `._*` junk, and the vendored `ltee_archive`). Every BUG and high-severity assumption was
  **reproduced by running the actual code** against your real config and fixtures, not inferred.
- **Part II — Whole-project review** read *diachronically* across the append-only docs archive
  (30 markdown files, ~137k words, spec rev3→rev13, state rev1→rev4, 12 decision records, the
  theory docs). This traces how the thinking *moved* — drift, reversals, scope — which a
  single-snapshot read can't see.
- **Part III — Thoughts, suggestions, and ideas**, including the workflow itself.

A note on method, because you asked specifically for LLM-shaped mistakes and unvalidated
assumptions: I treated my own output as suspect too. Nothing in Part I is asserted from reading
alone — I ran it. Where I could only reason, it's labelled INFERRED. One finding below (the CSV→xlsx
class) I independently re-derived, then found your own 2026-07-04 decision record had *already*
caught it — a good sign your primary-source discipline works, and a caution that a fresh reviewer
and the record agree on where the soft spots are.

---

# Part I — Code-Level Review

## The one to fix first — a silent failure of the xlsx class

### H1 · ASSUMPTION · `ingest/holdings.py:87-95` · `_parse_weight` hardcodes ÷100 with no guard
```python
cell = raw.strip().rstrip("%").replace(",", "").strip()
return float(cell) / 100.0   # "SPDR daily files are always in percent, so we always divide by 100"
```
**Reproduced:** `_parse_weight("7.06%") -> 0.0706` (correct), but `_parse_weight("0.0706") -> 0.000706`
— a file already expressed as fractions (or a bare-decimal source) is silently scaled 100× too small.
**Why it's the dangerous class:** the failure is *invisible to the tests*. `weight_covering_members`
works on the coverage **ratio**, which is scale-invariant, so the round-trip and coverage tests stay
green. But the downstream `corroboration.sector_min_weight = 0.10` is an **absolute** gate — at 100×-
small weights nothing ever clears it, so **every fund silently resolves `dormant`** and the cross-
stream lag quietly never fires. This is the exact shape of the CSV/xlsx bug: a belief about input
units, no runtime assertion, a fixture that shares the belief.
**Fix:** add a per-file sanity check where weights are assembled — assert they sum to ~1.0 (± tol), or
detect the `max(weight) <= 1.0 and sum < 0.5`-style contradiction and fault. The check that already
exists *in the test* should live *in the parser*.

---

## Confirmed defects (reproduced) — currently latent, guarded by the write path

### S1 · BUG · `fold/fold.py:88-90,122-127` · fold is order-dependent when a row lacks `event_id`
```python
def _sort_key(row): return (str(_get(row,"ts","")), str(_get(row,"event_id","")))
```
**Reproduced:** folding two same-`ts` events with **no** `event_id` (a `lead.spawned` + an
`xcorr.reverted`) gives `status="reverted"` one way and `"active"` reversed — the docstring promises
"any arrival order … fold to the identical state."
**Severity — latent:** `event_store.append` stamps `event_id = uuid4().hex` on every write, so events
that actually reach the store always have one. The hole bites only raw envelopes folded outside the
store (a future writer, an ad-hoc replay, a hand-built test). **The property test masks it** by
always generating unique `event_id`s, so it can never catch the degradation.
**Fix:** in `fold`, raise on a missing `event_id` (make the promise explicit) rather than silently
falling back to arrival order; or add a content-hash tiebreak.

### S2 · BUG · `store/layout.py:25-30` · `ts_compact` collapses sub-second instants to one filename
```python
return dt.strftime("%Y%m%dT%H%M%S") + "Z"
```
**Reproduced:** `ts_compact("…00.2+00:00") == ts_compact("…00.8+00:00")` → both `20260714T130000Z`.
Two reactive snapshots for one lead **in the same wall-clock second** (state changed between them)
write the same path; the second hits `write_snapshot`'s `path.exists()` branch, sees different
content, and raises `SnapshotDivergenceError` — aborting the run.
**Severity — latent today** (snapshots are ~daily), reachable the moment the M5 runner can snapshot a
lead twice within a second on a state change.
**Fix:** include sub-second precision in the compact form, or forbid sub-second `ts` at validation so
the compact form is lossless.

---

## Assumptions of the xlsx class (input-shape beliefs, no runtime check)

### H2 · ASSUMPTION · `ingest/holdings.py:216` · SPDR source still declared `ext="csv"`
```python
_SOURCES = {"spdr": _Source(ext="csv", url=_spdr_url, parse=parse_spdr_holdings)}
```
**Reproduced:** `SPDR_URL_TEMPLATE` ends `.xlsx` and the real body is a zip, but `ext="csv"` feeds
`frozen_path`, so a **real xlsx pull is frozen to disk as `<ticker>.csv`**. Parsing survives only
because `_rows_from_body` sniffs the `PK\x03\x04` zip magic, not the extension. Your own 2026-07-04
xlsx decision record says "the URL template is corrected to `.xlsx`" — but this `ext` field wasn't;
the fix was ~90% complete. Harmless to parsing today, misleading in the frozen archive later.
**Fix:** `ext="xlsx"` (the parser is already format-agnostic).

### H3 · ASSUMPTION · `ingest/holdings.py:129-136` · header located by exact lowercased `"name"`/`"weight"`
A column literally titled `"Weight (%)"` — a plausible issuer variant — fails the `"weight" in norm`
test and raises `no holdings header`. Loud (raises), so lower risk than H1, but the same "the header
text is exactly X" belief. **Fix:** match by prefix/contains, or normalize `weight*`.

### H4 · ASSUMPTION · `soi.py:99-111` · the REIT alias the docstring promises does not exist
**Reproduced against your real config:** I built the rollup table from `config/prospector.yaml` — it
has **no** `REAL ESTATE INVESTMENT TRUSTS` key, only `MORTGAGE REAL ESTATE INVESTMENT TRUSTS`,
`MORTGAGE … REITS`, `REAL ESTATE MANAGEMENT AND DEVELOPMENT`, and `SPECIALIZED REITS`. The docstring
claims the plain alias is registered as a safeguard; it isn't. A fund rendering the **plain** header
would `fault` with "unknown GICS industry", not roll up to Real Estate. The ingest reviewer confirmed
the plain header form **appears verbatim in both real NPORT-EX fixtures** (in the IG Public & Private
Credit ETF blocks) — the suite dodges it only because TEKX/DECO render `SPECIALIZED REITs` and the
credit funds that carry the plain header have no `COMMON STOCKS` block to parse.
**Fix:** add the plain `REAL ESTATE INVESTMENT TRUSTS → Real Estate` alias (or fix `_build_table` so
the parenthetical-strip produces it), plus a fixture with the plain header + an equity block.

### I1 · ASSUMPTION · `sensors/launch.py:74-75` · the detected series_id is discarded, then re-derived by ticker
```python
for symbol, _series_id in new_registrations(current, prior):   # detected pair
    status = machine.register_launch(symbol, name_raw=None, detected_at=now)  # only symbol passed
```
**Reproduced (code path):** `new_registrations` returns the exact new `(symbol, series_id)` pair, but
`scan` binds the series to a throwaway `_series_id` and passes only `symbol`; `register_launch` →
`resolve_ticker(symbol)` re-derives the series independently via `matches[0]`. This contradicts the
module's own "keys on series id" claim and defeats the advertised **HECO reused-ticker** case: on a
ticker-reuse transition the genuinely-detected series is dropped and `matches[0]` may pick the wrong
one. **Fix:** thread the detected `series_id` through `register_launch` and confirm/prefer it rather
than re-deriving.

### B1 · ASSUMPTION · `identity/resolution.py:240-256` (+ `edgar.py:205-224`) · prospectus "confirm exists" is trust-wide, not series-scoped
The EDGAR submissions doc is per-CIK (the whole trust) with no series/class dimension, so "a
prospectus filing exists" is verified at the **registrant** level and the stored
`prospectus_accession` is just the trust's newest 485BPOS/497/N-1A. **Confirmed:** CIK 1516212 hosts
TEKX/DECO/HECO+; resolving one series attaches the trust's newest prospectus regardless of which
series it belongs to. Given the whole identity layer exists to defeat the HECO false-positive, a
trust-level accession masquerading as series-level is a real integrity gap.
**Fix:** cross-check the picked accession's SERIES/CLASS header against the resolved series_id before
accepting, or store it explicitly as trust-level and flag "not series-confirmed."

### B2 · ASSUMPTION · `identity/resolution.py:241` (+ `edgar.py:207`) · only `filings.recent` is read; pagination ignored
`filings.recent` holds only the most recent ~1000 filings; older ones live in `filings.files[]` pages.
A long-lived registrant whose last prospectus-family filing predates the recent window resolves to
`no_prospectus` and lands in the manual queue wrongly. The fixture has only a `recent` block, so tests
never exercise the overflow. **Fix:** follow `filings.files[]` when nothing is found in `recent`;
minimally assert `len(recent["form"]) < 1000` and document the cap.

### B3 · ASSUMPTION · `backtest/runner.py:61-67` · market/SPY excluded only because it's absent from the seed
`tickers = sectors + [market]` with no `t != market` guard — the market is kept out of the 55 pairs
*only* because SPY isn't in the series_ids seed YAML. **Confirmed:** add SPY to the seed and
`_pairs_with_series` emits `('SPY','XLK')…` alongside the real pairs, silently corrupting the grid.
The docstring claims "excluding the market" as a guarantee the code doesn't enforce.
**Fix:** `sectors = [t for t in tickers if t in series_ids and t != market]`, or assert `market not in
series_ids` at load.

### P1 · ASSUMPTION (INFERRED) · `ingest/prices.py:108-117` · Stooq path assumes Close is adjusted
The Stooq branch treats `Close` as adjusted with no evidence and only a synthetic 2-row fixture that
can't exercise a split/dividend. (The Yahoo branch correctly reads `adjclose`.) If Stooq's Close is
*unadjusted*, every return across a corporate action is wrong — and returns are the base of the whole
sensor stack. **Fix:** verify against a known split (e.g. NVDA 2024) before trusting Stooq; prefer an
explicit adjusted field.

---

## NaN-phantom risk (INFERRED — not reachable through the current SPDR path)

### S5 · SMELL · `sensors/launch_corroboration.py:66`, `sensors/rebalance.py:76` · `str(NaN)` → `"nan"` slips the unresolved guards
```python
sec = str(row.get("sector", "")).strip()   # a float NaN -> "nan", not in {"", "-"}
```
`_UNRESOLVED_SECTOR` guards `""`/`"-"` and `_identified()` guards `""`, but a pandas NaN cell
stringifies to `"nan"` and passes both — a phantom `"nan"` sector that can accumulate weight and cross
`min_weight`, the exact class the guards exist to prevent. Not reachable via `parse_spdr_holdings` (it
fills `""`), but a future NPORT-P parser or a `pd.DataFrame` test fixture with NaN cells trips it.
**Fix:** `sec = "" if pd.isna(v) else str(v).strip()` (same for identifier).

---

## Lower-severity smells (worth a look, not blocking)

- **`launch_corroboration.py:197`** — `cross_stream_lag` picks T1 (earliest spawn) by **lexical**
  string sort while T2 uses `parse_ts`. Fine for canonical `…Z` whole-second ts, wrong if
  spellings/fractional seconds mix. Fix: `min(..., key=parse_ts)`.
- **`dispersion.py:81-86`** — the documented "no real split → degenerate → Q=NaN" safety essentially
  never triggers; a pure-noise contrast axis still yields a finite Q, and near-degenerate eigenvalues
  make the split unstable. Consider gating on the eigengap (λ₂/λ₁ floor) before trusting a
  bipartition. (INFERRED)
- **`backtest/corroboration.py:29,56-62`** — the 8→2 word-boundary fix guards tokens **<4 chars**;
  tokens ≥4 keep plain-substring matching, so `reit`⊂`reiterate`, `bank`⊂`embankment` can still
  bridge. Low risk (small curated table) but apply `\b` at all lengths for safety.
- **`backtest/report.py:99`** — `(stress_validation or {}).get("acute_crises",[{}])[0]` raises
  IndexError if a caller passes `acute_crises: []` (the default only covers a *missing* key). Fix:
  `... .get("acute_crises") or [{}]`.
- **`store/registry.py:125-135`** — SQL table name interpolated via f-string guarded only by
  `assert`; under `python -O` the assert is stripped. Not externally reachable today. Fix: literal
  dict lookup `table -> (sql, pk)`.
- **`edgar.py:185`** — silent `matches[0]` on an ambiguous symbol (ties into I1/B1); prefer an
  explicit "ambiguous → fault" like the SOI anchor path already does.

---

## Verified clean / correct

- **xcorr math** (`sensors/xcorr.py`): no look-ahead — betas `.shift(1)` to t-1, baseline excludes the
  current value via `.shift(1)`; Fisher clip guards |r|→1; `std==0 → NaN`. Sound.
- **The xlsx fix itself** (`_rows_from_body`): genuine, zip-magic sniffed, covered by a recorded-real
  SSGA golden. (Only residue is the `ext="csv"` label, H2.)
- **soi.py anchor discipline**: exact-then-unambiguous-substring with a >1-match **fault**,
  unknown-industry **fault**, and a reconcile-to-COMMON-STOCKS check. Careful, correct code.
- **Lag sign convention**: `launch_lag = detected_at − structural_ts`, positive = packaging follows
  structure — matches the doc; reads **only** `detected_at` (no resolution-time leak).
- **Fold verdict succession**: dangling / fork / cycle all resolve deterministically to a head with a
  recorded anomaly; never crashes.
- **Backtest isolation**: writes only under `backtest/`; the word-boundary token fix is present; no
  bare-ticker leak past the write gate. **prospectus.py**: clean.

## Code-review through-line

The codebase's dominant instinct is **fail loud / fault rather than mis-roll** — the SOI parser, the
mandate diff, the identity queue all prefer a fault to a wrong answer, and that discipline held up
under scrutiny. The findings that matter are the few places that **fail *silently*** instead:
**H1** (weight units — the true xlsx-class bug), **H4** (a documented REIT safeguard that doesn't
exist), and **I1/B1** (series identity discarded / prospectus trust-wide, both weakening the HECO
guarantee the identity layer exists to provide). S1/S2 are real but latent — worth fixing before the
M5 runner makes them reachable. Everything else is hardening.

---

# Part II — Whole-Project Review (read across the append-only archive)

This pass read the docs in **date/rev order** to see how the thinking moved — the review a
single-snapshot reader can't do. The archive is genuinely well-kept: reversals are recorded with the
old claim left intact, and the "n=1, existence proof, not a rate" caveat travels with the headline
number everywhere. The problems are few, specific, and concentrated in doc *structure*, not thinking.

## The headline: your memory prosthetic is working — with two specific leaks

You use these docs as working memory across ~8 projects. So the failure mode that matters most is a
place where the archive *misremembers* — tells a returning you something false. I found exactly two,
both confirmed against the text:

### DRIFT-1 · The state doc contradicts itself on what's built · `state rev4 §2.9` vs `§5.2`
- **§2.9 "What is deferred"** (line 149, byte-identical since rev2): *"Remaining milestone-4 slices:
  the **rebalance sensor** and the **launch corroboration hook** … both now unblocked by holdings
  ingest."*
- **§5.2 "Built"** (line 257): lists **`sensors/rebalance.py`** and **`sensors/launch_corroboration.py`**
  as shipped, 367 tests.

The root cause is structural: Parts I–IV of the state doc are copied forward verbatim each rev, and
only §5 + the changelog header get refreshed. So **any built-vs-deferred statement outside §5 rots
silently.** A returning you who opens §2.9 (the natural "what's left" section) is told the two hardest
M4 slices are still pending — when they shipped a rev ago. This is precisely the memory-prosthetic
failure this review exists to catch.
**Fix (cheap):** make §5 the single source of truth on status; either regenerate §2.9 each rev or
delete it and point to §5. Don't treat any status prose as immutable.

### DRIFT-2 · "Aging-monitor reference pinned" was announced done in rev5 but is still open in rev13
- **rev5 changelog** (and rev6): *"§4a aging-monitor reference pinned."*
- **rev13 body §4a** (line 171, verbatim from rev5): *"One reconciliation to close: the decision note
  cites calm p95 as both ~0.81 … and ~0.668 … the note should be pinned to that one definition so the
  margin is unambiguous."*

The *decision* was made (use the calm-regime measure, ~0.18 headroom to the 0.85 gate), but the
changelog said "pinned/closed" while the body kept the open to-do for **8 revisions**. The headroom of
your only frozen dial is still stated two ways (~0.04 all-days vs ~0.18 calm-regime). A changelog "done"
that contradicts a still-open body line is the one place the archive's self-report drifted from itself.
**Fix (one line):** delete the "one reconciliation to close" sentence from §4a and state the single
calm-regime margin as settled.

## Reversals — handled well (protect this habit)

Every genuine change of mind in the archive names the old claim rather than vanishing it. The strong
examples, all confirmed:

- **Stress gate 0.65 → frozen absolute 0.85, crisis-only.** The single most-traced number; changed
  value, status (DEFAULT → frozen CONTRACT), *and* job (broad crash-suppression → acute-onset-only).
  Recorded at length with the retired premise named, the empirical rejection of the baseline-relative
  form shown (windows 5/10/15 × baselines 63/126/252 all fail), the superseded rev3 §4a "left intact as
  history," and a `config.changed` machine fossil. This is a model decision record.
- **Launch stream: lead-spawner → corroboration + consensus-clock (rev7).** "Three spawners" became
  "two"; surfaced in the changelog header, not silently swapped.
- **Verdict `no` retired (rev6).** Explicitly flagged as *closing a code-ahead-of-spec drift*, split
  into `off-thesis-real` + `noise`, with the fold kept able to render the legacy value.
- **`crash_revert_weeks` — a *non*-change, on merits.** rev1 mused about widening 8→13–26 weeks; after
  the 7/10 persistent flags, the outcome record *kept* 8 and named the trap: widening to make them
  "pass" as transient would be fitting the threshold to its result. Refusing the tempting change is the
  mirror image of drift, and you got it right.

## Abandoned assumptions — all caught, one class systematized

- **"SPDR publishes daily CSVs" (rev3) → xlsx (rev12).** Baked into the keystone ingest and hidden for
  nine revisions by a labelled-synthetic CSV fixture; caught only by opening a real filing. My Part-I
  H1/H2/H3 are the *residue* of this same assumption's fix.
- **"The daily file carries GICS sectors" → it doesn't** (blank `Sector` for active funds), which drove
  the whole SOI-resolver slice.
- **The systematized win:** after the third such surprise you named the failure mode — the *convergent-
  prior error* (code and fixture sharing one wrong prior, invisible to divergent cross-review) — and
  installed a durable countermeasure: **every fixture is now recorded-real (with provenance) or declared
  synthetic in-band.** Extracting the root cause instead of fixing three bugs in isolation is exactly
  the right move, and it's the reason the "sensors-complete-but-offline" risk stays bounded.

## Scope — the writing is outrunning the code (the pattern to watch)

This is not a defect; it's a tendency, and you already suspect it. The confirmed signals:

- **Spec size 39.7KB → 97.6KB; CONTRACT tokens 17 → 37; changelog stack 1 → 11** — roughly doubled —
  while the build advanced one milestone band (M4 of M7). Fastest growth is the §4c/§4d
  launch+rebalance family (six consecutive revs).
- **Several CONTRACTs guard subsystems that don't run yet:** the §9 runner state-source invariant (M5,
  unbuilt), the §6 capture budget breaker (M6), the "off-thesis-real must never absorb watch" inertness
  guard (no verdicts exist until deploy), the 17-year aging watch-item (on a days-old system). This is
  careful forward-design *and* where effort is spent guarding the imagined rather than the built.
- **"Live" / "sensors-complete" vocabulary runs ahead of a system that has never run on cadence** and,
  until the xlsx fix, could not read a single real input file. "Live cross-stream lag" means
  "real-data-derived in an offline test on a hand-frozen fixture," not "running in production." The
  "all offline" caveat is honestly present — but the word choice is the writing outrunning the code, and
  it's what let three convergent-prior errors accumulate before any real-data contact.
- **The `+593` numeric collision.** In state rev4 §5.1 the same number is both a settled backtest recall
  result ("the instrument sees structure form, +593-day lead") and the deflated live existence proof
  ("still an existence proof, n=1") — a few bullets apart. They're different measurements that coincide.
  A skimming reader can let the "proven" framing of the first silently upgrade the second. Consider
  visually distinguishing them (e.g. "recall: +593d on curated backtest" vs "live SOI-derived: +593d,
  n=1 snapshot").
- **The theory docs are the extreme case.** The 36KB rho-G/Hawkes subsystem is 100% unbuilt design-ahead
  for the *sibling* Smoke Detector, gated behind an integration that also isn't built — and Prospector's
  own design explicitly *refuses* the capacity-heavy version ("the fancy distance is refused"). The
  crash-flags episode: **7 flagged pairs → ~52KB of prose across 4 docs + a permanent CONTRACT vocabulary
  change**, while the *code* response was a single read-only `beta_diagnostic.py`. The reasoning is sound;
  the volume-per-line-of-code is the sharpest intellectual-satisfaction-vs-capability asymmetry in the
  archive.

I want to be precise about how to read this: the scope-ahead is **disciplined** — the theory is tagged
`[HYPOTHESIS]`/`[DECISION]`, given explicit kill-criteria, "engineered to be losable," and parked in
`deferred/`. It is honest about being ahead. The risk isn't dishonesty; it's that, for a builder whose
*own stated primary risk is the over-engineering/tinkering impulse* (the smoke-detector brief says so
directly), **the writing is the most seductive tinkering channel of all** — it feels like progress, it's
frictionless, and elegant unbuilt theory is exactly where that impulse would hide from you.

## Coherence — the thesis survived intact

Despite doubling in size and reversing two major decisions, the governing premise is word-for-word stable
across nine revisions: *"watches the ETF universe for structural novelty and proposes reading, never
orders"*; the firewall (§1), append-only (§5/§7), and no-LLM-text-as-data are unchanged verbatim. The
additions strain scope but never contradict the founding thesis. The pieces still form one argument.

One minor coherence nit worth a header caveat: the two same-named SOI docs — the top-level
`2026-07-04-soi-…md` is a *pre-build* spec (self-flagged: "reconcile the function names below against the
live code") while the `decisions/` copy is the *ratified post-build* record (with the "Filed truth over
prose" three-sector → four-sector correction). A fresh reader who opens the top-level first gets
intentions, not built truth. It's self-flagged, so it's handled — but two docs with one name where one
silently supersedes the other is the classic prosthetic tripwire.

## What is genuinely strong (protect these)

1. **The caveat travels with the claim.** `+593` never appears without "n=1, existence proof, not a
   rate" — in the spec, the state doc, the product doc, everywhere. The most abuse-prone number in the
   project is disciplined into never standing alone.
2. **Frozen-threshold anti-fitting, paid for on the record.** The rule survived its two sharpest tests
   without a knob moving: real TEKX landing `dormant` (you declined to lower `sector_min_weight` to
   rescue your best demo) and the 10.7%-vs-6.4% Utilities knife-edge. Discipline that costs you the
   headline case and is paid anyway is the strongest possible evidence it's real.
3. **Append-only reversal hygiene** — old claims quoted, not deleted; machine fossils alongside prose
   amendments.
4. **The convergent-prior countermeasure** — a recurring failure diagnosed, named, and converted to
   standing practice (fixture provenance).
5. **Design-ahead that's honest about being ahead** — epistemic tags, kill-criteria, `deferred/`
   placement, and active consolidation of overlapping notes (the product doc merges two priors into one
   source of truth and timestamps the supersession).

---

# Part III — Thoughts, Suggestions, and Ideas

## The one thing I'd change about how the project spends effort

Bias the next several sessions hard toward **shipping the §9 M5 runner and banking real prospective
firings**, and away from another rev of the spec. The system is now well-documented enough — arguably
over-documented relative to what runs. What it's starved for is *out-of-sample evidence*: the only way
`n=1` becomes a rate, and the only way you learn whether the tool fires on junk 20 times for every real
shift. Everything the docs are careful about (false-discovery rate, precision, whether the edge is real
or just architectural coherence) is *unanswerable until something runs on cadence*. The runner is the
gate to every empirical question you actually care about.

Concretely, in rough priority:
1. **Fix H1 first** (weight-units sanity check) — it's the one silent failure, and the runner will lean
   on `holdings.py` on every tick.
2. **Ship the M5 runner** — even a thin fetch-on-cadence loop that just accumulates firings and dormant
   dispositions into the fossil record. The dormant pile *is* the map of what the tool can't see yet;
   start drawing it.
3. **Then** the ticker→GICS classifier (the real existence-proof→rate unblock) and broader holdings
   intake — because those widen coverage, which is the binding constraint the corroboration slice
   already identified.

Fix H4, I1, B1 opportunistically before the runner leans on those paths (they're all in code the runner
exercises). S1/S2 can wait but should be closed before the runner can double-snapshot.

## A concrete suggestion for the doc structure (addresses both DRIFT findings)

Both memory-prosthetic leaks have the same root: **prose that states current status is copied forward
as if it were immutable history.** Two rules would prevent the whole class:
- **One status section, regenerated every rev.** Let §5 be the *only* place that says what's built vs
  deferred. Any status claim elsewhere (like §2.9) either gets regenerated from §5 or deleted. History
  sections should describe *decisions and rationale* (which are immutable) — never *current build state*
  (which isn't).
- **A changelog "closed" line must delete the open to-do it closes.** The aging-monitor drift happened
  because "pinned" was *added* to the changelog while the "reconciliation to close" line was *left* in
  the body. Closing an item should be a delete-and-restate, not an append.

Neither costs real time, and both directly serve the memory-prosthetic purpose you built the archive for.

## On the workflow itself (Desktop → Code → Science)

The three-tool split is sound, and the reason is specific: the failure mode you're guarding against — an
LLM confidently carrying a wrong assumption forward — is *correlated within a single context*. The model
that wrote the code is the worst-positioned to see its own baked-in premise (the CSV assumption *felt*
true to whoever wrote it, and to the fixture). A separate agent, fresh context, no stake in the code
being right, breaks that correlation. This review is the proof: I independently re-derived the CSV→xlsx
class before discovering your own record had already caught it — two independent paths landing on the
same soft spot is signal, not redundancy.

Two things make the QA seat here specifically strong, worth leaning into:
1. **This seat can *run* the code, not just read it.** Every BUG in Part I was reproduced by execution
   against your real config/fixtures. That's a different, stronger check than a design-time read — hand
   me the thing *after* it's written and I'll try to break it with real inputs.
2. **Fresh context is the feature.** Because I don't carry the design conversation, I read the code as
   the code, not as the code-you-meant. That's what surfaces the "you all looked past this" class.

**The one leak to guard in a multi-tool setup: the game of telephone.** Desktop's design intent can drift
by the time Code implements it, and QA then reviews against a third understanding. Your append-only docs
*are* the antidote — they're the shared ground truth all three read. The highest-leverage handoff to this
seat is **the diff plus the CONTRACT it's meant to honor**: "here's the new sensor, here's §4c." That lets
me check *faithfulness to your spec* rather than re-deriving intent — which is exactly the review that
caught H4 and B1 here (both are code-vs-stated-contract mismatches, invisible without the contract in hand).

## On the edge question (you raised it, so I'll answer honestly)

Your bet — "the coherence of the architecture unlocks any real edge that lives in the market" — is a real
hypothesis, and I think you already hold it correctly: as a hope with a lot of `if`s, not a claim. What
this review can say with confidence is a narrower thing: you have demonstrated **falsifiability**, not
**profitability**. Those are different properties, and only the first is shown. The system will *know when
it's wrong* — the null test ran before calibration, the falsifiers have teeth and have fired, the thresholds
are frozen against interest. That is genuinely more than most market tooling ever achieves, and it's the
necessary precondition for ever answering the edge question. But "falsifiable" and "has edge" are separated
by exactly the prospective, on-cadence evidence the runner would start accumulating. Build the runner, let
it run, and the market will answer the edge question for you — which is the only reviewer whose opinion on
that actually counts.

## A few smaller ideas

- **Make the dormant pile a first-class output, early.** You've framed `holdings_unavailable` /
  `sectors_unresolved` / `holdings_unavailable → dormant` as "the map of what the tool can't yet see."
  That map is *itself* a valuable artifact and a coverage roadmap — surface it as a standing report the
  moment the runner exists, not as an afterthought. It'll tell you where to widen intake next, ranked by
  how often you're blind there.
- **A "scope ledger" alongside the spec.** Since the writing-outruns-code tendency is real and you know
  it, a tiny running table — *feature / spec rev introduced / build status / LOC* — would make the gap
  between guaranteed-surface and built-surface visible at a glance, and turn "am I building or am I
  writing about building?" into a number you can check each session.
- **The Stooq adjusted-close question (P1) is worth 10 minutes now.** It's the one INFERRED finding that,
  if true, corrupts the base of the entire sensor stack (returns across any split/dividend). Pull one
  known split and check before the runner trusts that path.

---

## Appendix — review provenance

- **Code review:** four delegated reviewers (sensors, ingest, store/fold, identity/backtest) + my own
  read of the highest-risk files. Package scope ~5,390 LOC in `prospector/` (excludes tests, macOS `._*`
  resource-fork files, and the vendored `BuildContextFiles/ltee_archive`). Snapshot artifact
  `prospector-repo-snapshot.tar.gz`. Every BUG and high-severity ASSUMPTION reproduced in-kernel.
- **Whole-project review:** three diachronic readers over the mounted append-only docs archive
  (`/docs`, 30 markdown files, ~137k words) — spec line rev3→rev13, state line rev1→rev4, all 12 decision
  records, both theory docs, crash-flags guidance, and the deferred product doc — each reading in date/rev
  order. 36 observations (2 confirmed DRIFT, 4 REVERSAL, 10 SCOPE, 3 ABANDONED_ASSUMPTION, 13 STRENGTH, 4
  COHERENCE). The two headline DRIFT findings were re-verified by me against the raw doc text.
- **Discipline:** findings labelled `confirmed` were reproduced (code) or quoted from both revisions
  (docs); `inferred`/`impression` are reasoned but not executed/quoted end-to-end. I flagged my own
  earlier scope-line error (~4,900 → ~5,390 LOC) rather than carry it forward.
