# Design-seat record — 2026-07-11 to 2026-07-13

*What the design/review seat (this thread) did and discovered over the stretch that took Prospector from §10
completion to **v1 build-complete**. Written to preserve the *reasoning*, not just the outcomes — the outcomes
are in the decision records and the state doc (rev 7); this captures why each call went the way it did, and the
durable learnings worth mining later. The implementation side (build details, the crash-recovery mechanics,
the adversarial-panel finds) is Code's to record separately. Read cold: each entry gives enough context to
stand on its own.*

---

## The arc in one paragraph

The §10 email sender was finished and made honest from both directions (two alarm-layer bugs caught and
ruled). The docs were put under two new constitutional rules (amend-never-regenerate, born-dated naming) and
reorganized; an INDEX was written; the repo became the single source of truth. A CI test-gate + branch-
protection ruleset was specced and stood up — the tests became a *mechanical* merge gate. The v1 finish was
sequenced (autonomy before discourse), three build notes were written (rebalance, backup, M7 core), and their
design forks resolved. A literature scan reframed the v2 scientific question and was banked as a deferred note.
A hedge-fund technical briefing was written, fact-checked (catching two of the design seat's own errors), and
finished. Production came up on a pinned release via a git worktree, launchd armed the dead-man, and **v1 is
build-complete** — the instrument finished, the multi-year run begun.

---

## Part 1 — Decisions & rulings (the design-seat calls, with reasoning)

**§10 volatile-message suppression (ruling).** QA found the nuisance-suppression defeated on the live path: a
persistent lapsed-sub 403 rendered a different message each tick (the Tiingo URL carries moving dates), so it
paged daily — the GPWS "cried wolf" failure §10 exists to prevent. Ruled: adopt the stable-key fix (separate
suppression key from display message; `_fault_signature` keys on `(subsystem, key or message)`; the two
URL-bearing price sites key on `(ticker, status)`). The granularity *is* the contract — `(ticker, status)`
beats a coarser `(subsystem, status)` because it pages a *new specific* failure rather than swallowing it.
Added two things QA hadn't: a **ticker-dimension guard test** (so neither dimension of the key can be silently
coarsened later) and a **`key=` convention at the emit site** (so a future volatile-message fault doesn't
silently reopen the gap). Deferred the flapping-fault (E2) case as `xfail(strict)`.

