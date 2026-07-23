# Project Prospector — Architecture, Findings, and Current State (rev 9)

*Canonical state-of-the-project record — **rev 9, 2026-07-22** (rev 8 was 2026-07-16; rev 7, 2026-07-11).
Captures what Prospector is, what has been built, what the build has empirically found, the discipline that
governs it, and where it stands — with every claim in §5 sorted by **register** (built / queued / deferred-
named / aspirational-v2) so the record neither over- nor under-claims. **As of rev 9, v1 is build-complete and
cut/deployed as `v1.0.6`:** both structural spawners are live (xcorr paging, dispersion in shadow burn-in), the
§10 sender fires honest alarms, rebalance is runner-wired (the last M4 slice), and the **M7 autonomy core is
built** — a launchd-scheduled runner that fires `pros run && pros backup` on cadence and **arms the §8a
dead-man**. Rev 9 records the **post-#99 hardening arc** (no new milestone): the mandate diff earned its B1
SGML series-scoped confirmation + fund-block isolation, the `edgar.py` submissions helpers' six-instance
state-collapse family was closed, and §8a's operational-vs-review-advisory test was sharpened to
**broken-vs-incomplete** (spec rev 18) — the instrument got more defensively built, not larger. What finished is
the **instrument**; the measurement — the years-long prospective run that converts existence-proofs into a
*rate* — has not started: falsifiability is shown, a rate and profitability are not. Companion to the
founding document, the decisions review, and the v1 build spec (**rev 18** — this arc's CONTRACT deltas now
folded; the canonical build instructions, of which this doc is the orientation/status/roadmap synthesis).
Supersedes rev 8.*

**What changed since rev 8 (for the returning reader).** rev 8 recorded v1 reaching build-complete — the
runner able to run itself. **rev 9 records the post-#99 hardening arc and the `v1.0.6` cut/deploy** — no new
milestone; the instrument made more defensively built where a cold real-data QA read found it thin. Since rev 8,
four things:

1. **The mandate diff earned its B1 series-scoped confirmation + fund-block isolation.** A multi-fund prospectus
   carries one strategy section per fund, and the submissions doc has no series dimension — so the diff could
   mis-attribute the first fund's strategy to every series sharing the filing. The fix verifies coverage live
   via the SGML `<SERIES-AND-CLASSES-CONTRACTS-DATA>` header (`parse_series_classes`) and isolates the target
   fund's block by its SGML series-name before diffing, so each series now diffs ITS OWN section
   (`2026-07-21-mandate-series-scoped-confirmation-*` + `-fund-block-isolation.md`; closes
   `MANDATE-MULTIFUND-SECTION`); the J.P. Morgan Q&A question-form heading joined the recognised set. So
   **combined-prospectus multi-fund extraction — the one mandate item §2.9/§5.2 carried deferred — is now
   built** (this closes DRIFT-1).
2. **The `edgar.py` state-collapse family was enumerated and closed — six instances.** The submissions/manifest
   helpers each returned ONE sentinel, so distinct, differently-actionable failure states fused into it. All six
   are now split: N8's three-way, F1 shape-drift-vs-absence, F5 prior-coverage asymmetry, the pagination
   third-state (`SubmissionsIncompleteError` → review-advisory), and two BK-MSG-01 mislabels (SOI manifest drift
   → `SOI_ERROR`, `confirm_prospectus` drift → `submissions_shape`). Recorded as a signature in
   `docs/bugs/README.md` §1, with the enumeration's bounds stated (the columnar-JSON family, not the
   filing-bytes parsers).
3. **§8a's alarm test was sharpened to broken-vs-incomplete (spec rev 18).** *Operational* = a contract the
   system depends on was violated (it cannot do its job → pages); *review-advisory* = it did its job and the
   result needs a human's judgment (surfaced-not-paged). The rev-16 "right to expect success" framing became the
   fetch-outcome corollary — a fetch that *succeeds* but returns incomplete coverage (submissions pagination) is
   review-advisory. Three design rulings in four days re-derived the test; the spec now binds the general form.
