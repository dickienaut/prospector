# Project Prospector — Architecture, Findings, and Current State (rev 6)

*Canonical state-of-the-project record — **rev 6, 2026-07-10** (rev 5 was 2026-07-08). Captures what
Prospector is, what has been built, what the build has empirically found, the discipline that governs it, and
where it stands — with every claim in §5 sorted by **register** (built / queued / deferred-named /
aspirational-v2) so the record neither over- nor under-claims. **As of rev 6 the second spawner is live and
has fired:** §9e wired **dispersion into the runner in shadow**, its constituent-price vertical is built, and
a real `pros run` produced dispersion's first un-planted live firing — **XLI split, z≈4.0→4.15, in shadow,
90-day burn-in running**. The going-live surprise this arc was a genuine one, caught by primary-source
contact: the constituent price pull was ticker-anchored, and a real SSGA file's foreign local ticker (`ENR` =
Siemens Energy, EUR) collides with a live US symbol (Energizer) — a **silent-wrong-series** hazard, fixed at
the mechanism. The read-only **board-snapshot export** (§8b) also landed. **~520 tests green.** Companion to
the founding document, the decisions review, and the v1 build spec (**rev 14**, the canonical build
instructions; this doc is the orientation/status/roadmap synthesis over it).*

**What changed since rev 5 (for the returning reader).** The **§9e dispersion + constituent-price vertical
landed and fired.** Dispersion is now the runner's **second live spawner**, wired in **shadow** (records and
spawns but does not page, excluded from the ceiling) — which **started its 90-day burn-in clock**; the
holdings/constituent-price vertical it needs is built (`HoldingsIngest` runner-wired for the first time). Two
adjudicated findings landed with the slice: **(A)** a latent **shadow-push CONTRACT collision** — shadow
exclusion was enforced at the ceiling/digest (`active_nonshadow`) but *not* at the push trigger, so a shadow
spawn would have paged (inert under `NullNotifier`, but real); resolved at the mechanism (push iff a changed
lead is non-shadow *after* the change); and **(B)** the **ticker bridge** — the SPDR parser now carries the
file's own Ticker column, the panel keys on CUSIP (never the ticker), the ticker↔CUSIP map coming from the
primary file itself. Then **QA (Claude Science) found a HIGH-severity live-data bug by cold code-read** — the
constituent pull trusted the ticker to be a unique US symbol, which the real TEKX file breaks three ways
(`ENR` foreign-collision → silent wrong series; `-` cash and a placeholder ticker → 404-drop → overstated
coverage) — the **HECO "never anchor on a ticker" rule recurring one level down, at the constituent grain,
for the third time.** The **fix** (design-adjudicated, Code-built): exclude non-priceable lines at the
membership boundary (non-USD `Local Currency`, cash/placeholder), key the structure on CUSIP so a non-unique
ticker can't collapse a CUSIP, and report **honest** coverage; foreign symbol *resolution* is deferred-named
(not-yet-live scope). The **widened primary-source gate passed on real files**: `BRK.B`→`BRK-B` priced,
`GOOG`+`GOOGL` both priced, 323 clean symbols, nothing foreign/placeholder leaked — and XLI (US-only) is a
sound firing. Separately, the read-only **§8b board-snapshot export** shipped (one self-describing markdown
file — manifest + panels + tick-collapsed active-lead timelines — a pure read of the view-models, no
recompute), and its first real output surfaced two **launch-panel legibility** fixes (drop the structurally-
empty name column; filter unlisted no-ticker rows from the survey table but keep them *counted* as a coverage
fact). Two DEFAULT/doc decisions also landed: the **active-lead ceiling is being raised 8→20** (it is a
banner, not a spawn cap, so this quiets the XLV-web nag without suppressing anything), and the README's §4b
dispersion line is corrected from "not yet wired" to **wired-live-in-shadow**. **The honest status is
unchanged in kind: live and firing, now on two spawners, still unfalsified — dispersion's firing is n=1,
the false-discovery rate is unmeasured; falsifiability is demonstrated, profitability is not.** Part V is
fully refreshed; §5.3 now begins at **§10 (the email sender)**.

