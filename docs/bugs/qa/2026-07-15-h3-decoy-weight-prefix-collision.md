# H3-DECOY — prefix header matcher silently reads a decoy 'weight*' column

**Severity:** LOW (latent — not reproducible on the current equity-ETF substrate; bites when the universe extends to bond funds)
**Verdict:** NEW / CONFIRMED on real substrate (found in the cold read of PR #67)
**File:** `prospector/ingest/holdings.py` — `_col` (lines ~146-156), used to locate the weight column
**Class:** loud→silent severity inversion — the exact class PR #67's own tier4-sweep build-note ground-rule names as its one design line

## What
PR #67's H3 fix changed `_col` to match header columns by prefix (`startswith`) and **first-match-wins**.
A decoy column whose name merely starts with "weight" — e.g. `Weighted Average Life`, a standard column
on SPDR fixed-income (bond ETF) holdings files — placed before the real `Weight` column is read AS the
weight, silently, with no fault, then passes the H1 weight-sum sanity band. The shipped mandatory-negative
test only covers a fully-alien header, not a prefix-decoy collision.

## Reproduction (branch tier4-sweep @ e0739956)
```
header: Name,Weighted Average Life,Weight,Sector   rows: ACME,55,60,…  BETA,45,40,…
  main (exact membership): weights [0.60, 0.40]  — the real Weight column
  tier4-sweep (prefix):    weights [0.55, 0.45]  — the DECOY column, NO fault
```
Latent: the real TEKX equity-ETF fixture has `Weight` as its only weight-prefixed column, so the current
universe never triggers it.

## Deliverables in this branch (Option 2 — QA proposes, implementer applies)
- **RED-first test:** `tests/test_holdings_weight_decoy.py` — 1 `@pytest.mark.xfail(strict=True)` test driving
  the REAL `parse_spdr_holdings` with a decoy-before-real header on a real-shaped body, plus an
  over-correction guard (single `Weight` and the `Weight (%)` H3 variant both still parse). Asserts
  BEHAVIOUR (a decoy must not be silently used; ambiguity may fault loud), not a specific implementation.
  - RED against `tier4-sweep`: 1 xfailed (bug reproduced).
  - GREEN against the reference fix: 1 XPASS(strict). Full suite 630 passed / 1 skip / 2 xfail on the fix tree.
- **Reference fix:** `docs/notes/h3_decoy_fix.diff` — `_col` prefers an EXACT match over a prefix match,
  and faults loud when >1 weight-prefixed column is present with no exact `Weight` (fail-loud, not silent —
  the same no-inversion rule the prefix match itself protects). 1 source file.

## SEQUENCING (important)
The patch targets the H3 code, which lives on `tier4-sweep`, NOT on main.
- `git apply --check` is **clean on `tier4-sweep`**.
- It **does not apply on main** (main has no H3 fix yet).
So this is a **follow-on to PR #67**: fold it into #67 before merge, or apply to main after #67 lands.

## Implementer handoff (xfail-strict protocol)
Apply `h3_decoy_fix.diff`, then remove the `xfail(strict=True)` marker from the test — it reads as
XPASS(strict) ("failed") until removed, which is the landed signal.

See `docs/notes/2026-07-15-pr67-pr66-cold-review_qa.md` for the full review (all 11 #67 claims + all 6 #66
checks CONFIRMED-CLOSED, plus the two LOW #66 findings LOCK-TEST-TAUT and DEPLOY-OVERLAY-DRIFT).
