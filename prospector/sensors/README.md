# `prospector/sensors/` — the deterministic writers that turn frozen substrate into events (spec §4)

Sensors sit between `ingest/` (frozen raw bytes, §3) and the `store`/`fold` (the append-only fossil
record a lead is folded from). Each is a **pure function over pandas/dicts** — no store, no network,
no clock — driven once per tick by `runner/`. They emit **facts, never verdicts**: a `lead.spawned`,
an `xcorr.tick`, a `rebalance` — the human owns the verdict. Milestone 4 is "sensors complete" (spec
§4). One distinction governs the whole package: **`xcorr` is the primary live lead-spawner;
`dispersion` is built but shadow/not-yet-wired; the other four accretion sensors NEVER spawn a lead**
— they attach facts onto leads that already exist (routed by forward-hash, CONTRACT §4d).

## Modules

- **`xcorr.py`** — §4a excess-correlation, the inter-basket edge detector and the **PRIMARY live
  spawner** (a real `pros run` fired 5 leads on the SPDR grid). Pure pipeline: returns → β-strip →
  residual correlation → Fisher-z → departure-z vs a frozen baseline. `scan()` is the runner's live
  driver; a spawn is `shadow=False`, so it pages and counts toward the §8a ceiling. The **stress gate**
  (absolute 0.85, crisis-only — CONTRACT, `docs/decisions/2026-07-02-stress-gate-recalibration.md`)
  freezes a crisis-day entry to a `_system` `xcorr.departure`, never a spawn. Owns the shared
  `xcorr_lead_id`. Thresholds are empirical (backtest-set), never Gaussian tail probabilities.
- **`dispersion.py`** — §4b intra-basket fracture: one basket splits into two blocks via spectral
  bipartition (2nd-eigenvector sign), scored by cluster-quality `Q`. **BUILT but NOT wired into the
  runner** — the runner slot (§9e) is deferred pending the holdings/constituent-price vertical
  (runner.py:19). Ships **shadow** (`shadow=True` until a human flips `dispersion.paging`) and carries
  the **generous-payload CONTRACT** (§4b rev8): the `dispersion.tick` banks full membership +
  sub-cluster assignment + correlation structure so the deferred v2 proto-cluster layer can thaw
  backward — you cannot backfill a payload you did not capture.
- **`launch.py`** — §4c launch detection + two-phase recording (the consensus clock). Diffs two frozen
  `company_tickers_mf.json` snapshots; a new `(symbol, seriesId)` is a registration. A launch
  timestamp **cannot be backfilled**, so this runs continuously and nails `detected_at` before
  resolution. Over-detects (the MF map covers mutual funds too) — every unverified detection lands on
  `_system`, keying no lead. Recording is wired live; the emission itself lives in
  `ResolutionMachine.register_launch`.
- **`launch_corroboration.py`** — §4c capstone, the live **signed** cross-stream lag (T2−T1). A
  launch's sectors are derived from its **first holdings** (look-through-is-truth, never prose); a
  both-sides overlap **accretes** the launch onto a live lead (never spawns — rev7). Holds
  `route_corroboration` (the shared overlap/emit tail), `lead_sectors` (forward-hash), and
  `pending_soi_resolution` (the §9d work-list, folded from the record). The holdings-source
  `corroborate()` pass is **deferred** — it fires only when first holdings land, and its runner wiring
  waits on the same holdings vertical; the SOI-source path (below) IS wired. Finding, recorded at full
  strength: the live lag is **bounded by holdings coverage, not the hook** — an existence proof, not a
  rate.
- **`mandate.py`** — §4d prospectus mandate-diff: a new prospectus → diff the **principal-strategy
  section only** (a full-text diff is a false-positive machine) → `mandate.changed` accreted onto live
  leads (else `_system`). **BUILT and wired live** (`runner._run_mandate`). Extraction-unreliable →
  `fault` for manual review, **never a false change**. §9c invariant: the "prior" is the last *frozen*
  blob, never the registry accession field (an identity pass may advance it intra-run).
