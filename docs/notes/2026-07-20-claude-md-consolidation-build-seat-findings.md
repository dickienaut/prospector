# CLAUDE.md consolidation — Build-seat findings (2026-07-20)

*The second of three independent reads (Design / **Build** / QA), to be reconciled into a consolidation
rev. Design's read is `2026-07-16-claude-md-consolidation-design-seat-findings.md`; this one answers the
items it explicitly handed to Build, and adds Build's own beat: **stale facts, broken references, rules
that don't match the code, unrecorded behaviour.***

*Read against `CLAUDE.md` (299 lines) at `c8d2d42` — main after #122, with **v1.0.5 deployed to prod**.
**Every finding below names the file, line, or command that establishes it.** Where I could not verify,
it says so. Design's framing rule applies unchanged: the forbidden thing was never rewrite, it is
rewrite unchecked — this document exists to make the check possible.*

---

## 0. On Design's reframe

**Agreed, and now with evidence.** Length is the wrong target; the diagnosis is navigability and second
homes. I'd add one sharpening from the Build seat: the doc's *worst* property is not that it is long, it
is that **its most-edited section is the one with the least operative content** (the spec-rev narrative),
so the maintenance cost falls precisely where the value is lowest.

Two places where this read **diverges** from Design's — and per Design's §6, divergence is the signal
worth reading:

- **§3 (the firewall ledger) is wrong in a useful direction.** Design tiered clause 1 as "mechanism" from
  the state doc's IAM claim. There are actually **grep tests** — which Design didn't have — but they are
  **allowlists over 6 of 54 modules**, not a wall. Neither "mechanism" nor "prose". Detail in §3.
- **C-1's blanket deletion is unsafe, and I can now name the specific clause.** Design flagged the risk
  and couldn't check it. One CONTRACT in that narrative resolves **nowhere** in the spec. Detail in §2.

---

## 1. Stale facts — verified

**B-1 · The spec-rev pointer has already re-drifted, in four days.** *Class: drifted. Severity: this is
the finding that settles C-1.*

```
CLAUDE.md:6      "The canonical spec is `docs/spec.md` (rev 15, stated in its header…"
docs/spec.md:1   "# Project Prospector — v1 Build Specification (rev 16)"
```

Design predicted the narrative would self-inflict drift forever. It did not have to wait: **rev 16
landed 2026-07-19** (the §8a controlled-vs-uncontrolled fetch taxonomy) and CLAUDE.md still says rev 15.
So C-1 is no longer an argument about maintenance burden — it is an **observed recurrence**, the second
in one week, in a doc whose opener also still narrates rev12→rev5 while stopping short of 13, 14, 15,
and now 16.

This upgrades C-1 from "should" to "the highest-value single edit in the consolidation."

**B-2 · `.github/CODEOWNERS` points at a superseded decision record.** *Class: stale reference, live
file.* Its comment closes with `docs/decisions/2026-07-12-code-does-not-merge-human-reviews.md` —
which `CLAUDE.md` itself states is **superseded by** `2026-07-16-agent-identity-split-and-merge-gate.md`.
Not in scope for CLAUDE.md's own diff, but it is the same clause's second home, and a consolidation
touching the merge rule should fix both or neither.

**B-3 · The state doc is rev 8 (2026-07-16) and predates four days of behaviour-changing work** (#118,
#119, #121, #122, v1.0.5). **Not a defect** — Part V is re-synthesized each rev by its own rule — but the
consolidation should not read rev 8's status claims as current, and Design's §3 IAM claim was read from
exactly that snapshot.

---

## 2. C-1 deletion safety — the answer Design asked Build for

Design: *"Before a single line is deleted, each claim must be shown to resolve in rev15. Anything that
doesn't resolve is a **finding**, not a deletion. I cannot check this from the design seat. Hand it to
Build."*

**Answer: mostly safe, with one clause that must not be deleted. The caution was justified.**

| CONTRACT claim in CLAUDE.md's opener | resolves in `docs/spec.md`? |
|---|---|
| §9c mandate prior = last **frozen** blob, never `prospectus_accession` | ✅ **yes, verbatim** — spec.md:51, :233, and named at :350 |
| forward-hash routing (`xcorr_lead_id`/`dispersion_lead_id`) | ✅ yes (6 occurrences) |
| `sectors_unresolved` → dormant | ✅ yes (6) |
| `prospectus_accession` as the thing *not* to read | ✅ yes (4) |
| **frozen `gics_industry_sector` table (config, CONTRACT)** | ❌ **no — 0 occurrences** |

The last row is the finding. `gics_industry_sector` appears **0 times in the spec**, 3 times in
`config/prospector.yaml`, and in 2 decision records. CLAUDE.md is currently the **only canonical
statement** that this table is CONTRACT — *"re-freeze only on a GICS structure revision, never a knob."*

So a wholesale "delete the narrative, the spec carries it" would silently drop a live CONTRACT. Per
Design's own rule that makes it a **finding, not a deletion**. Two clean resolutions, either acceptable:

1. **Fold it into the spec first** (§4c), then delete from CLAUDE.md — preferred, since it puts the
   contract where contracts live; or
2. **Keep a one-line pointer** in CLAUDE.md's CONTRACT-vs-DEFAULT list (which is where config-level
   CONTRACTs already belong) rather than in the rev narrative.

