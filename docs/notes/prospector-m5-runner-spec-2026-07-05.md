# Project Prospector — Milestone 5 spec: the runner + outputs

*Design-thread spec, 2026-07-05. For the implementer (VSCode Claude Code) to build against, and the QA layer (Claude Science) to review the implementation against. Builds on **spec rev 13** (M4 sensors-complete + the SOI resolver). Cite this spec + the diff when handing work for review. Folds into a future spec rev when built. Where this says **DEFAULT**, it is config; where it says **CONTRACT**, do not deviate without the design thread.*

*Completed 2026-07-06 with the gaps a cold implementer would hit — §9a (ingest orchestration + `EdgarClient` lifecycle), §9f (between-tick state = the fossil record, concretely), §9g (run-log + exception granularity), the §10 state-change-push precision (pinned to `fold.state_changed`), and the **dormant-pile coverage report** — and reconciled with the Claude Science QA review (`docs/prospector_full_review_claude_science.md`): its two runner-blocking findings are **landed** (H1 weight-units sanity, S2 snapshot sub-second-lossless), and the identity-integrity trio (I1/B1/B2) + H4 are the named runner-path next slice (see **Prerequisites**, below).*

---

## What M5 is (and what it deliberately is not)

Everything built through M4 is a pure function or a deferred pass **waiting for a driver** — the sensors, the SOI resolver, the identity retries, the corroboration reach-back all exist and are tested offline, but nothing runs on a schedule. **M5 is that driver, plus the two surfaces that make the record legible: email and a read-only dashboard.** After M5, Prospector is *live* — it records on cadence, pushes on state change, and you can look at it.

**The one load-bearing design rule: the runner adds no intelligence.** It is a scheduler and orchestrator — it invokes the deterministic sensors in order, on cadence, and renders their output. All *judgment* lives where it already lives: in the sensors (deterministic, countable facts) and in the human (verdicts). **CONTRACT: the runner must never grow decision logic.** It orchestrates; it does not decide. If a change to the runner would make it *interpret* rather than *sequence*, it belongs in a sensor or in the human's hands, not here. (Same class of rule as "no LLM text as data.")

**The firewall holds at the runner too (CONTRACT).** The runner touches its own store, sends its own email, and renders its own dashboard. It **never** places/sizes/recommends a trade, **never** reads `portfolio.yaml` or the detector's bucket, and has **no run-now surface** anywhere it exposes (CLI, endpoint, or dashboard control). A lead still graduates to the portfolio only by the human passing the per-thread pipeline by hand.

---

## §9 — The runner (the scheduled entrypoint)

**Shape.** A single stateless entrypoint (cron on a small instance, or Lambda + EventBridge — DEFAULT; the choice is M7's, not M5's). **CONTRACT: stateless between runs except the store.** All state is the fossil record; the runner holds nothing across runs, so two runs from cold produce the same result as one warm process. This is what makes it safe to run as an ephemeral scheduled job (and mirrors the three-stateless-Claudes discipline — coordinate only through the durable record).

**Run order (CONTRACT — the sequence is load-bearing, not incidental).** Each run executes in this order:

1. **Config honesty first.** Hash the config; if it changed, emit `config.changed` with the diff **before any sensor runs**. A run must never act on a config whose change hasn't been fossilized first.
2. **Ingest.** Holdings (issuer daily); **SOI-fetch** for the due `sectors_unresolved` launches (§9b); rebalance/mandate inputs. Freeze-before-parse throughout.
3. **Sensors (§4a–§4d), in order.** Excess-correlation (§4a) → dispersion (§4b, shadow — §9e) → launch recording + the **corroboration retry pass** (§4c, §9d) → rebalance accretion + mandate-diff (§4d, honoring the frozen-prior invariant §9c).
4. **Identity retries.** Drain the failed-resolution queue (daily retry for N days, then manual queue). Nothing evaporates.
5. **Capture for due leads** — **stub / no-op until M6.** The step exists in the run order now so M6 plugs in without reshaping the runner; in M5 it does nothing.
6. **Snapshots.** Materialize folds at the reactive cadence (dense while active, sparse when quiet, immediately on any state change).
7. **Push email if state changed** (§10). Same-day.

**Weekly run adds:** the etfdb scrape (draft grid refresh, verified against EDGAR before any write) + the **heartbeat email** (§10), regardless of activity.

**Every run:**
- writes a **run-log** object (what ran, what changed, elapsed, config hash);
- on **any exception**, emits a `fault` event **and still attempts the push email** — a fault email beats silence. A crashed run must not fail silently.
- all record times are **UTC**; email renders local.

