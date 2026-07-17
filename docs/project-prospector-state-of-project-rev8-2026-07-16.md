# Project Prospector — Architecture, Findings, and Current State (rev 8)

*Canonical state-of-the-project record — **rev 8, 2026-07-16** (rev 7 was 2026-07-11; rev 6, 2026-07-10).
Captures what Prospector is, what has been built, what the build has empirically found, the discipline that
governs it, and where it stands — with every claim in §5 sorted by **register** (built / queued / deferred-
named / aspirational-v2) so the record neither over- nor under-claims. **As of rev 8, v1 is build-complete:**
both structural spawners are live (xcorr paging, dispersion in shadow burn-in), the §10 sender fires honest
alarms, rebalance is runner-wired (the last M4 slice), and the **M7 autonomy core is built** — a
launchd-scheduled runner that fires `pros run && pros backup` on cadence and **arms the §8a dead-man** —
awaiting only a one-time on-Mini activation. What finished is the **instrument**; the measurement — the
years-long prospective run that converts existence-proofs into a *rate* — has not started: falsifiability is
shown, a rate and profitability are not. Companion to the
founding document, the decisions review, and the v1 build spec (**rev 15** — this arc's CONTRACT deltas now
folded; the canonical build instructions, of which this doc is the orientation/status/roadmap synthesis).
Supersedes rev 7 (§10) and rev 6.*

**What changed since rev 7 (for the returning reader).** rev 7 recorded the §10 sender landing — the system
becoming an always-on monitor. **rev 8 records v1 reaching build-complete, and the shift in what "done" means.**
Since rev 7, four things:

1. **The M7 autonomy core is built — the runner leaves manual `pros run`.** A launchd-scheduled runner fires
   `pros run && pros backup` on cadence (`2026-07-12-m7-autonomy-core.md`), which **arms the §8a dead-man**
   ("silence past 7 days = broken" becomes a real guarantee, not a manual-run artifact) and adds an
   OK/DEGRADED health line to the heartbeat. It awaits a one-time on-Mini activation (`ops/README.md`); after
   that, v1 runs itself. This is the piece rev 7's "built now, arms at M7" dead-man was waiting on.
2. **The durability + concurrency floor landed.** A **single-writer `run.lock`** (`fcntl.flock`, acquired by
   the runner and `deploy.sh` — `2026-07-14-single-writer-lock-and-deploy-coordination.md`) converts the prose
   single-writer assumption to a mechanism; **store-durability backup** (`pros backup` / `pros store
   verify-restore`, a local-HDD mirror of the fossil store, fail-loud — `2026-07-12-store-durability-backup.md`)
   with backup health surfacing on the one fault→heartbeat channel (`2026-07-14-backup-health-one-fault-channel.md`).
3. **Rebalance is runner-wired — the last M4 sensor into the runner** (`2026-07-12-rebalance-runner-wiring.md`),
   a silent accretion sensor that accretes facts onto live leads and never spawns.
4. **The build spec folded to rev 15.** The CONTRACT deltas of this whole arc — the page-worthy alarm posture,
   dispersion's constituent vertical, the effective-merged config hash, the byte-exact *ordered* query-drift
   gate, the board export, the M7-built status, and the lock's not-built items named in the §0 OUT — are now
   in the canonical build spec (rev 15), whose clause-trace drift audit caught a latent §4b/§8a contradiction
   the code had already outgrown (D2).

The shift to hold onto: **build-complete is a finish line *and* a starting line.** What finished is the
instrument. The false-discovery rate is unmeasured, dispersion's burn-in is barely started, and the edge
question is open — none of those resolve by building. Part V reads accordingly: *the instrument is done; the
measurement hasn't started.*

---

# Parts I–IV — carried forward from rev 5/6, unchanged

