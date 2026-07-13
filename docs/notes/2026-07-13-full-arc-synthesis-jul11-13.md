# Full-arc synthesis — 2026-07-11 to 2026-07-13 (design seat + build seat)

*A **synthesis**. This document merges the two seat records of the stretch that took Prospector from §10
completion to **v1 build-complete and deployed** — the design-seat record
(`2026-07-13-design-seat-record-jul11-13.md`: the rulings and the *why*) and the build-seat record
(`2026-07-13-build-seat-record-jul11-13.md`: the slices and the *how*). **Those two remain the canonical
seat records**; this is the derived, single narrative over them — each decision fused with its build, and the
learnings deduplicated, with the places where **both seats independently hit the same pattern** surfaced as
the strongest signals of the stretch. Deeper reasoning lives in the decision records under `docs/decisions/`.
Read cold: each entry stands on its own.*

---

## The arc in one paragraph

The §10 email sender was finished and made honest from both directions — a QA-caught suppression bug (volatile
fault messages defeating the nuisance gate) and a split-write-path taxonomy bug ("0 faults" beside nine
advisories) were each ruled on and fixed, producing the §8a advisory-posture CONTRACT. The docs came under two
new constitutional rules (amend-never-regenerate; born-dated naming), were reorganized by kind with an INDEX
front door, and the repo became the single source of truth. A CI test-gate + branch-protection ruleset made
the test suite a *mechanical* merge gate — catching two of its own setup gaps on the way up. The v1 finish was
re-sequenced (autonomy before discourse), and three slices shipped through the new gate: the rebalance sensor
wired into the runner (completing the M4 sensor phase), a dual-HDD fossil-store backup, and the M7 autonomy
core (launchd + wrapper + one plist) that armed the dead-man. Production stood up, hit a two-clones footgun,
and was rebuilt as a git worktree pinned at a release tag with a tag-only `deploy.sh`; a mid-rearrange crash
was recovered by a fresh thread reading state off disk; machine-local config moved to an untracked overlay
with the config hash folded over the merged result. A hedge-fund technical briefing was written, fact-checked
across seats (catching the design seat's own aspirational-as-built claims), and finished; the v2
flow-vs-structure grounding was banked as a deferred note. Three tags were cut; the scheduler runs the
worktree at **`v1.0.2`**, a release it can't accidentally un-pin. **v1 is build-complete** — the instrument
finished, the multi-year run begun.

---

## Part 1 — The work: each decision fused with its build

**§10 made honest from both directions.** *Suppression:* QA reproduced the live-path bug — a persistent
lapsed-sub 403 renders a different message each tick (the Tiingo URL carries moving dates) → a new signature →
pages daily, the GPWS "cried wolf" §10 exists to prevent. Ruled and built: a stable suppression key separate
from the display message (`_fault_signature` on `(subsystem, key or message)`; the URL-bearing price sites key
`(ticker, status)`), with the design seat adding a ticker-dimension guard test (neither key dimension can be
silently coarsened later) and a `key=` convention at the emit site; E2 (flapping) deferred as `xfail(strict)`.
*Taxonomy:* "0 faults while 9 fired" traced to a split write path — mandate/SOI advisories bypassed the
runner's per-tick list, so they neither counted nor reached the push decision. Ruled and built as the
shadow-push shape one layer down: one fault accumulator, `category` (`operational | review-advisory`) +
`on_live_lead` tags, `_compute_push` paging operational faults **plus advisories on a fund touching a live
lead** (the risk-owner's call); everything else counted-and-surfaced, never paged. Confirmed live:
`faults=9, pushed=False` on the iShares launch wave. Now the recorded §8a advisory-posture CONTRACT.

**The doc constitution.** Two rules formalized into CLAUDE.md: **amend-never-regenerate** (canonical docs
change by surgical diff + appended changelog; a rewrite only as a consolidation rev with a clause-by-clause
diff) and **born-dated naming** (leading ISO date on every new doc; `-revN` only on versioned series, each rev
a new file; forward-only — never a bulk rename, because references resolve by filename). The reorg that
followed was a stress-test of three rules at once — move-never-rewrite (`git mv R100`),
relocate-never-rename, and the one un-fixable fossil path-drift *documented rather than edited* — and they
held and compounded. The bug-README was reviewed as a *bug epistemology* (genealogy not graveyard; classes as
early-warning; severity-as-silence-axis), its refinements scope-guarded against a parallel thread's
elaborations, and its §1 re-shelved preserving class numbers as stable IDs.

**The mechanical merge gate.** The CI workflow (`uv sync --locked` → `pytest -ra` → `pros --help`; no secrets
by design — the suite is offline) plus the `main` ruleset (require-PR, require `test`, block force-push,
**no bypass actor** — a ruleset the owner can bypass is theater). The gate caught two of its own setup gaps
immediately: the lockfile was gitignored (nothing to `--locked` against) and the default sync silently skipped
3 dashboard tests — a partial green, the exact false-gate the spec warned about — fixed to 0 skips. Proven by
a deliberately-red PR showing `BLOCKED`.

**v1 finish re-sequenced: autonomy before discourse.** M7's core (the monitor running itself, the dead-man
arming) is the value switch-on; M6 (discourse capture) is v2 scaffolding whose consumer doesn't exist yet — so
M7-core jumped the queue, split thin (scheduling + dead-man + concurrent-read now; hardening deferred until a
real pain earns it). A discourse burn-in was accepted as the cost.

**Rebalance wired — the M4 sensor phase completed.** A wiring slice over the §9e frozen holdings (never a
re-fetch). Three forks resolved: **(1)** the active-lead set *includes shadow leads* — a deliberate sibling
resolver (`active_incl_shadow_lead_ids`) beside the non-shadow helper, because rebalance is accretion and
never pages, so the shadow wall protecting the paging paths doesn't apply — and every dispersion lead is
currently shadow, so the non-shadow filter would sever rebalance from the entire dispersion side; guarded by a
violation-test where a basket's *only* lead is shadow. **(2)** **Seed silently on first sight** — this
*corrected the build note*, whose "no prior snapshot → fault" would have paged ~11 baskets on the first tick
(a day-one nuisance-alarm generator); fault only a genuinely broken feed, with two violation-tests pointing in
opposite directions. **(3)** A same-tick spawn+rebalance routes to `_system` and accretes from the next tick —
kept deliberately (self-correcting, rare) rather than amending §4d, because re-folding to catch it would
reintroduce the re-fold-divergence risk the materialized-fold invariant forbids.

**Store durability — the irreplaceable asset backed up.** The fossil store is the one asset that is both
irreplaceable (two years of holdings/prices/filings *as they were on those days* cannot be re-fetched) and —
until this slice — un-backed-up; code and docs live in distributed git, the store does not. `pros backup`
rsync-mirrors the fossil trees to both HDDs and safe-copies the WAL registry via the native `.backup()` API;
`pros store verify-restore` makes the restore test a first-class command (an untested backup is a hope, not a
backup). Build corrections that mattered: **`registry/` included in the fossil trees** (reindex never rebuilds
the `funds` table — fund identity was about to be left un-backed-up), and a **per-drive blessing marker**
(on macOS an unplugged drive's mount point vanishes; a naive `mkdir -p` would "back up" onto the boot disk —
the marker turns an unplugged drive into a loud fault). Best-effort-but-loud across targets. Offsite (S3) is
named M7-hardening, deferred.

**M7 autonomy core — the monitor runs itself; the dead-man arms.** **launchd, not cron** (cron silently skips
a job if the Mac slept; launchd runs it on wake — the difference between "ran late" and "silently didn't").
A wrapper script absorbs launchd's minimal environment (the classic `uv`/`.env`-not-found failures) and wires
the backup cadence: `pros run [--heartbeat] && pros backup`. **One plist, wrapper decides the heartbeat day —
for dead-man semantics:** one scheduled entity means a missing heartbeat unambiguously attests "the runner is
dead"; two plists would let a broken Sunday entity kill the heartbeat while dailies continue, injecting
ambiguity into the one channel whose whole job is unambiguous absence. The heartbeat gained an explicit
**OK / DEGRADED** health line (the §10 summary-honesty rule applied to the heartbeat's own line). The dead-man
itself is the **weak, self-owned version** — the design seat leaned strong (external healthcheck) and was
talked out of it: a 20-year dependency on an external service is exactly what the project refuses everywhere
else. Heartbeat-health-in-email + a self-owned calendar backstop; honest residual accepted and documented.

**Production topology — from footgun to structure.** Deploy-from-tag was first built as a second full clone
and produced the failure it invites the moment it existed: the owner edited dev, ran production, and couldn't
tell why nothing changed — two lookalike repos, two stores, "which is live?" Diagnosed as
discipline-by-vigilance and rebuilt as a **git worktree** pinned detached at a release tag — one repo, one
`.git`, two checkouts, so "production runs frozen released code" is a *structural fact*. `ops/deploy.sh <tag>`
is the one deploy command: **tag-only** (refuses any non-tag ref, so production can never pin to a moving ref)
and config-preserving; the plist's `WorkingDirectory` points at the worktree — that pointer *is* the
isolation. A mid-rearrange crash was recovered by a brand-new thread reconstructing the entire state from disk
against the pre-ratified decision doc, producing an accurate gap list (the `deploy.sh` default still pointed
at the old path). The layout consolidated to `~/prospector/{dev,prod,store}` with the store external to both
checkouts — no worktree or tag operation can ever touch the fossil record.

**Machine-local config — the overlay and the identity line.** Machine-local paths (`store.root`,
`backup.targets`) moved to an untracked, gitignored `config/prospector.local.yaml`, deep-merged at one choke
point — the config analog of `.env`. The CONTRACT fold: **the config hash is computed over the *merged*
result**, so `config.changed` fossilizes exactly the config a run used. The dividing line drawn: secrets stay
`.env`-only and never fossilize; paths belong in config and *should* fossilize when they change; and
`edgar.user_agent` is deployment **identity** — invariant across machines — so it went to the *tracked
default*, keeping the overlay purely per-machine (the categorization stays self-explaining). The migration was
hash-preserving, pinned by a test. Symptomatically, the whole decision was driven by a broken test — the
machine-local edit in the tracked file tripped the pin on shipped defaults — the seam paying for itself loudly.

**The external briefing and the v2 grounding.** A hedge-fund technical briefing was written to the project's
Known/Thought/Unknown standard, then fact-checked across seats: the reviews caught the design seat describing
Marchenko–Pastur cleaning and null-model validation as *built* (they're planned/v2 — see Part 2), plus six
precision fixes (calendar-vs-trading days on the +593 lead; the March-2020 falsifier restated as the routed
classification it actually was — 2 of 3 criteria held, 7/10 persisted, pre-committed diagnostic dispositioned
"real but off-thesis"; the in-sample-by-construction disclosure attached to the headline number; the TEKX
inception date verified against the issuer). The counter-intuitive confirmation: stated precisely, the
falsifier story reads *stronger* to a quant, not weaker. Separately, a literature scan reframed v2's central
question — the enemy is not noise hiding signal but **reflexive flow mimicking structure** (Ponzi Funds) — and
established why the project is unusually well-aimed at beating that null (liquid large-caps; lead measured
*before the fund vehicle exists*); banked with references in
`deferred/2026-07-11-v2-research-grounding-flow-vs-structure.md`.

**Three tags.** `v1.0.0` (build-complete) → `v1.0.1` (running deployment, worktree) → `v1.0.2` (consolidated
layout + config overlay). The scheduler runs the worktree at **`v1.0.2`**.

---

## Part 2 — Durable learnings (convergent findings first — both seats hit these independently)

**The operating culture: failure is learning, bounded.** The frame over everything below. This is a culture of
feedback, learning, and curiosity — not one afraid to try things because they might fail. Failure is how you
learn; the falling *is* the process, the way a child learning to walk falls constantly because the falls are
the path, not a detour. The goal is not zero failure — it is to **fail less and less often, and to bound the
blast radius when we do.** Two things make the boldness safe, and they move together: ruthless mechanical
verification (bold on ideas, strict on checking — the boldness is safe *precisely because* the checking is
non-negotiable), and metabolizing every caught slip into a named pattern plus a mechanical check, so each
catch makes the next one faster. Take big swings; let the artifact get the last word.

**Mechanism over vigilance — named independently by both seats as the through-line.** Every load-bearing
choice of the stretch is the same move: convert a discipline-you-remember into a structure-that-holds. The
ruleset with no bypass actor; `deploy.sh` refusing non-tags; the worktree dissolving (not managing) the
two-clones confusion; the config hash over the merged result; the blessing marker turning an unplugged drive
into a loud fault; one-plist-so-absence-is-unambiguous; the never-execute firewall enforced by test. The
governing reason: a 20-year personal system cannot depend on the operator never being tired.

**The signature failure generalized twice — same class, two new substrates.** The project's named failure
("green on the shared prior / synthetic, wrong against the artifact / real substrate") surfaced in two places
it had never been seen: **on the design seat's reasoning** — the briefing described MP-cleaning and null
models as built because they lived in the surrounding discourse, and a structurally repo-blind seat writing
from the discourse is the *anticipated* consequence of blindness, caught because two reviewers went to the
artifact — and **on real deployment media** — the backup's mtime skip-check held on the dev disk and re-copied
everything on the real HDDs (exFAT timestamp granularity), catchable only by running against the real drives.
The class now spans code, reasoning, and hardware; the countermeasure is the same everywhere: primary source,
real substrate, artifact gets the last word.

**The net holding — verification-by-artifact catches what CI structurally cannot.** Seven catches this
stretch, none by the suite: the briefing's aspirational-as-built claims (two reviewers, primary source);
`registry/` omitted from the backup trees (fund identity nearly left un-backed-up); first-sight seeding that
would have paged ~11 baskets on day one; a stale runbook that would have *aborted the next deploy* (doc-drift
with teeth — the doc wins at the worst moment); machine-local config breaking the shipped-defaults test (the
symptom that drove the overlay); the two-clones footgun producing its failure immediately; the CI gate's own
two setup gaps. The lesson is structural, not moral: the separation-plus-cross-check *is* the safety net, the
net held every time, and each catch is now a named pattern that makes the next one faster. This is what
licenses reaching further from a seat working with incomplete information.

**Spec-first is triggered by *untested state*, not abstract complexity — both seats, from the crash.** A
sensor slice is self-contained and CI-guarded; the topology rearrange touched the working tree, the
scheduler's `WorkingDirectory`, `deploy.sh`, and two checkouts at once — state no test covers. That is the
shape that most needs a written plan before hands move, and the shape where a mid-flight crash leaves the
worst mess. The tell: "does it touch state no test covers (filesystem, scheduler, git structure)?"

**The append-only record paid off in the crash — as designed.** Recovery worked *because the design had been
ratified in a decision doc before the crash*: a brand-new thread reconstructed the whole state from disk,
diffed it against the ratified target, and produced an accurate gap list. The writing-things-down discipline
proved itself in the exact scenario it exists for — including on the one task where the build spec was
skipped.

**The summary must match what fired — one rule, applied three times.** The §10 arc's standard (the dead-man's
one-line summary can't read calm when a queue exists, and can't collapse "broke" into "correctly punted")
closed the suppression bug from one side, the taxonomy bug from the other, and then reached the heartbeat's
own line (OK/DEGRADED — a bare "OK" on a faulting cycle lies by connotation).

**Fail-loud is the default; severity tracks silence.** The blessing marker, best-effort-but-loud backup exit
codes, faults preferred over mis-rolls, `verify-restore` as a first-class command. The codebase's dominant
instinct is to fault rather than guess, so a finding's severity is read off *how silently it fails* — the
bug-README's severity axis, now visibly organizing new work.

**Compose over the frozen substrate — never re-fetch.** Rebalance reads the holdings §9e already froze; the
backup is a pure read of the store; the heartbeat rides an actual run. New capability composes over the fossil
record already captured, adding no new fetch surface and inheriting the freeze discipline for free — the same
reason payloads are captured richly up front (you can't backfill what you didn't record).

**The dead-man was latent until the scheduler existed.** "Silence past 7 days = broken" was inert until
launchd ran the runner on a cadence — a monitor that watches for its own death only becomes real when
something external to the watched process drives it. The arming was the quiet payoff of the whole M7 slice.

**Design-seat learnings carried forward:** the flow-vs-structure reframe as v2's real question (with
launch-as-consensus-clock as the possibly-novel operationalization, resting on Ben-David et al.); honesty as
the credibility with a rigorous audience (the precisely-stated falsifier reads stronger, and what's honest is
also hard to poach — funds reallocate for track records, not existence proofs); and the growth model from the
CAMS/IMDS discussion — the maintenance-system shape is already in the project's bones, so **grow the record
side freely, add process only under real recurring pain** (grow into the rigor, not the weight).

---

## Part 3 — Where it stands, and what's open

**v1 is build-complete and deployed.** Both spawners live (xcorr paging; dispersion in shadow burn-in — XLI at
z≈4.0, XLP fading), the §10 sender honest from both directions, the fossil store code-backed to dual HDDs, the
suite a mechanical merge gate, and the monitor running itself off a worktree pinned at `v1.0.2` with the
dead-man armed.

**Verification owed — prove it the way the CI gate was proven: watch it work once, don't assume.** All
owner/on-Mini steps: watch the first *scheduled* (not manual) run fire on its own (launchd log **and** a new
run in the store); test the dead-man's human loop (stop the LaunchAgent a cycle, confirm the heartbeat
does **not** arrive and the calendar backstop catches it); bless the HDDs, first backup, `verify-restore` with
counts matching the live store; confirm the dashboard reads cleanly (WAL) during a scheduled write.

