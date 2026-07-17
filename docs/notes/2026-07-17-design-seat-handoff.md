# Design-seat handoff — 2026-07-17

*What this seat is carrying, written before it goes away. **The point of this doc:** Code's and QA's handoffs
carry their *state* — branches, verified facts, queues. This one carries the **rulings and their reasoning**,
because most of today's decisions have no record yet, and the reasoning is the part that dies when a thread
ends. Where a ruling is worth a decision record, it's marked.*

***As-of caveat.*** *Written from a frozen project-knowledge snapshot (last sync 2026-07-17) plus what was
pasted in. This seat cannot see commits, diffs, or branches. Every claim below about repo state is a **lead,
not a verdict** — ground it against live `main` before acting. One specific uncertainty is flagged in §3.*

---

## 1. Ratified today (no decision records yet — these are the ones worth writing)

**QA's skill: repo is the source, publishing is the deploy.** The decisive argument is *not* "so it can be
reviewed" — it's that **a DRIFT signal against a mirror is cry-wolf.** A mirror lags by design; drift is its
*expected* state, so a drift check against one fires constantly and means nothing — a brand-new alarm on this
project's most-scarred failure mode. Against a source, DRIFT is a finding. That's not a placement detail; it's
what makes the signal a signal. (Code's earlier "build it in the right place first" was a rework argument and
was withdrawn in favour of this one.)

**Home: `tools/qa-skill/`, not `qa/`.** Convention argument: every top-level directory in this repo names a
**kind**, not an owner — `prospector/` the package, `tests/` the suite, `docs/` the record, `ops/` operations,
`config/` config. `qa/` would be the only owner-named directory in the tree, encoding the wrong thing at
exactly the moment you're deciding the *repo* owns the artifact rather than QA. Also: `docs/` holds
`METHOD.md`, which governs QA, and nobody calls it QA's.

**The pattern this completes:** `CLAUDE.md` governs Code (in-repo, reviewed, gated). `METHOD.md` governs every
seat (in-repo, reviewed, gated). QA's skill governs QA — and didn't. It's the only seat-procedure that is
**executable**, which is exactly why it drifted out of the record: prose lands in `docs/` naturally; code that
isn't the product had nowhere obvious to go, so it went nowhere. `tools/` is the missing home, and the set
closes.

