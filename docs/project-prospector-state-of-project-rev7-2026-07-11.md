# Project Prospector — Architecture, Findings, and Current State (rev 7)

*Canonical state-of-the-project record — **rev 7, 2026-07-11** (rev 6 was 2026-07-10; rev 5, 2026-07-08).
Captures what Prospector is, what has been built, what the build has empirically found, the discipline that
governs it, and where it stands — with every claim in §5 sorted by **register** (built / queued / deferred-
named / aspirational-v2) so the record neither over- nor under-claims. **As of rev 7 the §10 email sender is
live and firing honest heartbeats:** both structural spawners are live (xcorr paging, dispersion in shadow
burn-in), and the sender — the last unbuilt piece of the M5 outputs — went from `NullNotifier` to a working
alarm that is now correct **from both directions**: it no longer cries wolf on a persistent fault (the
volatile-message suppression fix) and it no longer buzzes on low-value advisories while still surfacing them
(the §8a advisory-posture CONTRACT). Both fixes were caught by cold real-data QA on the alarm layer itself
and verified on real runs. **~554 tests green.** Companion to the founding document, the decisions review,
and the v1 build spec (**rev 14**, pending a **rev 15** fold of this arc's CONTRACT deltas — the canonical
build instructions; this doc is the orientation/status/roadmap synthesis over it). Supersedes rev 6 (§9e +
§8b) and rev 5.*

**What changed since rev 6 (for the returning reader).** The **§10 email sender landed, and with it the
system became an actual always-on monitor** — the record now reaches the operator's pocket, not just the
store. Three things, all on the alarm layer, all confirmed on real data:

1. **The sender is built and firing** (`runner/notify.py::SmtpNotifier`, `runner/email_render.py`). Weekly
   heartbeat/dead-man + immediate state-change and fault pushes, deterministic-templated from the folds (no
   generated prose). **Transport is SMTP** (Google Workspace app-password; the password is env-only from the
   git-ignored `.env` as `PROSPECTOR_SMTP_PASSWORD`, handled exactly like the Tiingo token — never config,
   never committed, and `pros run` fails fast if the host is configured but the password is unset). **The
   dead-man ("silence past 7 days = broken") does not truly ARM until M7 schedules the runner** — a heartbeat
   that only fires on a manual `pros run` (or `pros run --heartbeat`) proves the send path, not the guarantee.
   Built now, arms at M7. Also closes the paid-Tiingo-sub lapse-risk dead-man once scheduled.
2. **The nuisance-alarm suppression was defeated on the live path — found and fixed.** `_compute_push` keyed
   suppression on the message-exact `_fault_signature`, but the live `ingest.prices` fault message embeds the
   Tiingo fetch URL, whose `startDate`/`endDate` move every tick — so a *persistent* lapsed-sub 403 (the exact
   failure §10 exists to close) rendered a different message daily → paged every day (the GPWS "cried wolf"
   mode, silently reopened). **Fix (design-thread Option 1):** `_emit_fault` gains a stable `key=`;
   `_fault_signature` keys on `(subsystem, key or message)` — the message keeps the full URL for forensics,
   only the suppression key is stabilized; the two URL-bearing sites (sector-panel + dispersion constituent
   pull) pass `key=(ticker, status)`. A persistent fault now pages once, then rides the heartbeat. Both
   dimensions of the key are pinned by test (status *and* ticker), and a one-line convention at `_emit_fault`
   tells future volatile-message sites to pass a key. The flapping-fault case (E2) is deferred, `xfail(strict)`.