**Cadence (CONTRACT — the alert-posture floor).** Daily run + weekly run. A **hard cadence floor** (weekly heartbeat is the slowest anything goes). **No run-now** command, button, or endpoint — record on cadence, push on state change. (`pros store reindex` remains repair, not run-now — it recomputes nothing.)

**Active-lead ceiling is a tripwire, surfaced not enforced (CONTRACT).** Each run checks the non-shadow active-lead count against the §8a ceiling. Exceeding it is a **tripwire for human recalibration of sensor sensitivity**, surfaced in the heartbeat and dashboard — **never** an auto-tune of thresholds. No threshold in this system is ever moved by a self-updating rule; every change leaves a deliberate `config.changed` fossil.

---

## §9a — Ingest orchestration + the `EdgarClient` lifecycle

Run-order step 2 fans out to every source; all share the §3 **freeze-before-parse** discipline (the raw body lands via `write_atomic` before anything reads it, so a corrupt body is still a postmortem artifact). What is fetched, on what cadence (DEFAULT):

- **Prices** (`PriceIngest.pull`) — the sector-ETF universe, **daily** (Yahoo primary → adjusted close; Stooq fallback). Feeds the xcorr + dispersion pipelines. (P1 open item: confirm the Stooq branch reads an *adjusted* close before it's ever the live source — see Prerequisites.)
- **Holdings** (`HoldingsIngest.pull`) — each **watched** fund's issuer daily file, **daily**; the input to dispersion, rebalance, and the corroboration reach-back. The weight-units sanity check (H1, landed) faults a mis-scaled file rather than silently resolving every fund dormant.
- **MF-ticker map** (`EdgarClient.mf_tickers`) — **daily**, diffed against the prior frozen snapshot to detect launches (§4c). Seed the prior at deploy so a first run doesn't flag the whole universe.
- **Submissions** (`EdgarClient.submissions`) — **daily** for the funds in the identity-retry window and any watched fund, to drain the failed-resolution queue and to discover a new prospectus (mandate, §4d) or SOI (§9b) accession.
- **SOI** (§9b) — **weekly**, and only for launches still `sectors_unresolved` (SOIs post ~quarterly, so a daily re-fetch is waste).
- **etfdb** — **weekly** grid-draft refresh, verified against EDGAR before any write.

**`EdgarClient` lifecycle (DEFAULT).** One client per run (stateless between runs); its `persist` seam wired to `write_atomic(layout.edgar_path(date, name), body)` so every fetch is frozen; rate-limited at `edgar.max_requests_per_sec` (8, under SEC's 10/s); **single-threaded** (the daily fund count is small — concurrency is an M7 optimization, never an M5 requirement); a per-fetch timeout; and a fetch failure (404 / timeout / non-2xx) is a **soft fault** — emit a `fault`, skip that fund, continue (§9g) — never a run-abort. A brand-new fund whose accession EDGAR hasn't indexed yet is a *not-yet*, re-attempted next run (§9d), not a failure.

---

## §9b — SOI-fetch (the deferred fetch, now wired to `EdgarClient`)

The SOI **reader** is built (rev 13); M5 wires the **fetch**. It discovers *which* accession and *which document within it* carries a fund's current GICS-industry-grouped SOI, freezes it, and hands it to the reader.

- **Scope:** `SOI_FORMS` (start with `NPORT-EX`, then `N-CSR`, `N-CSRS`); a `latest_soi(submissions)` mirroring `latest_prospectus`; and accession `index.json` resolution for the non-primary SOI document within a filing. `NPORT-EX` is the sector-bearing artifact (N-PORT *XML* carries no GICS).
- **Wiring:** freeze via `SoiIngest.freeze` (already the write primitive); wire the `sensors/soi.scan` `fetch_body` seam to `EdgarClient`. Tests pass a fixture thunk to the seam — the runner passes the real client.
- **CONTRACT — drop-and-freeze for tests, fetch-on-cadence for the runner, never conflated.** The frozen `.htm` fixtures are dropped once by hand and are **never** refreshed by fetch code — the offline tests must stay deterministic. The runner's fetch feeds the *live* pipeline only.
- **Two robustness items (from the real fixtures — do not skip):** **(1) anchor each fund on a unique stem, never a full title** — funds rebrand (TEKX was "SPDR Galaxy…" then "State Street Galaxy…"), so key on `Galaxy Transformative Tech Accelerators`, never a dated title, never bare `Galaxy` (matches three funds → ambiguous-anchor fault). **(2) header variants** — accept the `CONSOLIDATED SCHEDULE OF INVESTMENTS` prefix (sibling blocks bound the target) and exclude `…(continued)` continuation headers (or a fund's block fragments).
- **Which launches trigger a fetch:** the `sectors_unresolved`-dormant launches, on the retry schedule (§9d). Do not fetch SOIs for funds that aren't waiting on sector resolution.

---

## §9c — The mandate frozen-prior invariant (CONTRACT)

The mandate sensor diffs a fund's *new* prospectus strategy-section against its *prior*. **The prior is its last FROZEN prospectus blob — never the registry's `prospectus_accession` field.** An identity pass earlier in the same run may advance `prospectus_accession` in the registry; if the mandate sensor read the prior from the registry, it would diff the new filing against a "prior" it never actually froze, and either miss a real change or hallucinate one. **The runner must source the mandate prior from the frozen blob store, not the registry.** This is a runner-level state-source invariant precisely because the runner is where the identity pass and the mandate pass share a run.

---

## §9d — Deferred-pass scheduling: retry-until-it-lands (CONTRACT)

Corroboration and SOI-resolution are **deferred passes**: a launch is recorded dormant at detection (`detected_at` nailed), its sectors (holdings or SOI) land days-to-months later, and the pass re-runs when they land — **reaching back, preserving the original `detected_at` as T2** so the cross-stream lag measures to detection, never to when sectors happened to arrive.

- **The runner owns the retry scheduling.** On each run, for each launch still in a `holdings_unavailable` / `sectors_unresolved` / dormant-pending state, attempt to fetch its holdings/SOI. If they've landed → run the corroboration pass (which reaches back). If not → leave it dormant and re-attempt next run. **CONTRACT: the pass is *called with* holdings/sectors; it never assumes they exist.** The unavailable/unresolved disposition is a first-class recorded state (flag the blind spot, never guess), re-attempted, not an error.
- **Retry horizon (DEFAULT):** retry until sectors land or the launch ages past a config horizon (`corroboration.retry_horizon_days`), after which it stays dormant-terminal and is surfaced for deliberate survey. No infinite unbounded fetching of ancient launches.
- **Wiring at resolution would silently never fire** (it'd find the empty set) — the pass is deferred *by design*; do not "optimize" it into the launch-resolution path.

---

## §9e — Dispersion's shadow clock (CONTRACT)

Dispersion ships in **shadow mode**: it records and spawns but does **not** page, and is **excluded from the active-lead ceiling**, for its first live quarter (~90 days) of burn-in — because survivor-biased calibration under-predicts live firing rates, so it needs a live-forward window before it's trusted to page.

- **The runner tracks the shadow clock** (days since dispersion went live) and **surfaces it** (heartbeat + dashboard) so the human knows when the burn-in is complete.
- **CONTRACT: no auto-promotion.** The shadow→paging transition is a **human config flip that leaves a `config.changed` fossil** — the runner never flips it automatically, no matter what the clock reads. Surface the readiness; leave the decision.
- This is also where the live-forward false-discovery signal starts to accumulate (the number the product idea in `docs/` is ultimately gated on) — another reason the burn-in is observed, not rushed.

---

## §9f — Between-tick state lives in the fossil record, never a cache (CONTRACT)

The statelessness rule (§9) is concrete: everything the runner carries across runs is **recovered from the durable record**, never held in a side cache that could drift from it. The carry-over state and its single source:

- **The prior MF-ticker snapshot** (launch diffing) → the last frozen `ingest/edgar/{date}/` `mf_tickers` blob.
- **A fund's prior holdings** (rebalance diff) → the last frozen `ingest/holdings/{series_id}/{date}/` file.
- **A fund's mandate prior** (mandate diff) → the last **frozen prospectus blob** (`ingest/prospectus/{series_id}/{accession}/`), never the registry `prospectus_accession` field (§9c).
- **A launch's awaiting-holdings / `sectors_unresolved` state** (deferred-pass scheduling, §9d) → the **fold over that launch's events** (the registry-materialized snapshots), the same single-source-of-truth as enumerating active leads. There is no separate "pending launches" table.

**Why a CONTRACT, not a convenience:** a side cache is a second source of truth that a partial or failed run can desync from the record — the exact hindsight hole the config-honesty and frozen-prior rules already close. Two cold runs over the same store produce identical output *because* the state is the store (the statelessness property, §9, property-tested).

---

## §9g — Run-log + exception granularity (a crashed run must be legible, not silent)

- **Run-log (every run).** One object under `runs/{date}_{run_id}.json`, indexed in the registry so the dashboard can render run history: config hash, wall-clock elapsed, which ingests/sensors ran vs were skipped, event counts by type, faults raised, and the state-change/push decision. It is **operational telemetry — not** an event on a lead (it never folds into lead state).
- **Exception granularity (CONTRACT — a local failure never silences the whole run).** A per-fund / per-sensor exception is a **soft fault**: emit a `fault` on `_system` (subsystem named), skip that unit, continue — one fund's 404 prospectus or one basket's degenerate matrix must not blind the others. Only a **store-integrity** failure (registry corruption, a divergent snapshot with no sink) is run-fatal — and even then the run **still attempts the push email** with the fault, because a fault email beats silence (§10 dead-man). The `.backup`-before-upload of the WAL SQLite (§7) guards the store from a mid-upload crash.

---

## §10 — Outputs: email (heartbeat + push)

- **Weekly heartbeat = the dead-man's switch.** Fires **every week regardless of activity**; the subject encodes state (e.g. counts, faults, shadow-clock status), so **silence beyond 7 days unambiguously means broken, never calm.** This is the single most important output property — a monitoring tool that goes quiet when it dies is worse than none.
- **State-change push:** same-day on any state change or `fault`.
- **What "state change" means, precisely (CONTRACT — the push is pinned to the fold, not to raw events).** A run pushes iff `fold.state_changed(prior_snapshot, new_fold)` returns a non-empty subset of **{status, shadow, verdict}** — the built fold helper is the single arbiter, so the push set cannot drift from the materialized state. `status` flips on `lead.spawned` / `xcorr.departure` / `xcorr.reverted` / a dispersion entry-exit; `shadow` flips **only** on the human de-shadow config flip (§9e); `verdict` flips on a `verdict` event. Everything else is deliberately **silent**: a weekly `xcorr.tick` / `dispersion.tick` (same lead, no status change), a silent corroboration (`rebalance` / `mandate.changed` / a `launch` accretion — surveyed by the human, never paged), and `resolution.resolved` / `resolution.failed` (queue mechanics) do **not** push. A `fault` always pushes. (This is the anti-slot-machine cadence made mechanical.)
- **Deterministic templating only (CONTRACT).** Email renders from folds by deterministic template — **no model-generated prose, ever.** Honest by construction.
- **Anti-engagement cadence (CONTRACT).** This is a tool built to make you trade *less*; its email must not become a slot machine. No "you might also like," no digest-for-its-own-sake, no manufactured urgency. It reports what changed and goes quiet.
- **Content:** new/activated leads; verdict-eligible candidates awaiting adjudication; faults; the manual-resolution queue; active-lead-ceiling tripwire status; shadow-clock status; and the dormant-pile coverage line (below). Weekly heartbeat carries the same, plus the "still alive" signal even when nothing changed.
- **The dormant-pile coverage report (new — the map of what the tool can't yet see).** A first-class heartbeat section: the standing count of the inert dispositions — `holdings_unavailable` / `sectors_unresolved` / `no_dominant_sector` / `dormant_no_match` — **ranked by where the tool is blindest** (the fund families with the most unresolved coverage). It is the coverage roadmap: it tells the human where to widen intake next, and it is the substrate the live false-discovery rate accrues against (the number the product idea is ultimately gated on). Read-only reference, the same class as the macro catalog — it never triggers a fetch, a tilt, or a threshold move; it reports blindness and goes quiet.

---

## §11 — Outputs: the read-only dashboard (Streamlit)

Renders the persisted store and event streams. **CONTRACT: no recompute on view, no autorefresh, no run-now** — the discipline variable is *computation cadence*, not display richness (the deliberate inversion of a live autorefreshing cockpit). Display richness is fine; a surface that only renders stored runs cannot reward compulsive checking.

- **Panels:** ranked active leads; per-lead event timeline (thaw-backward); the dispersion **shadow panel**; the **manual-resolution queue**; registry health; capture inventory (stub until M6); the unknown-type panel (exists from day one for v2 writers); the **fault log**; the **macro catalog** (`off-thesis-real` reference — read-only context, never a trade/tilt trigger, never a "regime forming" alert stream); the **launch panel**; and the **coverage / dormant-pile panel** (the §10 blindness map, ranked — the same read-only-reference class as the macro catalog).
- **Read-only means read-only (CONTRACT):** the dashboard reads snapshots the fold already wrote; it never triggers a computation or a fetch. The `forensics.py` query shapes port directly as views.

---

## Prerequisites (land before the runner leans on these paths) + the QA-review triage

The Claude Science QA review (`docs/prospector_full_review_claude_science.md`) reproduced-by-execution a set of findings on code the runner exercises. Disposition:

- **Landed with this spec (the two runner-blocking ones):**
  - **H1 — weight-units sanity.** `parse_spdr_holdings` now faults on an implausible weight-sum instead of silently ÷100-mis-scaling a fractions-format file — which would resolve *every* fund dormant under the absolute §4c gate (the one silent-failure class). The check moved from the test into the parser.
  - **S2 — snapshot sub-second collision.** `ts_compact` is now sub-second-lossless, so the reactive policy (§9 step 6) can snapshot a lead twice in one wall-clock second (a state change) without a `SnapshotDivergenceError` abort.
- **Named runner-path next slice (fix before the runner leans on the identity/HECO path):** **I1** — thread the *detected* series_id through `register_launch` rather than re-deriving by ticker (the current re-derive defeats the HECO reused-ticker guarantee the identity layer exists for); **B1** — series-scope the prospectus-exists confirm (a trust-wide accession masquerading as series-level weakens the same guard); **B2** — follow `filings.files[]` pagination so a long-lived registrant isn't wrongly queued; **H4** — register the plain `REAL ESTATE INVESTMENT TRUSTS` GICS alias (+ a fixture with an equity block; the plain header appears verbatim in the real IG-Credit blocks); and the `edgar.py` ambiguous-symbol → **fault** (mirror the SOI anchor discipline).
- **Cheap hardening (opportunistic, when touching the file):** H2 (`ext="xlsx"` label so the frozen archive isn't misnamed), S5 (`pd.isna` NaN-sector guard for a future NPORT-P parser), B3 (explicit backtest market-exclusion guard), H3 (holdings header prefix-match), the small smells (`cross_stream_lag` T1 `parse_ts` sort, `report.py` empty-`acute_crises`, `registry.py` SQL-name literal lookup).
- **Verify (10 min, corrupts the return base if true):** P1 — confirm the Stooq branch reads an *adjusted* close (Yahoo, the primary, already does); pull one known split. Low live risk today, but a hard prerequisite before Stooq is ever the live source.
- **Doc-hygiene (memory-prosthetic leaks):** DRIFT-1 (state doc §2.9 vs §5.2 contradict on built-vs-deferred — make §5 the single status source), DRIFT-2 (delete the closed aging-monitor to-do still open in the rev13 body; state the calm-regime margin as settled), the +593 recall-vs-live label, the two same-named SOI docs. *This spec applies the same rule to itself: one status source, and status prose is never copied forward as if it were history.*

---

## Build order within M5 (suggested)

1. **The runner skeleton** — entrypoint, the CONTRACT run-order, config-hash-before-sensors, run-log, fault-on-exception-still-emails. It invokes the *existing* pure-function sensors; tested offline with a **fixture clock**. This is the spine; get the order and the invariants right before wiring anything new.
2. **SOI-fetch wired to `EdgarClient`** (the `fetch_body` seam) with the two robustness items; tested offline against the frozen fixtures.
3. **Deferred-pass retry scheduling (§9d) + the mandate frozen-prior invariant (§9c) + the shadow clock (§9e).** The genuinely new runner logic — spec-cite each in the code.
4. **Email** (§10) — heartbeat/dead-man + state-change push, deterministic templating.
5. **The read-only dashboard** (§11).

Then M6 (capture + budget guard) plugs into the step-5 capture no-op; M7 (infra-as-code + deploy) wraps the whole runner.

---

## Testing / CONTRACT for M5

- **Offline, always.** The runner is tested with a **fixture clock** driving cadence; the network guard fails any test that opens a real socket; `EdgarClient` fetch is behind the `fetch_body` seam (tests pass a fixture thunk, the runner passes the real client). No test reaches the live internet.
- **Determinism.** Two cold runs over the same fixture store + clock produce identical events (the statelessness CONTRACT, property-tested).
- **Fossils.** Every state transition, every fault, every config change leaves an event. A run that changes state without a fossil is a bug.
- **No run-now surface** anywhere — asserted, not assumed.
- **The firewall** — no code path reads `portfolio.yaml` / the detector bucket, or places/sizes/recommends a trade. A test guards the wall.

---

## The genuinely subtle bits (comment the *why* in the code)

Most of the runner is mechanical orchestration of things that already work. Four places are where it can go quietly wrong, and each encodes a CONTRACT that isn't obvious from the mechanics — comment them:

1. **Config-hash before any sensor** (§9-run-order-1) — acting on an un-fossilized config change is a hindsight hole.
2. **Mandate prior from the frozen blob, not the registry** (§9c) — the intra-run accession-advance trap.
3. **Deferred passes are called with sectors, never assume them** (§9d) — wiring at resolution finds ∅ and silently never fires.
4. **The shadow clock surfaces readiness but never auto-promotes** (§9e) — auto-promotion would reintroduce trusting survivor-biased calibration.
