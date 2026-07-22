# Bug archive — doctrine: the classes, the boundary, the record format

*Stable-named, amended in place. **This file is the doctrine half of the archive; the searchable register is
[`INDEX.md`](INDEX.md).*** Two files, two lifetimes: this one holds the meta-bug **classes** (§1), the
**boundary** rules, the record **template** (§4), the tag **vocabulary** (§5), and the **how-to** (§6) — the
parts that change only when the *system* changes. [`INDEX.md`](INDEX.md) holds the row-per-bug register you
grep, and churns every slice.*

***Rules are born from bugs.** A defect surfaces → we root-cause it → fix it → guard it with a regression test
→ and when it reveals a *pattern*, a rule or CONTRACT is born to stop the whole class recurring. **Refer to
[`INDEX.md`](INDEX.md) before shipping a slice** — grep the subsystem you're about to touch; a miss there means
new territory. The §1 classes below are where this project's bugs actually come from.*

---

## How this works

- **Meta-bug classes** (§1) — the recurring patterns, each with its instances and the **rule/discipline it
  birthed.** This is the load-bearing doctrine: repeat offenders are where rules come from, so a new bug's
  first question is *"which class is this?"* — which resolves to one of the **§1a taggable failure-classes**
  (1, 3, 4, 5, 7, 9) or `one-off`. The **§1b frame** (2, 6, 8) is never a tag: it is the lens you *read* to
  understand a bug — its root (2), the countermeasure (6), the severity axis (8).
