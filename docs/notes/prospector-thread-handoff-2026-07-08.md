# Prospector — thread handoff snapshot (2026-07-08)

*A cold-readable orientation for a new design/review thread. Drop this in alongside the current canonical
docs (state-of-project **rev 5**, spec **rev 14**) and the decision records. It summarizes the last stretch
of work and what's next; the canonical docs are the source of truth.*

---

## What this seat is

The **design / review seat** for Project Prospector — a read-only, never-execute ETF-universe structural-
novelty scanner feeding a personal Roth 401(k). Four stateless seats coordinate **only** through git + the
written record: **this thread** (design + review), **Claude Science** (QA — mounts and runs the code cold),
**Claude Code / VSCode** (implementation), and **git**. No live context is shared between seats; the human
is the courier. This thread reads live code via project-knowledge search (the filesystem mount is a
conversation-start snapshot; knowledge search reaches synced code).

## Where things stand (one paragraph)

**The system is live and firing.** The M5 runner is built; a real `pros run` fired **5 live xcorr leads**
on the SPDR grid; the going-live bugs (N1–N10) are fixed; **499 tests green.** The honest status: **live and
firing, but n=1 and unfalsified — falsifiability is demonstrated, a rate and profitability are not.** The
firing is the *starting* line — the point where reality can begin correcting the map — not the finish.

## The last stretch, in order (what just happened)

1. **The M5 runner arc, built slice by slice** — each a committed decision record under `docs/decisions/`:
   runner skeleton (§9 cadence driver) → SOI-fetch (§9b) → identity fixes (I1 series-threading / B1 / B2 /
   `ambiguous_symbol` fault) → §9d deferred SOI-corroboration retry (reaches back, `detected_at`=T2) → §9c
   mandate frozen-prior invariant → prices vertical → xcorr wired live (§4a) → read-only dashboard (§11).
2. **Went live and fired.** First real `pros run` produced 5 live xcorr leads (XLU×XLV, XLRE×XLY, XLC×XLF,
   XLC×XLV, XLRE×XLV). n=1; the correlated structure collapses 5 into ~2–3 independent events (XLV recurs).
   Read, don't trade — XLV is a watch candidate; 5 is under the 8 ceiling.
3. **Yahoo broke → pivoted to Tiingo.** Yahoo turned out to **bot-challenge non-browser clients on a TLS
   fingerprint** (not a rate-limit, not a cookie/crumb gap; Chrome 200s where httpx/curl 429). Pivoted the
   price source to **Tiingo** — CRSP split+dividend-adjusted close, **verified against the NVDA-2024 split**,
   API **key read from the environment (never committed — the project's first secret)**. A keyed authorized
   API is the honest + durable choice over browser impersonation (an arms race). Note: adjClose is
   *retroactively mutable* (CRSP re-adjusts history); the dated price substrate already absorbs it.
4. **QA pass 2 (Science) → fix batch (N1–N10).** Science found 3 confirmed BUGs + assumptions + smells, all
   run cold. The fixes landed (499 tests), each with the **violation-test** that would have caught it — and
   **two came in better than the reference patch, both by testing the violation not the easy case:** **N1**
   used `mode=ro` (WAL-readable, sees fresh writes) **not** `immutable=1` (would render stale), proven by a
   freshness test; **N2** keyed idempotency on the **stable series-id** (moving-clock-proof) where the
   reference patch's `(ticker, detected_at)` only dedups under a fixed clock. The read-only firewall is now
   **enforced by the substrate**, not asserted in prose.
5. **`/remote-control` unlock.** The full workflow (design / QA / build / merge) now runs from the phone —
   the interface finally matching a system already designed to be operated remotely. Capability, not
   obligation; the commit-to-branch-as-you-go discipline matters *more* in fragmented sessions.
6. **The doc pass (just completed).** State-of-project **rev 5** and spec **rev 14** are cut: §5 regenerated
   into the three-register structure (built / queued / deferred / aspirational), the two DRIFT spots closed
   (the §2.9 deferred-list that wrongly listed built items; the §4a aging-monitor 0.81-vs-0.668 pinned to the
   calm-regime margin), and the honest live-but-unfalsified status recorded throughout.

## Next steps (the queue, in order)

1. **§9e — dispersion + the holdings/constituent-price vertical.** Wire dispersion into the runner in
   **shadow** (silent, non-paging, excluded from the ceiling) — which starts its **90-day burn-in clock** and
   pulls in **constituent-price ingest**, confronting **holdings-intake coverage** as its own slice (its
   consumer is finally built). The **"prove a spawner fires on real seed data, not merely that it's wired"**
   rule — learned when xcorr would have been permanently inert reading an empty registry — gets its first test
   here. This is the bigger lift; it needs prices flowing (Tiingo) first, which is now true.
2. **§10 — the email sender.** Weekly heartbeat/dead-man + state-change push, with the **nuisance-alarm
   suppression built in** (push once on a *new* fault, then fall to the heartbeat until it clears/changes) —
   the one place the architecture as-is would train the operator to ignore the alarm (the Protector brief's
   own GPWS failure mode). Currently `NullNotifier`.
3. **M6** (discourse capture + budget guard) → **M7** (infra-as-code + **scheduled** deploy — where the runner
   leaves manual `pros run`; M7 also owns the deferred SOI-corroboration **cadence gate** and the read-only-
   media **WAL-checkpoint**).

**Immediate:** drop in rev 5 / rev 14. One code-side item is still owed from the QA review — the **C.2 doc
drift**: `ARCHITECTURE.md` and the runner docstrings need regenerating from the actual wired set (the build
seat's job, not this thread's). The inline docstrings were corrected in the fix batch; the systematic
regeneration wasn't.

## Standing disciplines to carry into the new thread

- **Register discipline.** Every claim is *built* / *queued* / *aspirational*; **status lives only in §5** of
  the state doc — decision docs are point-in-time. Scope-creep is aspirational migrating into queued/written
  unearned. Ideation is the engine; the governor is the wall at the queue boundary.
- **Test the violation, not the easy case.** A stated invariant not enforced by mechanism is a comment; a
  test that never *attempts* the violation tests nothing. (Generalizes `fires-not-called`.)
- **Primary source over convergent prior.** The shared wrong prior that all same-model instances hold is only
  broken by opening the real artifact / running the real thing. It has recurred ~a dozen times.
- **Live ≠ validated.** n=1, FDR unmeasured; the runner exists to convert existence proofs into *rates*, and
  that work has barely started. Falsifiability is shown; profitability is not.
- **The never-execute wall is architectural, not habitual.** The runner sequences deterministic sensors and
  renders output; it never decides. The read-only surface renders; it never acts.
- **Ship, don't over-write.** The writing is the most seductive tinkering channel for a builder whose primary
  risk is over-engineering. Bias hard toward shipping the queue over more specification.

## Key artifacts (upload to the new thread as needed)

- **`project-prospector-state-of-project-rev5-2026-07-08.md`** — orientation / status / roadmap (start here).
- **`prospector-v1-spec-rev14-2026-07-08.md`** — the canonical "what to build."
- **`docs/decisions/2026-07-08-live-cadence-qa-fixes.md`** — the N1–N10 fix batch record.
- **`prospector_followup_review_2026-07-07.md`** — Claude Science's live-cadence QA review (the evidence).
- The per-slice decision records under `docs/decisions/` (skeleton, SOI-fetch, identity, §9d, §9c, prices/P1,
  xcorr-live, dashboard) — the fossil trail of the M5 arc.
