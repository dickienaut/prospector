# Generous dispersion payload + the proto-cluster layer (rev 8)

**Status:** design-thread guidance, ratified 2026-07-03 (spec rev 8, §4b + Appendix B). Records the
one CONTRACT change rev 8 makes to the current build — the **generous `dispersion.tick` payload** —
and why the **proto-cluster / pseudo-ETF** idea it serves is deliberately **v2, not v1**. This is a
scope + payload-richness decision; no sensor/gate behavior changed.

## The idea being banked (Appendix B, v2)

ETFs are the corpus, but they are also its ceiling: the tool can only see a thesis someone has
already *packaged*. The constituent layer breaks the ceiling — a thesis no one has packaged is still
visible in the substrate as a **cluster of names co-moving across the existing sector boundaries** (a
"pseudo-ETF"). That is the earliest possible T0 for the cross-stream lag: names cohere before the
linkage is even articulated, let alone packaged. The 2023 nuclear+AI cluster, before NUKZ existed, is
the worked example.

Three things make this an *extension* of the existing design, not a new project — and each is a hard
constraint on how it may ever be built:

- **Price-only, not keywords.** Emergent co-movement is correlation one level down; it needs no
  language model. The layer is found by constituent price co-movement, **not** by keyword/NLP mining
  of discourse or prospectuses. This is what keeps it clear of the "no LLM text as data" and
  "no tag-minting gate" contracts (§0 OUT). (The design-thread's verbal "keywords we are unearthing"
  framing is *not* the built form — the built form is deterministic correlation.)
- **The canary is a cluster, never a single name — and never the trade.** A single stock moves for a
  thousand idiosyncratic reasons; the signal is the coherent *cross-boundary* co-movement of a set.
  Single-name granularity is exactly where over-trading **and** concentration risk both peak, so for a
  survivability-first 17-year owner the correct response to a forming pre-ETF thesis is to **watch it
  and buy the diversified ETF when it packages** — never a concentrated single-name bet whose
  "early-access premium" is just concentration risk repriced. The cluster tells you where to look; it
  is never itself the position. (The owner's standing "not buying individual names" is this
  constraint, not a hedge.) Same firewall as the reading-list wall, at its sharpest edge.
- **Scope-pruned and box-B-dispositioned.** Never all-pairs across the universe (~125k constituent
  pairs = instant oracle death); the cheap 11-basket dispersion sensor *aims* the expensive
  constituent analysis — you drop to single-name detail only inside a basket already flagged. And an
  emergent cluster is real co-movement whose on-thesis-vs-macro status is the same `yes / watch /
  off-thesis-real / noise` call (§5) as everywhere else.

## Why it is v2, not v1

Historical validation of this layer inherits — and *worsens* — the delisted-constituent problem that
already defers the dispersion PIT backtest (§3b): the acquired winners are precisely the small
companies bought *because* their thesis turned out real, so they vanish from any survivor set,
**biasing a backtest against the very signals the layer exists to detect.** Live-forward watching is
clean; backtesting is not, and must not be trusted until that data question is solved. The
interpretation also belongs downstream of a *calibrated* dispersion sensor — building it on an
uncalibrated pre-filter would be premature. So the interpretation waits.

## The one v1 action: capture the substrate richly now

This is the **capture-now-interpret-later** forced ordering again (the shape that governs the launch
sensor, the discourse stream, and the stress gate). The v2 layer must **thaw backward** over
dispersion history — and **you cannot backfill a payload you did not capture** (append-only
forced-ordering, §5). So the `dispersion.tick` payload is amended from scalar-Q-only to **generous
(CONTRACT, §4b):**

- full **constituent membership**, each name's **sub-cluster assignment**;
- the **cluster centroids**;
- the **constituent correlation structure** (within/cross-cluster summaries at minimum; the pairwise
  matrix or its top structure where volume allows).

A scalar-only tick would permanently blind the future layer to *which* names formed the proto-cluster
and *how* they cohered. The substrate then accrues from the moment dispersion goes live, with zero
new capture — the v2 layer is a pure re-read of history, buildable "against the day it is earned."

## The forced timing (why land this before dispersion is built)

Rev 8's only code consequence constrains the dispersion sensor — **which does not exist yet**
(deferred M4-remaining, gated on holdings ingest). Landing the generous-payload CONTRACT *now* means
the sensor is built generous from its **first tick**. Had dispersion shipped scalar-only first, this
amendment would arrive too late to bank the early substrate cleanly. This is the same reason the
launch sensor's recording half had to run before its corroboration half.

## What this changes in the build

- **`dispersion.tick` payload** ships generous from day one (see `sensors/dispersion.py`, the
  §4b build). A test asserts the membership + sub-cluster + correlation structure are present — the
  CONTRACT guard, not just the scalar Q.
- **A config knob** governs how much correlation structure to persist
  (`dispersion.correlation_detail`, DEFAULT `full` during the shadow burn-in — see
  `docs/decisions/2026-07-03-dispersion-shadow-first.md`).
- **Nothing else.** The proto-cluster interpretation is not built. No new event type, no new surface,
  no envelope/fold change — the generous payload rides inside the open-vocabulary `payload` object.