**§10 fault taxonomy / advisory-posture (ruling → §8a CONTRACT).** The "0 faults while 9 fired" symptom traced
to a *split write path*: mandate/SOI advisories were written straight to the store, bypassing the runner's
per-tick list, so they neither counted nor reached the push decision. Ruled: one fault accumulator, each fault
tagged `operational | review-advisory` + `on_live_lead`; `_compute_push` pages the page-worthy subset —
**operational faults, plus advisories on a fund touching a live lead** (the risk-owner's call); everything else
advisory is counted-and-surfaced but doesn't page. The shape is the shadow-push fix one layer down: keep the
record whole, filter page-worthiness at the decision. This is now a recorded CONTRACT.

**Docs — amend-never-regenerate (formalized into CLAUDE.md).** Elevated a one-off judgment (amend the spec,
don't regenerate it) into a standing rule: canonical contract/reference docs change by surgical diff +
appended changelog, never wholesale rewrite (which silently drifts contract text). Escape valve: a rewrite is
allowed *only* as a consolidation rev with a clause-by-clause diff proving nothing changed unintended. The
state doc is the partial exception (stable body amended; status rollup re-synthesized each rev).

**Docs — born-dated naming (formalized into CLAUDE.md).** Every doc born with a leading ISO date; `-revN` only
on a versioned series (each rev a new dated file, prior → `history/`); stable-named exceptions (CLAUDE.md,
INDEX.md, ARCHITECTURE.md, package READMEs) amended in place. **Forward-only** — governs new files, never a
bulk rename, because renaming breaks the filename-references the reorg preserved.

**Docs reorganization (reviewed, affirmed).** The by-kind grouping with current docs at root was sound; the
deeper win was that it was a stress-test of three rules at once (move-never-rewrite via `git mv R100` =
amend-never-regenerate; relocate-never-rename = references survive; the one un-fixable fossil path-drift
*documented* not edited = the fossil rule beating "fix all refs"). Flagged the rho-G *deletion* as the one
place the reorg stepped outside its own move-everything principle → resolved by moving it to `origins/`.

**Bug-README review + the scope-creep episode.** Reviewed the bug archive as a "bug epistemology" (genealogy
not graveyard; classes as early-warning; severity-as-axis). Proposed four *bounded* refinements. A separate
thread then elaborated them (a four-level split, stable slug IDs, a survivorship line, a new class); walled
that back to the bounded set with an explicit §5 scope-guard in the spec. Key structural call: re-shelve §1
into taggable-classes vs frame **preserving the numbers as stable IDs** (renumbering would break the §2 Class-
column references — the taxonomy's version of relocate-never-rename).

**CI + branch-protection (specced).** Wrote the setup spec: the Actions workflow (offline suite as the gate,
no secrets by design), the ruleset (require-PR, require `test`, no force-push, no bypass), the ordering gotcha
(workflow must run on `main` before the check is selectable), and the two silent-failure guards — **moto must
install or the S3 tests skip green** (false gate), and **no self-bypass** (a bypassable ruleset is theater).

**v1 finish sequencing (decision).** Chose **autonomy before discourse** (M7 core before M6) against the
register order: M7 is the core value switch-on (the monitor runs itself, the dead-man arms); M6 is v2
scaffolding whose consumer doesn't exist yet. Accepted a discourse burn-in as the cost of front-loading M6
later. Split M7 into a thin autonomy *core* (scheduling + dead-man + concurrent-read) vs deferred *hardening*.

**Dead-man design (Lyle changed my mind).** I leaned *strong* (an external healthcheck that alerts on a missed
run). Lyle's counter — a 20-year dependency on an external service is exactly what the project refuses
everywhere else — was the more project-consistent argument, and I conceded. Landed on the **weak** version made
reliable without external dependency: explicit OK/DEGRADED health in the heartbeat email + a *self-owned*
recurring calendar reminder timed to the expected heartbeat, so absence prompts a check. Honest residual
accepted and documented.

**Deploy topology (worktree + tag).** Chose a git worktree pinned at a release tag over two clones. Reasoning:
two lookalike clones is safety-by-vigilance (remember which is which, for 20 years); a worktree *dissolves* the
confusion — one repo, one `.git`, two checkouts at different commits — so "production runs frozen released
code" is a structural fact, not a remembered rule. Handed Code two enforcement points: the plist's
`WorkingDirectory` points at the worktree, and `deploy.sh` refuses to pin to anything but a tag.

**Machine-local config (ruling).** `store.root`/`backup.targets` are per-machine → gitignored overlay. But
`edgar.user_agent` (the SEC contact) is *deployment identity*, not machine-specific — the same on any box — so
it belongs in the **tracked default**, not the overlay. The principle that keeps the overlay self-explaining:
overlay = strictly per-machine paths, tracked = identity + shared. Option 2 (keep the personal gmail as the
default, override per machine) would tax *every* deployment forever to preserve a default that's wrong for any
real deployment.

**Plist shape (ruling).** One plist + wrapper-decides-the-day, not two plists. The real reason is dead-man
semantics: two independently-failing scheduled entities mean a broken Sunday plist kills the heartbeat while
the daily runs continue — silence stops unambiguously meaning "the runner is dead." One plist = one entity: if
it fires everything fires, if it dies everything dies. The channel whose whole job is unambiguous absence can't
have ambiguity injected into it.

---

## Part 2 — Discoveries & durable learnings (the part worth mining)

**The operating culture: failure is learning, bounded.** The frame over everything below, stated plainly so it
survives: this is a culture of feedback, learning, and curiosity — *not* a culture afraid to try things because
they might fail. Failure is how you learn; the falling *is* the process, the way a child learning to walk falls
constantly because the falls are the path to walking, not a detour from it. The goal is not zero failure — it's
to **fail less and less often, and to bound the blast radius when we do.** Two things make that boldness safe,
and they move together: (a) **ruthless, mechanical verification** — bold on the ideas, strict on the checking,
and the boldness is safe *precisely because* the checking is non-negotiable (if the strictness ever softens,
the boldness stops being safe); and (b) **metabolizing every caught slip into a named pattern plus a
mechanical check**, so the net isn't static — each catch makes the next one faster. Bold hypotheses, ruthless
checking, named patterns: the culture that gets *more* reliable as it moves faster, which is the opposite of
how it usually goes. Take big swings; let the artifact get the last word.

**A blind-seat error surfaced and the cross-check caught it — the net working as designed.** The technical
briefing's first draft described Marchenko–Pastur *cleaning* and null-model *validation* as built; they're
planned/v2. But the honest diagnosis is not "the seat should have known better." The design seat is
**structurally blind to the repo by design** — it sees only what's dropped into the thread. Given the
surrounding discourse (the lit scan, the v2 notes) and *not* the artifact, writing from the discourse is the
only thing that thread could do: it's the predictable, *anticipated* consequence of a blind seat, not a lapse.
What matters is what happened next — two reviewers went to the primary source and the error never reached the
quant. That is the separation-plus-cross-check doing exactly its job, on schedule: **the net holding, not
barely surviving.** And because the pattern is now named (it joins green-on-synthetic and doc-drift-with-teeth),
the next catch is faster. So the lesson isn't "be more careful" — it's that the architecture *expects* the
blind seat and the cross-check closes the gap, which is exactly what *licenses* reaching further from a seat
working with incomplete information. The net was built *because* the seat is blind, not in spite of it; the net
working is a story about the net holding, not about a slip. (Convergent-prior class, bug-README §2 — now
observed to operate on reasoning, not only code, and closed by the same primary-source discipline.)

**Mechanism over vigilance — the through-line of everything built.** The branch-protection ruleset, the
never-execute firewall, the worktree/deploy-from-tag, the config-hash-over-merged-result, `deploy.sh`
refusing non-tags, one-plist-so-absence-is-unambiguous: every one is the same move — **make the safe thing
structural instead of remembered.** The governing reason, stated repeatedly and worth keeping: a 20-year
personal system *cannot* depend on the operator never being tired. Whenever a choice was between a discipline
you apply and a mechanism that enforces it, the mechanism won.

**The dead-man was latent until the scheduler existed.** "Silence past 7 days = broken" is inert until
something runs the runner on a cadence — the whole §10 dead-man layer was *built but not armed* until M7's
launchd landed. Worth remembering as a general shape: a monitor that watches for its own death only becomes
real when something external to the watched process drives it. The arming was the quiet-but-real payoff of the
whole M7 slice.

**The flow-vs-structure reframe (v2's real question).** The literature scan corrected the intuitive framing:
the enemy is *not* random noise hiding a signal — it's **reflexive fund flow mimicking structure** (Ponzi
Funds: a thematic ETF's own flow, 20× the underlying's daily volume, self-generates the co-movement, which
reverts). The apparent theme-correlation may *be* the crowd's money, not structure the crowd missed. And the
project is unusually well-aimed at beating exactly this: liquid large-caps where flow can't manufacture
correlation, and **lead measured before the fund vehicle exists** (which rules out that vehicle's flow by
construction) — the +593 (calendar; ~407 trading) day lead is the cleanest evidence of structure-ahead-of-flow.
The distinctive contribution is the *operationalization* (launch-as-consensus-clock + measured lead), not the
detection; the prior art it rests on is Ben-David et al. (specialized ETFs launch at peak hype, underperform).

**Growth model — grow the record freely, add process under duress.** The CAMS/IMDS discussion clarified that
Lyle wasn't reaching for a new system — the maintenance-system shape (immutable log, status tracking,
scheduled+reactive maintenance, deferred discrepancies, reliability trending) is *already in the project's
bones*. The caution that matters: CAMS/IMDS are also cautionary tales (rigid, bloated). Grow into the *rigor*
(auditability, config discipline, trending), not the *weight* (process bloat, sign-off theater). Concretely:
the record side compounds and is low-risk (grow it freely); formalized process is weight that must justify
itself (add only under real recurring pain). The CI gate earned itself out of "tests are the gate," not out of
"a real system would have CI."

**Spec-first is triggered by *untested state*, not by abstract complexity.** The repo-rearrange crash taught
the boundary precisely: a sensor slice is self-contained and CI-guarded; a rearrange touches the working tree,
the scheduler's `WorkingDirectory`, the deploy script, and two checkouts at once — **state no test covers
(filesystem, scheduler, git structure).** That's the shape that most needs a written plan before hands move,
because you can't lean on green CI to tell you it's right, and it's the shape where a mid-flight crash leaves
the worst mess. The tell for "spec this first" is not "is it complex" but "does it touch state no test covers."

**The append-only record paid off in the crash — as designed.** When Code errored mid-rearrange, a *brand-new
thread* reconstructed the entire state from disk and produced an accurate gap list — because the design had
been ratified in a decision doc *before* the crash. The writing-things-down discipline proved its value in the
exact scenario it exists for, including on the one task where the build spec was skipped.

**Honesty is the credibility, for a rigorous audience.** The briefing's fact-check confirmed the counter-
intuitive point: stating the March-2020 falsifier as the *routed classification it actually was* (2 of 3
criteria held; the third fired, 7/10 persisted; a pre-committed diagnostic dispositioned them "real but
off-thesis") reads *more* impressively to a quant than "tested and held" — because it's the falsifier visibly
working without post-hoc rationalization. Likewise the "in-sample by construction" disclosure attached to the
headline number, and the base-rate disclosure (2/98 corroboration, floor-limited) instead of adjectives. The
honesty that makes it credible also makes it hard to poach: funds reallocate for track records, not existence
proofs.

**Doc-drift has teeth, and CI doesn't catch it.** The adversarial panel caught a stale runbook that still told
operators to put machine-local config in the tracked file *after* the mechanism changed — following it would
have aborted the next deploy. A documentation-vs-mechanism disagreement where the doc wins at the worst moment
(bug-README class 9), catchable only by adversarial *reading*, not by the test suite. This is the standing
argument for the bug-README's lineage-check idea: docs describing a mechanism should be verified against it.

---

## Part 3 — Where it stands, and what's open

**v1 is build-complete.** Both spawners live (xcorr paging, dispersion in shadow burn-in), the sender honest,
the fossil record backed up to dual HDDs, a mechanical merge gate, docs under a naming law, a bug epistemology
that sharpens as it grows, and the monitor **running itself** off a pinned release (`v1.0.2`) it can't
accidentally un-pin, with the dead-man armed.

**The line to hold:** build-complete is a finish line *and* a starting line. What finished is the *instrument*.
What starts is the multi-year run that turns existence-proofs into rates — the false-discovery rate is still
unmeasured, dispersion is still n=1, flow-vs-structure is still open, and *none of those resolve by building.*
The immediate posture is **let it run**, not build the next thing.

**Open, none blocking:**
- *Confirm the autonomy holds* — watch the first *scheduled* (not manual) runs fire on their own; test the
  dead-man's human loop (the calendar backstop). Prove it the way the CI gate was proven: watch it work once.
- *Spec rev 15 fold* — the doc layer still carries §9e/§8b/§10/M7 in decision records. Build-complete is the
  natural moment to fold, because it records a *stable* state. (Lean: watch-first-then-fold — the spec should
  record a state confirmed real.)
- Stale-branch cleanup (Code owes ~4 merged branches); the non-blocking Node-20 CI action bump.

**On the horizon, not now:** M6 (discourse capture, front-loaded for v2), then v2 itself — the proto-cluster
and discourse layers — with the flow-vs-structure grounding already banked in
`deferred/2026-07-11-v2-research-grounding-flow-vs-structure.md`. Those wait.