*Parts I (The Idea, §1.1–1.9), II (Architecture & Implementation, §2.1–2.8), III (Findings), and IV (The
Operating Discipline, §4.1–4.7) are unchanged — the premise, the consensus trap, novelty-not-quality, the
ETF-as-thesis instrument, the three streams, the wall/scarce-oracle, the firewall, the fossil record, the M3
findings, and the seven operating disciplines are all stable. Carry them forward verbatim from rev 5/6.*

**§2.9 "What is deferred," updated for rev 8 (walked item-by-item; rebalance, the M7 core, and M6 capture have closed):**

> ## 2.9 What is deferred
> - **M7-hardening remainder.** The M7 autonomy core (launchd scheduling, the single-writer lock, the
>   fail-loud HDD backup) is **built** — the runner leaves manual `pros run`, and the §8a **dead-man arms** on
>   activation; the hardening tail stays deferred: the SOI-corroboration cadence gate, the read-only-media
>   WAL-checkpoint-out, and **offsite S3** (the live durability story is now local-disk + HDD; §7's S3-first
>   framing is the dormant target).
> - **Milestone 3b** (dispersion PIT calibration + NPORT-P parser) — data-gated; live burn-in substitutes;
>   not a v1 blocker.
> - **Named coverage/observability gaps (non-blocking, surfaced-not-lost):** broader holdings-intake coverage;
>   foreign constituent symbol resolution (§9e Option 3 — **kept deferred by spec rev 15 §4b**);
>   **`coverage_actual` surfacing** (computed in the runner/ingest; **not yet shown** in the dashboard or
>   email); **fault-log bounding** (the `fault_log` read is unbounded — reads every fault event then caps
>   display — a perf/scale concern that grows with the record, distinct from any display window; trigger is
>   volume); **live-lead advisories on the lead's own timeline** (today all advisories hit `_system`
>   undifferentiated; the paging call already distinguishes live-lead, but prominent per-lead surfacing is a
>   later refinement); **combined-prospectus multi-fund extraction** (the mandate extractor is
>   single-fund-tuned; a combined iShares/Vanguard prospectus faults to manual review — raw HTML is frozen and
>   extraction is on-read, so nothing is lost and a better extractor re-parses later; the fault is honest, not
>   a break).

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

**BUILT (634 tests, all offline):**
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

**QUEUED (named, next):**
- **The on-Mini activation** — *not a build, a deploy action:* install the launchd job, bless the backup
  drives, run the first scheduled tick. Flips v1 from build-complete to *running*. (`ops/README.md`.)

**DEFERRED (named, with reason):**
- **M7-hardening remainder** — the SOI cadence gate, the WAL-checkpoint-out, offsite S3 (live durability is
  local-disk + HDD; S3 dormant).
- **Milestone 3b** (dispersion PIT calibration + NPORT-P parser) — data-gated; live burn-in substitutes.
- **The coverage/observability gaps** (per §2.9): broader holdings coverage; foreign symbol resolution
  (Option 3, kept deferred by rev 15 §4b); `coverage_actual` surfacing (computed, not shown); **fault-log
  bounding** (unbounded read, grows with the record); live-lead advisories on the lead's timeline;
  **combined-prospectus multi-fund extraction** (honest fault, raw banked, re-parseable on-read).

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
Build-complete is the starting line, not the finish. This doc (rev 8) records the build-complete state; spec
rev 15 carries the CONTRACT deltas.

---

*Closing note (carried, lightly updated). The distinguishing property of this project is that it is
engineered, in writing, before building, to be able to **lose** — falsifiable at every layer, an immutable
record that grades its own calls, metrics that refuse to flatter themselves. This arc, the place it could
have lost was the alarm layer itself — twice — and the cold real-data QA read caught both before a real alert
could go missing or a false one could train the operator to ignore it. The tool notices; the human decides;
the core absorbs; the record remembers. That division is the whole design — and with v1 build-complete, it now
runs on its own clock, the record waiting on the years of evidence that will say whether the leads were ever
real.*
