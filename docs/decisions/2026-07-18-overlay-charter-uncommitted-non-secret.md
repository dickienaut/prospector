# The local overlay's charter is "uncommitted, non-secret config" — not "per-machine paths"

**Date:** 2026-07-18
**Status:** ratified (design thread).
**Supersedes (broadens):** the charter clause of `docs/decisions/2026-07-12-local-config-overlay.md` — that
record stays as the immutable fossil; this one broadens the boundary it drew. Surfaced by the M6 capture
arming (`docs/notes/2026-07-18-capture-armed.md`), which placed a non-path operational value in the overlay.

## The grounding fact (checked, not asserted)

`config.changed` hashes the **effective merged config**: `load_config` computes the sha256 *after* the
deep-merge, so the hash covers the overlay too (the `prospector/config.py` module docstring and the 2026-07-12
record both confirm it). So the arming budget already emitted a `config.changed` and is recorded correctly.
**This is a charter question, not a behavior bug** — the mechanism was already right.

## The decision

The overlay was defined as *machine-local **paths*** — values that "genuinely differ per machine." The M6
arming budget (`capture.monthly_budget_usd: 25`) does **not** fit that: it is the *same policy on any
machine*. Yet it belongs in the overlay. Broaden the charter to the property that actually governs it:

**The overlay's boundary is *uncommitted, non-secret config* — not *per-machine*.** State it as a **boundary,
not a list** (a list goes stale the next time a fourth value lands — the doc-drift shape we kill everywhere
else). Three homes, decided by two questions — *is it a secret?* and *must it be committed?*:

- **Secrets that must never fossilize → `.env`.** `ANTHROPIC_API_KEY`, `TIINGO_API_TOKEN`,
  `PROSPECTOR_SMTP_PASSWORD`. The never-record home.
- **Uncommitted, non-secret config → `config/prospector.local.yaml`.** Set locally, not committed, and it
  *should* fossilize when it changes (via the merged hash). Two kinds qualify: **per-machine paths**
  (`store.root`, `backup.targets` — uncommitted *because they differ per machine*) and **owner operational
  overrides** (the arming `capture.monthly_budget_usd` — uncommitted *because owner-arming*). Different reason,
  same home.
- **Shared committed contract → tracked `config/prospector.yaml`.** DEFAULTs, the ships-disabled
  `capture.monthly_budget_usd: null` the overlay overrides, and deployment identity like `edgar.user_agent`.

## Why the budget can't just join the API key in `.env`

`.env` is the *never-fossilize* home. But "the owner set the cap to $25" is **honest record** — it should
appear in the `config.changed` fossil, which the overlay path gives it and `.env` would not. The
secret/non-secret **fossilization** line beats the "keep the arming levers together" intuition: the key stays
in `.env` (a secret, never recorded); the budget goes in the overlay (non-secret, recorded). And a live budget
in *tracked* config is doubly wrong — it would ship capture **armed** (breaking the ships-disabled §6
contract) and put a private spend policy in git.

## Side effect — CAP-USD closes

The ~$0.01 live spend of the item-14 armed call empirically confirms `unit_price_usd = 0.01`, so the USD cap
now has a real, verified non-zero price to enforce against instead of silently no-op'ing at zero.

## Change

The live charter statement is `prospector/config.py`'s module docstring; it is amended to state the broadened
boundary in the same PR. This record is the design-thread trace.
