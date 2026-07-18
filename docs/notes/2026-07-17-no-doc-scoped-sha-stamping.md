# No doc-scoped SHA stamping — the anchoring rule is CLAIM-scoped, and git already holds the trail

*Decision record, 2026-07-17. Ratifies the design-thread ruling on the question **"should every seat that
builds or touches code stamp a commit SHA on its documents, so there's a clear trail of what was done, by
whom, on what code?"** — QA already stamps; should Code? **No.** The existing claim-scoped anchoring rule
stands and already covers the real case. Governing: `METHOD.md` (*"every durable claim is tied to something
outside the narrative — a commit SHA, a failing test, a real breakage"*); the append-only discipline.
Companion to `2026-07-17-status-truth-one-prose-home.md` — same reasoning, different surface.*

## Context — the ask is reasonable and the answer is already built

The trail exists, and it is stronger than any document stamp: **git**. Author (meaningful since the
2026-07-16 identity split — agents commit as `claudeatalphalabsengineering`), parent commit, exact diff, date,
PR. **Merge-commits-not-squash** preserved all of it deliberately. *"What was done, by whom, on what code"* is
answered cryptographically by `git log --follow`. Both times the question came up in practice —
**M6-CAPTURE-DRIFT** and **PAGE-WORTHY-MIRROR** — git answered in one command, zero damage.

## Decision — no doc-scoped stamping for Code

**The structural reason, and it is the whole thing: QA's output is DECOUPLED from its input; Code's output IS a
commit.**

QA reads commit `X`, tests it, and delivers a findings PR **somewhere else entirely** — a different branch, a
different tree. **Nothing but the stamp records the link**, which is precisely why the branch could move
underneath it and the stamp could name a commit QA never read (the defect `reviewed_sha` closed). Code has no
such gap: the document its work produces **is** the commit. The link is git's, **by construction, unfakeable**.

**So a doc-scoped stamp would re-home a fact git already holds** — hand-maintained, drift-capable, in prose. A
fifth home for provenance. That is the four-homes defect, a fourth time, and it fails the same test the
`status.yaml` proposal failed: a stamp does not vouch for the claim, only that **someone typed a SHA**.

**And "stamp everything" is document-scoped where the real rule is claim-scoped.** It would force SHAs onto:
- **decision records**, which *precede* their code — there is no commit to cite;
- **build notes**, which are written *before the work exists* — the SHA cannot exist yet.

Ceremony that rots, on artifacts the rule was never about.

## What already applies (and already fires correctly)

`METHOD.md`'s rule is **claim-scoped**: *a durable claim about code state is tied to something outside the
narrative — a commit SHA, a failing test, a real breakage.* Live instances:
- **rev15's M6 correction cites `4739b52`** — *"M6 is built"* is a claim about code state made in a doc, so it
  carries a SHA. That is the rule working, and it is why the correction traced to **the commit, not an invented
  decision record** (there was no decision — inventing `2026-07-16-m6-is-built.md` would have been a fake
  record ratifying a fact).
- **QA's provenance stamp** — the decoupled case, correctly mechanized.

The rule needs no extension. It needs **application**, which it is getting.

## Accepted — one opportunistic fix

**The bug register's ~10 bare `file.py:line` citations → `file.py:51 @ <sha>`.** Line numbers rot on any edit
**above** them — structural, not speculative. And it is sharper here than for a living doc: **a bug record is a
fossil**, so a bare line already means *"line 51 at the time"* without saying **when**. The SHA finishes an
anchor the fossil format already implies.

It passes both tests cleanly — it **finishes an existing anchor** rather than adding a home, and it **proves
the claim** rather than token-matching. But it is **recoverable-class** (a rotted line is fixed when noticed,
zero damage), so the pain test says **not urgent**: a bounded ~10-line sweep, folded in the next time the
register is touched. Cheap, correct, unhurried.

## Also accepted (build-seat commitment, not a mechanism)

When the build seat relays repo state to the design seat, it **cites `origin/HEAD`** — so the design seat's
as-of is **checkable rather than a date**. This is the natural pair to the design seat's structural blindness
(it sees a frozen working-tree snapshot; no `.git`, no commits, no diffs). It is **discipline, not a gate**,
and named as such.

## Scope / what did NOT change

QA's stamp stands — it closes a gap Code structurally does not have. The claim-scoped anchoring rule is
unchanged. No document acquires a stamp field. The register `line@SHA` sweep is queued, not blocking.
