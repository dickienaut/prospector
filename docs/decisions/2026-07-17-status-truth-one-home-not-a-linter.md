# Rejected: a `status.yaml` status-linter and doc-scoped SHA stamping — status truth is one home, provenance is claim-scoped

**Date:** 2026-07-17
**Status:** ratified (design thread). **A rejected mechanism is a decision** — and the one most likely to be
**re-proposed**, because nothing else in the repo argues against it. Without this record the next seat reaches
for a status linter cold, from the trenches, with the same good instinct, and the whole argument re-runs from
zero. This is the clearest case the project has for recording a *no*.

## Decision

Two mechanisms proposed the same day for keeping status / provenance "truthful" are **rejected**, on one
shared diagnosis:

1. **A `docs/status.yaml` + a CI status-check** — a machine-readable build-status register the prose docs
   render from, or are checked against.
2. **Doc-scoped SHA stamping** — stamping Code's documents with the commit they describe (parallel to QA's
   `reviewed_sha`).

**Landing point instead:**

- **Doc-vs-doc → one home, three pointers.** The state doc's §5.2 register is the single source;
  `ARCHITECTURE.md`, `README.md`, and the spec's §9 build-status **point at it**, not restate it.
- **Doc-vs-code → discipline, honestly named in the ledger** — where a seat that didn't write the doc catches
  this class (three-for-three so far).
- **The one mechanical thing worth building → a cited-path / SHA-resolution gate** (below).

## Why the `status.yaml` fails — four independent grounds, any one sufficient

1. **It is `provenance_stamp` before `reviewed_sha`.** A green `m6: built` proves a doc-token equals a
   YAML-token and vouches for **nothing** about whether M6 is built. Presence enforced, truth not — the
   un-anchored claim wearing a receipt, the exact anti-pattern QA had to unwind. It would not even have caught
   its *motivating* bug: the drift read *"front-loaded to v2"*, which no `deferred` grep matches.
2. **No binding available.** *"Is M6 built"* is a **judgment against spec §6**, not a repo fact. QA could bind
   its stamp to a fetched commit; there is no equivalent here. The derivation needs a hand-written
   milestone→evidence mapping — prose in YAML, in a file nobody reads. Drift **relocated, not killed.**
3. **It breaks the mirror's joint.** PAGE-WORTHY-MIRROR worked because `import` means **one artifact.**
   "Generate-from / CI-check-against" leaves four prose registers + a YAML + a synchronizer = **five homes.**
   The lesson was *fewer homes*, not a better checker.
4. **The pain test + the freeze.** The doc-drift class fired 3×, was caught 3×, **zero damage** — in the most
   volatile month this repo will ever see (28 records, every milestone moving). v1 is build-complete: **~3
   status events a year** from here. A tool + mapping + CI + tokens across four docs, maintained for years to
   guard three events the cross-seat read already catches for free, is **process without pain** — the one
   thing the repo's own rule forbids.

## Why doc-scoped SHA stamping fails — the same diagnosis, second instance

QA needs a stamp because its output is **decoupled from its input** (it reads commit X, delivers findings
elsewhere; nothing but the stamp records the link — which is why the branch could move underneath it).
**Code's output *is* a commit** — the link is git's, by construction, unfakeable. Stamping a Code document
with a SHA re-homes a fact **git already holds**, hand-maintained and drift-capable (grounds 1 + 3 again: a
checker vouching for a token-match, and *more* homes not fewer). The rule that *does* apply is already in force
and **claim-scoped**: *a durable claim about code state is tied to a SHA* — rev15's M6 correction citing
`4739b52` is that rule firing correctly. "Stamp everything" would force SHAs onto records that precede their
code and build-notes written before the work exists.

## The pain test carries a boundary (a correction owed from this exchange)

The pain test — *"already being caught with zero damage = the mechanism working, not pain"* — is right where
the failure is **recoverable** (doc drift: the cost of a miss is one PR). It is **catastrophic as a general
rule**: you do not wait for the data-loss event to add backups, or the trade to build the firewall, or the
silence to arm the dead-man. This project already embodies the boundary — **the backup predates the loss, the
never-execute wall predates the trade, the dead-man predates the silence.** So: **the pain test applies where
the failure is recoverable; where it is irreversible, you mechanize before the pain, and "it hasn't bitten
yet" is the argument you ignore.** A disposition without its boundary becomes a wrong precedent.

## What to build instead — a cited-path / SHA-resolution gate

Every `docs/decisions/*.md` path and every commit SHA referenced in a doc **must resolve.** Pattern-free,
general, and it is *"every durable claim is tied to something outside the narrative"* made into a gate. It
proves the **anchor is real, not the claim** — exactly as far as a machine can honestly go for a judgment like
"built." It is now the **strongest-supported mechanism in the project**: it would have caught, mechanically
and with no judgment, *both* of the design seat's dangling references this week — the forward-reference to
`2026-07-16-rule-2-gate-enforced.md` before that record existed, and the handoff's citation of
`2026-07-16-claude-md-consolidation-design-seat-findings.md`, a findings doc that was written and presented but
never carried into the repo. Two instances is the archive's bar for naming a pattern: **anything a seat cites
as authority must be an artifact *in the record* — a citation to a file in a chat window is a promise, not an
anchor.**

## Opportunistic follow-through

The bug register's ~10 bare `file.py:line` citations → `file.py:line @ <sha>` (a line number rots on any edit
above it; a fossil's bare line already means "at the time" without saying when). This is the claim-scoped rule
doing real work at the one place it is currently half-done — cheap, recoverable-class, folded into the next
register edit, not a standalone PR.

## Provenance

A rejection has no code artifact. The motivating drift — M6 filed "front-loaded to v2" while `capture.py` was
built at `4739b52` — is recorded as `M6-CAPTURE-DRIFT` in `docs/bugs/INDEX.md`. The one-home fix and the
cited-anchor gate are queued in the CLAUDE.md consolidation, which by ruling **follows the on-Mini
activation** — sequenced on availability, not priority, so the last doc item doesn't beat the Mac work one
more round.
