# M6 discourse capture — ARMED (2026-07-18)

*Closes the deferred Part C (items 12–14) of `docs/notes/2026-07-17-activation-781.md` and the CAP-DRIFT
residual of `docs/decisions/2026-07-14-query-drift-byte-exact.md`. Capture now runs on the scheduled cadence,
banking the discourse substrate v2 will read. v1 captures, never interprets (CLAUDE.md "No LLM text as data" —
raw search-result blocks + fetched page text only).*

## Why now
The owner is beginning to ideate v2 (discourse interpretation) and wants capture data accumulating to build
against. v1's job is to bank the substrate richly — you cannot backfill an append-only record.

## What was done (Part C, items 12–14)

- **Item 12 — API key:** `ANTHROPIC_API_KEY` present in both `prod` and `dev` `.env` (env-only, never config,
  never committed).
- **Item 13 — price + budget:** `unit_price_usd = 0.01` verified against the live Anthropic web-search rate
  (**$10 / 1,000 searches**). Budget set to **`monthly_budget_usd: 25`** (owner) — a USD ceiling; normal
  operation is ~$1.50–3/mo (~7 active leads × 5 queries weekly), so the cap catches runaway, not normal
  capture. Set in the **prod machine-local overlay** (`config/prospector.local.yaml`); the run emitted a
  `config.changed` fossil.
- **Item 14 — CAP-DRIFT armed byte-compare: PASSED clean.** Bounded to one search (`max_searches_per_week: 1`)
  and run as a single `pros run` tick (run `5ef43431`, `2026-07-18T07:25:05Z`, ~$0.01). **Two witnesses:**
  - the stored blob `captures/xcorr-1556fe8c2f/20260718T072505Z/query_0.json` shows **`query` == `query_issued`
    byte-for-byte**: `'XLU×XLV'` == `'XLU×XLV'` (the unicode `×` round-tripped exactly);
  - **zero `capture.query_drift` faults** — the byte-exact guard never fired.

  The model echoes our templated query byte-exact, so **no normalization is needed**, and the CAP-DRIFT
  residual (`2026-07-14-query-drift-byte-exact.md`, 🟡 ratified-residual, "gated on one real armed call
  comparing bytes, performed before capture is armed") is **closed** by that call.

  **Scope — the compare closed on the *pair-display* shape only; do NOT read this as "all query shapes
  verified."** `'XLU×XLV'` is the safest string `build_queries` emits: well-controlled, one exotic character,
  and the `×` round-tripped. The *other* shape it emits — **constituent-name queries** (`meta["constituents"]`)
  — was **not** exercised (the gate was bounded to `query_0`, the display). Those routinely carry the
  characters a model is most likely to normalize benignly: **ampersands** (a healthcare basket surfaces
  *Johnson & Johnson*, *Merck & Co.*), apostrophes, hyphens, ALL-CAPS holdings strings. So CAP-DRIFT is
  satisfied **on the pair-display shape; constituent-name shapes are guarded-live-but-unexercised.** A
  `capture.query_drift` fault on those in the coming weeks is the **anticipated** shape, not a surprise — the
  live byte-exact guard is the correct protection, and the ordered gate's *observe-then-minimally-normalize*
  path stays open for the shape it hasn't met yet. This is **not** a reason to pre-normalize (the ruling forbids
  a `strip()` against imagined behavior).
- **Armed:** the bound removed → count cap back to the tracked `60/week`. The scheduled tick now captures the
  active (non-shadow) lead set weekly. Capture data confirmed landing: `captures/xcorr-1556fe8c2f/…` + one
  `capture.stored` event.

## Notes

- **The one-time DEGRADED email** (`[PROS] FAULT: capture.budget`, 07:25Z) was the *bounded* gate, not a
  defect: with `max_searches_per_week: 1`, capture correctly paused after the single armed search and pushed
  the operational `capture.budget:searches` fault. With the cap back at 60 it does not recur.
- **Disarm anytime** = set `monthly_budget_usd` back to `null` (next tick reads "disabled," no further spend).
  Captured blobs are append-only fossils, mirrored to the HDDs the same night — the intended substrate, not a
  loss.
- **Flag for Design (small, non-blocking):** the prod overlay now carries an *operational* value (the budget),
  not just paths, though its header still reads "per-machine PATHS only." Either broaden the header/scope
  (machine-local operational config) or reconsider the budget's home — worth a one-line ruling.

## What v2 can now build against

Per active lead, per weekly capture: `captures/{lead}/{ts}/query_{n}.json` — the templated query, the model's
issued query, the raw `web_search_tool_result` blocks, and the fetched page text (no model prose — the §6
wall). A **write-only substrate in v1** (`test_never_read_wall` enforces nothing reads it); v2 is what reads it.