**The generalizable lesson for the consolidation's diff:** "it's in the spec" must be *checked per
clause*, not assumed per section. Four of five resolved; assuming would have been right 80% of the time
and wrong about the one that mattered.

---

## 3. The firewall enforcement ledger — corrected

Design's §3 tiered the three clauses and flagged that it was reading the IAM claim from a stale state-doc
snapshot. Verified from the repo:

| clause | what actually enforces it, today | tier |
|---|---|---|
| never read the detector's **bucket** | **nothing.** No test greps for it. Separate repo = no import path, which is real but is *architecture*, not a gate | **prose + architecture** |
| never read **`portfolio.yaml`** | **two grep tests** — `tests/test_runner.py:334` (4 named runner modules) and `tests/test_dashboard_views.py:205` (`views.py`, `app.py`) | **partial mechanism — allowlist, 6 of 54 modules** |
| never place or size a trade | capability absence (no broker credentials, no portfolio data reachable) | **mechanism-adjacent** |
| never **recommend** a trade | **nothing** | **prose** |

Three corrections to Design's version:

1. **The grep tests exist.** Design's ledger didn't have them; `tests/test_capture.py:400` even refers to
   *"the portfolio-firewall grep tests"* as an established pattern. Clause 2 is better enforced than
   Design believed.
2. **But they are allowlists, not a sweep.** Both tests enumerate module names. `find prospector -name
   "*.py"` returns **54**; the tests cover **6**. A new sensor reading `portfolio.yaml` passes CI today.
   Clause 2 is therefore *worse* enforced than the word "test" implies.
3. **The IAM claim is not live.** I cannot read the IAM policy from here (still open, owner). What I can
   verify: `config/prospector.yaml:396` sets `s3.bucket: null`, and `prospector/store/s3_sync.py:11`
   imports boto3 **lazily** precisely so a `bucket=None` run "never touch[es] AWS machinery at all." So
   whatever the IAM posture is, it is **not currently load-bearing** — nothing reaches S3.

**The cheapest real improvement in this entire exercise** — and it is a *mechanism* change, not a doc
change: replace both allowlists with one package-wide sweep over `prospector/**/*.py`, and add the
detector-bucket term. It is ~5 lines, it converts an allowlist into an actual wall, and it makes the
constitution's strongest claim true rather than aspirational. Worth its own PR, independent of the
consolidation.

Design's core point stands and I'd restate it more strongly: **the doc should state the tiers.** An
overclaimed wall is the same defect class the rest of the consolidation is fixing, and clause 4 — the one
closest to the actual risk, since this system will talk an operator into a trade long before it places
one — is the one with nothing behind it.

---

## 4. Rules that DO match the code — the negative result

Recorded deliberately: a consolidation needs to know what not to touch, and "I checked and it was fine"
is evidence, not filler.

| CLAUDE.md claim | verdict |
|---|---|
| *"`VERDICT_VOCAB` in `prospector/fold/fold.py` is the single source of truth"* | ✅ true — `fold.py:54`; `cli/main.py:25` imports it and `:549` drives `--value` from it |
| *"a network guard fails any test that opens a real socket"* | ✅ true — `tests/conftest.py` patches `socket.socket.connect` |
| *"`pros store reindex` … computes nothing new, so it is repair, not run-now"* | ✅ true — present in `cli/main.py`, rebuilds from the fossil record |
| the Development merge clause (machine account, cannot self-approve) | ✅ **true and now genuine mechanism** — `.github/CODEOWNERS` is `* @dickienaut`; the `main` ruleset is **active** |
| *"Every fund keys on its SEC series ID… a bare ticker is rejected at the write path"* | ✅ true (registry write-path validators) |

**C-4 is closed.** Design flagged the merge clause as FALSE with an amendment in flight; that amendment
landed and the current text is accurate. The consolidation should not re-litigate it.

---

## 5. Unrecorded behaviour — what the last four days taught, that the constitution doesn't say

Design's M-1…M-6 are process rules the doc never caught up with. These are **verification** rules, all
earned in the 2026-07-18→20 mandate arc, all currently living only in decision records and notes:

