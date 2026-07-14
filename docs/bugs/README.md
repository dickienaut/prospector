# Bug & fix archive — the bugs, and the rules born from them

*Living index (stable-named, amended in place). **Rules are born from bugs.** A defect surfaces → we
root-cause it → fix it → guard it with a regression test → and when it reveals a *pattern*, a rule or CONTRACT
is born to stop the whole class recurring. This archive tracks both: the individual defects **and** the
meta-bugs that keep biting, with the lineage from each to the rule it spawned. **Refer back here before
shipping a slice** — the classes below are where this project's bugs actually come from.*

---

## How this works

- **Meta-bug classes** (§1) — the recurring patterns, each with its instances and the **rule/discipline it
  birthed.** This is the load-bearing register: repeat offenders are where rules come from, so a new bug's
  first question is *"which class is this?"* — which resolves to one of the **§1a taggable failure-classes**
  (1, 3, 4, 5, 7, 9) or `one-off`. The **§1b frame** (2, 6, 8) is never a tag: it is the lens you *read* to
  understand a bug — its root (2), the countermeasure (6), the severity axis (8).
- **The bug index** (§2) — every logged defect, compact: symptom · status · class · guarding test · the rule
  or decision it spawned · where the full detail lives.
- **Per-bug records** (`YYYY-MM-DD-<slug>.md`) — born dated (per the naming rule), for bugs found **going
  forward**; template in §4. Historical bugs keep their detail in their original QA docs under `notes/`
  (**never moved** — indexed here, not duplicated).

## Boundary (so this doesn't fragment)

- **`bugs/` = the defect lifecycle** — broke → root cause → fix → regression test → **rule born.**
- **`decisions/` = design / contract choices.** A bug that forces a CONTRACT change gets its own decision
  record; the bug entry **links** to it (the lineage), it doesn't restate it.
- **`notes/` = the raw QA findings & reviews** (the primary detail: the H/S/B/I/P review, the N-series
  follow-up, the §9e and §10 findings). This archive **indexes** them; it never moves or rewrites them.

---

## §1 · Meta-bug classes — the patterns that keep biting

*Ordered by how much they've cost. Each is a bug **factory**; the rule in the last column is the machine we
built to shut it down. When a new defect matches a **taggable** class here, tag it — and if the class has no rule yet, that
absence is the next rule.*

*§1 splits in two. **§1a — taggable failure-classes** (1, 3, 4, 5, 7, 9): the defect *shapes* a new bug
tags to. **§1b — the frame** (2, 6, 8): the root, the countermeasure, the severity axis — read to understand
a bug, never tagged (you can tag a bug "class 5"; you can't tag one "class 6 — go to primary source," that's
the fix, not a defect). **The numbers 1–9 are stable IDs — never renumbered:** the §2 "Class" column
references them by number, so the split only *groups* them (a `Class` value like `1,2,8` still resolves —
taggable 1, rooted in frame 2, fails silently per frame 8). The taxonomy's version of moving files into
folders without renaming them.*

### §1a · Taggable failure-classes — what a new bug tags to

*The actual defect patterns; "which class is this?" resolves to one of these — or `one-off`.*

#### 1. Green-on-synthetic / broken-on-real  ·  *the project's signature failure*
Code reads correctly, passes its tests, and breaks on the **real** substrate — because the test exercised a
*synthetic* fixture that couldn't reproduce the real shape. Named explicitly in the §10 finding: *"the third
time this pattern surfaced… the first on the alarm layer itself."*
- **Instances:** H1 (÷100 scale, scale-invariant tests stay green) · H4 · P1 (2-row fixture can't exercise a
  split) · S1 (property test masks it) · 9e-ENR (bare-ticker pull returns a real *wrong* series only vs the
  real TEKX file) · E1 ("same shape as the H1/H4 misses") · R1 (rebalance cash exclusion keyed on empty
  identifier; real SSGA cash lines carry CUSIPs — every fixture used cash-free equity baskets).