---

# Parts I–IV — carried forward from rev 5, unchanged

*Parts I (The Idea, §1.1–1.9), II (Architecture & Implementation, §2.1–2.8), III (Findings), and IV (The
Operating Discipline, §4.1–4.7) are unchanged from rev 5 — the premise, the consensus trap, novelty-not-
quality, the ETF-as-thesis instrument, the three streams, the wall/scarce-oracle, the firewall, the fossil
record, the M3 findings, and the seven operating disciplines are all stable. Carry them forward verbatim.*

**One delta in Part II — §2.9 "What is deferred," updated:**

> ## 2.9 What is deferred
> - **The last M4-into-runner slice:** the **rebalance sensor's runner wiring** (`_run_rebalance` — holdings-
>   diff accretion onto live leads). The sensor is built; its wiring was gated on the holdings/constituent
>   vertical, which §9e has now built (the runner freezes each basket's holdings every tick), so this is
>   **unblocked** — the small next wiring slice, at a clean seam. *(The launch-corroboration hook, mandate-
>   diff, and SOI resolver are already built and runner-wired.)*
> - **Milestones 5-remaining → 6 → 7:** **§10** (the email heartbeat/dead-man + state-change push — the only
>   unbuilt piece of the M5 outputs; the Streamlit dashboard, the board-snapshot export, and the CLI are
>   built); then **M6** (discourse capture + budget guard); then **M7** (infra-as-code + **scheduled** deploy
>   — where the runner stops being a manual `pros run`). M7 also owns two named items: the SOI-corroboration
>   **cadence gate** (0 cost today — empty dormant pile) and the runner-side **WAL-checkpoint-out** for
>   serving the store from read-only *media*.
> - **Milestone 3b** (dispersion PIT calibration + the NPORT-P parser) — data-availability-gated
>   (survivorship-clean historical holdings + delisted-constituent prices), and *worse* for the proto-cluster
>   layer per §1.9. **The live shadow burn-in substitutes; 3b is not a v1 blocker.**
> - **Broader holdings-intake coverage** — a real but **secondary** widening (per-issuer parsers / NPORT-P);
>   the SOI path already resolves the active-fund sector case, so this turns the live lag from existence-proof
>   toward a representative *rate* rather than unblocking it.
> - **Foreign constituent symbol resolution** (§9e follow-on, Option 3) — CUSIP/SEDOL→US-symbol mapping for
>   non-USD holdings; needs a primary-source mapping and serves the not-yet-live foreign/thematic scope.
>   Exclusion-with-a-reported-gap is the honest v1 default until a resolution slice earns it.

---

# Part V — Current State & Roadmap

## 5.1 Where the 17-year arc stands

Milestones 1–4 are complete, the SOI resolver is in, the M5 runner is live — and, new since rev 5, **the
second spawner is wired and firing.** A real `pros run` fires both structural detectors on cadence; every
step has left an auditable fossil. Where it stands:

- **Two live spawners.** Excess-correlation (§4a) pages and counts toward the ceiling; **dispersion (§4b/§9e)
  runs live in shadow** — records and spawns, excluded from paging/ceiling, its 90-day burn-in clock running.
  The two genuinely-early detectors the whole design rests on are both now producing real data.
- **Dispersion fired for real — n=1, existence proof, not rate.** Its first un-planted live firing is a
  fracture in **Industrials (XLI split, z≈4.0→4.15)**, in shadow, on real constituent data — the "prove a
  spawner fires on *real seed data*, not merely that it's wired" rule (the xcorr-empty-registry lesson)
  passed its first post-xcorr test. This is dispersion's *starting line*: the point where reality begins
  correcting the map, not a finish.
- **Primary source corrected the map again — twice in one slice.** The rev-2 gate anticipated dual-class
  symbols and stopped there; only reading the real TEKX file surfaced the `ENR` foreign-collision (a valid-
  looking symbol pointing at the *wrong company* — a failure mode the dual-class check would never catch).
  And the implementation had **half-applied** the CUSIP-key discipline (panel re-keyed, but the pull left
  ticker-anchored). Both fixed; the lesson — enforce the identity key **end-to-end** — is in the code
  comments. The widened gate then **passed on the real sector files** (`BRK-B` + both GOOG classes priced,
  323 clean symbols, no foreign/placeholder leakage; XLI sound).
- **The review surface got a real upgrade.** The §8b board-snapshot export renders the whole live board as
  one self-describing markdown file — a *pure read* of the same tested view-models the dashboard shows, no
  recompute (the anti-slot-machine discipline, extended). Its first output proved the tick-collapse holds
  (a long timeline reads as two state-change lines + "N ticks, latest z"), and surfaced the launch-panel
  legibility fixes now landed.
- **The M3 existence proofs still stand, still existence proofs.** Recall (+593 on real sectors), the twice-
  confirmed β-strip, the re-armed falsifier with its correctly-routed box-B flag, the inert verdict layer —
  all as of rev 5. Converting these from existence proofs into *rates* remains the prospective, on-cadence
  work that has barely started.

## 5.2 Status by register — the single source of truth for what's built

**BUILT (~520 tests, all offline):**
- *Foundation + M4 + SOI + M5 runner* — as of rev 5, unchanged: the fossil record, identity layer, excess-
  correlation sensor + frozen stress gate, backtest + full M3 gate, the M4 sensors (`holdings`, `rebalance`,
  `mandate`, `launch_corroboration`) + the SOI resolver, and the §9 runner (SOI-fetch, §9d retry, §9c mandate
  invariant, the Tiingo prices vertical, **xcorr wired live and paging**, the read-only dashboard).
- ***NEW — §9e: dispersion wired live in shadow, the second spawner.*** `_run_dispersion` at the §4b slot;
  **`HoldingsIngest` runner-wired** (the holdings feed goes live); constituent-price ingest; **shadow spawn
  starts the burn-in clock, excluded from ceiling/paging** (the shadow-push collision closed at the push
  boundary — push iff non-shadow after the change); the **generous `dispersion.tick` payload** confirmed live
  (`clusters` with sub-cluster membership + centroids, CUSIP-keyed — the v2 proto-cluster substrate accruing).
  Cadence daily. Fired **XLI split** on real data.
- ***NEW — §9e constituent-symbol resolution (the ENR fix).*** The ticker bridge (SPDR Ticker column carried,
  panel CUSIP-keyed, map from the primary file); **`priceable_members`** excludes non-USD + cash/placeholder
  lines at the membership boundary; the panel is built from **`(ticker, identifier)` pairs** (a non-unique
  ticker can't collapse a CUSIP; `build_panel` faults on a duplicate CUSIP); **`coverage_actual` computed
  over the priced set** (honest, not overstated). Four RED-first violation tests on the real TEKX fixture.
  The P1 fail-closed guard extended to the constituent pull; the holdings-fault-vs-coverage-skip granularity
  split. **Verified green on real sector files.**
- ***NEW — §8b board-snapshot export.*** `dashboard/export.py` — a pure, tested serialization layer rendering
  one markdown board-snapshot (manifest + panels + tick-collapsed all-active timelines incl. shadow), plus
  explicit CSV buttons on the three sortable panels; **pure read, no recompute, cannot drift from the screen**
  (serializes the same view-models), firewall intact. **Launch-panel legibility fixes**: dropped the
  structurally-empty name column; filtered unlisted no-ticker rows from the survey table while **keeping them
  counted** as a coverage fact.

**QUEUED (named, next):**
- **§10 — the email sender.** Weekly heartbeat/dead-man + immediate state-change push, carrying the
  **nuisance-alarm suppression** (push once on a *new* fault, then fall to the heartbeat until it clears/
  changes). Currently `NullNotifier`. This is the **only unbuilt piece of the M5 outputs** and completes
  milestone 5. It also closes the paid-Tiingo-sub lapse-risk (a dead key silently empties the panel via soft
  faults; the 7-day dead-man catches it *once the sender exists*).
- **Rebalance runner-wiring (`_run_rebalance`).** The last M4-into-runner slice — sensor built, now unblocked
  by §9e's holdings vertical (the runner already freezes each basket's holdings per tick). Small; confirm
  current wired status with the build seat.

**DEFERRED (named, with reason):**
- **M6** (discourse capture + budget guard) → **M7** (infra-as-code + **scheduled** deploy; + the SOI cadence
  gate and the WAL-checkpoint-out).
- **Milestone 3b** (dispersion PIT calibration + NPORT-P parser) — data-gated; live burn-in substitutes; not
  a v1 blocker.
- **Broader holdings-intake coverage** — secondary widening (existence-proof → rate), not unblocking.
- **Foreign constituent symbol resolution** (§9e Option 3) — not-yet-live scope; exclusion + reported gap is
  the honest default.
- **Surfacing large per-basket coverage gaps** — `coverage_actual` is computed but not yet surfaced (an
  observability refinement; the number is reconstructible from the fossils, so nothing is lost by waiting).

**ASPIRATIONAL (v2, walled off — captured, not queued):**
- The **proto-cluster / pseudo-ETF** layer and Prospector-as-product (§1.9) — its substrate already accrues
  via the generous dispersion payload (now *confirmed accruing* in the live XLI firing), so nothing to build,
  keep capturing.
- The **discourse-interpretation** program (v2).

**The load-bearing honesty line:** everything under BUILT is *built and running*, not *validated* — the
false-discovery-rate and edge questions live in the gap between "the runner fires" and "the firings mean
something," and closing that gap is prospective, on-cadence work. Dispersion firing on real data is n=1;
"live" is not "proven."

## 5.3 Next steps — prioritized marching orders

The two structural spawners are live; the constituent vertical is built and gate-verified; the review surface
is upgraded. What remains for v1 is the sender, one small wiring slice, capture, and scheduled deploy:

1. **§10 — the email sender.** The next thing. Weekly heartbeat/dead-man + state-change push with nuisance-
   alarm suppression built in — the one place the architecture-as-is would train the operator to ignore the
   alarm. Completes the M5 outputs and turns the system from a hand-run script into an actual always-on
   monitor (once M7 schedules it). Closes the paid-sub lapse-risk dead-man.
2. **Rebalance runner-wiring.** The last M4 slice into the runner, unblocked by §9e — small, at a clean seam.
   Can follow §10 or ride alongside.
3. **M6** (discourse capture + budget guard) — raw, frozen, uninterpreted capture targeted at structural
   hits, with hard budget caps (K queries, M fetches, weekly/monthly ceilings; a fault on breach, never a
   silent overrun or skip).
4. **M7** (infra-as-code + **scheduled** deploy) — the runner leaves manual `pros run` for a real cadence, and
   the deferred M7 items land. **After M7, v1 is build-complete.**

**Two things that are not builds but gate v1's meaning:**
- **Dispersion's 90-day burn-in must complete**, then a *human* decides promotion to paging (a `config.changed`
  flip) — calendar-bound, running-it, not a slice.
- **The long prospective run.** After M7, v1's remaining work is *running it on cadence long enough for the
  false-discovery rate to become a measured number* — the multi-year, event-gated accumulation of
  corroborated firings that is the only thing that answers whether the edge is real or merely architectural
  coherence. That is v1's actual finish line, and it is measured in years, not slices.

**Immediate action:** merge the two clear branches (the §9e fix, gate-green; the independent §8b export),
land rev 6 and the README fix with them, then build §10.

---

*Closing note (carried from rev 5, lightly updated). The distinguishing property of this project is that it
is engineered, in writing, before building, to be able to **lose** — falsifiable at every layer, with an
immutable record that grades its own calls and metrics that refuse to flatter themselves. So far, at each
layer where it could have lost, it has instead surfaced something true — including, this arc, a real
silent-corruption hazard that a cold read of a primary file caught before it could poison a baseline, and a
second spawner that fired a genuine, un-planted fracture on its first live run. The tool notices; the human
decides; the core absorbs; the record remembers. That division is the whole design.*
