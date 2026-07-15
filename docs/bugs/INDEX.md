# Bug register — the searchable index (grep this first)

*The register you search. **Start here for every bug hunt.** This is a map, not a document: one row per
**distilled** bug (root-caused + classed), whatever its status. It is a **living file** — appended every slice.
The doctrine (the meta-bug classes, the boundary, the template) lives in [`README.md`](README.md); this file is
the list you scan.*

**The load-bearing property: a miss here = new territory.** Every distilled bug in the project is a row below,
open or closed. So if you search for what you're about to touch and find nothing, you are genuinely in
un-hit ground — reason from first principles, not from a prior fix. If you find a row (even a `⭕ open` /
`💤 deferred` one), that is the highest-value hit there is: a known failure in the exact subsystem you're
working, waiting for you.

## How to search it (two axes + status)

Two controlled tag columns, each answering a different question — grep either:

- **Subsystem** — *"show me every bug that has bitten `backup`."* `grep -i "backup" docs/bugs/INDEX.md`
- **Shape** — *"where else has a `spurious-fire` alarm bitten?"* `grep -i "spurious-fire" docs/bugs/INDEX.md`
- **Status** tells you whether it's closed (`✅`), still live (`⭕`/`🟡`), or parked (`💤`) — an open row in your
  subsystem is a warning, not noise.

