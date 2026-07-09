# §9e — the dispersion + constituent-price vertical: build note (2026-07-09)

*Design-thread build spec for the §9e slice; handoff to the build seat (VSCode implements, Claude Science
QA-reviews cold). Canonical build instructions remain spec **rev 14** (§4b dispersion, §9 runner, §8a
ceiling) and state-of-project **rev 5** (§5 registers, §5.3 marching orders); this note records the feed
decision that unblocked §9e and pins the slice's scope, CONTRACT invariants, and acceptance gate. It
**supersedes** the free-tier constraint-management design sketched in the design thread earlier the same day
— that design is now moot (see §1).*

---

## 1. Decision recorded — the price feed: Tiingo Power

The constituent-price vertical was blocked on the free tier (500 unique symbols/month; the 11-basket
constituent union ≈ most of the S&P 500, ≈ at the cap with no churn headroom). Resolved by upgrading the
existing Tiingo account to **Power ($30/mo)** — a plan flip: no new integration, no new secret, no code
change beyond deleting the workaround.

- **[DECISION] Deliberate §11 cost-envelope revision.** Power is ~5× the spec §11 "single-digit $/mo"
  framing. This is recorded as a *decision*, not slipped scope. Justification: (a) it deletes an entire
  constraint-management subsystem whose only job was dodging the cap; (b) it makes the **silent-partial-breach**
  failure — a soft-fault on churned-in constituents that drops names and poisons the trailing-252d Q baseline
  for a year, resetting only at the month boundary — **structurally impossible**, not merely guarded; (c) it
  makes the deferred roadmap data-feasible (broader holdings-intake coverage → turns the live lag from
  existence-proof toward a *rate*; the v2 proto-cluster layer → needs constituent data across many baskets),
  so the spend unblocks the whole downstream, not just the sector grid. Power's meters (108,758 symbols,
  10k/hr, 100k/day, 40 GB/mo) are effectively uncapped at v1 scale.
- **What this removes from the design (all moot — do NOT build):** the unique-symbol budget gauge; the
  soft-budget circuit-break; the coverage-as-headroom lever; the budget-forced weekly cadence; the free-tier
  union-count measurement. Each existed only to survive 500. Gone.
- **[CONTRACT-adjacent] Standing lapse-risk (17-year note).** A paid sub is a new lifetime-failure mode: an
  expired card returns auth-refused — the key does **not** degrade to free tier, queries simply stop —
  silently emptying the panel via soft-faults. Caught by the 7-day dead-man **only once §10 (the sender)
  exists.** One more reason §10 is the very next slice.

## 2. Scope — what to build

Wire the already-built `sensors/dispersion.py` into the runner as its **second live spawner**, with the
constituent-price vertical it depends on. Mirror the xcorr-live wiring (`_run_xcorr` at the §4a slot; the
`2026-07-07-xcorr-live.md` decision record is the template).

- **Constituent-price ingest.** Extend the Tiingo price path to pull daily adjusted closes for the
  weight-covering constituents of the 11 SPDR sector baskets, frozen to the dated substrate
  (`ingest/prices/`) exactly as the sector grid. Full coverage (`dispersion.weight_coverage: 0.90`) —
  uncapped now, so no trimming.
- **Membership source (CONTRACT — the empty-registry lesson).** Dispersion's per-basket constituent
  membership comes from `holdings.py` (SPDR daily files, 90%-weight, built, xlsx-capable) — an authoritative
  *live* feed, **never** the fund registry (empty in production; the exact trap that would have left xcorr
  permanently inert). Resolve membership from the parsed holdings this tick; a basket whose holdings don't
  parse is **skipped and surfaced, never guessed**.
- **Runner slot.** Build `dispersion.scan(...)` into `_run_dispersion` at the §4b slot in `_run_sensors`
  (the scan shape already exists — dispersion was built shadow-designed). Soft-fault per basket (§9g);
  no membership/prices → `skipped`, honest.
- **Cadence: daily.** The budget reason for weekly is gone; daily gives ~65 burn-in evaluations instead of
  ~13 — a richer calibration window at zero marginal cost on Power. (Fracture is months-scale, so daily vs
  weekly barely changes *detection*; the burn-in richness is the tiebreaker. Flag if you disagree — it's a
  DEFAULT, not load-bearing.)

## 3. CONTRACT invariants (pin these — a stated invariant not enforced by mechanism is a comment)