- **Rule born:** the **fixture-provenance discipline** — every fixture is *recorded-real* (source-URL +
  retrieval-date) or *declared-synthetic in-band*; and the QA seat **runs** the code against real
  config/fixtures, never just reads it. → [`CLAUDE.md` §Fixture provenance](../../CLAUDE.md#fixture-provenance) (validate slices against real/moving substrate).

#### 3. Invariant stated in prose, not enforced in mechanism
The code *says* an invariant in a docstring/comment but nothing makes it un-violatable; the test exercises the
*easy* version of the invariant, so the gap is invisible. The "governing frame" of the whole N-series fix plan.
- **Instances:** N1 (§11 read-only firewall — a `# read-only` comment that wrote to the store) · N2 ("two cold
  runs identical") · N3 (§3 no-fabrication) · N8 ("ambiguous → surface") · B3 (docstring "excludes the market")
  · SNAP-01 (the "never a raw `store.append` fault" rule stated in the `_emit_fault` docstring but not
  un-violatable — the snapshot sink re-introduced the bypass).
- **Rule born:** **(a)** convert the invariant from prose to **mechanism** (make it un-violatable — e.g. open
  the store `mode=ro`); **(b)** land a regression test that **attempts the violation**, not the easy case (the
  "fires-not-called" discipline). → [the `fires-not-called` discipline](../decisions/2026-07-06-soi-corroboration-retry-9d.md).

#### 4. A test that passes for the wrong reason
The suite is green, but *because of* the bug, or by an accident of the harness — so it certifies the defect.
- **Instances:** N1 (`test_dashboard_app` smoke passes only because the broken read-write dashboard creates the
  table on the fly) · N2 (two separate fresh stores dodge the same-store path) · N5 (relative config path
  resolves only because pytest runs from repo root) · E1 (synthetic `"boom"` message) · SNAP-01 (the existing
  divergence test passes `fault_sink=faults.append` — a list standing in for the accumulator — so it certifies
  "the sink fires", not that production's `store.append` sink reaches the accumulator).
- **Rule born:** **runner-faithful seeds** (test against the real store/path/message the runtime uses) + the
  violation-test rule (3b). Tightly coupled to classes 1 & 3.

#### 5. "Never anchor on a ticker" — the HECO lesson, recurring one grain deeper each time
A ticker is treated as a stable identity; it isn't (reuse, dual-class, foreign collision). Keeps reappearing at
finer grains as new layers land.
- **Instances:** I1 (launch series identity discarded, re-derived by ticker) · B1 (prospectus at trust level,
  not series) · 9e-ENR (constituent `ENR` = Siemens Energy *and* NYSE Energizer → wrong returns, silently) ·
  9e-membermap · smell-edgar-matches0 · R1 (the `identifier` field trusted to mean "real security position";
  a populated CUSIP on a cash/money-market line breaks that — the ticker-identity lesson one field over).
- **Rule born:** the **identity layer** (series-ID `S######` is the key; a bare ticker is rejected at the write
  path) + series-scoped `resolve_series` + the **§9e PRIMARY-SOURCE GATE**. → `docs/decisions/2026-07-06-identity-integrity.md`,
  `2026-07-10-9e-constituent-symbol-resolution.md`.

#### 7. Nuisance-alarm / GPWS — "the alarm that cries wolf trains you to disable it"
The smoke-detector brief's §2.4 failure, imported into our alert layer: a fault that pages every tick trains the
operator to ignore it.
- **Instances:** C.1 (every-tick fault push) · E1 (volatile message defeats suppression → pages daily) · E2
  (flapping fault) · the fault-taxonomy count-lie ("0 faults" beside nine that fired) · SNAP-01 (snapshot
  divergence counted 0 / never pages — the raw-`store.append` bypass re-opened on the snapshot layer) · R4
  (E1's volatile-message alarm re-appearing on the rebalance prior-parse path — a new `_emit_fault` site
  with no `key=`, proving the convention is not yet enforced in mechanism).
- **Rule born:** the **§8a alarm-posture CONTRACT** — push once on a *new/changed* fault, then fall silent to
  the weekly heartbeat; the `_emit_fault(key=…)` **stable-key** convention (key ≠ display message); operational
  faults page, manual-review advisories are counted+surfaced but don't page (except on a live-lead fund). →
  `docs/decisions/2026-07-10-10-email-sender.md`.

#### 9. Doc drift / memory-prosthetic leak
The archive misremembers — tells a returning reader something false — because status prose outside the
regenerated section rots, or a "closed" changelog line is added without deleting the open to-do it closed.
- **Instances:** DRIFT-1 (state doc §2.9 "deferred" vs §5.2 "shipped") · DRIFT-2 (aging-monitor "pinned"
  carried open 8 revs) · C.2 (code outran its docstrings + ARCHITECTURE.md).
- **Rule born:** **§5 is the single source of truth, regenerated every rev; history sections describe
  decisions, never current build-state**; a changelog "closed" line must **delete-and-restate** the to-do it
  closes. (Kin to the whole doc-discipline: amend-never-regenerate, the `2026-07-11-docs-reorganization` +
  `-doc-naming-convention` rules.)

### §1b · The frame — not taggable (read to understand: root · countermeasure · severity axis)

*Never a bug's tag. These are the lenses: **2** the root (why the silent set stays invisible), **6** the
countermeasure (go to the primary source), **8** the severity axis (how silently it fails). Convergent-prior
leads — the rest are its downstream symptoms.*

#### 2. Convergent-prior error  ·  *the root — why the whole silent set stays invisible*
Code **and** fixture share one wrong prior, so no divergent cross-review catches it — only the primary source
does. "The model that wrote the code is worst-positioned to see its own baked-in premise."
- **Instances:** the *"SPDR publishes daily CSVs"* prior (residue: H1/H2/H3) · the *"the daily file carries GICS
  sectors"* prior (drove the entire SOI slice) · S5 (a future NaN fixture).
- **Rule born:** **primary-source verification is the antidote** — read the *real filed artifact*, don't prove
  logic against imagined messiness; plus the three-seat workflow (design→build→QA) so the author isn't the
  reviewer. → `docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md`, `2026-07-04-soi-derived-sector-concentration.md`.

#### 6. Go to the primary source  ·  *the countermeasure that keeps paying off*
The one you named: the truth is in the filed artifact, and only opening it breaks the shared prior. Every time
we've gone to the source, it moved the design.
- **Instances:** the xlsx/blank-Sector discovery (opening a real SSGA file) · P1 (verify vs a known NVDA split
  before trusting a price source) · B1/B2 (registrant-level EDGAR truth) · 9e-ENR (widened the gate to
  dual-class + foreign + cash lines).
- **Rule born:** the **primary-source gate** before a live slice; the **no-third-party-symbol-feed** /
  **no-LLM-text-as-data** walls (a bought feed or model prose would breach the primary-source discipline).

#### 8. Fail-loud vs fail-silent  ·  *the severity axis, not a cause*
The codebase's dominant (good) instinct is to fail loud / fault rather than mis-roll. The bugs that **matter**
are the few that fail *silently* — this is the axis that ranks every class above, not a class of its own.
- **The silent set (the dangerous ones):** H1, H4, I1/B1, S1, S5, N1, N2, N3, N8, N10, 9e-ENR, E1, the count-lie.
- **Rule of thumb:** a finding's severity ≈ how silently it fails. A loud raise is a nuisance; a silent wrong
  number corrupts the fossil record.

---

## §2 · The bug index

*Status: ✅ fixed · 🟡 partial/ratified-residual · ⭕ open · 💤 deferred (xfail). "Class" → §1. Detail lives in
the linked `notes/` doc; the rule/decision each spawned is the lineage.*

### Full-review pass — 2026-07-05 (`notes/prospector_full_review_claude_science.md`)
| ID | Symptom (one line) | Status | Class | Guarding test / fix site |
|----|--------------------|--------|-------|--------------------------|
| **H1** | holdings weights already-fractional → silently ÷100 too small → every fund `dormant` | ✅ | 1,2,8 | per-file weight-sum sanity guard, `holdings.py:171` |
| **H2** | real xlsx frozen to disk mislabeled `.csv` | ⭕ | 2 | `ext="xlsx"` (Tier-4) |
| **H3** | `"Weight (%)"` header variant → `no holdings header` | ⭕ | 2 | prefix/contains match (Tier-4) |
| **H4** | plain `REAL ESTATE INVESTMENT TRUSTS` header → `fault` not Real-Estate rollup | ⭕ (re-scoped synthetic-only) | 1 | plain-REIT alias in `gics_industry_alias` |
| **S1** | same-`ts` no-`event_id` fold not order-invariant | ✅ | 1 | fold requires/handles `event_id` |
| **S2** | two sub-second snapshots collide → `SnapshotDivergenceError` | ✅ | — | sub-second `ts_compact` |
| **S3** | `^…$` regex admits trailing `\n` | ⭕ | — | `\Z`/`fullmatch` (Tier-4) |
| **S5** | pandas NaN sector → `"nan"` passes guards → phantom sector weight | ⭕ | 1,2 | `pd.isna` guard |
| **I1** | ticker-reuse: detected series dropped, `matches[0]` may mis-pick | ✅ | 5 | `2026-07-06-identity-integrity.md` |
| **B1** | prospectus attached at trust level, not series | 🟡 | 5,6 | series-scoped `resolve_series`; accession residual flagged |
| **B2** | old-filing registrant → wrong `no_prospectus` → manual queue | 🟡 | — | `older_filings_unread` reason; pagination deferred |
| **B3** | `SPY` in seed → market corrupts the 55-pair grid | ✅ | 3 | explicit `!= market` guard |
| **P1** | unadjusted Stooq Close → every cross-action return wrong | ✅ | 1,6 | `guard_live_source` + Tiingo adjClose vs NVDA-split |
| report.py | `acute_crises: []` empty list → `IndexError` | ⭕ | — | `... or [{}]` (Tier-4) |
| smells ×6 | lag-lexical-sort, eigengap, token-substring, sql-assert, edgar-`matches[0]`, ledger-datesort | ⭕ | mixed | low-severity sweep |
| **DRIFT-1/2** | state-doc self-contradiction; aging-monitor "pinned" 8 revs | ⭕ | 9 | doc pass owed |

### Going-live pass — 2026-07-07 (`notes/prospector_followup_review_2026-07-07.md`, `2026-07-07-live-cadence-qa-fixes.md`, `PROSPECTOR_REGRESSION_TESTS*_README.md`)
| ID | Symptom (one line) | Status | Class | Guarding test |
|----|--------------------|--------|-------|---------------|
| **N1** | rendering the "read-only" dashboard flips store to WAL + DDL + write-lock (breaks §11) | ✅ | 3,4 | `test_dashboard_readonly.py` · `2026-07-07-dashboard-11.md` |
| **N2** | second same-day `pros run` double-writes launch/resolution fossils | ✅ | 3,4 | `test_runner_idempotency.py` |
| **N3** | dup-date rows → outer join fabricates a cross-observation (breaks §3) | ✅ | 3 | `test_prices_panel_dedup.py` |
| **N4** | Tiingo 429 backoff sized per-second can't reopen an hourly cap; 403 retried | ✅ | — | `test_prices_retry_tiingo_cap.py` · `2026-07-07-prices-throttle-backoff.md` |
| **N5** | missing/relocated config → raw `FileNotFoundError` off repo-root | ✅ | 4 | `test_dashboard_config_path.py` |
| **N6** | bad `retry_days` in prologue blinds the *entire* sensor phase | ✅ | fault-isolation | `test_runner_prologue_faults.py` |
| **N7** | transient 5xx/timeout hits final `raise` on attempt 1, drops the column | ✅ | — | `test_prices_retry_transient.py` |
| **N8** | bare `except→None` collapses ambiguous-SOI fault into silent not-yet | ✅ | 3,8 | `test_soi_ambiguous_fault.py` · `2026-07-06-soi-*.md` |
| **N9** | SOI corroboration re-fetches every tick for 180d — no cadence gate | 💤 M7 | — | `test_soi_corroboration_cadence.py` **xfail** |
| **N10** | inert `off-thesis-real` lead still shows in "Active leads" panel as a signal | ✅ | state-as-signal | `test_dashboard_offthesis_rank.py` |
| **C.1** | `_compute_push` pages every tick on a persistent fault (no dedup) | ✅→E1/E2 | 7 | folded into §10 sender |
| **C.2** | runner docstrings + ARCHITECTURE "what's built" stale by a milestone | ⭕ | 9 | doc pass owed |

### §9e dispersion — 2026-07-09 (`notes/dispersion_foreign_ticker_findings.md`)
| ID | Symptom (one line) | Status | Class | Guarding test |
|----|--------------------|--------|-------|---------------|
| **9e-ENR** | constituent `ENR` pulled by bare ticker → NYSE Energizer's returns relabeled as Siemens Energy's CUSIP (silent wrong substrate) | ✅ | 1,5,6,8 | `test_dispersion_foreign_and_cash_tickers.py::test_foreign_listing_is_not_pulled_by_a_colliding_us_ticker` · `2026-07-10-9e-constituent-symbol-resolution.md` |
| **9e-coverage** | cash/placeholder lines 404 silently; `coverage_actual` computed pre-drop → overstated | ✅ | 6 | `::test_coverage_actual_reflects_the_priced_set` |
| **9e-membermap** | two `-`-ticker lines collapse to one dict key, dropping a CUSIP (latent) | ✅ | 5 | `::test_member_map_does_not_collapse_duplicate_tickers` |

### §10 email sender — 2026-07-10 (`notes/email_nuisance_suppression_findings.md`, `notes/PROSPECTOR_FAULT_SUPPRESSION_README.md`)
| ID | Symptom (one line) | Status | Class | Guarding test |
|----|--------------------|--------|-------|---------------|
| **E1** | volatile fault message (moving URL dates) defeats suppression → **pages every day** on the live price path | ✅ | 1,4,7,8 | `test_runner_fault_suppression_volatile_message.py` (4 tests) · [worked record](2026-07-10-email-volatile-fault-suppression.md) |
| **E2** | flapping fault (present→clears→returns) pages on every return | 💤 by design | 7 | `::test_flapping_fault_does_not_page_on_every_recurrence` **xfail** |
| fault-taxonomy | heartbeat read "0 faults" beside nine that fired (advisories bypassed the alarm path) | ✅ | 8,9 | `test_runner_fault_taxonomy.py` · §8a CONTRACT |

### M6 deep review — 2026-07-14 (`notes/m6_deep_review_findings_qa.md`, `notes/PROSPECTOR_M6_REVIEW_TESTS_README_QA.md`)
| ID | Symptom (one line) | Status | Class | Guarding test |
|----|--------------------|--------|-------|---------------|
| **SNAP-01** | snapshot divergence (backdated event / non-det fold) counted 0 and never pages — `fault_sink=store.append` bypasses the `faults` accumulator | ✅ patch drafted | 3,4,7,8 | `test_snapshot_divergence_accumulator.py` · [record](2026-07-14-snapshot-divergence-accumulator-bypass.md) |
| **R1** | real SSGA cash lines carry CUSIPs → a benign money-market sweep fires a spurious "restructuring" rebalance onto shadow leads | ✅ patch drafted | 1,5,8 | `test_runner_rebalance_cash_and_prior.py::test_pure_cash_sweep_does_not_accrete_a_rebalance` · [record](2026-07-14-rebalance-cash-line-cusip.md) |
| **R4** | rebalance prior-parse fault has no `key=` → moving prior date pages daily (E1 recurrence on a sibling path) | ✅ patch drafted | 7 | `::test_unparseable_prior_fault_signature_is_stable_across_ticks` · [record](2026-07-14-rebalance-prior-parse-volatile-message.md) |
| **M7-01** | missed-Sunday heartbeat (launchd sleep-coalesce runs without `--heartbeat`) never caught up → false dead-man | 💤 decision-dependent (xfail) | 7 | `test_runner_heartbeat_catchup.py` **xfail** |

---

## §3 · Open / deferred — the live tail (refer-back while fixing)

- 💤 **N9** (SOI cadence gate → M7) and **E2** (flapping-fault window) — both pinned by `xfail(strict=True)`
  tests that flip to a loud XPASS the moment the fix lands. Zero cost today.
- 💤 **M7-01** (missed-heartbeat catch-up) — decision-dependent: needs a design choice (where catch-up logic
  lives — runner vs `run.sh`; what records "last heartbeat sent") before a fix. Pinned by
  `test_runner_heartbeat_catchup.py` `xfail(strict=True)` — flips to XPASS when the mechanism lands.
- 🟡 **B1 / B2** — ratified with an **honest residual**: `prospectus_accession` stays registrant-level
  (flagged in the docstring); following `filings.files[]` pagination is the named deferral.
- ⭕ **Doc debt** — DRIFT-1, DRIFT-2, C.2 (regenerate "what's built" from the wired set; §5 as single source).
- ⭕ **Tier-4 low-severity sweep** — H2, H3, H4-alias, S3, S5, `report.py` empty-list, and the six smells.

---

## §4 · Per-bug record template (new bugs, going forward)

Copy this block into `docs/bugs/YYYY-MM-DD-<slug>.md` (born dated, per the naming rule):

```
# <slug> — <one-line symptom>
*Bug record, YYYY-MM-DD. Status: fixed | partial | open | deferred(xfail). Class: <§1 class, or one-off>.*

- **Symptom** — what was observed (the failing behaviour; who/what saw it).
- **Root cause** — the real why, not the surface. (Name the file:line.)
- **Fix** — what changed + the commit/PR.
- **Regression test** — `tests/<file>::<test>` — and how it goes RED without the fix (attempt the violation).
- **Rule born** — the rule/CONTRACT/decision this bug spawned, if any (link the `decisions/` record or the
  `CLAUDE.md` clause). ← the lineage this archive exists to keep.
- **References** — the QA finding it came from, the spec §, related bugs by ID.
```

*Rule of use: log a bug here the moment it's root-caused, not after it's fixed — the point is the trail, and a
bug whose fix births a rule is the most valuable entry in the repo.*
