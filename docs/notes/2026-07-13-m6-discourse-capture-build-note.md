# M6 — discourse capture + budget guard: build note (2026-07-13)

*Build note for Claude Code. **The last v1 build slice.** Spec §6 is the governing CONTRACT and is unusually
complete — read it in the repo first (current spec rev at `docs/`); this note transposes §6 onto the
infrastructure that has landed since it was written (the §9 runner, the §8a fault taxonomy, the §10
suppression keys, the backup FOSSIL_TREES, the prod worktree) and records the build-time calls. One decision
is the owner's and is marked OWNER below. After this slice, v1 has no code left — only verification and the
rev15 doc fold.*

## 1. What M6 is (and is not)

v1 **captures discourse, never interprets it** — deterministic-templated queries at structural hits, freezing
only raw search-result blocks and fetched page text, so v2's retrospective interpretation has an archive to
thaw backward through ("late-arriving meaning is free," applied to the discourse stream). No model-authored
prose is ever persisted as record content (CLAUDE.md wall). Nothing in v1 *reads* a capture — this is a
write-only substrate for v2.

## 2. The §6 CONTRACT, restated (verify against the repo's current spec)

- **Trigger:** a **non-shadow** lead entering `active`, then **weekly per active lead** (DEFAULT). Shadow
  leads never trigger capture — not yet trusted enough to spend on. (Dispersion's two shadow fractures
  therefore capture nothing until promoted.)
- **Query construction is deterministic templating — no LLM authorship.** From lead metadata: basket display
  names, top-N constituent names, concentration industries. K queries per capture (DEFAULT K=5).
- **Stored:** `captures/{lead_id}/{ts}/query_{n}.json` — query, timestamp, provider, raw result blocks
  verbatim. Plus `web_fetch` of the top-M URLs per query (DEFAULT M=2), storing extracted page text — the
  fetched text is the frozen substrate. One `capture.stored` event onto the lead per capture.
- **Budget guard (CONTRACT):** hard caps — `capture.max_searches_per_week` (DEFAULT 60) and
  `capture.monthly_budget_usd` (owner sets). On breach: **capture pauses + a `fault` event.** Never silently
  overrun; never silently skip.
- **The wall:** persist only raw result blocks / fetched text; any model prose from the plumbing is discarded,
  never written.

## 3. Build-time calls (the transposition onto what now exists)

**(a) [CRITICAL — the backup catch] `captures/` must be added to `FOSSIL_TREES`.** The backup slice predates
M6; its tree list (`events/ snapshots/ ingest/ baselines/ runs/ registry/`) does not include `captures/`.
Ship M6 without this and the discourse archive — the one dataset that *cannot* be backfilled — is the only
un-backed-up tree. This is the exact `registry/`-omission class from the backup build, one slice later.
Violation test: a store containing captures, backed up, contains them on the target.