- **Shadow mode (§4b).** Dispersion ships `shadow=true`: events written, leads spawned, but **excluded from
  paging, from the §8a active-lead ceiling, and from the state-change email section**; visible only in the
  dashboard shadow panel. The fold + `active_nonshadow` filter already enforce this (the same mechanism
  xcorr's non-shadow path rides, inverted) — **verify, don't assume**.
- **Burn-in clock starts on wire.** Wiring dispersion live starts the 90-day burn-in
  (`dispersion.shadow_days: 90`). Promotion to paging is a **human `config.changed` flip**
  (`dispersion.paging: true`) after a calibration review — never automatic. The dashboard shows days-elapsed
  vs `shadow_days`; readiness is surfaced, never auto-promoted.
- **Generous payload (§4b — banks the deferred proto-cluster substrate).** `dispersion.tick` carries **full
  constituent membership with each name's sub-cluster assignment, the cluster centroids, and the within/cross-
  cluster correlation structure** — not the scalar Q alone. You cannot backfill a payload you did not capture
  (append-only forced ordering). Non-negotiable even though nothing interprets it until v2.
- **Never-execute wall.** Dispersion spawns a shadow lead and renders it; it never decides, never routes
  anywhere actionable, never touches a trade path or `portfolio.yaml`. Firewall intact (own store,
  source-grep guarded).

## 4. DEFAULT config (tunable; not spec-load-bearing)

`dispersion.weight_coverage: 0.90` · `dispersion.shadow_days: 90` · entry z ≥ 2.5 / exit z ≤ 1.0 (Schmitt,
matching xcorr) · daily cadence · `dispersion.paging: false` (until the human flip).

## 5. Acceptance gate — the tests ARE the gate (prove-fires-on-real-seed-data)

This slice is where the standing rule — **prove a spawner fires on real seed data, not merely that it's
wired** (the xcorr-empty-registry lesson) — gets its first post-xcorr test. The acceptance test must, mirroring
the xcorr-live acceptance discipline:

- **fires live end-to-end on REAL membership:** real holdings-derived constituent membership + a constituent
  price panel that genuinely departs → one `run_tick` spawns a real `lead.spawned` (`spawner=dispersion`,
  `shadow=true`) that folds active-shadow, is **excluded** from `active_nonshadow` (so it does **not** page and
  does **not** consume a ceiling slot), and starts the burn-in clock. The membership must come through the real
  holdings path — a test that feeds synthetic membership that could never occur live proves nothing (that is
  the exact failure the rule names).
- **generous payload asserted:** the spawned `dispersion.tick` carries membership + sub-cluster assignments +
  centroids + correlation structure, not just Q.
- **null-silent:** a basket with no fracture spawns nothing.
- **state reconstruction (§9f):** an already-active shadow lead **ticks** (does not re-spawn); a reverted one
  can re-enter — proving state comes from the record, not a recompute.
- **soft-fault boundary:** a basket missing prices/membership faults **that basket**, not the run.

Suite stays green (currently **500 passed / 1 xfailed**) plus the new §9e acceptance + violation tests.

## 6. Explicitly NOT in this slice (deferred, named — do not let removing the cap tempt scope back in)

- **The skip-if-frozen-today dedup** — necessary under the free cap, now closes **no live gap** on Power
  (100k/day). Deferred. Do **not** smuggle it in as "hygiene" — it is unearned scope until a real
  request-meter pressure exists.
- **Broader per-issuer / NPORT-P holdings coverage** — a rate-widening (existence-proof → representative
  rate), not an unblock. Stays deferred per state rev 5.
- **Dispersion PIT backtest (milestone 3b)** — data-availability-gated (survivorship-clean historical
  holdings + delisted prices). Live shadow burn-in stands in meanwhile; 3b is not a blocker.
- **§10 — the email sender** — the next slice after this one, not part of it.

## 7. Handoff / sequence

- **Desktop + cold Science QA.** This is the heavier vertical (new ingest surface, a spawner that must be
  *proven* to fire on real data, a live `pros run` to verify) — batch it for a desktop session where Science
  mounts and runs it cold, not a fragmented remote one. Branch off `main`, PR, cold review before merge (the
  `CLAUDE.md` branch rule, PR #17).
- **Sequence:** §9e (this) → §10 (sender; also closes the lapse-risk dead-man in §1) → M6 → M7 (scheduling,
  where the burn-in clock runs on a real cadence).
- **"Done" for this slice is "fires on real seed data + burn-in clock started + suite green," not
  "validated."** The burn-in is a *calibration* window (the live firing rate, for the promote-to-paging
  decision), not a falsification window — see the design-thread discussion of the same date (90 days is the
  nuisance/calibration line; edge falsification is a multi-year, event-gated accumulation). This slice only
  starts the instrument that will feed that.