- **The register** ([`INDEX.md`](INDEX.md), what was §2–§3) — every **distilled** defect, one row: symptom ·
  the two search axes (subsystem · shape) · status · class · guarding test · where the full detail lives. The
  file you grep; a miss = novelty. Kept out of *this* file on purpose — logging a bug must not edit the
  doctrine (that would be class-9 drift aimed at the archive's own governance).
- **Per-bug records** (`qa/YYYY-MM-DD-<slug>.md`) — born dated (per the naming rule), authored in `bugs/qa/`
  when a finding is **root-caused** (§6); template in §4. The **raw** review a record was distilled from stays
  in `notes/` (**never moved**), and the record links back to it.

## Boundary (so this doesn't fragment)

*Where does a finding live? — the question that keeps the archive from sprawling. The rule is a one-way
pipeline: `notes/` (staging) → distill → `bugs/INDEX.md` (register) [→ `bugs/qa/` record if it earns one].*

- **`notes/` = staging — the raw QA findings & reviews** (the H/S/B/I/P review, the N-series follow-up, the
  §9e / §10 / M6 findings). A multi-finding review lives here **whole and is never moved** — its findings
  close asynchronously, so relocating it would tear a live document. This is where a finding *starts*.
- **`bugs/` = the distilled defect lifecycle** — broke → root cause → fix → regression test → **rule born.** A
  finding **graduates** from a `notes/` review into `bugs/` by being **distilled** (root-caused, classed,
  tagged) into an [`INDEX.md`](INDEX.md) row — and, if the fix mints or re-proves a rule, a `qa/` record —
  **not by being relocated.** The record links back to the review; the review is never edited to point forward.
- **Distilled, not resolved — status is a column, not a gate.** The register holds *every* distilled bug
  whatever its status: `⭕ open`, `💤 deferred`, and `🟡 partial` rows **stay**, because a known-unfixed bug in
  the subsystem you're touching is the highest-value hit there is. "In the register" means root-caused, not
  fixed. (This is why a *miss* can be trusted to mean novelty — the register is not a fixed-bugs list.)
- **A raw finding is not yet a register bug.** A `notes/` review may hold a "looks off, unverified"
  observation; it becomes a register **row only once it's root-caused** — a named cause at `file:line`, a
  class, a reproduction. Until then it stays in the review, not the register. That threshold is exactly what
  makes a register miss meaningful. *(So: yes, QA findings dropped in `notes/` belong there — and their
  root-caused defects belong, distilled, in the register. The review stays; the bug graduates.)*
- **`decisions/` = design / contract choices.** A bug that forces a CONTRACT change gets its own decision
  record; the bug entry **links** to it (the lineage), it doesn't restate it.

---

## §1 · Meta-bug classes — the patterns that keep biting

*Ordered by how much they've cost. Each is a bug **factory**; the rule in the last column is the machine we
built to shut it down. When a new defect matches a **taggable** class here, tag it — and if the class has no rule yet, that
absence is the next rule.*

*§1 splits in two. **§1a — taggable failure-classes** (1, 3, 4, 5, 7, 9): the defect *shapes* a new bug
tags to. **§1b — the frame** (2, 6, 8): the root, the countermeasure, the severity axis — read to understand
a bug, never tagged (you can tag a bug "class 5"; you can't tag one "class 6 — go to primary source," that's
the fix, not a defect). **The numbers 1–9 are stable IDs — never renumbered:** the §2 "Class" column
references them by number, so the split only *groups* them (a `Class` value like `1,2,8` still resolves —
taggable 1, rooted in frame 2, fails silently per frame 8). The taxonomy's version of moving files into
folders without renaming them.*

### §1a · Taggable failure-classes — what a new bug tags to

*The actual defect patterns; "which class is this?" resolves to one of these — or `one-off`.*

#### 1. Green-on-synthetic / broken-on-real  ·  *the project's signature failure*
Code reads correctly, passes its tests, and breaks on the **real** substrate — because the test exercised a
*synthetic* fixture that couldn't reproduce the real shape. Named explicitly in the §10 finding: *"the third
time this pattern surfaced… the first on the alarm layer itself."*
- **Instances:** H1 (÷100 scale, scale-invariant tests stay green) · H4 · P1 (2-row fixture can't exercise a
  split) · S1 (property test masks it) · 9e-ENR (bare-ticker pull returns a real *wrong* series only vs the
  real TEKX file) · E1 ("same shape as the H1/H4 misses") · R1 (rebalance cash exclusion keyed on empty
  identifier; real SSGA cash lines carry CUSIPs — every fixture used cash-free equity baskets).
- **Rule born:** the **fixture-provenance discipline** — every fixture is *recorded-real* (source-URL +
  retrieval-date) or *declared-synthetic in-band*; and the QA seat **runs** the code against real
  config/fixtures, never just reads it. → [`CLAUDE.md` §Fixture provenance](../../CLAUDE.md#fixture-provenance) (validate slices against real/moving substrate).

#### 3. Invariant stated in prose, not enforced in mechanism
The code *says* an invariant in a docstring/comment but nothing makes it un-violatable; the test exercises the
*easy* version of the invariant, so the gap is invisible. The "governing frame" of the whole N-series fix plan.
- **Instances:** N1 (§11 read-only firewall — a `# read-only` comment that wrote to the store) · N2 ("two cold
  runs identical") · N3 (§3 no-fabrication) · N8 ("ambiguous → surface") · B3 (docstring "excludes the market")
  · SNAP-01 (the "never a raw `store.append` fault" rule stated in the `_emit_fault` docstring but not
  un-violatable — the snapshot sink re-introduced the bypass).
- **Rule born:** **(a)** convert the invariant from prose to **mechanism** (make it un-violatable — e.g. open
  the store `mode=ro`); **(b)** land a regression test that **attempts the violation**, not the easy case (the
  "fires-not-called" discipline). → [the `fires-not-called` discipline](../decisions/2026-07-06-soi-corroboration-retry-9d.md).

#### 4. A test that passes for the wrong reason
The suite is green, but *because of* the bug, or by an accident of the harness — so it certifies the defect.
- **Instances:** N1 (`test_dashboard_app` smoke passes only because the broken read-write dashboard creates the
  table on the fly) · N2 (two separate fresh stores dodge the same-store path) · N5 (relative config path
  resolves only because pytest runs from repo root) · E1 (synthetic `"boom"` message) · SNAP-01 (the existing
  divergence test passes `fault_sink=faults.append` — a list standing in for the accumulator — so it certifies
  "the sink fires", not that production's `store.append` sink reaches the accumulator).
- **Rule born:** **runner-faithful seeds** (test against the real store/path/message the runtime uses) + the
  violation-test rule (3b). Tightly coupled to classes 1 & 3.

#### 5. "Never anchor on a ticker" — the HECO lesson, recurring one grain deeper each time
A ticker is treated as a stable identity; it isn't (reuse, dual-class, foreign collision). Keeps reappearing at
finer grains as new layers land.
- **Instances:** I1 (launch series identity discarded, re-derived by ticker) · B1 (prospectus at trust level,
  not series) · 9e-ENR (constituent `ENR` = Siemens Energy *and* NYSE Energizer → wrong returns, silently) ·
  9e-membermap · smell-edgar-matches0 · R1 (the `identifier` field trusted to mean "real security position";
  a populated CUSIP on a cash/money-market line breaks that — the ticker-identity lesson one field over).
- **Rule born:** the **identity layer** (series-ID `S######` is the key; a bare ticker is rejected at the write
  path) + series-scoped `resolve_series` + the **§9e PRIMARY-SOURCE GATE**. → `docs/decisions/2026-07-06-identity-integrity.md`,
  `2026-07-10-9e-constituent-symbol-resolution.md`.

#### 7. Nuisance-alarm / GPWS — "the alarm that cries wolf trains you to disable it"
The smoke-detector brief's §2.4 failure, imported into our alert layer: a fault that pages every tick trains the
operator to ignore it.
- **Instances:** C.1 (every-tick fault push) · E1 (volatile message defeats suppression → pages daily) · E2
  (flapping fault) · the fault-taxonomy count-lie ("0 faults" beside nine that fired) · SNAP-01 (snapshot
  divergence counted 0 / never pages — the raw-`store.append` bypass re-opened on the snapshot layer) · R4
  (E1's volatile-message alarm re-appearing on the rebalance prior-parse path — a new `_emit_fault` site
  with no `key=`, proving the convention is not yet enforced in mechanism).
- **Rule born:** the **§8a alarm-posture CONTRACT** — push once on a *new/changed* fault, then fall silent to
  the weekly heartbeat; the `_emit_fault(key=…)` **stable-key** convention (key ≠ display message); operational
  faults page, manual-review advisories are counted+surfaced but don't page (except on a live-lead fund). →
  `docs/decisions/2026-07-10-10-email-sender.md`.

#### 9. Doc drift / memory-prosthetic leak
The archive misremembers — tells a returning reader something false — because status prose outside the
regenerated section rots, or a "closed" changelog line is added without deleting the open to-do it closed.
- **Instances:** DRIFT-1 (state doc §2.9 "deferred" vs §5.2 "shipped") · DRIFT-2 (aging-monitor "pinned"
  carried open 8 revs) · C.2 (code outran its docstrings + ARCHITECTURE.md).
- **Rule born:** **§5 is the single source of truth, regenerated every rev; history sections describe
  decisions, never current build-state**; a changelog "closed" line must **delete-and-restate** the to-do it
  closes. (Kin to the whole doc-discipline: amend-never-regenerate, the `2026-07-11-docs-reorganization` +
  `-doc-naming-convention` rules.)

#### Non-defect Class values — `one-off` and `judgment`
Not every row is one of the numbered patterns above. Two Class values sit **outside** §1a's defect list,
and the boundary between them is load-bearing (so the register never blurs "adjudicated" or "singleton"
into "unexamined"):
- **`one-off`** — a **real defect** that matches **no** recurring pattern: a genuine singleton, the honest
  answer when forcing a numbered class would coin a fake one. It still has a fix + a guarding test.
- **`judgment`** — **not a defect at all.** An adjudicated **design call** (M7-04 / M7-06 concurrency
  posture, R2's cash-sentinel constraint, BK-3's deferral) or a **verified non-defect** (GI-01 — checked
  and cleared). Its "resolution" is a ruling or a verification, recorded so the row is a deliberate,
  complete entry — but there is nothing *broken* to fix.
- **The boundary:** `one-off` is *a defect with no pattern*; `judgment` is *no defect* — an owner /
  design-thread call (or a clearance) captured so the register stays complete. Neither is a §1a taggable
  failure-class; both live in the Class column so a reader never mistakes an adjudicated call or a cleared
  check for un-hit ground.

### §1b · The frame — not taggable (read to understand: root · countermeasure · severity axis)

*Never a bug's tag. These are the lenses: **2** the root (why the silent set stays invisible), **6** the
countermeasure (go to the primary source), **8** the severity axis (how silently it fails). Convergent-prior
leads — the rest are its downstream symptoms.*

#### 2. Convergent-prior error  ·  *the root — why the whole silent set stays invisible*
Code **and** fixture share one wrong prior, so no divergent cross-review catches it — only the primary source
does. "The model that wrote the code is worst-positioned to see its own baked-in premise."
- **Instances:** the *"SPDR publishes daily CSVs"* prior (residue: H1/H2/H3) · the *"the daily file carries GICS
  sectors"* prior (drove the entire SOI slice) · S5 (a future NaN fixture).
- **Rule born:** **primary-source verification is the antidote** — read the *real filed artifact*, don't prove
  logic against imagined messiness; plus the three-seat workflow (design→build→QA) so the author isn't the
  reviewer. → `docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md`, `2026-07-04-soi-derived-sector-concentration.md`.

#### 6. Go to the primary source  ·  *the countermeasure that keeps paying off*
The one you named: the truth is in the filed artifact, and only opening it breaks the shared prior. Every time
we've gone to the source, it moved the design.
- **Instances:** the xlsx/blank-Sector discovery (opening a real SSGA file) · P1 (verify vs a known NVDA split
  before trusting a price source) · B1/B2 (registrant-level EDGAR truth) · 9e-ENR (widened the gate to
  dual-class + foreign + cash lines).
- **Rule born:** the **primary-source gate** before a live slice; the **no-third-party-symbol-feed** /
  **no-LLM-text-as-data** walls (a bought feed or model prose would breach the primary-source discipline).

#### 8. Fail-loud vs fail-silent  ·  *the severity axis, not a cause*
The codebase's dominant (good) instinct is to fail loud / fault rather than mis-roll. The bugs that **matter**
are the few that fail *silently* — this is the axis that ranks every class above, not a class of its own.
- **The silent set (the dangerous ones):** H1, H4, I1/B1, S1, S5, N1, N2, N3, N8, N10, 9e-ENR, E1, the count-lie.
- **Rule of thumb:** a finding's severity ≈ how silently it fails. A loud raise is a nuisance; a silent wrong
  number corrupts the fossil record.
- **The `edgar.py` single-sentinel state-collapse signature (a recurring shape *within* this axis).** The
  columnar submissions helpers (`latest_prospectus` / `prospectus_history` / `latest_soi` / `confirm_prospectus`
  / `classify_soi_target`) each return ONE sentinel (`None`/`[]`/one reason), so every distinct failure mode
  lands in the same hole. **Six instances so far:** N8's three-way (ambiguous/error/not-yet), F1 shape-drift-vs-
  absence, F5 prior-coverage, the pagination-undetermined third-state, and two mislabels found by enumerating
  the family — SOI `index.json` drift → `SOI_AMBIGUOUS` (should be `SOI_ERROR`), `confirm_prospectus` drift →
  `http_error`. **The discipline: when you touch one of these helpers, enumerate the states that map to its
  return, and split any two that are distinguishable AND differently actionable** (Design's N8 rule;
  `../decisions/2026-07-22-submissions-pagination-undetermined.md`). Distinguishing is not always *fixing* — a
  split state may still route to one disposition — but the split is what makes the choice visible.

---

## §2–§3 · The register — moved to [`INDEX.md`](INDEX.md)

*The bug index (was §2) and the open/deferred live tail (was §3) now live in **[`INDEX.md`](INDEX.md)** — the
searchable register, one row per **distilled** bug, with the two grep axes (subsystem · shape), a status
column, and a class reference. **The §-numbers are stable IDs** (like the class numbers): they were relocated
byte-preserved, not renumbered, so any "§2"/"§3" reference in a fossil still resolves — to `INDEX.md` now. New
bugs are appended there, never here; this file stays doctrine, and its §-count is deliberately gappy so the
old numbers keep pointing at the same content.*

- **Grep the register**, don't read it top-to-bottom: `grep -i "<subsystem>" INDEX.md` (e.g. `backup`,
  `rebalance`, `heartbeat`) or `grep -i "<shape>" INDEX.md` (e.g. `spurious-fire`, `fail-silent`). A miss =
  new territory (see the boundary rules above and §5's controlled vocabulary).

---

## §4 · Per-bug record template (new bugs, going forward)

Copy this block into `docs/bugs/qa/YYYY-MM-DD-<slug>.md` (born dated, per the naming rule; authored in
`bugs/qa/`). A record is the *distilled* long form of a bug — write one when the fix mints or re-proves a rule,
or the bug is load-bearing enough to want its own page. Every distilled bug also gets an [`INDEX.md`](INDEX.md)
row (§6); the record is what that row links to.

```
# <slug> — <one-line symptom>
*Bug record, YYYY-MM-DD. Status: fixed | partial | open | deferred(xfail). Class: <§1 class, or one-off>.
Tags: <subsystem> · <shape> — the §5 controlled vocabulary, the same terms as the INDEX row.*

- **Symptom** — what was observed (the failing behaviour; who/what saw it).
- **Root cause** — the real why, not the surface. (Name the `file:line`.)
- **Fix** — what changed + the commit/PR.
- **Regression test** — `tests/<file>::<test>` — and how it goes RED without the fix (attempt the violation).
- **Rule born** — the rule/CONTRACT/decision this bug spawned, if any (link the `decisions/` record or the
  `CLAUDE.md` clause). ← the lineage this archive exists to keep.
- **References** — the `notes/` review it was **distilled from** (link it; the record points back, the review
  is never moved), the spec §, related bugs by ID.
```

*Rule of use: log a bug — the INDEX row, plus a record if it earns one — the moment it's root-caused, not after
it's fixed. The point is the trail, and a bug whose fix births a rule is the most valuable entry in the repo.*

---

## §5 · Tag vocabulary (controlled)

*Two axes, a fixed word-list each, so the [`INDEX.md`](INDEX.md) grep is reliable — a new row **reuses** these
terms, it never coins a synonym (a synonym is a silent miss). Extend the list deliberately, here, when a
genuinely new subsystem or shape appears — the same discipline as the class numbers.*

**Subsystem — *where it bit*** (one or more, `·`-joined):
`backup` · `rebalance` · `heartbeat` · `snapshot` · `dispersion` · `xcorr` · `identity` · `config` ·
`dashboard` · `email` · `runner` · `store` · `fold` · `capture` · `backtest` · `deploy` · `ops` · `docs` ·
`ingest` (qualify the source: `ingest·holdings` / `·prices` / `·edgar` / `·soi` / `·prospectus`).

**Shape — *how it failed*** (one or more; the recurring cross-cutting patterns — a genuinely singular shape
gets `—`):
`fail-silent` · `spurious-fire` · `identity-anchor` · `green-on-synthetic` · `invariant-in-prose` ·
`test-passes-wrong-reason` · `convergent-prior` · `doc-drift` · `split-path` · `count-lie` · `concurrency`.
*Also on older rows (finer-grained, doubling as their class): `fault-isolation` (N6, BK-1), `state-as-signal`
(N10).*

The **Shape axis is the §1a taggable classes made searchable** — the correspondence, written down here so
the two columns can't silently drift apart (the denormalization is **deliberate**: Shape is the greppable
projection of the classes): `green-on-synthetic` ↔ class 1 · `invariant-in-prose` ↔ 3 ·
`test-passes-wrong-reason` ↔ 4 · `identity-anchor` ↔ 5 · `spurious-fire` ↔ the class-7 nuisance-alarm
surface · `doc-drift` ↔ 9 · `fail-silent` ↔ the class-8 fail-silent-degradation **frame** (§1b — the
severity axis, not a numbered §1a pattern). `concurrency` (M7-04, M7-06) is the exception that proves the
rule: a genuinely new shape with **no §1a class twin** — its rows are `judgment` design-calls, not a
numbered defect pattern; if a *coded* concurrency defect ever lands, that is when it earns a class number.
Grep a shape to find every instance of a class across every subsystem; that cross-cut is the point.

*Future guard (noted, NOT built — the real-pain rule):* if the two columns ever actually drift, the fix is
a one-line lineage assertion over `INDEX.md` (a class-7 row must carry `spurious-fire`; a class-1 row
`green-on-synthetic`; …). Build it the day a drift bites, not before.

---

## §6 · How to log a bug — the two-author handoff (bake this in)

*The archive is written by two seats. **QA authors the Problem; build authors the Fix.** No step is optional,
and none needs a judgment call about *whether* — only *which class / which tags*. Follow it verbatim.*

**QA — when a finding is root-caused (a named cause at `file:line`, a class, a reproduction):**
1. **Append an [`INDEX.md`](INDEX.md) row** under the right pass-heading: ID · one-line symptom · **Subsystem**
   and **Shape** from §5 · **Status `⭕ open`** (it isn't fixed yet) · **Class** (§1) · the fix-site or the
   `notes/` review it came from. *(A "looks off, unverified" observation is **not** a row yet — it stays in the
   `notes/` review until it's root-caused. That threshold is what keeps a register miss meaningful.)*
2. **If it's load-bearing, or its fix will mint / re-prove a rule, also write a `qa/` record** (§4 template).
   Otherwise the row is enough.
3. **Leave the `notes/` review in place** — link to it from the row/record; never move or rewrite it.
4. **Open the PR** (the row + any record + the RED-first regression test). QA does not merge.

**Build — when implementing the fix:**
5. **Land the fix + its guarding test, then flip the row's Status to `✅ #<PR>`** (and the record's status line)
   **in the same change.** Add the **Rule born** link if the fix spawned a decision / CONTRACT.
6. **A fix is not done until its `INDEX.md` row is current** — the same gate as "a fix needs a guarding test."
   A merged fix with a stale row is the class-9 drift this archive exists to stop (the drift #55's
   "patch drafted" statuses actually showed — the reason this discipline is written down).

**The invariant:** every distilled bug is a row; every row's status matches reality; the raw review it came
from never moves. Keep those three true and a register *miss* means exactly one thing — **novelty.**
