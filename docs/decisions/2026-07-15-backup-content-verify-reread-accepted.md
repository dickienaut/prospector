# BK-2's content re-read is accepted — correctness over cost at current scale (BK-READ-01)

*Decision record, 2026-07-15. Ratifies the design-thread ruling on **BK-READ-01**, the cost residual BK-2's
fix introduced. Sits under the §7 store-durability line; sibling of
`docs/decisions/2026-07-14-backup-health-one-fault-channel.md`. Ridealong of the Tier-4 sweep.*

## Context

BK-2 fixed a real aliasing bug: a same-size in-place rewrite (an `ingest/` same-day re-pull, a `registry/`
identity update) landing inside the exFAT mtime window read as "unchanged" and left a **permanently-stale
copy** on the HDD. The fix content-verifies the rewritten-in-place trees (byte-compare when size+mtime would
say "skip"). The residual — **BK-READ-01** — is that this content-verify **re-reads every unchanged
rewritten-in-place file every run**: destination-HDD read amplification that grows with the store's mutable
subset. Correctness is intact; this is a *cost* regression.

## The decision — accept and document

**Accept the re-read; add no hash-cache or new mechanism now.** Correctness beats cost at the current scale:

- The content-verify runs **post-tick**, when nothing waits on it (the tick has already recorded + pushed) —
  seconds on a single-digit-GB store.
- It is bounded to the **rewritten-in-place subset** (`ingest/` + `registry/`), never the append-only bulk
  (`events/` + `snapshots/`, which keep the cheap size+mtime skip). The amplification is over the small
  mutable tail, not the whole store.
- A hash-cache (persist per-file digests, compare instead of re-read) is **real new state to keep coherent** —
  the wrong trade for a post-tick cost that is currently seconds.

## Revisit trigger (named, so the acceptance is not open-ended)

Re-open this — build the hash-cache or a cheaper verify — when **either**: backup wall-time exceeds ~a
minute, **or** store growth makes the content-verify pass minutes-long. Measure, don't guess.

## Override condition

If QA's **#64** reproduction shows the amplification is **materially worse than seconds today** (not merely at
some future scale), this comes **back to the design thread immediately** rather than riding the acceptance —
measurement beats the ruling. The register status records exactly this posture: **🟡 ratified-residual**, not
closed.
