# Mandate-diff: the targeted strategy-section diff, and a deliberate dependency

**Status:** design-thread guidance, ratified 2026-07-03; built as the mandate-diff slice
(`ingest/prospectus.py`, `sensors/mandate.py`, `EdgarClient.filing_text`, `StoreLayout.prospectus_path`).
Records the spine (target the strategy section, not the whole filing), the corroboration-not-claim
framing, the extraction-unreliable fallback, the bs4 structure/meaning/significance boundary, and the
one deliberate dependency this project has added. **Folds into spec rev10** (as the launch honest-test
boundary became rev7). This is the second half of §4d, the deferred slice whose named unblock was
"EDGAR prospectus-*text* fetch + `ingest/prospectus/` storage."

Why it matters: a fund quietly rewriting what it's *about* is exactly how a position bought for one
thesis becomes something else underneath a 17-year holder. Catching the issuer moving its own boundary
is worth getting right rather than fast.

## The spine — targeted section, not full-text

A whole-filing diff is a **false-positive machine.** A prospectus is mostly boilerplate that re-files
for reasons unrelated to the thesis — annual updates, fee tables, legal language, dates. Diffing all of
it is the **diff-trap** (spec §3, the etfdb lesson: a diff of a churning source carries mostly
data-quality churn, not real change; HECO is the standing proof a source's face value can be
categorically wrong). So the sensor targets the **principal-investment-strategy / investment-objective
section specifically** (a priority match — prefer the detailed Strategies section, fall back to the
Objective) and diffs only that, bounded to the next section heading.

## Corroboration for human adjudication, not a substantive-change claim

`mandate.changed` accretes as a **silent corroboration** onto the live leads touching the fund (fold
already folds it so — no status/paging change), never a pager. The sensor decides only whether the
strategy **text moved**; the **human verdict** is the referee of cosmetic-vs-substantive — the same
resolution as the etfdb category diff ("diffs accrete as context; humans decide substance"). The
whitespace-normalized comparison already drops pure formatting/date/fee re-flows; a wording change
surfaces with a bounded unified-diff `summary` as the go-look content.

## Extraction-unreliable fallback

Targeted section-extraction is fragile across issuers' formats. When extraction is unreliable — the
strategy heading isn't found, the section is trivially short, or it runs to EOF with no boundary — the
sensor emits a **`fault` for manual review** and **no `mandate.changed`**. A false change-claim is
worse than a missed one, so we never diff what we couldn't reliably extract. (Audit is still served:
the new filing is on the record; the human is told to look.)

## The dependency — beautifulsoup4, deliberate and pinned

The project is dependency-minimal, and this slice adds **beautifulsoup4** (pinned `==4.15.0`,
`html.parser` backend, no lxml). Recorded here as a considered call against a standing value, not
dependency creep:

- **It is infrastructure, not intelligence.** The minimalism was never "no dependencies"; it is "no
  dependencies you can't understand and don't need," and it has always been *asymmetric* — ruthless in
  the *intelligence* layer (deterministic sensors, z-scores over neural embeddings, no black box in the
  thing that decides), while standing on solid infrastructure it didn't write everywhere else (numpy,
  SQLite, boto3, the EDGAR endpoints). Parsing malformed real-world filing HTML is squarely
  infrastructure. Hand-rolling an HTML tokenizer would be reinventing a solved problem worse and owning
  a fragile new surface — the opposite of what minimalism buys. The dependency you understand is a
  smaller attack surface than the parser you wrote at 11pm.
- **The boundary it must not cross.** bs4's job ends at **structure** — turn markup into navigable text
  and locate the section (`html_to_text`, the heading scan). This code owns **meaning** — *which*
  section is the strategy, and whether its text changed (`extract_mandate`, `diff_mandate`). The human
  owns **significance**. The extraction logic must never grow a "this change looks meaningful" opinion;
  a test asserts `diff_mandate` returns only `{changed, reliable, summary, reason}` — no significance
  field — so that line can't quietly drift.
- **Pinned** because it is the only dependency that parses external, occasionally-malformed input: a
  silent upstream parsing-behavior change would perturb the extracted section and thus the fossil
  record. Bump it deliberately. (Same discipline as labeling the NPORT stub a deliberate deferral — the
  point isn't the decision, it's that it left a reasoned mark.)

## Storage (Decision 2, rev9 §7)

Frozen **blob-per-accession** under `ingest/prospectus/{series_id}/{accession}/index.html`, SHA'd via
`write_atomic`, reference-only in the registry — never a mutable `FundEntry` field. `mandate.changed`
is a diff *across* accessions, so every version must be kept immutably; overwriting on re-file would
destroy the prior and break the very thing the sensor detects. Extraction re-derives from the frozen
HTML, so a later, better extractor re-reads old filings with no stored staleness.

## Runner note (§9, M5+) — do not fall into a self-inflicted ordering trap

The sensor's "prior" is the **last prospectus it has on file** (the prior frozen accession), *not*
necessarily the registry's `prospectus_accession` — an identity-resolution pass may have already
advanced that field to the new filing. Passing the frozen prior keeps the diff correct regardless of
intra-run ordering; the sensor's state is its frozen blobs. Detection = current latest prospectus
(`edgar.latest_prospectus`) ≠ the prior on file; the trigger is the daily filings-index check
(event-driven, §3), never a calendar cron. NPORT-P quarterly cross-check remains the labeled §3b stub.

## What shipped

`EdgarClient.filing_text` (Archives fetch) + `latest_prospectus` (accession **and** primaryDocument);
`StoreLayout.prospectus_path`; `ingest/prospectus.py` (`ProspectusIngest` freeze-per-accession,
`html_to_text`, `extract_mandate`, `diff_mandate`); `sensors/mandate.py` (`scan` — detect → freeze →
diff → route/emit `mandate.changed` / `fault` / nothing, routing reused verbatim from
`sensors/rebalance.py`); a `mandate:` config block; `beautifulsoup4==4.15.0`; a realistically messy
485BPOS fixture + 13 offline tests. **Not built:** NPORT-P (§3b stub), the live §9 runner. **Next
(rev9 §12):** the launch **corroboration hook** — the M4 capstone, its own PR and the hardest review
(the live-lag honest-test boundary), back to the design thread before green.