The tag vocabulary is **controlled** (defined in [`README.md` §5](README.md#5--tag-vocabulary-controlled)) so
the grep is reliable — new rows reuse the existing terms, they don't coin synonyms. **Class** → the §1 meta-bug
class (or `judgment` for a design-judgment call that isn't a code defect); the linked `notes/` doc holds the
full finding, and the rule/decision each spawned is the lineage.

**Status legend:** ✅ fixed · 🟡 partial / ratified-residual · ⭕ open · 💤 deferred (xfail / parked-by-decision).

---

## The full-review pass — 2026-07-05 (`notes/prospector_full_review_claude_science.md`)

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **H1** | holdings weights already-fractional → silently ÷100 too small → every fund `dormant` | ingest·holdings | green-on-synthetic · fail-silent | ✅ | 1,2,8 | per-file weight-sum sanity guard, `holdings.py:171` |
| **H2** | real xlsx frozen to disk mislabeled `.csv` | ingest·holdings | convergent-prior | ✅ (already on main) | 2 | `holdings.py:320` `ext="xlsx"` — fixed pre-currency-rule; **register drift** corrected by the sweep |
| **H3** | `"Weight (%)"` header variant → `no holdings header` | ingest·holdings | convergent-prior | ✅ #67 | 2 | prefix `_col(startswith)` in `holdings.py` · `test_holdings.py::test_parse_accepts_a_weight_percent_header_variant` + `::test_parse_still_faults_on_a_genuinely_alien_header` (mandatory negative) |
| **H4** | plain `REAL ESTATE INVESTMENT TRUSTS` header → `fault` not Real-Estate rollup | ingest·soi | green-on-synthetic | ✅ (alias present; real fault-path synthetic-only) | 1 | `gics_industry_alias: Real Estate Investment Trusts` in config; on real NPORT-EX the plain header sits under `CORPORATE BONDS` (excluded from the equity rollup), so the fault path is synthetic-only-reachable |
| **S1** | same-`ts` no-`event_id` fold not order-invariant | fold | green-on-synthetic | ✅ | 1 | fold requires/handles `event_id` |
| **S2** | two sub-second snapshots collide → `SnapshotDivergenceError` | snapshot·store | — | ✅ | — | sub-second `ts_compact` |
| **S3** | `^…$` regex admits trailing `\n` | store | — | ✅ (already on main) | — | `fund_registry.py:33-34` + `envelope.py:26` all use `\Z` (every write-path validator); **register drift** corrected |
| **S5** | pandas NaN sector → `"nan"` passes guards → phantom sector weight | ingest·soi | convergent-prior · fail-silent | ✅ #67 | 1,2 | `pd.isna` guard at `launch_corroboration.py:70` + `rebalance.py:82,94` · `test_launch_corroboration.py::test_sector_concentration_ignores_a_nan_sector_no_phantom_bucket` + `test_rebalance_sensor.py::test_identified_excludes_a_nan_identifier_no_phantom_security` |
| **I1** | ticker-reuse: detected series dropped, `matches[0]` may mis-pick | identity | identity-anchor | ✅ | 5 | `2026-07-06-identity-integrity.md` |
| **B1** | prospectus attached at trust level, not series | identity·ingest | identity-anchor | 🟡 | 5,6 | series-scoped `resolve_series`; accession residual flagged |
| **B2** | old-filing registrant → wrong `no_prospectus` → manual queue | identity·edgar | — | 🟡 | — | `older_filings_unread` reason; pagination deferred |
| **B3** | `SPY` in seed → market corrupts the 55-pair grid | xcorr | invariant-in-prose | ✅ | 3 | explicit `!= market` guard |
| **P1** | unadjusted Stooq Close → every cross-action return wrong | ingest·prices | green-on-synthetic | ✅ | 1,6 | `guard_live_source` + Tiingo adjClose vs NVDA-split |
| report.py | `acute_crises: []` empty list → `IndexError` | backtest | — | ✅ (already on main) | — | `report.py:101` `((…).get("acute_crises") or [{}])[0]` — catches present-but-empty; **register drift** corrected |
| **lag-lexical-sort** | T1 spawn chosen by lexical ts sort, asymmetric with T2's `parse_ts` → wrong T1 on mixed-format timestamps | identity·runner | — | ✅ #67 | — | sort T1 by `parse_ts` · `test_launch_corroboration.py::test_cross_stream_lag_picks_the_earliest_spawn_chronologically_not_lexically` |
| **eigengap** | no λ₂/λ₁ floor before trusting the spectral bipartition → a pure-noise contrast axis still yields a finite Q | dispersion | — | 💤 (parked-with-gate) | judgment | shadow-only today (spurious Q floods only the shadow record). **Must be answered at the dispersion PROMOTION review** — the moment blast radius shifts to real pages. Retroactively computable: constituent prices are frozen fossils, so set the floor from **measured** gap-vs-outcome across burn-in firings, not a guessed constant (the fossil store pays for the park) |
| **token-substring** | ≥4-char tokens match by plain substring (`reit ⊂ reiterate`, `bank ⊂ embankment`) — can bridge unrelated sectors | backtest | — | ✅ not-a-defect | judgment | deliberate recall-biased **stem** match over a **curated** static table, **backtest-only** (`corroboration.py`); mismatches surface in recall/precision. **Scope: do NOT reuse on uncurated input without revisiting** — there it is the I1/`matches[0]` class wearing a different hat |
| **sql-assert** | upload table name f-string-interpolated, gated only by a `-O`-strippable `assert` | store | — | ✅ #67 | — | literal-dict lookup (fail-closed even under `-O`) · `test_registry.py::test_upload_table_name_is_validated_fail_closed` |
| **edgar-`matches[0]`** | silent first-pick on an ambiguous symbol (the reused-ticker trap) | ingest·edgar | identity-anchor | ✅ (already on main) | 5 | `edgar.py:400-405` returns an `ambiguous_symbol` fault before `matches[0]`; **register drift** corrected |
| **ledger-datesort** | prior-snapshot selection compared date-dir names lexically | runner | — | ✅ (already on main) | — | `runner.py:170` `date.fromisoformat(name) < date.fromisoformat(current_date)`; **register drift** corrected |
| **DRIFT-1/2** | state-doc self-contradiction; aging-monitor "pinned" 8 revs | docs | doc-drift | ⭕ | 9 | doc pass owed |

## The going-live pass — 2026-07-07 (`notes/prospector_followup_review_2026-07-07.md`, `2026-07-07-live-cadence-qa-fixes.md`, `PROSPECTOR_REGRESSION_TESTS*_README.md`)

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test |
|----|--------------------|-----------|-------|--------|-------|---------------|
| **N1** | rendering the "read-only" dashboard flips store to WAL + DDL + write-lock (breaks §11) | dashboard·store | invariant-in-prose · test-passes-wrong-reason | ✅ | 3,4 | `test_dashboard_readonly.py` · `2026-07-07-dashboard-11.md` |
| **N2** | second same-day `pros run` double-writes launch/resolution fossils | runner·store | invariant-in-prose · test-passes-wrong-reason | ✅ | 3,4 | `test_runner_idempotency.py` |
| **N3** | dup-date rows → outer join fabricates a cross-observation (breaks §3) | ingest·prices | invariant-in-prose | ✅ | 3 | `test_prices_panel_dedup.py` |
| **N4** | Tiingo 429 backoff sized per-second can't reopen an hourly cap; 403 retried | ingest·prices | — | ✅ | — | `test_prices_retry_tiingo_cap.py` · `2026-07-07-prices-throttle-backoff.md` |
| **N5** | missing/relocated config → raw `FileNotFoundError` off repo-root | config·dashboard | test-passes-wrong-reason | ✅ | 4 | `test_dashboard_config_path.py` |
| **N6** | bad `retry_days` in prologue blinds the *entire* sensor phase | runner | fault-isolation | ✅ | fault-isolation | `test_runner_prologue_faults.py` |
| **N7** | transient 5xx/timeout hits final `raise` on attempt 1, drops the column | ingest·prices | — | ✅ | — | `test_prices_retry_transient.py` |
| **N8** | bare `except→None` collapses ambiguous-SOI fault into silent not-yet | ingest·soi | fail-silent · invariant-in-prose | ✅ | 3,8 | `test_soi_ambiguous_fault.py` · `2026-07-06-soi-*.md` |
| **N9** | SOI corroboration re-fetches every tick for 180d — no cadence gate | ingest·soi·runner | — | 💤 M7 | — | `test_soi_corroboration_cadence.py` **xfail** |
| **N10** | inert `off-thesis-real` lead still shows in "Active leads" panel as a signal | dashboard | state-as-signal | ✅ | state-as-signal | `test_dashboard_offthesis_rank.py` |
| **C.1** | `_compute_push` pages every tick on a persistent fault (no dedup) | email·runner | spurious-fire | ✅→E1/E2 | 7 | folded into §10 sender |
| **C.2** | runner docstrings + ARCHITECTURE "what's built" stale by a milestone | docs | doc-drift | ⭕ | 9 | doc pass owed |

## §9e dispersion — 2026-07-09 (`notes/dispersion_foreign_ticker_findings.md`)

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test |
|----|--------------------|-----------|-------|--------|-------|---------------|
| **9e-ENR** | constituent `ENR` pulled by bare ticker → NYSE Energizer's returns relabeled as Siemens Energy's CUSIP (silent wrong substrate) | dispersion·ingest | identity-anchor · green-on-synthetic · fail-silent | ✅ | 1,5,6,8 | `test_dispersion_foreign_and_cash_tickers.py::test_foreign_listing_is_not_pulled_by_a_colliding_us_ticker` · `2026-07-10-9e-constituent-symbol-resolution.md` |
| **9e-coverage** | cash/placeholder lines 404 silently; `coverage_actual` computed pre-drop → overstated | dispersion | fail-silent | ✅ | 6 | `::test_coverage_actual_reflects_the_priced_set` |
| **9e-membermap** | two `-`-ticker lines collapse to one dict key, dropping a CUSIP (latent) | dispersion | identity-anchor | ✅ | 5 | `::test_member_map_does_not_collapse_duplicate_tickers` |

## §10 email sender — 2026-07-10 (`notes/email_nuisance_suppression_findings.md`, `notes/PROSPECTOR_FAULT_SUPPRESSION_README.md`)

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test |
|----|--------------------|-----------|-------|--------|-------|---------------|
| **E1** | volatile fault message (moving URL dates) defeats suppression → **pages every day** on the live price path | email·runner | spurious-fire · green-on-synthetic · fail-silent | ✅ | 1,4,7,8 | `test_runner_fault_suppression_volatile_message.py` (4 tests) · [record](qa/2026-07-10-email-volatile-fault-suppression.md) |
| **E2** | flapping fault (present→clears→returns) pages on every return | email·runner | spurious-fire | 💤 by design | 7 | `::test_flapping_fault_does_not_page_on_every_recurrence` **xfail** |
| fault-taxonomy | heartbeat read "0 faults" beside nine that fired (advisories bypassed the alarm path) | email·runner | count-lie · fail-silent · split-path | ✅ | 8,9 | `test_runner_fault_taxonomy.py` · §8a CONTRACT |

## M6 deep review — 2026-07-14 (`notes/m6_deep_review_findings_qa.md`, `notes/PROSPECTOR_M6_REVIEW_TESTS_README_QA.md`)

*The complete finding set (all 15), not only the ones that earned a record — so a miss here is real. HIGH-value
alarm-layer cluster: three of the five HIGH items sit on the fault/alarm layer, this project's signature class.*

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **M7-01** | missed-Sunday heartbeat (launchd sleep-coalesce runs without `--heartbeat`) never caught up → false dead-man | heartbeat·ops | spurious-fire · fail-silent | ✅ #58 | 7 | `test_runner_heartbeat_catchup.py` + run_tick catch-up/failed-send (`test_runner.py`) · [build note](../notes/2026-07-14-m7-heartbeat-cluster-build-note.md) |
| **SNAP-01** | snapshot divergence (backdated event / non-det fold) counted 0 and never pages — `fault_sink=store.append` bypasses the `faults` accumulator | snapshot·runner | split-path · count-lie · fail-silent | ✅ #55 | 3,4,7,8 | `test_snapshot_divergence_accumulator.py` · [record](qa/2026-07-14-snapshot-divergence-accumulator-bypass.md) |
| **BK-1** | a blessed drive failing mid-copy (ENOSPC/unplugged) skips the healthy drive and records no failure | backup | fail-silent · fault-isolation | ✅ #56 | 8 | `test_backup.py::test_a_blessed_target_failing_mid_copy_records_a_failure_and_still_backs_up_the_healthy_drive` |
| **R1** | real SSGA cash lines carry CUSIPs → a benign money-market sweep fires a spurious "restructuring" rebalance onto shadow leads | rebalance | green-on-synthetic · identity-anchor · spurious-fire | ✅ #55 | 1,5,8 | `test_runner_rebalance_cash_and_prior.py::test_pure_cash_sweep_does_not_accrete_a_rebalance` · [record](qa/2026-07-14-rebalance-cash-line-cusip.md) |
| **M7-02** | backup runs in a separate process, writes no fault event → the weekly email reports "Health: OK" while backups fail for weeks | backup·heartbeat·email | fail-silent | ✅ #60 | 8 | `test_runner_backup_stale.py` + `test_backup.py` (marker) · [record](qa/2026-07-14-backup-stale-health-channel.md) |
| **M7-03** | in-email "Heartbeat: OK/BROKEN" line structurally always OK — its BROKEN branch is dead code in any sent email (keyed on the last RUN, not the last heartbeat) | heartbeat·email | fail-silent | ✅ #58 | 7 | `test_email_render.py::test_heartbeat_body_reports_cadence_state_not_a_tautological_ok` · `test_dashboard_views.py` |
| **R3** | two cash/derivative lines sharing the `-` sentinel collapse to one diff key; the lighter one silently vanishes | rebalance | identity-anchor · fail-silent | 🟡 (subsumed by R1's `-`-exclusion #55; no dedicated guard) | 5 | R1's `_is_cash_or_derivative` drops `-` lines before the key |
| **R4** | rebalance prior-parse fault has no `key=` → moving prior date pages daily (E1 recurrence on a sibling path) | rebalance | spurious-fire | ✅ #55 | 7 | `::test_unparseable_prior_fault_signature_is_stable_across_ticks` · [record](qa/2026-07-14-rebalance-prior-parse-volatile-message.md) |
| **BK-2** | mtime-window aliasing: a same-size content change within 2s of the prior backup is silently skipped → stale HDD copy | backup | fail-silent | ✅ #56 | 8 | `test_backup.py::test_a_same_size_ingest_re_pull_within_the_mtime_window_still_re_copies` |
| **M7-04** | `deploy.sh` can swap code/deps under an in-flight scheduled tick — no lock coordinates the two | deploy·runner | concurrency | ⭕ | judgment | lock/coordination — not yet designed |
| **M7-05** | heartbeat day keyed on LOCAL weekday while the cadence anchor is UTC; `schedule.weekly_day` dormant (read nowhere) | heartbeat·ops | doc-drift | ✅ #58 (swept by M7-01) | 9 | M7-01 retired the local-weekday gate + `weekly_day` |
| **R2** | the *naive* R1 fix (route the diff through `priceable_members`) would drop foreign equities whose add/drop IS signal — needs a cash-sentinel, not the price-universe gate | rebalance | identity-anchor | ✅ (constraint honored by R1, #55) | 5 · judgment | R1's `-`-sentinel keeps foreign constituents in the diff |
| **BK-3** | fire-and-forget copy: no post-copy read-back/checksum (the store's `write_atomic` does this; backup doesn't) | backup | — | 💤 (deferred, decision #57) | judgment | scheduled `verify-restore` leaning (decision #57) |
| **M7-06** | no single-instance lock / no `busy_timeout` PRAGMA; concurrency rests on launchd serialization + atomic appends | runner·store | concurrency | ⭕ | judgment | `kickstart -k` escape hatch documented |
| **GI-01** | couldn't verify `prospector.local.yaml`/`.env` are gitignored (source export carried no `.gitignore`) | config | — | ✅ (verified: `.gitignore:12`,`:15`) | judgment | both gitignored — verified 2026-07-14, not a defect |

## M6 discourse-capture review — 2026-07-13 (`notes/m6_capture_review_qa.md`)

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **CAP-DRIFT** | `capture.query_drift` compares the provider-issued query byte-exact; any benign normalization (trim / smart-quote / case) fires it on **every** capture — cry-wolf on the determinism guard | capture·runner | spurious-fire · green-on-synthetic | 🟡 ratified byte-exact; live-arming verify is the gate (stacked, PR pending QA) | 1,7 | **ordered by ruling** ([decision](../decisions/2026-07-14-query-drift-byte-exact.md)): observe first — one armed byte-compare **before arming** → byte-exact stands if the echo is clean → only a *demonstrated* transform earns a *minimal, observed-scoped* normalization (trims → `strip` only; documented finding), never a pre-emptive `strip()`; tests `test_build_queries_deterministic_and_ordered` + `test_query_drift_is_byte_exact_a_cosmetic_normalization_still_faults` |
| **CAP-USD** | monthly-USD cap silently stops enforcing if `unit_price_usd` is unset/0 — only the weekly count cap then guards spend | capture | fail-silent | ✅ (stacked, PR pending QA) | 8 | loud `capture.budget:usd_unpriced` fault when armed + unpriced · `test_capture.py::test_usd_cap_unenforceable_when_unpriced_faults_loud` |

## Post-M6 stack cold review — 2026-07-14 (`notes/2026-07-14-post-m6-stack-review_qa.md`, PR #64)

*A cold read of the whole post-M6 stack over real substrate: all 7 landed fixes CONFIRMED-CLOSED; 5 new
findings. The MED is the M7-03 fix's own regression — a nuisance-alarm the alarm-layer fix introduced, the
project's signature "fix makes cry-wolf" shape.*

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **M7-DASH-01** | the M7-03 fix relocated OK/BROKEN to the dashboard + board-snapshot but both hardcode `floor_days=7`, ignoring `schedule.heartbeat_cadence_days` (which the email honors) → a healthy system reads **BROKEN** on a >7d cadence (or false-OK on <7d) | dashboard·heartbeat | spurious-fire · green-on-synthetic | ✅ (stacked, PR pending QA) | 1,7 | `test_dashboard_heartbeat_cadence.py` (real export + app.py call sites) · [record](qa/2026-07-14-m7-dash01-heartbeat-cadence-hardcode.md) |
| **HB-NOTE-01** | heartbeat email footer hardcodes "7-day floor" text regardless of cadence — same one-clock drift, cosmetic | email | doc-drift | ✅ (stacked, PR pending QA) | 9 | `email_render.py` footer threads `hb['floor_days']` |
| **M7-DOC-01** | `runner.py` §9d docstring cites the retired `schedule.weekly_day` key | docs·runner | doc-drift | ✅ (stacked, PR pending QA) | 9 | docstring updated (`weekly_day` retired with M7-01; cadence gate is the deferred N9) |
| **BK-READ-01** | BK-2's content-verify re-reads every unchanged rewritten-in-place file every run (dst-HDD read amplification, unbounded as `ingest/` grows) — correctness intact, **cost** regression | backup | — | 🟡 ratified-residual | judgment | **accept + document** (correctness over cost at current scale — the re-read runs post-tick, seconds on a single-digit-GB store) · [decision](../decisions/2026-07-15-backup-content-verify-reread-accepted.md). Revisit trigger: backup wall-time > ~1 min or store growth making it minutes-long; **override:** if QA's #64 repro shows amplification materially worse than seconds, back to the design thread |
| **BK-MSG-01** | backup's broad `except Exception` labels ANY mid-copy fault "retry once the drive is healthy" — mislabels a non-drive fault | backup | — | ✅ #67 | one-off | hint gated on `isinstance(e, OSError)`; non-drive faults surface the real error · `test_backup.py::test_a_non_drive_midcopy_fault_does_not_get_the_drive_health_hint` |

---

## §3 · Open / deferred — the live tail (refer-back while fixing)

- 💤 **N9** (SOI cadence gate → M7) and **E2** (flapping-fault window) — both pinned by `xfail(strict=True)`
  tests that flip to a loud XPASS the moment the fix lands. Zero cost today.
- ✅ **M7-02** (backup-health → the weekly email) — **LANDED (#60)**, and the **dogfood** of this archive: the
  first bug carried end-to-end under the §6 discipline. `pros backup` stamps a last-success marker on each
  target on verified success; the runner reads it each tick and folds `backup.stale` (missing / older than
  `backup.max_age_days`) into the §8a heartbeat's one health channel (decision #57). Together with the
  heartbeat cluster (**M7-01** catch-up + **M7-03** in-email honesty, #58) the M7 dead-man now reports the two
  facts that matter — *is the runner alive* and *is the record being backed up*. Its "ran but bad" checksum
  sibling **BK-3** stays deferred (decision §3, scheduled `verify-restore`).
- 🟡 **CAP-DRIFT** — **SETTLED (decision 2026-07-14): observe first, then decide — not either/or.** The
  ORDERED gate, not a menu: (1) one armed byte-compare **before capture is armed** (it ships disabled) to
  see what the provider actually echoes; (2) the byte-exact guard **stands if the echo is clean**; (3)
  **only** a *demonstrated* transform earns a **minimal normalization scoped to that transform** (trims →
  `strip` and only strip; smart-quotes → that mapping), recorded as a finding — never a pre-emptive `strip()`
  against imagined behavior (pre-softening the guard is green-on-synthetic aimed at our own determinism
  guard). Our-side templating is already proven byte-deterministic. ✅ **CAP-USD** rides along — a loud
  `capture.budget:usd_unpriced` fault when armed-but-unpriced. (Both stacked, PR pending QA.)
- ⭕ **Concurrency judgments** — **M7-04** (deploy vs in-flight tick, no lock) and **M7-06** (no single-instance
  lock / `busy_timeout`) — design-judgment, currently resting on launchd serialization; open for a ratified
  coordination design.
- 🟡 **B1 / B2** — ratified with an **honest residual**: `prospectus_accession` stays registrant-level
  (flagged in the docstring); following `filings.files[]` pagination is the named deferral. **R3** rides here
  too (subsumed by R1's `-`-exclusion; a dedicated two-`-`-line regression is the residual).
- ⭕ **Doc debt** — DRIFT-1, DRIFT-2, C.2 (regenerate "what's built" from the wired set; §5 as single source).
  Deliberately **not** in the Tier-4 sweep — rides the rev15 spec-fold ("record matches territory", done together).
- ✅ **Tier-4 low-severity sweep — CLOSED (#67):** H3/S5/lag-lexical-sort/sql-assert/BK-MSG-01 fixed
  (commit-per-item); H2/H4/S3/report.py/edgar-`matches[0]`/ledger-datesort were already fixed on main and the
  **register drift** (false-⭕) is corrected with citations; **eigengap** → 💤 parked-with-gate (dispersion
  promotion review), **token-substring** → ✅ not-a-defect (curated backtest stem-match, scope-bounded);
  **BK-READ-01** → 🟡 ratified-residual (decision `2026-07-15-backup-content-verify-reread-accepted.md`).
- 💤 **BK-3** — post-copy checksum deferred by decision #57 (leaning toward a scheduled `verify-restore`).

---

*Maintenance: append a row the moment a bug is root-caused (not after it's fixed — the trail is the point), and
flip its status the moment the fix merges. **A fix isn't done until its row here is current** — the same gate as
"a fix needs a guarding test." That discipline is what keeps this register honest enough that a miss can be
trusted to mean novelty. The how-to is in [`README.md` §6](README.md#6--how-to-log-a-bug--the-two-author-handoff-bake-this-in).*
