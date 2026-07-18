# Mandate faults — noise-cut landed, and what's next (2026-07-18)

*For async review. This PR does the **upstream noise-cut** you approved; the remaining items are listed so
you can pick the next one from the phone. The diagnosis it's built on is captured in the decision record
`docs/decisions/2026-07-18-mandate-supplement-not-a-prospectus.md`.*

## What this PR does

The ~30 `strategy-section extraction unreliable` advisories per run were **11 documents**, ~⅔ of them **497
stickers / SAI filings** that have no strategy section and were mistaken for prospectuses. The fix classifies
the document (`is_prospectus_supplement`) and **skips a supplement/SAI current (no fault) and refuses to diff
against a supplement prior (baseline)** — cutting **~26 of 30**, leaving the ~4 real parser gaps.

- **Verified against all 30 real failing blobs** (20 stickers + 2 SAI caught, 8 full left, zero misses / no
  false positives) — grounded in filed reality, not imagined HTML.
- **+5 tests** (classifier + the two sensor behaviors); **hermetic suite green (658 passed)**.
- CONTRACT boundary held: a real *full* prospectus we can't parse **still** faults; no significance judgment.

## Next steps — pick one (roughly in order)

1. **The ~4 real parser gaps (workstream 2).** Each narrow, real-fixture-backed, anchored (don't loosen the
   heading match into prose — that re-creates the false-extraction below):
   - **Split heading** — `Principal` `\n` `Investment Strategies…` (a source-embedded newline splits the
     heading; Clough 015168): de-tokenize in `html_to_text`.
   - **TOC first-match** — the Table-of-Contents entry matches first, so the "section" is a page number
     (015023): continue-scan past a trivially-short first hit.
   - **Heading variants** — `"Investment Strategies of the Fund"` (015093), J.P. Morgan's Q&A
     `"main investment strategies"`: add the *observed* variants as whole-line headings.

2. **The false-extraction bug (Case D) — a correctness item, not just noise.** For a J.P. Morgan fund the
   `startswith("investment objective")` fallback matched a **body-prose fragment** and returned
   `reliable: True` on garbage — which could fire a **spurious `mandate.changed`** onto a live lead. It only
   didn't because its prior also faulted. Fix: the fallback must match a *heading*, never a prose substring.
   **Worth a `docs/bugs/INDEX.md` row.**

3. **Diff annuals across intervening supplements (optional improvement).** The prior-resolution still hands
   the sensor the newest frozen accession; when that's a sticker we baseline rather than reach back to the
   prior *full* prospectus. Not a regression (today it faults there) — an improvement: make
   `_last_frozen_prospectus` return the newest full prospectus.

4. **Test hermeticity (small, found in passing).** The dev checkout's machine-local
   `config/prospector.local.yaml` overlay (added for the deploy lock-path) leaks into local test runs — it
   fails `test_backup.py::…no_targets_configured` because the overlay injects `backup.targets`. **CI is
   clean** (the overlay is gitignored), but a local `uv run pytest` isn't hermetic. Fix: tests that need the
   tracked defaults should load an isolated config, not the real `config/prospector.yaml` (which merges the
   overlay). One-line-ish, isolates the suite from machine config.

## How to review this PR

- The classifier: `prospector/ingest/prospectus.py::is_prospectus_supplement` (+ the docstring).
- The wiring: `prospector/sensors/mandate.py::scan` (classify current → skip; classify prior → baseline).
- The real fixtures: `tests/fixtures/prospectus/497_supplement_sticker.html`, `…/497_sai.html` (provenance
  headers).
- The tests: `tests/test_mandate_sensor.py` (last 4 functions).
- The ruling: `docs/decisions/2026-07-18-mandate-supplement-not-a-prospectus.md`.
