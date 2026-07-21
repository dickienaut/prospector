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
| **B1** | prospectus attached at trust level, not series | identity·ingest | identity-anchor | 🟡 | 5,6 | series-scoped `resolve_series`; accession residual flagged. **Advanced 2026-07-21 (PR mandate-sgml-header-guard):** the mandate diff now VERIFIES coverage live via the SGML `<SERIES-AND-CLASSES-CONTRACTS-DATA>` header (`parse_series_classes`), so the trust-level accession no longer produces false diffs — the over-attribution guard skips a filing that does not cover the series. Registry `prospectus_accession` field stays registrant-level (the honest residual). [decision](../decisions/2026-07-21-mandate-series-scoped-confirmation-over-attribution-guard.md) |
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
| **M7-04** | `deploy.sh` can swap code/deps under an in-flight scheduled tick — no lock coordinates the two | deploy·runner | concurrency | ✅ #66 | judgment | `deploy.sh` takes the runner's lock via `pros store lock-run` · `test_run_lock.py` · [decision](../decisions/2026-07-14-single-writer-lock-and-deploy-coordination.md) |
| **M7-05** | heartbeat day keyed on LOCAL weekday while the cadence anchor is UTC; `schedule.weekly_day` dormant (read nowhere) | heartbeat·ops | doc-drift | ✅ #58 (swept by M7-01) | 9 | M7-01 retired the local-weekday gate + `weekly_day` |
| **R2** | the *naive* R1 fix (route the diff through `priceable_members`) would drop foreign equities whose add/drop IS signal — needs a cash-sentinel, not the price-universe gate | rebalance | identity-anchor | ✅ (constraint honored by R1, #55) | 5 · judgment | R1's `-`-sentinel keeps foreign constituents in the diff |
| **BK-3** | fire-and-forget copy: no post-copy read-back/checksum (the store's `write_atomic` does this; backup doesn't) | backup | — | 💤 (deferred, decision #57) | judgment | scheduled `verify-restore` leaning (decision #57) |
| **M7-06** | no single-instance lock / no `busy_timeout` PRAGMA; concurrency rests on launchd serialization + atomic appends | runner·store | concurrency | ✅ #66 | judgment | single-writer `run.lock` (`fcntl.flock`) + `busy_timeout=5000` belt · `test_run_lock.py` · [decision](../decisions/2026-07-14-single-writer-lock-and-deploy-coordination.md) |
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

## Post-#67/#66 cold review — 2026-07-15 (`notes/2026-07-15-pr67-pr66-cold-review_qa.md`, PR #69)

*QA cold read of the tier-4 sweep (#67) + single-writer lock (#66): all 11 #67 claims + all 6 #66 checks
CONFIRMED-CLOSED; three new LOW findings — one on #67's H3 fix, two on #66 — all now disposed (below).*

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **H3-DECOY** | H3's prefix header match is first-match-wins → a decoy `Weighted Average Life` column before the real `Weight` is silently read as the weight (latent — bites when the universe extends to bond funds) | ingest·holdings | green-on-synthetic · fail-silent | ✅ #71 | 1,8 | `_col` prefers **exact** match + `_weight_prefix_count` faults loud on >1-weight-prefix-no-exact · `test_holdings_weight_decoy.py` · [record](qa/2026-07-15-h3-decoy-weight-prefix-collision.md) |
| **LOCK-TEST-TAUT** | the M7-06 `busy_timeout` test asserts `==5000`, but CPython's `connect(timeout=5.0)` default already yields 5000 → green even with the PRAGMA deleted (test-integrity, class-4 one layer down) | store | test-passes-wrong-reason | ✅ #72 | 4 | writer connects `timeout=0` so the PRAGMA is the authoritative source; test asserts behaviour (RED when the PRAGMA is dropped) · `test_run_lock.py::test_busy_timeout_is_set_by_our_pragma_not_the_connect_default` |
| **DEPLOY-OVERLAY-DRIFT** | deploy locks from the DEV checkout on the premise dev/prod resolve `store.root` identically; a drifted untracked `prospector.local.yaml` overlay would lock the wrong store silently | deploy·config | — | 🟡 design-acknowledged | judgment | inherently unverifiable in a single checkout; mitigation = the on-Mini **dual `lock-path` GATE** — run `pros store lock-path` in **both** checkouts, assert identical (activation-checklist design note item 11 + decision `2026-07-14-single-writer-lock-and-deploy-coordination.md` on-Mini §) |

## Design-seat code review — 2026-07-15 → 07-17 (findings the design seat originated from code access)

*The design seat gained read-only **search** of a `main` snapshot (retrieval by query — not browse, not run),
and its first use surfaced a class-3 it reasoned through, flagging the one thing it structurally could NOT
check (is there an agreement test?); the build seat grounded it against live `main` @ `1e577b9`. The seam
held — new capability, no erosion of QA's independence (which still comes from QA's different position, not
the design seat's access).*

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **PAGE-WORTHY-MIRROR** | the §10 page-worthiness predicate is implemented **twice**, byte-identical (`runner._page_worthy_faults` / `email_render._page_worthy`), agreement asserted **only in both docstrings** and no test importing both — so a change to one silently diverges the **push decision** (runner's `_compute_push`) from the email **subject** (email_render's `push_subject`), landing a fault-driven push subject-lined `state change: …`, mislabeled on the one line §8a makes load-bearing | email·runner | invariant-in-prose | ✅ #73 | 3 | predicate lifted to `runner/fault_taxonomy.py`, imported by both consumers — drift impossible **by construction**. Duplication was **import-graph-forced** (`runner.py:51` imports email_render; email_render imports nothing back — a cycle blocks the naive import), so the fix is the shared home, not an import. **No agreement test by design** — post-lift it would assert `f(x)==f(x)`, the tautology this repo disposed as **LOCK-TEST-TAUT**; the structure is the guard, and the two consumers keep their own behaviour tests. Sibling **M7-DASH-01** (one rule, two homes). `_partition_faults` is **not** a sibling — it splits on `category` alone, ignoring `on_live_lead` (a category split, not a page-worthiness split); verified, not a defect |
| **M6-CAPTURE-DRIFT** | rev8 (state doc) files **M6 capture DEFERRED / "front-loaded to v2"** while it is **BUILT** on `main` (`capture.py` `4739b52`, "the last v1 build slice"; wired at runner phase 5; ships-disabled — *same shape as M7, opposite register*). The **634 count includes `tests/test_capture.py`**, contradicting the register that calls itself the source of truth for what's built. Root: **one stale `README.md` line laundered through both the rev15 and rev8 folds** — Code reasoned from the README's *account* of the code instead of opening `capture.py` (a **rule-3 miss**, Code's 2nd — same shape as the fixture-provenance scar). "Front-loaded to v2" **conflated** two things: capture (v1, built) vs interpretation (v2). | docs | doc-drift | ✅ (this PR) | 9 | **split the conflation:** capture → BUILT (arming rider names the CAP-DRIFT armed byte-compare), interpretation → ASPIRATIONAL, the DEFERRED entry gone; corrected across **rev8 · README · rev15** (`ARCHITECTURE.md` was already correct — the alignment target). Traced to **`4739b52`** (the artifact, not an invented record — METHOD.md's "a commit SHA" anchor). Found by Design's snapshot search, traced by Code to live `main`; caught because the register-check belonged to a seat that didn't write the register. **Lesson → METHOD.md rule-3 Code ledger (2nd scar; deferred, separate)** |

## Mandate supplement noise-cut follow-up — 2026-07-18 (`../notes/2026-07-18-mandate-noise-cut-next-steps.md`)

*The Case D correctness item split out of the 2026-07-18 upstream noise-cut (decision
`../decisions/2026-07-18-mandate-supplement-not-a-prospectus.md`): the one live-signal risk in that finding
set — a false extraction that could fire a spurious `mandate.changed`. The ~4 parser gaps (recall, safe-fault)
stay in the note.*

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **MANDATE-PROSE-HEADING** | `extract_mandate`'s heading match used bare `startswith`, so a short body-prose line OPENING with a strategy phrase (JPM Q&A: "Investment objectives may change…") was accepted as the strategy heading → `reliable: True` on the text below it (garbage) → a spurious `mandate.changed` could accrete onto a live lead (didn't fire only because the prior also faulted) | ingest·prospectus | spurious-fire · green-on-synthetic | ✅ (this PR) | 1,7 | `_is_heading(strict=True)`: the phrase must BE the heading (complete its final word + only a connective qualifier tail), a prose tail → no match → fault (safe); the supplement/SAI *declaration* match keeps the loose default, so the noise-cut is untouched · `test_mandate_sensor.py::test_is_heading_strict_rejects_prose_but_keeps_real_heading_variants` + `::test_extract_faults_on_a_prose_investment_objective_line_no_false_section` + `::test_prose_heading_cannot_produce_a_spurious_mandate_change` |
| **MANDATE-SOURCE-NEWLINES** | `html_to_text` derived line breaks from **source whitespace** as well as tag boundaries, but a newline in HTML text is insignificant (it renders as a space). Filers hard-wrap markup, so (a) headings arrived split — `Principal` ⏎ `Investment Strategies of the Fund` → "heading not found" on filings that plainly carry the section; and (b) **prose arrived chopped into heading-shaped fragments** — `principal investment strategy to do so` passed the `strict` guard (tail opens with the connective "to") → `reliable: True` on **risk text as the strategy** — MANDATE-PROSE-HEADING still live through a different door: not a bad pattern, a **bad line** | ingest·prospectus | spurious-fire · fail-silent | ✅ (this PR) | 1,7 | line breaks come from **block structure only** (`_BLOCK_TAGS` + collapse all source whitespace); reflowed prose lands far over the 80-char heading bar so the guard sees prose as prose · `test_mandate_sensor.py::test_html_to_text_keeps_a_hard_wrapped_heading_on_one_line` + `::test_html_to_text_still_breaks_lines_on_block_tags` + `::test_reflowed_prose_cannot_pose_as_a_heading` + `::test_extract_recovers_the_section_from_a_hard_wrapped_heading` · `../decisions/2026-07-19-mandate-extraction-structural-lines.md` |
| **MANDATE-TOC-SHADOW** | `extract_mandate` took the FIRST heading-shaped line and failed on it, so a **table-of-contents entry** shadowed the real section: the TOC lists `PRINCIPAL INVESTMENT STRATEGY`, then the page number, then the next TOC entry (a stop heading) → the "section" was the string `2` → too short → the whole filing reported unreliable while its real section sat 140 lines below | ingest·prospectus | fail-silent | ✅ (this PR) | 1 | continue-scan: a candidate is the heading only if it **bounds a section**; pattern priority preserved, no qualifying candidate → still faults, reason reported is the **first** candidate's · `test_mandate_sensor.py::test_extract_scans_past_a_table_of_contents_entry_to_the_real_section` + `::test_continue_scan_still_faults_when_no_candidate_bounds_a_section` |
| **MANDATE-DECL-BAR** | *(near-regression, caught in verification — never shipped)* fixing the two rows above reflowed a 497 sticker's self-declaration onto one **98-char** line ("Supplement dated … to the Pictet AI & Automation ETF's and Pictet Cleaner Planet ETF's …"), over the 80-char heading bar → `is_prospectus_supplement` stopped recognising **11 real stickers**, which would have re-created the exact advisory noise the 2026-07-18 cut removed. Found by diffing per-document outcomes across **all 148 frozen blobs**, not by inspection — the break was in the population that was already *passing* | ingest·prospectus | spurious-fire | ✅ (this PR) | 7 | declaration mode gets its own bar (`_DECLARATION_MAX_CHARS = 240`); safe because declaration matching is **anchored at line start**, so prose merely mentioning a supplement still cannot match · `test_mandate_sensor.py::test_a_sticker_declaring_itself_over_the_heading_bar_is_still_a_supplement` + `::test_the_looser_declaration_bar_does_not_admit_prose_mentioning_a_supplement` · **lesson: a fix verified only on the documents it targeted is verified on a biased sample** — the throwaway check is now standing infrastructure: `tools/corpus-check/` (run it on every change to `ingest/prospectus.py`; it reproduces this row's numbers with `--baseline 5e6da15`) |

## Pair-blindness + multi-fund sections — 2026-07-19 (`../notes/2026-07-19-mandate-pair-blindness-and-multifund-sections.md`)

*Found while trying to close the last 3 mandate advisories with a one-line config addition. The addition
was correct in isolation, scored clean on every metric the corpus harness produced, and would have shipped
3 false `mandate.changed` events. Reverted unshipped; the findings are the deliverable.*

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **CORPUS-CHECK-PAIRBLIND** | the frozen-corpus harness judged documents **one at a time**, but the sensor diffs a **PAIR** (prior, current) — so a candidate fix scoring "6 newly reliable, 0 regressions, 0 flips" would have emitted **3 false `mandate.changed`**, each diffing two DIFFERENT funds' prospectuses (B1: several series point at one trust-level filing). Per-document metrics are blind to this **by construction** — no care reading that report would have caught it | qa·tools | green-on-synthetic · invariant-in-prose | ✅ (this PR) | 1,7 | harness **section 6**: resolves each series' (prior, current) pair as `_last_frozen_prospectus` does, runs the real `diff_mandate` under both refs, reports **pairs that would newly fire**, and flags the structural tell — **an accession frozen under >1 series** · `tools/corpus-check/` · **lesson: verifying the unit you changed is not verifying the unit that acts** |
| **MANDATE-MULTIFUND-SECTION** | a **multi-fund** prospectus carries one strategy section **per fund**; `extract_mandate` takes the FIRST heading that bounds a section, so every series sharing the filing diffs the **first fund's** strategy (`0001999371-26-014940`: 2 sections, **4** series). Sibling shape: a single-fund filing claimed by 2 series (`0001999371-26-015168`) — B1 mis-attribution. **Fund-block isolation was made mandatory for multi-fund NPORT-EX in the SOI work; the mandate extractor never got it**, because these documents used to fail extraction and fault safely. #118 converts those safe faults into **firing** corroborations (6 newly-firing vs pre-fix, 5 shared-accession) | ingest·prospectus·identity | spurious-fire | 🟡 | 1,5 | **Shape A (over-attribution) FIXED 2026-07-21 (PR mandate-sgml-header-guard):** the SGML SERIES/CLASS header says which series a filing covers; the mandate over-attribution guard skips a filing that does not cover the series (chose option 2's real primary-source over option 1's blunt `series_sharing` guard). **Shape B (genuine multi-fund) PENDING PR2** — block isolation anchors on the same header's per-series fund name to isolate each fund's block; until then a covered multi-fund filing still diffs the first fund's section. [decision](../decisions/2026-07-21-mandate-series-scoped-confirmation-over-attribution-guard.md) · `test_mandate_sensor.py` (guard) + `test_runner_mandate.py` (not_covered / coverage-aware prior). **Blast radius was contained CIRCUMSTANTIALLY (all 64 historical `mandate.changed` on `_system`); the guard makes Shape-A containment STRUCTURAL** |

## v1.0.4 deploy + activation gates — 2026-07-19 (`../notes/2026-07-19-v1.0.4-deploy-and-activation-gates.md`)

*Found by **running a pending gate**: activation item 10 ("`deploy.sh` refuses under a held lock") had been
untestable until the lock shipped in v1.0.3. Running it passed on **behaviour** and failed on **diagnosis** —
the ideal gate outcome.*

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **DEPLOY-LOCK-MSG** | `ops/deploy.sh` read `rc=$?` immediately after `if ! ( … ); then` — which captures the **negation's** status (always 0 when the branch runs), never the inner `lock-run`'s **75** — so the "a scheduled tick is in flight, retry in a few minutes" branch was **unreachable dead code**, and genuine lock contention was reported as `deploy mutation (checkout / uv sync) failed`, pointing the operator at a broken checkout instead of a running tick | deploy | — | ✅ (this PR) | one-off | capture with `\|\| rc=$?` (also errexit-safe: a command before `\|\|` does not trip `set -e`) · found by running the item-10 gate 2026-07-19; verified **RED→GREEN** by re-running the contention test (wrong message → correct STOP message, prod unmoved both times). Sibling of **BK-MSG-01** (a mislabeled fault message: right refusal, wrong cause) |

## The firewall was an allowlist — 2026-07-20 (`../notes/2026-07-20-claude-md-consolidation-build-seat-findings.md`)

| ID | Symptom (one line) | Subsystem | Shape | Status | Class | Guarding test / fix site |
|----|--------------------|-----------|-------|--------|-------|--------------------------|
| **FIREWALL-ALLOWLIST** | the constitution's first firewall clause was guarded by two **hand-maintained allowlists** — `test_runner.py` (4 named runner modules) + `test_dashboard_views.py` (2 dashboard files) = **6 of ~54 package modules**. A new sensor reading `portfolio.yaml` **passed CI**. One rule, two homes, each needing an edit whenever a module is added (the `M7-DASH-01` / `PAGE-WORTHY-MIRROR` shape). Found by the Build read of CLAUDE.md, not by a failure | tests·firewall | invariant-in-prose · fail-silent | ✅ (this PR) | 3,7 | `tests/test_firewall.py` sweeps the **whole package**, both allowlists retired. **AST, not grep** — `dashboard/export.py` names `portfolio.yaml` in a docstring *asserting* the firewall, so a text scan false-positives; the sweep ignores comments (absent from the AST) and docstrings (prose) and inspects real string literals + real imports. Also guards the sibling-`models/` import ban (provenance headers, which name the sibling repo, must survive) and confines S3 client construction to the one config-driven module — the structural proxy for the detector's bucket, whose **name is deliberately absent from this repo**, so there is nothing to grep. **Proven RED on a real planted violation in `sensors/xcorr.py`** (one of the 48 modules the allowlist never covered), plus 4 negative controls incl. the docstring false-positive. **Residual, honestly:** the spec's stronger claim (credentials *unable* to read the bucket — "enforced at IAM, not convention") lives outside this repo and outside CI |

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
- ✅ **Concurrency (M7-04 / M7-06) — LANDED (#66):** one single-writer `run.lock` (`fcntl.flock`), acquired
  in-process by `pros run` and by `deploy.sh` (via `pros store lock-run`), + a `busy_timeout` belt. flock
  releases on process death, so a crash never wedges the lock (`kickstart -k` stays safe). The invariant is
  now mechanism, not assumption (decision `2026-07-14-single-writer-lock-and-deploy-coordination.md`).
- 🟡 **B1 / B2** — ratified with an **honest residual**: `prospectus_accession` stays registrant-level
  (flagged in the docstring); following `filings.files[]` pagination is the named deferral. **R3** rides here
  too (subsumed by R1's `-`-exclusion; a dedicated two-`-`-line regression is the residual). **B1 advanced
  2026-07-21:** the deferred "filing SERIES/CLASS header" unblock is now BUILT for the mandate diff — the
  over-attribution guard verifies coverage live, so B1 no longer produces false `mandate.changed`. The
  registry-field residual (and B2 pagination) remain the named deferrals.
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
