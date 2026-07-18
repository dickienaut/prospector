# A 497 supplement / SAI is not a full prospectus — the mandate-diff skips it, never faults it

**Date:** 2026-07-18
**Status:** ratified (design thread — owner approved the upstream noise-cut).
**Touches:** the §4d mandate sensor's disposition (CONTRACT-adjacent), inside the existing boundary.

## The finding

The mandate sensor was emitting ~30 `strategy-section extraction unreliable` review-advisory faults per
run. A primary-source diagnosis (running the real extractor against the **frozen blobs of every faulting
filing**) found the 30 were **11 distinct documents** (multi-fund filings fault once per series), and split
three ways:

- **~22/30 — genuinely unparseable, *correctly* faulted.** These are **Form 497 "stickers"** (one-page
  supplements) and **SAI** (Statement of Additional Information) filings that carry **no
  principal-investment-strategy section at all.** The detector upstream (`edgar.latest_prospectus`) treats
  *any* `485BPOS/485APOS/497/N-1A` as "the latest prospectus," and **497 covers stickers and SAI as well as
  full prospectuses** — so a sticker was handed to the diff as a prospectus. The parser was right to refuse;
  the category error is upstream.
- **~8/30 — genuine parser gaps** (a real strategy section the parser misses) — deferred to a follow-up.
- **1 live *false* extraction** (a body-prose fallback match returning `reliable: True` on garbage) —
  deferred, tracked separately.

## The decision

**A 497 supplement (sticker) or an SAI is not a full prospectus, so it is not a mandate-diff event.** The
sensor classifies the fetched document and:

- **current is a supplement/SAI → skip** (`action: "supplement"`), no review-advisory fault. The standing
  prospectus remains the fund's mandate; a supplement is not a new prospectus to diff.
- **prior on file is a supplement/SAI → baseline** (don't diff a real full prospectus *against* a sticker —
  that mislabels the real filing extraction-unreliable; the prior-blob contamination).

This cuts ~26 of the 30 faults (22 supplement/SAI currents + ~4 sticker-as-prior contamination), leaving the
~4 real parser gaps for the follow-up.

## The signal — anchored, structure-only, grounded in filed reality

`is_prospectus_supplement(body)` (in `ingest/prospectus.py`): a filing **declares itself** — a sticker opens
*"Supplement dated…/Supplement to…"*, an SAI titles itself *"Statement of Additional Information"*. The check
is the same three-owner boundary as `extract_mandate`: **structure only, anchored to a short heading-shaped
line** (the SAI title in the opening window; the sticker phrases, which do not appear as a heading in a full
prospectus, anywhere), **never a substring buried in prose** — so a full prospectus that merely mentions
"supplement" or references its SAI is not tripped. **Verified against every one of the 30 real failing blobs**:
20 stickers + 2 SAI caught, 8 full prospectuses left, zero small-doc misses, no huge-doc false positives — not
designed against imagined HTML (the convergent-priors / fixture-provenance discipline). Fixtures are
**recorded-real excerpts** of the actual filings (accessions 0001193125-26-307874 sticker, 0000894189-26-021151
SAI), with provenance headers.

## The CONTRACT boundary held

- **Extraction-unreliable → fault STAYS** for a real *full* prospectus we genuinely cannot parse (the ~8 gaps
  still fault — a false `mandate.changed` is still worse than a missed one). Only documents that were never
  full prospectuses stop faulting.
- **No significance judgment added.** The classifier decides only *"is this a full prospectus"* — which
  section, never whether a change matters (that stays the human's verdict).

## What this deliberately does NOT do (deferred, see the next-steps note)

- **The ~8 real parser gaps** (split heading, TOC first-match, heading variants) — workstream 2.
- **The false-extraction bug** (a body-prose fallback returning `reliable: True`) — a bug-register row + fix.
- **Parse stickers for strategy amendments** — a sticker that *amends* the strategy is not diffed. But the
  current design never diffed stickers (it faulted on them), so this removes a false fault, not real coverage;
  whether to diff supplement deltas is a separate v-next question.
- **Diff annuals *across* intervening supplements** — the prior-resolution still hands the sensor the most
  recent frozen accession; when that is a sticker we baseline rather than reach back to the prior full
  prospectus. Not a regression (today it faults on the sticker prior); an improvement for a follow-up.