3. **The fault taxonomy / advisory-posture — a §8a CONTRACT.** The mandate/SOI "extraction-unreliable →
   manual review" faults were written straight to the store, bypassing the runner's per-tick list — so the
   heartbeat read "0 faults" while nine sat in the review section, *and* they never reached the push decision
   at all (a whole class of faults silently escaping the alarm path). **Ruling + fix (the shadow-push shape,
   one layer down):** one fault accumulator, each fault tagged `category` (`operational` | `review-advisory`)
   + `on_live_lead`; `_compute_push` pages the page-worthy subset — **operational faults, plus advisories on a
   fund touching a live lead** (the risk-owner's call). Everything else advisory is **counted and surfaced but
   does not page**. Display splits distinctly: `N fault(s) · M for review this run`, a Faults section separate
   from Manual-review advisories. Confirmed live: `faults=9, pushed=False` on the iShares combined-prospectus
   launch wave — surfaced, not paged. **The §8a advisory-posture is now a recorded CONTRACT** (see the §10
   decision doc; folds into spec rev 15).

Part V is fully refreshed to this state; §5.3 now begins at **rebalance-wiring** (the last M4-into-runner
slice, unblocked by §9e's holdings vertical).

---

# Parts I–IV — carried forward from rev 5/6, unchanged

*Parts I (The Idea, §1.1–1.9), II (Architecture & Implementation, §2.1–2.8), III (Findings), and IV (The
Operating Discipline, §4.1–4.7) are unchanged — the premise, the consensus trap, novelty-not-quality, the
ETF-as-thesis instrument, the three streams, the wall/scarce-oracle, the firewall, the fossil record, the M3
findings, and the seven operating disciplines are all stable. Carry them forward verbatim from rev 5/6.*

**§2.9 "What is deferred," updated for rev 7:**

> ## 2.9 What is deferred
> - **Rebalance runner-wiring (`_run_rebalance`) — the imminent next slice.** The holdings-diff accretion
>   sensor is built; its runner wiring was gated on the holdings/constituent vertical, which §9e built (the
>   runner freezes each basket's holdings every tick), so it is **unblocked** — the last M4-into-runner piece,
>   at a clean seam. *(xcorr, dispersion, launch-corroboration, mandate, and SOI are all built and
>   runner-wired; §10 the sender is now built too.)*
> - **Milestone 6 → 7:** **M6** (discourse capture + budget guard); then **M7** (infra-as-code + **scheduled**
>   deploy — where the runner leaves manual `pros run`, and the §10 **dead-man arms**). M7 also owns the SOI
>   cadence gate and the WAL-checkpoint-out. **After M7, v1 is build-complete.**
> - **Milestone 3b** (dispersion PIT calibration + NPORT-P parser) — data-gated; live burn-in substitutes;
>   not a v1 blocker.
> - **Named coverage/observability gaps (non-blocking, surfaced-not-lost):** broader holdings-intake coverage;
>   foreign constituent symbol resolution (§9e Option 3); `coverage_actual` surfacing; **fault-log bounding**
>   (the `fault_log` read is unbounded — reads every fault event then caps display — a perf/scale concern that
>   grows with the record, distinct from any display window; trigger is volume); **live-lead advisories on the
>   lead's own timeline** (today all advisories hit `_system` undifferentiated; the paging call already
>   distinguishes live-lead, but prominent per-lead surfacing is a later refinement); **combined-prospectus
>   multi-fund extraction** (the mandate extractor is single-fund-tuned; a combined iShares/Vanguard prospectus
>   faults to manual review — raw HTML is frozen and extraction is on-read, so nothing is lost and a better
>   extractor re-parses later; the fault is honest, not a break).

---

# Part V — Current State & Roadmap

## 5.1 Where the 17-year arc stands

Milestones 1–4 + the SOI resolver + the M5 runner are complete, both structural spawners are live and firing,
and — new since rev 6 — **the output layer reaches the operator.** Where it stands:

- **Two live spawners, both producing real data.** Excess-correlation (§4a) pages and counts toward the
  ceiling (six active leads, XLV-centered). Dispersion (§4b/§9e) runs live in shadow — two baskets fractured
  (XLI at z≈4.0, XLP fading toward the z_out reversion line), both in 0/90 burn-in.
- **The §10 sender is live and *honest*.** It fires the weekly heartbeat and would push on state change or
  operational fault; and the two alarm-layer bugs are closed, confirmed on real runs — a persistent fault
  pages once (`(ticker, status)` key), and the low-value advisory wave is counted-and-surfaced-not-paged
  (`faults=9, pushed=False`). The dead-man's one-line summary is now both **complete** (it can't read calm
  when a queue exists) and **un-flat** (it keeps "something broke" distinct from "the sensor correctly
  punted"). This was the exact standard the two bugs violated from opposite sides; both are closed by the
  same principle — *the summary must match what fired.*
- **The recurring pattern surfaced twice more, both on the alarm layer.** Code that reads right, passes its
  tests, and breaks on the real substrate — the volatile-message suppression and the split-write-path
  taxonomy — now the project's **named, third-and-fourth-time failure mode**, and the strongest case for
  keeping the cold real-data QA read on every slice. (Memory saved to that effect.)
- **The M3 + §9e existence proofs still stand, still existence proofs.** Recall (+593), the twice-confirmed
  β-strip, the box-B falsifier, dispersion's real XLI firing. Converting these from existence proofs into
  *rates* remains the prospective, on-cadence work — now with the monitor able to actually reach the
  operator, but the false-discovery-rate question unanswered and the burn-in barely started.

## 5.2 Status by register — the single source of truth for what's built

**BUILT (~554 tests, all offline):**
- *Foundation + M4 + SOI + M5 runner + §9e + §8b* — as of rev 6, unchanged: the fossil record, identity
  layer, excess-correlation + frozen stress gate, backtest + full M3 gate, the M4 sensors + SOI resolver, the
  §9 runner (SOI-fetch, §9d retry, §9c mandate invariant, Tiingo prices, xcorr live), **§9e** (dispersion
  wired live in shadow + the constituent-price vertical + the CUSIP-key/exclusion/honest-coverage symbol
  resolution, the ENR foreign-collision fix), and **§8b** (the pure-read markdown board-snapshot export + the
  launch-panel legibility fixes).
- ***NEW — §10: the email sender (M5 outputs complete).*** `SmtpNotifier` + `email_render` — weekly
  heartbeat/dead-man + state-change/fault push, deterministic-templated from folds; SMTP transport, secret
  env-only, fail-fast when configured-but-unset. **Live and firing.** (Dead-man arms at M7.)
- ***NEW — §10 volatile-message suppression fix.*** Stable `(subsystem, key or message)` signature; the two
  URL-bearing price sites key on `(ticker, status)`; a persistent fault pages once then rides the heartbeat.
  Both key dimensions pinned by test; the emit-site `key=` convention documented. E2 (flapping) deferred
  (`xfail(strict)`).
- ***NEW — §10 fault taxonomy / advisory-posture (§8a CONTRACT).*** One fault accumulator, `category` +
  `on_live_lead` tags, `_compute_push` pages operational + live-lead-advisory only; distinct
  `N faults · M for review` display; the split write-path closed. Confirmed live (`faults=9, pushed=False`).

**QUEUED (named, next):**
- **Rebalance runner-wiring (`_run_rebalance`).** The last M4 sensor into the runner — sensor built, unblocked
  by §9e's holdings vertical. Small, clean seam.

**DEFERRED (named, with reason):**
- **M6** (discourse capture + budget guard) → **M7** (infra-as-code + **scheduled** deploy; where the §10
  dead-man arms; + the SOI cadence gate and WAL-checkpoint-out). After M7, v1 is build-complete.
- **Milestone 3b** (dispersion PIT calibration + NPORT-P parser) — data-gated; live burn-in substitutes.
- **The coverage/observability gaps** (per §2.9): broader holdings coverage; foreign symbol resolution;
  `coverage_actual` surfacing; **fault-log bounding** (unbounded read, grows with the record); live-lead
  advisories on the lead's timeline; **combined-prospectus multi-fund extraction** (honest fault, raw banked,
  re-parseable on-read).

**ASPIRATIONAL (v2, walled off — captured, not queued):**
- The **proto-cluster / pseudo-ETF** layer and Prospector-as-product (§1.9) — its substrate accrues via the
  generous dispersion payload (confirmed accruing in the live XLI/XLP firings), so nothing to build, keep
  capturing.
- The **discourse-interpretation** program (v2).

**The load-bearing honesty line:** everything under BUILT is *built and running*, not *validated*. The system
is now a monitor that reaches the operator — but dispersion firing is n=1, the false-discovery rate is
unmeasured, and the dead-man's guarantee arms only at M7. "Live and honest" is not "proven."

## 5.3 Next steps — prioritized marching orders

Both spawners are live, the constituent vertical is built and gate-verified, the review surface delivers to
the pocket, and the alarm is honest from both directions. What remains for v1 is short:

1. **Rebalance runner-wiring.** The last M4 slice into the runner, unblocked by §9e — small, at a clean seam.
2. **M6** (discourse capture + budget guard) — raw, frozen, uninterpreted capture at structural hits, hard
   budget caps, fault-on-breach.
3. **M7** (infra-as-code + **scheduled** deploy) — the runner leaves manual `pros run`, the §10 dead-man
   arms, the deferred M7 items land. **After M7, v1 is build-complete.**

**Two things that gate v1's meaning, not builds:**
- **Dispersion's 90-day burn-in completes**, then a *human* promotes it to paging (a `config.changed` flip) —
  calendar-bound.
- **The long prospective run.** After M7, v1's remaining work is running it on cadence for years until the
  false-discovery rate is a measured number — the multi-year, event-gated accumulation that is the only thing
  that answers whether the edge is real. That is v1's actual finish line, measured in years, not slices.

**Immediate action:** land the §10 PR (#28 — the sender + suppression fix + taxonomy fix, verified), then
rebalance-wiring. This doc (rev 7) records the §10-complete state; the spec rev 15 folds the CONTRACT deltas.

---

*Closing note (carried, lightly updated). The distinguishing property of this project is that it is
engineered, in writing, before building, to be able to **lose** — falsifiable at every layer, an immutable
record that grades its own calls, metrics that refuse to flatter themselves. This arc, the place it could
have lost was the alarm layer itself — twice — and the cold real-data QA read caught both before a real alert
could go missing or a false one could train the operator to ignore it. The tool notices; the human decides;
the core absorbs; the record remembers. That division is the whole design.*
