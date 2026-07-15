# `capture.query_drift` stays BYTE-EXACT — prove byte-exactness, never normalize the comparison

*Decision record, 2026-07-14. Ratifies the design-thread ruling on the M6 capture-review finding
**CAP-DRIFT** (`docs/notes/m6_capture_review_qa.md`). Governing: spec §6 (discourse capture — "no LLM text
as data" / deterministic templating), §10 (fault taxonomy / cry-wolf). Fix site:
`prospector/runner/runner.py::_run_capture` (the `capture.query_drift` guard). This record settles the
DESIGN; it changes no comparison logic — the guard was already byte-exact and stays that way.*

## Context — the finding and its fork

`capture.query_drift` is the §6 no-LLM-authorship guard: for each capture, our deterministically-templated
query is embedded as instruction text in the prompt, and the guard faults **loud** if the query the model
actually placed on the `web_search` tool call (`query_issued`) differs from ours — the tripwire for "the
model silently rewrote our search." The comparison is byte-exact (`issued != query`, no normalization).

QA flagged the risk (CAP-DRIFT, HIGH): a live model is free to *cosmetically normalize* the query it echoes
— trim trailing whitespace, collapse doubled spaces, fold smart quotes, re-case. Any one of those makes
`issued != query` true on **every** capture, so `query_drift` fires every tick a capture runs — the GPWS
"cried wolf" failure, and on the exact determinism guard whose job is to be trusted. QA offered a fork:
**(a)** normalize both sides before comparing (`issued.strip() != query.strip()`), or **(b)** prove
byte-exactness holds against the live API first, before shipping the strict `!=`.

## Decision — (b): prove byte-exactness first; do NOT normalize

**Normalizing is discarding evidence before you've read it.** The premise of the capture layer is
deterministic templating: identical lead metadata *must* produce identical query bytes, because that
determinism is what makes the archive trustworthy and thaw-backward-able. So the contract to assert is
**raw byte-exactness**, not equal-after-cleanup.

**Why order matters (the trap in (a)).** A normalize-then-compare that passes proves only the *weaker*
claim ("equal after scrubbing") and **masks** whether the real claim holds — worse, it stays green even if
a genuine nondeterminism creeps in later (a dict/set iteration change, a timestamp leaking into a query),
as long as normalization happens to paper over it. That is green-on-synthetic again: the test passes for
the wrong reason, against a scrubbed input rather than the real one — the exact failure class this project
has been bitten by repeatedly. So: **assert byte-exactness against raw output. If it holds, the strong
property is proven and there is nothing to normalize. If it fails, the failure is telling you determinism
is actually broken — and the fix is to make the query construction deterministic (find the ordering leak
and close it), not to normalize the comparison until the symptom disappears.** Normalization treats the
alarm; determinism fixes the fault.

## What this means concretely (two halves — keep them separate)

1. **Our side — the templating — is proven deterministic, offline, RAW.** `capture.build_queries` is
   ordered, order-preserving-deduped, carries no timestamp/randomness; `test_build_queries_deterministic_
   and_ordered` asserts identical metadata → byte-identical query bytes with **no normalization**. That is
   the "prove byte-exactness first" deliverable, and it passes — the strong property holds on our side.
2. **The model-echo side — does a LIVE model return our query byte-for-byte — cannot be proven offline**
   (capture ships **disabled**; there is no armed API in the test env). So the guard **stays byte-exact**,
   and its production safety is gated on **one real armed call comparing bytes, performed BEFORE capture is
   armed.** If that call shows the model normalizes benignly, that is a **finding** — and only then, if the
   source is genuine, understood, and unavoidable, is a **minimal, named** normalization introduced for
   *that specific source*, documented as to why, with the byte-exact assertion still covering everything
   else. Needing it is a finding, never a convenience — never a silent `.strip()`.

## Guardrail in code (so the ruling can't drift back to normalize)

- The `query_drift` guard keeps `issued != query` (no `.strip()`/case/quote-fold), with an inline comment
  citing this record and the live-arming gate.
- `test_query_drift_is_byte_exact_a_cosmetic_normalization_still_faults` locks it: a provider that echoes a
  cosmetically-normalized query (a trailing space) STILL trips `query_drift`. The test goes RED the moment
  someone adds normalization — forcing any future softening to be a deliberate, test-updating, documented
  act (per the ruling), not a silent convenience.

## Status / residual (register: CAP-DRIFT → 🟡 ratified-residual)

The design is settled and our side is locked, but the model-echo cry-wolf risk is **not** closed by code —
it is deferred to the live-arming verification. CAP-DRIFT is therefore **🟡 ratified-residual**, not ✅: the
gate is "one armed byte-compare before capture is armed," and today the failure mode is silent (capture is
off). **CAP-USD** (the monthly-USD cap silently unenforced when `unit_price_usd` is 0) rides the same
pre-arming slice and is closed there (a loud guard). Both were the last two open items from the M6 capture
review.

## Scope / what did NOT change

No change to `build_queries`, the guard's comparison, or the capture wall. This record + the inline comment
+ the lock test are the deliverable; the comparison logic is unchanged because it was already correct.