- **`rebalance.py`** — §4d holdings-diff accretion: a material add/drop/weight-delta over identified
  securities → a `rebalance` fact. An **accretion sensor** — no Schmitt, no lead of its own, carries no
  z. **BUILT and wired live** (`runner._run_rebalance`, 2026-07-12; reuses the §9e frozen holdings,
  seed-on-first-sight). Its `watching_leads` (forward-hash routing) and `active_nonshadow_lead_ids` (reads
  the fold's materialized snapshots, never a side cache) are the shared routing/enumeration helpers reused
  live by `mandate.py`. `active_incl_shadow_lead_ids` is the sibling of the latter for the rebalance path
  itself — same materialized-fold source, but KEEPS shadow leads, because rebalance accretes and never
  pages (so unlike the paging paths it corroborates burn-in dispersion leads). See
  `docs/decisions/2026-07-12-rebalance-runner-wiring.md`.
- **`soi.py`** — §4c resolver of `sectors_unresolved`: when a fund's file carries no GICS sectors
  (every active thematic ETF), its first industry-grouped **Schedule of Investments** yields the
  sectors, routed through the SAME `route_corroboration` path — the deferred reach-back preserves
  `detected_at` as T2. **BUILT and wired live** (`runner._run_soi_corroboration`). Accretion sensor,
  never a spawner; extraction-unreliable → `fault`, never a wrong sector set.
- **`schmitt.py`** — the shared two-threshold hysteresis trigger for the *departure* sensors (xcorr,
  dispersion): entry `z ≥ z_in`, exit `z ≤ z_out`, `z_in > z_out` so a hovering z can't flap.
  Statelessness (§9): `state_from_last_event_type` reconstructs trigger state from the record — QUIET
  only on `None` or a `*.reverted`, else ACTIVE (keyed on the `.reverted` suffix so it is correct for
  dispersion, which has no `.departure` event). A None/NaN z never transitions (warmup safety).

## Important to know

- **Spawner vs accretion is the load-bearing split.** Only `xcorr` (live) and `dispersion` (built,
  shadow, not-wired) run a Schmitt trigger and can birth a lead. `rebalance`, `mandate`, `soi`, and
  `launch_corroboration` **accrete** onto existing leads and never touch the §8a ceiling.
- **Forward-hash routing (CONTRACT §4d).** To find every live lead touching a fund, re-hash its
  memberships with `xcorr_lead_id`/`dispersion_lead_id` **verbatim** and intersect with the active set.
  Never add `series_ids` to a lead payload — the lead-id already encodes them; duplication invites drift.
- **Extraction-unreliable → `fault`, never a guess** (`mandate`, `soi`): a false claim is worse than a
  missed one. bs4/parsing owns structure, our code owns which-section/which-industry, the human owns
  significance.
- **Determinism for the append-only SHA:** floats are rounded and NaN/inf → None before payload
  assembly (`_round` in `dispersion`/`rebalance`), because `canonical_json` uses `allow_nan=False`.
- **Leads key on SEC series IDs, never tickers** (§2/§5). A pair with an unresolved ticker is skipped —
  bounded and honest, never keyed on a display string.

## See also

- Spec §4 in `docs/spec.md`; `ARCHITECTURE.md` §2/§4/§9 and the runner
  state map at `prospector/runner/runner.py:15-21` (the authoritative wired-vs-slot source).
- `docs/decisions/`: `2026-07-03-{dispersion-payload-generous,rebalance-accretion-and-routing,
  mandate-diff-targeted-section,launch-corroboration-existence-proof}.md`,
  `2026-07-04-soi-derived-sector-concentration.md`, `2026-07-02-stress-gate-recalibration.md`,
  `2026-07-07-xcorr-live.md`.