**Named follow-ups (not blocking):** teach `pros store reindex` to rebuild the `funds` table from
`registry/funds/*.json` (until then the `.backup` registry copy on the drives is the instant restore); the N9
cadence gate and E2 flapping window (both pinned by `xfail(strict)`, flip loud the day they land); the doc
debt (DRIFT-1/2, C.2); the **spec rev 15 fold** — the doc layer still carries §9e/§8b/§10/M7 in decision
records, and build-complete is the natural fold moment (lean: watch-first-then-fold, so the spec records a
state confirmed real); stale-branch cleanup; the Node-20 CI action bump.

**Deferred — M7-hardening (earned when a real pain lands, not before):** infra-as-code provisioning;
WAL-checkpoint-out; offsite backup (S3/Backblaze as the fire/theft copy — the mechanism extends trivially);
bit-rot checksums.

**The line to hold — both seats, same words:** build-complete is a finish line *and* a starting line. What
finished is the *instrument*; what starts is the multi-year run that turns existence-proofs into rates. The
false-discovery rate is still unmeasured, dispersion is still n=1, flow-vs-structure is still open — and none
of those resolve by building. The posture now is **let it run**: confirm the autonomy holds, fold the doc
layer once the running state is confirmed real, and let the record start accruing. On the horizon, not now:
M6, then v2 — with its grounding already banked.
