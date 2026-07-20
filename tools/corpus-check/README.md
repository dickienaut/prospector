# `tools/corpus-check/` — did my parser change touch anything I wasn't looking at?

A build-seat instrument. Re-runs prospectus extraction over **every frozen blob in the store** and
diffs the outcome, document by document, against a baseline git ref.

## Why it exists

On 2026-07-19 a mandate-extraction fix was verified against the four filings it targeted — all four
fixed, tests green. Run against the whole frozen corpus, the same change also reclassified **11
genuine 497 stickers** as full prospectuses, which would have re-created precisely the advisory noise
the 2026-07-18 supplement cut had removed.

The break was **nowhere near the failing filings**. It was in the population that was already passing.

> **A fix verified only on the documents it targeted is verified on a biased sample.**

That check was a throwaway script. This is it, kept.
(`docs/decisions/2026-07-19-mandate-extraction-structural-lines.md`; register rows
`MANDATE-DECL-BAR`, `MANDATE-SOURCE-NEWLINES`, `MANDATE-TOC-SHADOW`.)

## Run it

```sh
uv run python tools/corpus-check/extraction_corpus_check.py                  # vs origin/main
uv run python tools/corpus-check/extraction_corpus_check.py --baseline HEAD~1
uv run python tools/corpus-check/extraction_corpus_check.py --verbose --json report.json
```

Takes ~2 minutes on ~150 blobs. `--store` if the store isn't at `~/prospector/store` or `./store`;
`--strict` exits 1 on any regression or classification flip.

**Run it on every change to `prospector/ingest/prospectus.py`.** That is the whole discipline.

**Read section 6 before believing sections 1–5.** They answer different questions, and only section 6
answers the one that matters: *what would the sensor emit?*

## What it reports, and why each section is there

| # | Section | Why |
|---|---------|-----|
| 1 | **Supplement/SAI classification flips** | A document changing *kind*. This is the one that caught the 11-sticker regression — and note it is a category the change wasn't supposed to touch **at all**, which is exactly why it gets reported rather than assumed. Expect 0 unless you changed the classifier. |
| 2 | **Reliability matrix + regressions** | What stopped extracting. **Read every one** — sometimes a regression is the fix (a false-reliable extraction of the wrong text that correctly begins to fault instead). That call is a human's; the script refuses to make it. |
| 3 | **Newly reliable** | What the change bought, per document. |
| 4 | **Section text changed** | Reliable both ways but the extracted section *moved* — the same filing would now diff differently. Often the most interesting section. |
| 5 | **Remaining unreliable, by reason** | The residual work grouped by **shape**, not row count. |
| 6 | **Pairs — what the sensor would actually do** | Sections 1–5 judge documents *one at a time*; the sensor diffs a **pair**. A change can improve every document individually and still make the sensor emit garbage. On 2026-07-19 a candidate fix scored "6 newly reliable, 0 regressions, 0 flips" above and would have emitted **3 false `mandate.changed`** — the two accessions were different funds' prospectuses (B1). Also flags the structural tell: **an accession frozen under more than one series**. |

## Why a tool and not a test

The suite is hermetic and offline: repo fixtures, in CI, no store. This reads the **live frozen
store**, which is machine-local, unbounded, and not in the repo — so it cannot be a test. They are
complements: **fixtures pin known cases forever; this asks what happened to everything else.**

## What it does not do

- **No network.** It reads blobs already frozen under `ingest/prospectus/`. It never fetches.
- **No writes, no events, nothing into the record.** Read bytes → re-derive in memory → print.
- **Not a `pros` subcommand, deliberately.** The CLI is the operator's product surface; this is a
  build-seat instrument. (It also computes nothing new, so it is not a run-now surface either way.)

Extraction being a pure function of frozen bytes is what makes this possible at all — a later,
better extractor re-reads old filings with no stored staleness (`ProspectusIngest.load_frozen`).

## Self-check

It reproduces the finding it was built from. Against the pre-fix commit:

```sh
uv run python tools/corpus-check/extraction_corpus_check.py --baseline 5e6da15
#  1 classification flip (the correct Sprott catch)
#  reliability 41/68 -> 61/68 · 21 newly reliable
#  1 "regression" — the false-reliable `principal investment strategy to do so`
#    extraction that correctly began to fault
```

Those are the numbers recorded in the decision record. If a future change to this harness stops
reproducing them, the harness broke, not the extractor.
