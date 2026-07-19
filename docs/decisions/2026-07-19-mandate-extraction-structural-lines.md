# Mandate extraction: lines come from block structure, never from source whitespace (§4d)

*2026-07-19 · build seat · closes workstream 2 of `../notes/2026-07-18-mandate-noise-cut-next-steps.md`
(items 1a "split heading" and 1b "TOC first-match"; item 1c dissolves — see below).*

## What prompted it

The 2026-07-19 scheduled run recorded 7 `strategy-section extraction unreliable` review-advisories.
These are the residual "~4 real parser gaps" the 2026-07-18 supplement noise-cut deliberately left
standing. Diagnosis ran **offline against the frozen blobs** (`ingest/prospectus/`), which is the whole
point of freezing raw HTML per accession: the extractor is a pure function of bytes we already hold, so
a parser question is answerable without touching the network.

## Root cause — one bug, two symptoms

`html_to_text` derived line breaks from **two** sources: every bs4 tag boundary (`get_text(separator=
"\n")`) **and** every newline the source bytes happened to contain (it collapsed `[^\S\n]+`, deliberately
preserving `\n`). Both are wrong. **A newline inside HTML text is insignificant whitespace — it renders
as a space, not a break.** Only block-level tags (and `<br>`) end a line.

Filers hard-wrap their markup, so the heading arrives as:

```html
<b><ix:nonNumeric name="oef:StrategyHeading">Principal
Investment Strategies of the Fund</ix:nonNumeric></b>
```

which the old code turned into two lines — `Principal` and `Investment Strategies of the Fund` — and the
phrase was never visible on any single line. Hence **symptom 1: "strategy heading not found"** on filings
that plainly carry the section. (This also dissolves item 1c of the next-steps note: `"Investment
Strategies of the Fund"` is not a heading *variant* needing a new pattern, it is the **tail of a split
heading**. Adding it as a pattern would have been a fix aimed at a symptom, and it would have loosened
the heading match toward prose — the thing item 1's own warning says not to do.)

**Symptom 2 is the dangerous one.** The same splitting chopped *prose* into heading-shaped fragments. In
one real filing a risk sentence yielded the standalone line `principal investment strategy to do so`,
which **passed** the `strict=True` prose guard — its tail opens with the connective "to" — and returned
`reliable: True` with **risk text as the strategy section**. That is the MANDATE-PROSE-HEADING class
(`../bugs/INDEX.md`) still live through a different door: not a bad pattern, a bad line. Had that fund's
next filing reworded the surrounding risk prose, the sensor would have emitted a **spurious
`mandate.changed`**. The guard was sound; it was being fed fragments.

**Symptom 3 (independent, same file): a table of contents shadowed the real section.** `extract_mandate`
took the FIRST heading-shaped line and failed on it. A TOC lists `PRINCIPAL INVESTMENT STRATEGY`, then
the page number, then the next TOC entry — which is a stop heading. So the "section" was the string `2`,
too short, and the filing was reported unreliable while its real section sat 140 lines below.

## The rulings

1. **Line breaks come from block structure only.** `html_to_text` marks block tags, collapses *all*
   source whitespace (including newlines), and splits on the structural marks. Inline tags join with a
   space (`Principal` + `Investment` must not become `PrincipalInvestment`).
2. **A heading candidate is the heading only if it bounds a section.** `extract_mandate` continue-scans
   past a candidate that yields a too-short / unbounded extraction, preserving the existing pattern
   priority (strategies before objective). This is **structure, not meaning**: it asks *"did this heading
   bound a section?"*, never *"is this the important one."* When no candidate qualifies the filing is
   **still unreliable** and still faults — the reason reported is the **first** candidate's, since that
   is what a human opening the filing sees first.
3. **The diff summary's unit is a sentence, not a line.** Once a paragraph is one structural line, a
   unified *line*-diff reports the whole paragraph as changed and the 800-char bound truncates away the
   words that actually moved. Sentence units restore granularity and, unlike the filer's line wrapping,
   are stable across re-files. Caught by an existing test, not by inspection.
4. **Declaration matching gets its own, looser line bar (240 chars; headings stay at 80).** Found by the
   corpus check, not by reading the code — see below.

None of this changes the §4d CONTRACT: extraction-unreliable still means *flag for manual review, never
diff*; the fault vocabulary is unchanged; nothing acquired an opinion about whether a change is
*meaningful*. bs4 still owns structure, this module still owns which-section-and-did-it-move, the human
still owns significance.

## The near-regression the corpus check caught

Verification ran the new code against **all 148 frozen prospectus blobs** and diffed the outcome per
document against `origin/main`. It reported **12 supplement/SAI classification flips** — a category the
change was not supposed to touch at all.

Eleven were a **real regression I had introduced**. A sticker's self-declaration is a single *long* line
— "Supplement dated July 15, 2026 to the Pictet AI & Automation ETF's and Pictet Cleaner Planet ETF's
currently effective Prospectus…" is **98 characters**. The old splitter only ever kept it under the
80-char bar by chopping it mid-phrase; reflowing it correctly pushed it over, so `is_prospectus_
supplement` stopped recognising 11 genuine 497 stickers and would have started faulting on them —
**re-creating precisely the advisory noise the 2026-07-18 cut removed.** Fixed by giving declaration
mode its own bar (`_DECLARATION_MAX_CHARS = 240`); it is safe because declaration mode is **anchored at
the start of the line**, so a full prospectus that merely *mentions* a supplement mid-sentence still
cannot match. Both halves are pinned by tests, one on the real Pictet filing.

The twelfth flip was a **correct new catch**: a Sprott 497 whose declaration the old splitter had broken
across lines is now recognised as the sticker it is, and stops faulting.

The lesson is the general one this repo keeps re-learning: **a fix verified only on the documents it was
aimed at is verified on a biased sample.** The regression was nowhere near the failing filings; it lived
in the population that was already passing. Checking the whole frozen corpus — cheap, because the
substrate is frozen — is what made an invisible fail-silent regression visible.

## Result (all 148 frozen blobs, measured)

| | before | after |
|---|---|---|
| reliable extractions (non-supplement blobs) | 41 / 68 | **61 / 68** |
| 2026-07-19 run's advisories | 7 | **3** |

The 3 residual advisories are all one J.P. Morgan document shape (a combined Part I/Part II filing whose
only occurrence of the phrase is in body prose — it genuinely carries no strategy heading), plus one
filing that now **honestly** faults where it previously returned a false-reliable extraction of risk
prose (symptom 2 above) — a case where "one fewer green" is the correct outcome.

## Anti-fitting

The residual faults must **not** motivate loosening the heading match toward prose, lowering
`min_section_chars`, or adding per-issuer special cases. A filing we cannot reliably parse faults for
human review; that is the designed behaviour, not a defect to tune away. Same discipline as
`2026-07-04-real-holdings-xlsx-and-blank-sectors.md`.

## Fixtures

Three recorded-real trimmed excerpts, each with a provenance header and each verified to reproduce the
**pre-fix** failure and the **post-fix** success (a trim that accidentally fixed the document would be a
fixture that tests nothing):
`497_split_heading_tema.html`, `497_toc_shadows_section_vpff.html`,
`497_supplement_long_declaration_pictet.html`.