4. **`v1.0.6` was cut and deployed to prod**, and two test-integrity items closed (the mandate review-advisory
   category tautology, driven now through the production reporter; and the owed `deploy.sh` lock-contention
   regression guard). The build spec folded to **rev 18**.

The shift to hold onto is unchanged from rev 8: **build-complete is a finish line *and* a starting line.** This
arc hardened the instrument; the false-discovery rate is still unmeasured, dispersion's burn-in barely started,
the edge question open — none resolve by building. Part V reads accordingly: *the instrument is done; the
measurement hasn't started.*

---

# Parts I–IV — carried forward from rev 5/6, unchanged

*Parts I (The Idea, §1.1–1.9), II (Architecture & Implementation, §2.1–2.8), III (Findings), and IV (The
Operating Discipline, §4.1–4.7) are unchanged — the premise, the consensus trap, novelty-not-quality, the
ETF-as-thesis instrument, the three streams, the wall/scarce-oracle, the firewall, the fossil record, the M3
findings, and the seven operating disciplines are all stable. Carry them forward verbatim from rev 5/6.*

**§2.9 "What is deferred," updated for rev 8, amended rev 9 (rebalance, the M7 core, M6 capture, and now combined-prospectus multi-fund extraction have closed):**

> ## 2.9 What is deferred
> - **M7-hardening remainder.** The M7 autonomy core (launchd scheduling, the single-writer lock, the
>   fail-loud HDD backup) is **built** — the runner leaves manual `pros run`, and the §8a **dead-man arms** on
>   activation; the hardening tail stays deferred: the SOI-corroboration cadence gate, the read-only-media
>   WAL-checkpoint-out, and **offsite S3** (the live durability story is now local-disk + HDD; §7's S3-first
>   framing is the dormant target).
> - **Milestone 3b** (dispersion PIT calibration + NPORT-P parser) — data-gated; live burn-in substitutes;
>   not a v1 blocker.
> - **Named coverage/observability gaps (non-blocking, surfaced-not-lost):** broader holdings-intake coverage;
>   foreign constituent symbol resolution (§9e Option 3 — **kept deferred by spec §4b**);
>   **`coverage_actual` surfacing** (computed in the runner/ingest; **not yet shown** in the dashboard or
>   email); **fault-log bounding** (the `fault_log` read is unbounded — reads every fault event then caps
>   display — a perf/scale concern that grows with the record, distinct from any display window; trigger is
>   volume); **live-lead advisories on the lead's own timeline** (today all advisories hit `_system`
>   undifferentiated; the paging call already distinguishes live-lead, but prominent per-lead surfacing is a
>   later refinement).
> - *(Closed rev 9 — **combined-prospectus multi-fund extraction is now built**: the mandate diff isolates the
>   target fund's block by its SGML series-name, so each series diffs its own strategy section rather than the
>   first fund's — `2026-07-21-mandate-fund-block-isolation.md`. Was carried here as deferred through rev 8.)

---

# Part V — Current State & Roadmap

## 5.1 Where the 17-year arc stands

v1 is **build-complete.** Milestones 1–6, the SOI resolver, and the M7 autonomy core are built; both
structural spawners are live; the runner can now run *itself*. Where it stands:

- **Two live spawners, both producing real data.** Excess-correlation (§4a) pages and counts toward the
  ceiling (xcorr leads on the SPDR grid, XLV-centered). Dispersion (§4b/§9e) runs live in shadow — real basket
  fractures recorded, in the 90-day burn-in.
- **The instrument is complete and self-running.** The §10 sender fires honest alarms — a persistent fault
  pages once (`(ticker, status)` key), the low-value advisory wave is counted-and-surfaced-not-paged
  (`faults=9, pushed=False`); rebalance is the last M4 sensor wired in; and the **M7 core** — launchd
  scheduling, the single-writer `run.lock`, the fail-loud HDD backup — fires `pros run && pros backup` on
  cadence with no human at the keyboard, **arming the §8a dead-man**. One on-Mini activation flips it from
  built to running.
- **The existence proofs still stand — still existence proofs.** Recall (+593), the twice-confirmed β-strip,
  the box-B falsifier, dispersion's real XLI firing. Converting these from existence-proofs into *rates* is
  the prospective, on-cadence work — and it **has not started.** The monitor can now reach the operator and
  run unattended, but the false-discovery rate is unmeasured, dispersion firing is n=1, and the burn-in is
  barely begun.
- **The recurring failure mode is named and mechanized.** Code that reads right, passes its tests, and breaks
  on the real substrate surfaced twice more on the alarm layer this arc (the volatile-message suppression and
  the split-write-path taxonomy — the project's third-and-fourth-time failure mode). The cold real-data QA
  read that caught both is now a **standing mechanism** — the four-seat model, `METHOD.md` — not a habit.

## 5.2 Status by register — the single source of truth for what's built

*(Register transitions since rev 7 are traced in the fold PR — each move names its record, each non-move is verified still-true, and the ASPIRATIONAL wall is checked for drift.)*

**BUILT (721 tests, all offline):**
- *Foundation + M4 + SOI + M5 runner + §9e + §8b + §10* — carried from rev 7, unchanged: the fossil record,
  identity layer, excess-correlation + frozen stress gate, backtest + full M3 gate, the M4 sensors + SOI
  resolver, the §9 runner (SOI-fetch, §9d retry, §9c mandate invariant, Tiingo prices, xcorr live), §9e
  (dispersion live in shadow + the constituent-price vertical + CUSIP-key/exclusion/honest-coverage), §8b
  (board-snapshot export + launch-panel legibility), and §10 (the sender + the volatile-message suppression
  fix + the fault-taxonomy/advisory-posture §8a CONTRACT).
- ***NEW — rebalance runner-wiring (QUEUED→BUILT).*** The last M4 sensor into the runner — a silent accretion
  sensor (no Schmitt, no lead of its own), forward-hash routed, active leads read from the
  registry-materialized fold. (`2026-07-12-rebalance-runner-wiring.md`.)
- ***NEW — the M7 autonomy core (DEFERRED→BUILT).*** launchd-scheduled `pros run && pros backup` on cadence,
  which **arms the §8a dead-man** and adds an OK/DEGRADED heartbeat line (`m7-autonomy-core`); the
  single-writer `run.lock` (`fcntl.flock`, runner + `deploy.sh` — `single-writer-lock-and-deploy-coordination`);
  store-durability backup (local-HDD mirror, fail-loud, health on the one fault→heartbeat channel —
  `store-durability-backup` + `backup-health-one-fault-channel`). Built; **awaits a one-time on-Mini
  activation** (below).
- ***NEW — M6 discourse capture (DEFERRED→BUILT).*** `ingest/capture.py` (`4739b52`, "the last v1 build
  slice"), the runner's phase 5 — K deterministic-templated queries → Anthropic `web_search` (forces our
  verbatim query; the model's prose is never persisted — the wall) → our httpx fetch of the top-M URLs →
  frozen under `captures/{lead}/{ts}/` (the one un-backfillable tree); a hard weekly/monthly budget cap
  pauses + faults on breach. **Ships disabled — same register as M7:** the owner arms it by setting
  `capture.monthly_budget_usd` + `ANTHROPIC_API_KEY`, behind the one-time **CAP-DRIFT armed byte-compare**
  (`query-drift-byte-exact`) that runs before capture is armed. Write-only — nothing in v1 reads a capture.
  (Anthropic `web_search` + $10/mo budget ratified per the M6 build note.)
- ***NEW — the post-#99 hardening arc (`v1.0.6`).*** No new milestone; the instrument made more defensively
  built where a cold real-data QA read found it thin. The mandate diff's **B1 SGML series-scoped confirmation +
  fund-block isolation** (a multi-fund prospectus now diffs each series' OWN strategy section, isolated by its
  SGML series-name — `2026-07-21-mandate-series-scoped-confirmation-*` + `-fund-block-isolation.md`; closes
  `MANDATE-MULTIFUND-SECTION`, and with it the last deferred mandate item); the **`edgar.py` submissions
  state-collapse family closed** — six instances split so distinct, differently-actionable failure states no
  longer fuse into one sentinel (N8, F1 shape-drift, F5 prior-coverage, the pagination third-state, and two
  BK-MSG-01 mislabels; signature recorded in `docs/bugs/README.md` §1); and **§8a sharpened to
  broken-vs-incomplete** (spec **rev 18** — *operational* = a violated contract that pages, *review-advisory* =
  the system did its job and a human decides; the pagination third-state is the worked example). Cut and
  **deployed to prod as `v1.0.6`.**

**QUEUED (named, next):**
- **The on-Mini activation** — *not a build, a deploy action:* install the launchd job, bless the backup
  drives, run the first scheduled tick. Flips v1 from build-complete to *running*. (`ops/README.md`.)

**DEFERRED (named, with reason):**
- **M7-hardening remainder** — the SOI cadence gate, the WAL-checkpoint-out, offsite S3 (live durability is
  local-disk + HDD; S3 dormant).
- **Milestone 3b** (dispersion PIT calibration + NPORT-P parser) — data-gated; live burn-in substitutes.
- **The coverage/observability gaps** (per §2.9): broader holdings coverage; foreign symbol resolution
  (Option 3, kept deferred by spec §4b); `coverage_actual` surfacing (computed, not shown); **fault-log
  bounding** (unbounded read, grows with the record); live-lead advisories on the lead's timeline.
  *(Combined-prospectus multi-fund extraction moved BUILT this rev — see the post-#99 hardening bullet above.)*

**ASPIRATIONAL (v2, walled off — captured, not queued):**
- The **proto-cluster / pseudo-ETF** layer and Prospector-as-product (§1.9) — its substrate accrues via the
  generous dispersion payload (confirmed accruing in the live XLI/XLP firings), so **nothing to build, keep
  capturing.** It stays walled off — a re-synthesis is exactly when an item like this drifts into a plan, and
  it must not.
- The **discourse-interpretation** program (v2) — the *interpretation* only; the capture that feeds it is
  built and ships-disabled (BUILT, above). v1 banks the substrate; v2 reads it.

**The load-bearing honesty line:** everything under BUILT is *built and running*, not *validated*. **The
instrument is done; the measurement hasn't started.** v1 is a complete, self-running monitor — but dispersion
firing is n=1, the false-discovery rate is unmeasured, the burn-in is barely begun, and the dead-man's
guarantee arms only on activation. Build-complete is **not** proven: falsifiability is shown, a rate is not,
profitability is not.

## 5.3 Next steps — prioritized marching orders

v1 is build-complete, so what remains is **not builds** — it is activation, then years of running:

1. **The on-Mini activation.** Install the launchd job, bless the backup drives, run the first scheduled tick —
   arms the §8a dead-man and starts the cadence (`ops/README.md`). The one action between build-complete and
   *running*.
2. **The long prospective run.** Once running, v1's remaining work is running it on cadence **for years** until
   the false-discovery rate is a measured number — the multi-year, event-gated accumulation that is the only
   thing that answers whether the edge is real. **This is v1's actual finish line, measured in years, not
   slices.**
3. **Dispersion's 90-day burn-in completes**, then a *human* promotes it to paging (a `config.changed` flip) —
   calendar-bound.

Beyond v1: the **discourse interpretation** (v2 — the capture that feeds it is built and ships-disabled, §5.2 BUILT) and the named coverage gaps as they bite. None of these gate v1's
*meaning* — only the run does.

**The shift to internalize:** the whole arc to here built the instrument. That is done. Everything that answers
the real question — does a structure-first signal have an edge — lives in the run, which has not started.
Build-complete is the starting line, not the finish. This doc (rev 9) records the build-complete-and-deployed
(`v1.0.6`) state; spec rev 18 carries the CONTRACT deltas.

---

*Closing note (carried, lightly updated). The distinguishing property of this project is that it is
engineered, in writing, before building, to be able to **lose** — falsifiable at every layer, an immutable
record that grades its own calls, metrics that refuse to flatter themselves. This arc, the place it could
have lost was the alarm layer itself — twice — and the cold real-data QA read caught both before a real alert
could go missing or a false one could train the operator to ignore it. The tool notices; the human decides;
the core absorbs; the record remembers. That division is the whole design — and with v1 build-complete, it now
runs on its own clock, the record waiting on the years of evidence that will say whether the leads were ever
real.*