**B-M1 · Verify against the unit that *acts*, not the unit you changed.** The two-day arc in one line.
A fix was verified on its 4 target filings (all fixed) → the corpus check found it broke **11 filings that
were already passing** → the corpus check itself scored a later fix "6 newly reliable, 0 regressions" while
that fix would have emitted **3 false corroborations**, because it judged documents and the sensor diffs
*pairs*. Three layers, each invisible from inside the one below.
*Operative form:* **a fix verified only on the documents it targeted is verified on a biased sample; and
the unit of verification must be the unit the system acts on.**

**B-M2 · The frozen substrate makes re-verification nearly free — so there is no excuse.** §7's
freeze-before-parse means extraction is a pure function of bytes we already hold, so *any* parser change
can be replayed over the entire corpus offline, with no network. `tools/corpus-check/` exists; the
constitution doesn't mention that this class of check is possible, let alone expected.

**B-M3 · A fixture must be proven to reproduce the pre-fix failure.** The fixture-provenance section
already demands real-vs-synthetic honesty. It does not demand that a fixture actually *fail before the
fix* — and a trimmed excerpt that accidentally fixes the document is a fixture that tests nothing. This
bit during this arc (a first trim silently dropped the stop heading).

**B-M4 · The deploy is not the proof; the tick is.** Practised twice now — deploy records carry an
explicit *to-be-appended* section, and on 7/19 the capture-403 box was deliberately left **unticked**
because the sensor never ran. *Operative form:* **an untested path that looks clean because it never ran
is a green earned for the wrong reason — record the null result, name the retest date.**

**B-M5 · Mark what you cannot attribute; never present it as clean.** #122's principle, and a genuine
third option between suppressing (which re-inflates noise) and emitting silently (which writes a
confident falsehood into an append-only store). Same family as `sectors_unresolved` and
`holdings-unavailable → dormant`: **flag the blind spot, never guess** — but for the case where the
signal is real and only its *attribution* is uncertain.

**B-M6 · Production deploys from a tag, by mechanism.** `ops/deploy.sh` refuses any ref that is not a
tag, and takes the single-writer lock so it cannot swap code under an in-flight tick. Operative, enforced,
and absent from the constitution.

---

## 6. Structure — where I'd go further than C-6, and where I'd stop

**Agreed on C-3 (one `## The record` heading) and C-6 (a five-line map).** C-6 is the highest value per
line in the exercise and I'd add it even if nothing else changed.

**Where I'd go further:** add a **table of contents** — rule *names* only, no restatement. A cold seat's
first question is "what applies to me," and 16 unlabelled sections can't answer it.

**Where I'd stop, and this is a real trap:** I considered proposing an "index of every NEVER" at the top.
**Don't.** Any such list either restates the imperatives — creating exactly the second home this whole
consolidation exists to remove — or it degrades into a bare pointer list that adds a maintenance
obligation with no reader value. The ToC must carry **section names, not rule text**. Noting the rejected
option because the next person will think of it too.

---

## 7. What I could not check from this seat

- **The IAM policy** — no credentials here. Still open; **owner**. What I could establish is that it is
  not currently load-bearing (`s3.bucket: null`, boto3 lazily imported).
- **Whether the rev-narrative's *attributions* are correct** ("rev12 folds §4c to built"). I checked
  whether each CONTRACT **resolves**, which is the deletion-safety question. Whether rev12 is the rev that
  did it is a different check, against the spec's own changelog.
- **Completeness.** Same caveat as Design, and it binds harder here: I verified claims I thought to test.
  A rule that is wrong in a way I didn't think to grep for is not in this list. That is what QA's read is
  for.
- **Whether `sensors/soi.py`, `ingest/holdings.py`, `INDEX.md` should be path-qualified.** CLAUDE.md
  writes several paths package-relative (`sensors/soi.py`) and one ambiguously (`INDEX.md` = `docs/INDEX.md`).
  Cosmetic, but a cold seat greps literally. Flagged, not ruled.

---

## 8. Divergence check against Design's §6 prediction

Design predicted Build would find *"stale facts, broken references, rules that don't match the code,
unrecorded behavior."* That is what this is — which is **weak evidence**, exactly as Design warned.

The entries worth the most reading are the two where the seats **disagree**:

1. **§3, the firewall ledger.** Design inferred tiers from the state doc; the repo says something
   different in both directions (tests exist → clause 2 stronger; allowlist over 6 of 54 → clause 2
   weaker). Neither seat alone had it right, and the reconciled version is sharper than either.
2. **C-1.** We agree it should go — but Design's *caution* turned out to be the load-bearing half, and it
   took a repo grep to find the one clause (`gics_industry_sector`) that would have been lost. **The
   agreement was cheap; the disagreement inside it was the value.**

One convergence I'd flag as *not* independent: both reads now say the rev narrative must go. Mine is
downstream of having read Design's. Treat it as confirmation of the evidence (rev 15 → rev 16), not as a
second opinion.
