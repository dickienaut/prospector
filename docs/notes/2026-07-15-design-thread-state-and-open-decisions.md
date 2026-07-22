# Design-thread state — decided, open, and queued (2026-07-15)

*A capture at an offline break, so nothing is lost and the open calls are thinkable away from the keyboard.
**As-of caveat:** written from the design seat, which sees a frozen code snapshot and whatever was pasted in.
PR numbers and register statuses were current when reported by the build seat; the live repo is the source of
truth. Filed to `notes/` — this describes, it doesn't ratify. The rulings below each have (or will have) their
own decision record; this is the index over them.*

---

## Part 1 — Decided (do not re-litigate; reasoning compressed)

**Tier-4 sweep** — 13 register items → 5 real fixes (H3 with a *mandatory* negative test, S5, lag-lexical-sort,
sql-assert, BK-MSG-01), 6 drift-corrections (already fixed on main — the register had gone false-open), 2
dispositions, 1 rider. **Eigengap → 💤 parked** with a gate: answered at the *dispersion promotion review*,
not now — tuning sensitivity during the sensor's own burn-in contaminates the observation, and the fossils make
the gap **retroactively computable**, so the floor gets set from measured gap-vs-outcome data instead of a
guess. **Token-substring → not-a-defect**, with the scope line attached: *stem-matcher over a curated table,
backtest-only — do not reuse on uncurated input without revisiting* (a disposition without its boundary becomes
a wrong precedent). **BK-READ-01 → 🟡 ratified-residual** (correctness over cost at current scale; revisit
trigger: backup wall-time > ~1 min, or store growth making the re-read minutes-long).

**M7-04/06 single-writer lock** — one lock, two acquirers. `flock` at the store root; **in-runner, not in
`run.sh`** (covers the manual `pros run`, which is the realistic collision); refuse-loudly-and-write-nothing;
flock-not-PID-file (kernel releases on death → `kickstart -k` stays safe by construction); `busy_timeout` belt.
**Deviation accepted and better than the note:** macOS has no shell `flock(1)`, so `deploy.sh` reuses the
runtime's own lock via `pros store lock-run` — one code path, not two agreeing implementations. On-Mini rider:
**assert `pros store lock-path` is identical from both checkouts** (pins the shared-store assumption the
dev-side lock stands on).

**CAP-DRIFT** — byte-exact stays; the ruling is an **ordered gate, not a menu**: observe one live armed call →
byte-exact stands if the echo is clean → only a *demonstrated* transform earns a normalization **scoped to
exactly that transform**, documented as a finding. 🟡 ratified-residual, gated on the armed byte-compare
**before capture arms**. CAP-USD closed (loud fault when `unit_price_usd` is unpriced).

**PAGE-WORTHY-MIRROR** — the §10 page-worthiness predicate lifted to one home (`runner/fault_taxonomy.py`);
duplication was import-graph-forced, not laziness. **No agreement test by design** — tautological post-lift
(cf. LOCK-TEST-TAUT); the structure is the guard. PR #73.

**Git strategy** — merge commits, not squash (the commits are clean and atomic; the full history is
informative; squash rewrites the record, which cuts against append-only). **[Corrected 2026-07-21, P-3: rebase-merge is now
disabled at the repo level too — both `allow_rebase_merge` and `allow_squash_merge` are OFF, merge-commits
only — so the "Update with rebase" button no longer exists.]** When a branch falls behind, update it via
GitHub's "Update with merge commit" (the back-merge commit is the accepted cost of the append-only trail)
or a local rebase + force-push. **Keep strict-up-to-date** (it's the gate that catches composition failures: branch green + main green
+ merged result broken).

**Bug archive → retrieval system** — `README.md` = doctrine (stable), `INDEX.md` = register (volatile, greppable).
Boundary is **distilled-vs-raw**, not resolved-vs-open (status is a column, not a gate — an open row in your
subsystem is the highest-value hit). Findings **distill** (author a per-bug record) rather than relocate; the
review stays whole in `notes/`. Two tag axes: subsystem · failure-shape. Maintenance gate: *a fix isn't done
until its row is current.*

**Process** — Option-2 composition (QA proposes RED test + reference patch; Code applies; `xfail(strict)`
handoff so the gate never goes red). **Dispatch is transport, not a seat** (never interprets findings, never
picks the branch; prompts are minimal skill invocations; *the summary is the doorbell, the PR is the package*).
**QA cadence:** per-PR always, plus a sweep at natural consolidation points — not on a timer.

**The four-seat doc** — QA's revision adopted: the enforced/aspired tier split, "the reviewer is a generator
too," the record-anchored-outside-itself discipline, and the honest cost that *the checker covers the artifact,
not the belief it encodes.*

---

## Part 2 — Open decisions (yours; each with the fork and a lean)

**1. `reviewed_sha` — required or optional?** QA built the provenance guard (delivery raises with zero writes if
the reviewed commit ≠ the branch head), but left it **optional for back-compat**, so `reviewed_sha=None` →
`provenance_enforced=False`. *Lean: make it required, remove the default.* An optional guard is discipline
wearing a mechanism's clothes — the seat must remember to pass it, which is the structure that just failed. And
"back-compat" protects nothing: one caller, in a skill being edited in the same breath, no external consumer.
The default exists solely to let the one seat the guard binds opt out of the guard — the no-bypass-actors
argument, third instance this month.