**(b) Budget enforcement is count-based primary, USD-estimate secondary.** Searches are exactly countable;
dollars are a pricing assumption. Enforce the hard cap on a **persisted weekly search counter** (stored, not
in-memory — it must survive restarts and be visible to the dashboard), and compute the USD figure as
`count × capture.unit_price_usd` (DEFAULT set from the provider's published price) checked against
`monthly_budget_usd`. Both breaches behave identically: pause + fault. This honors the CONTRACT's intent
(never silently overrun) with an enforcement primitive that can't drift from reality.

**(c) The breach fault is `operational` (it pages once) and carries a stable suppression key.** A paused
capture is something the operator must know about — §8a puts it in the paging class. Give it
`key="capture.budget"` (or per-cap: `capture.budget:searches` / `capture.budget:usd`) so §10's suppression
holds while the pause persists: pages once, then rides the heartbeat. A *transient* single-query fetch
failure is different — store the partial capture, soft-fault that query (`operational`, stable key
`capture.fetch:{status}`), never kill the whole capture over one URL.

**(d) Runner integration reuses the weekly-gate shape.** Capture rides the daily tick with a per-lead weekly
gate (the heartbeat's gate pattern): on each tick, capture for (i) any non-shadow lead that entered `active`
since the last tick, and (ii) any active non-shadow lead whose last capture is ≥7 days old. Order it **after**
the sensor phase (captures reference the tick's final lead state) and **before** the backup step in the
wrapper's sequence (so the night's captures are on the HDDs same-night).

**(e) Already-active leads start their archive at landing — no backfill, by nature.** The six current xcorr
leads get their first capture on the first tick after deploy (they're all ≥7 days stale by construction).
This is the accepted burn-in cost of sequencing M6 after M7; note it in the decision record so the archive's
start-date is explained, not mysterious.

**(f) The never-read wall gets a mechanical guard.** No module outside the capture writer imports from or
reads `captures/` in v1 — assert it (an import-graph or grep test, same shape as the never-execute firewall
test). v2 earns read access by design, not by drift.

**(g) Volume sanity (no action, just the arithmetic):** 6 active leads × K=5 weekly = ~30 searches/week —
half the 60 cap; ~60 fetches/week; single-digit MB/week of frozen text. The caps have real headroom without
being unbounded.

**(h) Dashboard: capture inventory is a DEFAULT, keep it tiny.** A count-per-lead line on the existing
store-monitor page satisfies §2.7's "capture inventory" — a new page is unearned. Code's call; defer freely.

## 4. OWNER decision — provider + budget number (the one open fork)

The spec deliberately makes the provider an implementation choice ("the contract is what gets stored, not the
provider"), but the **spend and the secret are the owner's**:

- **Recommended: the Anthropic Messages API `web_search` tool** with a minimal fetch-only prompt, persisting
  only the `web_search_tool_result` blocks verbatim. It's the spec's own named mechanism, the result blocks
  are exactly the frozen-substrate shape, and the wall ("model prose discarded") is a structural filter on
  block type — easy to test. Cost at the current cadence is small (roughly 260 searches/month ≈ a few dollars
  plus minimal tokens at published pricing — verify the current price when setting `unit_price_usd`).
- Alternative: any plain search API (Brave, etc.) — same storage contract, different key. Fine if preferred;
  nothing in the design depends on the provider.
- **Owner supplies:** the API key → **`.env` only** (`ANTHROPIC_API_KEY`), handled exactly like the Tiingo
  token and SMTP password — env-only, never config, never committed, fail-fast if capture is enabled and the
  key is unset. **And the `capture.monthly_budget_usd` number** — suggest something with headroom over the
  computed estimate (e.g. $10/mo) so the cap catches runaway behavior, not normal operation.
- **Ops note:** prod runs the worktree, whose `.env` is per-checkout — the key must be added to the **prod**
  `.env` (and dev's for testing). This lands as a feature release: tag **`v1.1.0`** (new capability, not a
  patch) and `deploy.sh v1.1.0`.

## 5. Acceptance — tests attempt the violation

- **Budget breach pauses and faults, never silently skips:** drive the counter over the cap → capture stops,
  an `operational` fault with the stable key fires once, subsequent ticks stay paused-and-suppressed, and the
  runlog shows the pause (loud, not skipped).
- **The wall holds structurally:** stored artifacts contain only result blocks / fetched text — assert no
  assistant-authored content type is ever written (and the plumbing's prose is verifiably discarded).
- **Shadow leads never capture:** a tick with only shadow leads produces zero searches.
- **Determinism pinned:** identical lead metadata → identical query set (no timestamps/randomness in query
  text).
- **Weekly gate:** a lead captured 3 days ago is skipped; at 7+ days it captures.
- **Backup includes captures** (per 3a).
- **Never-read wall:** the import/read guard test.
- Full suite green through the CI gate; owner reviews and merges per house rule.

## 6. After this lands

v1 is **code-complete**. Remaining to call v1 *done*: the on-Mini verification set (first scheduled run
observed, dead-man loop test, backup verify-restore), then the **spec rev15 fold + state rev8** recording the
finished state. Then the posture is *let it run* — and the design thread moves to v2 ideation from the banked
grounding (`deferred/2026-07-11-v2-research-grounding-flow-vs-structure.md`).