**Honest tiers for the ledger** (do not overclaim on the way in): *changes to QA's procedure are reviewed* →
**mechanism** (main is gated; a `qa/*` PR is the only path into the source). *The published copy matches the
source* → **discipline** (self-reported; the platform loads the catalog copy at session start, so the check
can only ever be self-reported — that's a genuine platform constraint QA verified, not a design shortcut).
*A drifted publish is visible* → the stamp (warn-loud), graduating to mechanism only when CI re-runs the
controls against the repo source.

**Accepted cost, named:** making it source slows QA's own iteration to PR-speed. That's METHOD.md's "overhead
per change" aimed at QA's tooling. Correct trade — the skill *is* the membrane, and it's the one artifact that
shipped two PR-shaped defects (`if provenance:`, the mock that failed open into a live write → PR #74 /
branch `qa/x`) with no PR available. Warn-don't-block keeps the mid-run patch path open.

**Rev-in-filename → stable names (`docs/spec.md`, `docs/state.md`).** The decisive argument: **the
rev-in-filename destroys the PR diff, and the diff is where the mandated check lives.** CLAUDE.md requires
*"diff against the prior version and confirm every changed clause traces to a decision record"* — but #86
showed git a **new file** (+2000 lines) and a **move**. No diff; the check unrunnable in review, so it ran by
hand. Same for #87, worse: *"Parts I–IV carried verbatim"* is the state doc's central discipline and the
naming convention made it **unverifiable in review**.

*Code's refinement is better than the original argument and should be the record's framing:* **it isn't a new
rule — it's the naming convention applied to itself.** The convention already says stable-named =
amended-in-place, dated = point-in-time or versioned; the spec is amended-in-place *by amend-never-regenerate's
own words*. It was **misclassified**. The correction makes two existing rules stop contradicting each other.
And the dated benefit was always for the **fossils** (multiple coexisting in `history/`), never for the single
live doc.

*Mechanism (this was loose in Code's first framing and matters):* you do **not** amend a decision record —
they're append-only fossils, and a record isn't a CONTRACT. The operative rule lives in **CLAUDE.md's
`## Doc naming`**. So: a **new record superseding** `2026-07-11-doc-naming…`, **plus** a surgical amendment to
that clause. Two artifacts.

*Execution:* standalone PR, **on rev15**, pure `R100` rename + pointer updates + an INDEX **transition marker**
(*"history/ holds the pre-2026-07-17 dated revs; from rev16 the spec is amended in place —
`git log --follow docs/spec.md`"*) — without it, a reader in a year sees rev5–15 and concludes revs stopped.
Grep the **whole repo**, not `docs/` (`ops/`, the QA skill, CI workflows, `pyproject.toml`, fixtures). Live
pointers update; **fossil citations do not** — rewriting a record to chase a rename is the violation. Dangling
rev-paths in old records are a **pre-existing backlog** (every rev bump already created them); don't let that
finding grow the PR.

## 2. Rejected today, and why (worth a record — a rejected mechanism is a decision)

**`status.yaml` + a CI status-check.** Four independent grounds, any one sufficient:

1. **It's `provenance_stamp` before `reviewed_sha`.** A green `m6: built` proves a doc-token equals a
   YAML-token and vouches for **nothing** about whether M6 is built. Presence enforced, truth not — the
   un-anchored claim wearing a receipt, the exact anti-pattern QA had to unwind. It also wouldn't have caught
   its motivating bug: the drift read *"front-loaded to v2"*, which no "deferred" grep matches.
2. **No binding available.** *"Is M6 built"* is a **judgment against spec §6**, not a repo fact. QA could bind
   its stamp to the fetched commit; there's no equivalent here. The derivation needs a hand-written
   milestone→evidence mapping — prose in YAML, in a file nobody reads. Drift relocated, not killed.
3. **It breaks the mirror's joint.** PAGE-WORTHY-MIRROR worked because `import` means **one artifact**.
   "Generate-from / CI-check-against" leaves four prose registers + a YAML + a synchronizer = **five homes**.
   The lesson was fewer homes, not a better checker.
4. **The pain test + the freeze.** The class fired 3×, was caught 3×, **zero damage** — in the most volatile
   month this repo will ever see (28 records, every milestone moving). v1 is build-complete: ~3 status events
   a year from here. A tool + mapping + CI + tokens in four docs, maintained twenty years to guard three
   events the cross-seat read already catches free, is process without pain.

**Landing point instead:** **one home, three pointers** for doc-vs-doc (rev8 §5.2 is the register; ARCHITECTURE
/ README / spec §9 point at it). **Discipline** for doc-vs-code, honestly named in the ledger — where a seat
that didn't write it has caught it three-for-three.

**A correction owed to the skill Code wrote from that exchange** (`mechanism-bias-run-the-pain-test`, indexed
today — a good artifact, and this is the kind of edit it invites). **Its check 1 needs a scope line it doesn't
have.** *"Already being caught with zero damage = the mechanism working, not pain"* is right where the failure
is **recoverable** — doc drift, where the cost of a miss is one PR. It is **catastrophic as a general rule**:
you don't wait for the data-loss event to add backups, or for the trade to build the firewall, or for the
silence to arm the dead-man. This project already knows that — **the backup predates the loss, the
never-execute wall predates the trade, the dead-man predates the silence.** So: **the pain test applies where
the failure is recoverable; where it is irreversible, you mechanize before the pain, and "it hasn't bitten yet"
is the argument you ignore.** A disposition without its boundary becomes a wrong precedent — Code's own words,
owed back to the skill that needs its own medicine.

**The one mechanical thing worth building:** a **cited-path / SHA-resolution gate** — every `decisions/*.md`
path and every SHA referenced in a doc must resolve. Pattern-free, general, and it's *"every durable claim is
tied to something outside the narrative"* made into a gate. It would have caught this seat's own dangling
forward-reference to `2026-07-16-rule-2-gate-enforced.md`. It proves the **anchor** is real, not the claim —
which is exactly as far as a machine can honestly go here.

**SHAs in Code's documents: no.** QA needs a stamp because its output is **decoupled from its input** (reads
commit X, delivers findings elsewhere; nothing but the stamp records the link — which is why the branch could
move underneath it). **Code's output *is* a commit** — the link is git's, by construction, unfakeable.
Document-scoped stamping re-homes a fact git already holds. The rule that *does* apply already exists and is
**claim-scoped**: *a durable claim about code state is tied to a SHA* (rev15's M6 correction citing `4739b52`
is that rule firing correctly). "Stamp everything" would force SHAs onto records that precede their code and
build-notes written before the work exists. Accepted, opportunistic: the bug register's ~10 bare
`file.py:line` citations → `file.py:51 @ <sha>` (line numbers rot on any edit above them; a fossil's bare line
already means "at the time" without saying when).

## 3. The one live finding — `docs/qa-config/prospector-branch-qa/`

**The mirror breaks on its own rationale.** Its README states the purpose: *"there is no undo unless a
known-good copy exists somewhere durable."* True when the skill lived only in the platform catalog. The moment
it lives in `tools/qa-skill/`, **git is that durable copy** — every version, with history. #93's README block
patched the mirror's **label** (*"convenience mirror only and may lag"*) and left the **artifact**, and the
reason the artifact existed dissolved in the same commit.

Three concrete failures:
- **The restore snippet reads the mirror** (`open("qa-config/prospector-branch-qa/SKILL.md")`) — so a restore
  restores the **lagging copy**. You reach for it exactly when the platform copy is wrong, and get known-stale
  bytes back. Its one purpose is what its lag breaks.
- **`MANIFEST.json` hashes the mirror** — the drift detector, whose stated job is *"a changed sha256 = the live
  copy diverged"*, is anchored to the copy that's *expected* to be wrong. Source moves, mirror doesn't,
  manifest reports clean.
- **It's a precondition for the stamp, not hygiene.** Step 4 compares catalog hashes vs **repo** hashes. Which
  repo copy? Read `tools/qa-skill/` → correct. Read `docs/qa-config/…` → DRIFT measured against a copy the
  README says may lag, and the stamp is *actively misleading*. One home = no ambiguity to get wrong. Two homes
  = the stamp's correctness depends on QA picking right, which is discipline where the point was mechanism.

**Fix: a deletion.** Drop `docs/qa-config/prospector-branch-qa/`; repoint `MANIFEST.json` and the restore
snippet at `tools/qa-skill/`. Cost of the mirror: a guaranteed-drifting home, a misaimed detector, a restore
that restores the wrong bytes. Benefit: two files in one folder. It's a path string versus a defect class —
and it's the **fourth instance** of the class, built deliberately three days after the third was closed.

**Uncertainty to resolve first:** this seat can't tell whether the `qa-config/README.md` it read is #93's
branch or `main`. If **main**, the README already claims `tools/qa-skill/` is authoritative while `tools/` may
not exist there yet — a **dangling forward reference**. QA or Code can settle it in one command.

**Downstream, not now:** after the deletion, `docs/qa-config/` holds only the profile — the last mirror in the
system. Same argument applies with less force (not executable, no CI story). If `tools/qa-skill/` is QA's home
in the repo, the profile arguably belongs there too, and `docs/qa-config/` disappears rather than surviving as
a half-directory whose name no longer describes it.

## 4. Queue and dependencies (order matters in two places)

**Ratified order for the QA-skill arc:** ratify source + home ✅ → relocate → lift the **network-free** membrane
controls (`verify_red_green`'s discriminators) into repo tests → the **stamp** → **injectable transport** →
delivery-path guards in CI.

**One gap to check before the stamp (new, 16:xx).** QA's stated next-up is *stamp → injectable transport →
delivery guards* — which **skips step 3: lifting the network-free membrane controls into repo tests.** Either
it rode #93 or it fell out. It matters: **a skill in the repo with no tests running against it is a file in the
repo, not a source under review.** Step 3 is what makes the relocation load-bearing, and it has **no
preconditions** (the controls are network-free, so they can land the moment the skill has a testable home).
Confirm it landed, or slot it back ahead of the stamp.

**The split that makes the order load-bearing:** `verify_red_green` is network-free (`git apply` + pytest), so
its controls can land in CI as soon as the skill has a testable home. `deliver_qa_findings_pr` hits the network
with a **hardcoded** transport (`import requests` inside the function) — so **injectable transport is a
precondition** for the delivery-path tests, not a nice-to-have. A CI job that monkeypatches around a live token
is the `qa/x` incident with no human watching.

**The stamp design is settled** (three-seat agreement): per-file `SKILL.md` / `kernel.py` hashes — because a
**`kernel.py` drift means the gates that produced the finding you're reading were unreviewed**, so you should
distrust the *finding*, not just the skill; a prose drift is benign. Both defects the skill ever shipped were
kernel logic. Catalog-vs-repo compare rendered in the provenance block (the PR body — where review already
happens). **Warn-loud, don't block**: a refusal means drifted-skill = no QA run, friction on the wrong side.

**Also open:**
- **#89** (QA's METHOD.md rule-3 seam) — verified `git apply --check`-clean against blob `3e32b24` =
  *then*-current `origin/main:METHOD.md`. **That verification decays with every merge.** #89 must precede
  Code's rule-3 ledger PR (same list, adjacent bullets), and if the rename lands first, **re-run
  `git apply --check`** before applying.
- **Code's rule-3 ledger PR** — fixture-provenance + M6 + the #88-stale-status miss. Two entries, per the
  reframe: Code's rule-3 slice, and the two-homes structural gap (different lessons).
- **The rename PR** (§1).
- **The `docs/qa-config/` deletion** (§3) — on the stamp's critical path.

## 5. What only this seat is carrying

- **The CLAUDE.md consolidation findings list**
  (`2026-07-16-claude-md-consolidation-design-seat-findings.md`) — deferred until after the folds, by ruling.
  Three items in it are load-bearing and nobody else has raised them:
  - **The firewall's three clauses have three different enforcement levels and the doc states them as one.**
    "Reads the detector's bucket / `portfolio.yaml`" → IAM-enforced. "Places or sizes a trade" → capability
    absence. **"Recommends a trade" → prose.** Nothing stops the sender rendering *"BUY XLK"* tomorrow — and
    that's the clause closest to the actual risk: the system was never going to place a trade, it was going to
    **talk the operator into one**. An overclaimed wall is the defect being fixed elsewhere in the same doc.
  - **The scar-tissue protected list** — the clauses that must survive a consolidation byte-identical or with
    a named record. They read as clutter precisely because their scars aren't visible in their text.
  - **What's missing is bigger than what's stale** — CLAUDE.md never mentions the QA seat, Option-2
    composition, the register's maintenance gate, or "every fix ships its violation test."
- **METHOD.md amendments pending:** rule-3's QA seam (#89) and Code's ledger (2 entries). Also flagged:
  the *"a stale read-only snapshot of **the code**"* line — it's now the code **and** the record.
- **The activation checklist design note** — build it with the rev16 fold; the item set is final by then.
- **The on-Mini verification set** and **the armed byte-compare gate before capture arms** — the two things a
  green CI can never cover.

## 6. This seat's limits (so the next one doesn't over-trust it)

Frozen snapshot; no commits, no diffs, no enumeration — **a search hit is a lead, not a verdict**, and every
claim carries an as-of. **Ask for a re-sync** rather than reasoning from a stale one; it costs the owner ~30
seconds and he'll forget otherwise. And the ledger entry is accurate: this seat's **document-claims are the
ones no seat is bound to catch** — the checks in this doc are the ones a reader should run first.

## 7. The line to hold

**v1 is build-complete. The instrument is done; the measurement hasn't started.** FDR unmeasured, dispersion
n=1, burn-in barely begun, flow-vs-structure open — and none of them resolve by building. The register's only
QUEUED item is **the on-Mini activation**, and it isn't a build: install the launchd job, bless the drives,
watch the first scheduled tick. **That single action is what stands between build-complete and *running*, and
nothing in §4 moves it.**

**On this week's shape, worth handing forward.** Every item in §4 is infrastructure with a **terminus** — the
consolidation ends when the findings list closes; the QA-skill arc ends when rule 3's QA slice becomes a gate;
the rename ends after two `git mv`s. That's what separates it from elaboration. The test for anything **new**:
*name what it enables.* A build or a decision → infrastructure. "A cleaner version of itself" → the named risk,
which always feels justified from the inside; that's what makes it a risk rather than a mistake.

The investment side is quiet right now **because every mechanism built to make it quiet is working** —
burn-in is calendar-bound, rebalancing is band-triggered and deposit-directed, exits are thesis-based. It is
demanding nothing, which is the one job it was given. The uncomfortable corollary: **attention flows to
whatever always has more to do.** One track is blocked by a calendar; the other is infinitely elaborable.
That's a structural pressure, not a character flaw — and the remedy is structural too: **a terminus per item,
named before starting.**