**2. Injectable transport for `deliver_qa_findings_pr`.** It does a *local* `import requests` inside the
function, so testing requires monkeypatching — and a monkeypatch can fail **open**, into a live write token
(it did: PR #74 / branch `qa/x`, since cleaned). *Lean: make the transport a parameter*, the way `run_tick(deps)`
takes `price_fetch` and `notifier` — then the test injects a fake and there's no path to the real API to
remember to block. Fail-closed by construction, in the one harness holding write credentials.

**3. CI gate re-running `verify_red_green` on findings PRs.** QA offered to draft it as a finding PR. This is
the graduation that moves the RED/GREEN membrane from a pre-flight the seat runs to a gate it cannot skip.
*Lean: yes, but sequence it after the permissions work* — it's a workflow file + a branch rule, and the rules
are about to change.

**4. Rule 2 in the four-seat doc.** It sits in **Enforced** and shouldn't: *"policy where it could be
capability"* under a header reading "a gate a stochastic seat physically cannot cross." Blocked on the identity
split (see Part 5). *Lean: leave as-is if the permissions work lands soon — then move it up-tier at that
moment, which demonstrates rule 5 live rather than describing it. If you share the doc before then, it's a
one-line fix: move it down, name the identity blocker.* Deferred by you already; recorded, not re-raised.

**5. Doc reconciliation** (rule 2 moved, the record-anchoring point folded into stateless-seats, length trimmed
back toward a three-minute read). Offered, not done. Only matters if you're about to share it.

---

## Part 3 — Queued work (no decision needed — execution only)

- **Tier-4 sweep PR** → one QA dispatch over the branch.
- **rev15 spec fold + state rev8 + the doc debt** (DRIFT-1/2, C.2) — one session; build-complete is the natural
  fold moment because it records a *stable* state.
- **Activation checklist** — build it with the rev15 fold (design note is written: challenge–response items with
  observed values, two witnesses per critical item, T.O./781 split, no-go gates marked).
- **The on-Mini verification set** — first unattended scheduled run; dead-man's human loop; HDD bless → first
  backup → `verify-restore` with counts matching; `deploy.sh` refusal under a held lock; dual `lock-path`.
  *Prove it once; don't assume.*
- Node-20 CI action bump; stale-branch cleanup.

**Gates before capture arms:** the one live armed byte-compare (CAP-DRIFT) · API key in **both** checkouts'
`.env` · `capture.monthly_budget_usd` set.

---

## Part 4 — Parked by decision, tripwired (closed as decisions — not open)

N9 cadence gate and E2 flapping window (both `xfail(strict)` — flip to a loud XPASS the day they land) · BK-3
checksum (deferred; a **scheduled `verify-restore` is the better instrument** — it proves the backup is
*usable*, not merely unchanged) · eigengap (💤, promotion-review gate) · B1/B2, R3 residuals · **M7-hardening:**
infra-as-code, WAL-checkpoint-out, offsite S3/Backblaze, bit-rot checksums.

*Un-parking any of these to green the board is completionism, not consolidation. Greenness isn't the goal;
decidedness is.*

---

## Part 5 — The permissions scoping (banked thinking, for the offline consideration)

**The problem, stated plainly:** every seat currently holds **your** GitHub identity. So every seat has maximum
privilege, and **every restraint in the system is instructed rather than structural** — the largest remaining
"policy where it could be capability" surface in the project. QA's helper *does* enforce its own limits (no
merge call, `qa/*`-only pushes), so it's mechanism for QA and policy for Code. That asymmetry is itself the
tell.

**What each seat actually needs** (falls out of what each does):
- **Design** — nothing. It's blind by design and touches no repo.
- **Code** — push to feature branches. Not merge. Not force-push. Not main.
- **QA** — push to `qa/*`. Not merge. Not main.
- **Dispatch** — nothing of its own; it drives QA's browser, so it acts *as* QA.

**The prerequisite chain, which is the non-obvious part:** rule 2's graduation is **not** "add a required
approval" — that alone **deadlocks**. GitHub forbids self-approval, and there's exactly one identity in the
repo, which is why `required_approving_review_count` is 0 today. The chain is: **separate identities → require
one approval → "the human disposes" becomes structural instead of instructed.** So rule 2 isn't a separate item
on the board; it's a *byproduct* of the permissions work.

**Open questions inside it, worth thinking about offline:**
- **GitHub App vs. machine user?** An App scopes permissions finely and isn't a "person"; a machine user is
  simpler but occupies a seat and needs its own credentials. The approval mechanic may decide it — an App's
  reviews behave differently from a user's.
- **Where does the token live?** QA's helper holds a PAT today; per-seat identity means per-seat secrets, per
  checkout, with the `.env` discipline extended.
- **What breaks when a seat is blocked mid-work?** The cost of scoping is that a legitimate action can fail at
  an inconvenient moment. Prefer that to the alternative — but know it's the cost.
- **Does the CI-gate work (Part 2 #3) wait on this?** Probably yes: it's a branch rule, and the rules change.

---

## Part 6 — Where it stands

**v1 is build-complete and deployed** — both spawners live (xcorr paging; dispersion in shadow burn-in), the
§10 sender honest from both directions, the store backed to dual HDDs, a mechanical merge gate, the monitor
running itself off a worktree pinned at `v1.0.2` with the dead-man armed. **Free-standing** is one sweep + one
doc fold away: every register row ✅ or explicitly parked-with-a-tripwire.

**The line to hold:** build-complete is a finish line *and* a starting line. What finished is the *instrument*.
The false-discovery rate is still unmeasured, dispersion is still n=1, flow-vs-structure is still open — and
none of those resolve by building. The posture is **let it run**.

**On the horizon, not now:** the permissions scoping → M6's remaining arming gates → then v2 (proto-clusters,
discourse interpretation), whose grounding is already banked in
`deferred/2026-07-11-v2-research-grounding-flow-vs-structure.md`. The two ideas most worth not losing there:
the **flow-vs-structure discriminator** and **launch-as-consensus-clock**.
