# Build-seat record — 2026-07-11 to 2026-07-13

*What the build/implementation seat (Code) did and discovered over the stretch that took Prospector from §10
completion to **v1 build-complete** and onto a running deployment. The design seat's record
(`2026-07-13-design-seat-record-jul11-13.md`) captures the *why* — the rulings and the reasoning behind each
call; this is its twin and captures the *what* and *how*: the slices as built, the build-time forks resolved,
the crash-recovery mechanics, and the adversarial-panel finds — the three the design record explicitly handed
to Code to record separately. The durable reasoning lives in the decision records under `docs/decisions/`;
this stitches them into one narrative of the build. Read cold: each entry stands on its own.*

---

## The arc in one paragraph

Six slices shipped, each through the mechanical gate the first of them stood up. The **rebalance sensor was
wired into the runner** — the last M4 sensor, completing the sensor phase — resolving three build forks
(shadow-inclusive routing, seed-on-first-sight, same-tick-to-`_system`). The **fossil store got a dual-HDD
backup** (`pros backup` / `pros store verify-restore`), a read of the store that can't touch it. The **M7
autonomy core** landed the `ops/` scaffolding that lets the monitor run itself (launchd wrapper + one plist)
and armed the dead-man with an OK/DEGRADED heartbeat health line. A **CI test-gate + branch-protection
ruleset** made the 576-test suite a *mechanical* merge gate — and immediately caught two of its own setup
gaps. Production was stood up, hit a two-clones footgun, and was rebuilt as a **git worktree pinned at a
tag** with a tag-only `deploy.sh`; a mid-rearrange crash was recovered by a fresh thread reading state off
disk; the paths were consolidated to `~/prospector/{dev,prod,store}` and machine-local config moved to an
**untracked overlay** with the config-hash folded to cover the merged result. Three release tags were cut
(`v1.0.0` → `v1.0.1` → `v1.0.2`); the scheduler runs the worktree at **`v1.0.2`**, a release it can't
accidentally un-pin. **v1 is build-complete** — every slice landed green, reviewed, and merged by the owner.

---

## Part 1 — What was built (the slices, with the build-time forks resolved)

**Rebalance runner-wiring (§4d) — the last M4 sensor into the runner.** `_run_rebalance` at its slot in
`_run_sensors`, reusing the §9e frozen holdings (a wiring slice, not new sensor logic). Three forks resolved
and ratified (`2026-07-12-rebalance-runner-wiring.md`): **(1) the active-lead set includes shadow leads** —
`active_incl_shadow_lead_ids`, a deliberate *sibling* to the shipped non-shadow helper (rebalance pages
nothing, so the shadow wall that protects the paging paths doesn't apply — and right now *every* dispersion
lead is shadow, so the non-shadow filter would sever rebalance from the entire dispersion side); guarded by a
violation-test where a basket's *only* live lead is a shadow one. **(2) Seed silently on first sight, fault
only a broken feed** — this corrected the build note, which had said "no prior snapshot → faults that
basket": faulting a normal cold start would have paged ~11 baskets on the first rebalance tick, the exact
day-one nuisance-alarm §10 exists to prevent. Two violation-tests point in opposite directions
(`test_first_sight_basket_seeds_silently`, `test_broken_current_feed_faults_that_basket`). **(3) A same-tick
spawn+rebalance routes to `_system`** and accretes from the next tick on — kept deliberately, *not* an §4d
amendment, because the alternative (re-folding here to see same-tick spawns) would reintroduce the
re-fold-divergence risk the "materialized fold, never re-fold" invariant forbids. 11 offline tests
(`test_runner_rebalance.py`). After this, the runner's sensor phase is whole.

**Store-durability backup (§7) — `pros backup` + `pros store verify-restore`.** The append-only store is the
one irreplaceable, un-backed-up asset (code and docs are distributed in git; two years of holdings/prices/
filings *as they were on those days* cannot be re-fetched). `store/backup.py` rsync-mirrors the fossil trees
to both HDDs and safe-copies the WAL registry via the native `Connection.backup()` API. Build calls
(`2026-07-12-store-durability-backup.md`): **`registry/` is INCLUDED** in `FOSSIL_TREES` — another build-note
correction: reindex rebuilds the events/snapshots index but *never* the `funds` table, so
`registry/funds/{series_id}.json` is irreplaceable from the fossils alone and must be on the drives.
**Fail-loud via a per-drive blessing marker**, not a bare path check — on macOS an unplugged drive's mount
point vanishes, so a naive `mkdir -p` would recreate it *on the boot disk* and "back up" nothing durable; a
required pre-existing `.prospector-backup-target` makes an unplugged drive fault instead. **Best-effort-but-
loud** across targets: a missing drive never skips the healthy one, but still exits non-zero. Native Python
copy, not shelling out (consistent with `primitives/sqlite_backup.py`). 10 offline tests (`test_backup.py`).
The physical activation (bless drives, first backup, restore test) is the owner's Mac session —
`2026-07-12-mac-backup-activation-checklist.md`.

**M7 autonomy core — the monitor runs itself, the dead-man arms.** The `ops/` scaffolding
(`2026-07-12-m7-autonomy-core.md`): **`ops/run.sh`**, the wrapper launchd invokes (`cd`s to repo root, fixes
`PATH` — launchd's minimal env has no profile, the classic "`uv`/`.env` not found" failures — then runs
`pros run [--heartbeat] && pros backup`, which is where the backup cadence is wired). **launchd, not cron** —
cron *silently skips* a job if the Mac slept at the scheduled time; launchd runs the missed job on wake, the
difference between "ran late" and "silently didn't, and the dead-man now has to catch it." **One plist**
(`com.prospector.run.plist`) + `install.sh`/`uninstall.sh`, the wrapper deciding heartbeat day
(`date +%u == 7`) — *for dead-man semantics*: one scheduled entity means a missing heartbeat unambiguously
attests "the runner is dead"; two plists would let a broken Sunday entity kill the heartbeat while dailies
continue, injecting ambiguity into the one channel whose whole job is unambiguous absence. **Heartbeat health
line** (`email_render.py`) — explicit **OK / DEGRADED** (DEGRADED the moment an operational fault fires),
reusing the render's existing view-models: the §10 summary-honesty rule applied to the heartbeat's own line
(a bare "Heartbeat: OK" lies by connotation on a faulting cycle). Nothing in `ops/` executes until
`install.sh` runs on the Mini — the PR's blast radius is zero until activation.

**CI test-gate + branch-protection ruleset — the tests made a mechanical merge gate.** `.github/workflows/
ci.yml`: `uv sync --locked` (fails if the lock drifted from `pyproject.toml`) → `pytest -ra` (skip/xfail
reasons visible) → `pros --help` smoke; no secrets block by design (the suite is offline, the network guard
fails any socket). Two setup gaps surfaced *immediately* and were fixed in-flight (see Part 2). The `main`
ruleset (Settings, not a tracked file): require-PR, require the `test` check, block force-push, restrict
deletions, **no bypass actor** (a ruleset the owner can bypass is theater). Sequenced the deploy tag,
environments, and Projects board as later, non-blocking work (`2026-07-11-ci-and-branch-protection.md`).

**Production topology — worktree + tag-only `deploy.sh`.** Deploy-from-tag was first built as a *second full
clone* and immediately hit the footgun it invites (Part 2). Rebuilt as a **git worktree** pinned detached at
a release tag: one repo, one `.git`, two checkouts — "production runs frozen released code" becomes a
structural fact, not a remembered rule (`2026-07-12-production-worktree-and-deploy.md`). **`ops/deploy.sh
<tag>`** is the one deploy command, run from the dev repo: **tag-only** (refuses any ref that isn't a tag via
`refs/tags/<tag>^{commit}`, so production can never pin to a moving ref) and config-preserving. The plist's
`WorkingDirectory` points at the worktree — that pointer *is* the isolation. Then consolidated to
`~/prospector/{dev,prod,store}` with the store external to *both* checkouts, so no worktree/tag operation can
ever touch the fossil record (`2026-07-12-consolidated-prospector-layout.md`).

**Machine-local config overlay — the config-honesty CONTRACT fold.** Machine-local paths (`store.root`,
`backup.targets`) moved out of the tracked `config/prospector.yaml` into an **untracked
`config/prospector.local.yaml` overlay**, deep-merged at load in one choke point (`load_config`) — the config
analog of `.env` (`2026-07-12-local-config-overlay.md`). **The CONTRACT fold: the single sha256 is computed
*after* the merge**, so `config.changed` fossilizes exactly the config a run used and a machine-local change
correctly fossilizes (it's real, non-secret config). This is the dividing line: secrets (`TIINGO_API_TOKEN`,
SMTP password) stay `.env`-only and never fossilize; paths belong in config and *should* fossilize when they
change. `edgar.user_agent` is deployment *identity* (invariant across the owner's machines), so it went to
the tracked default, not the overlay. `deploy.sh` dropped its stash/pop gymnastics — an untracked file is
invisible to `git checkout --detach`. Migration was hash-preserving (byte-identical merged config → no
spurious `config.changed`), pinned by a test.

**Three release tags.** `v1.0.0` (build-complete: M1–5 + backups + CI gate + M7 core) → `v1.0.1` (the
running-deployment release, worktree deploy) → `v1.0.2` (deploy-path consolidation + config overlay; no
behavior change). The scheduler runs the worktree pinned at **`v1.0.2`**.

---

## Part 2 — Discoveries & durable learnings (the build-side part worth mining)

**The crash-recovery mechanics — the append-only record and a pre-ratified decision doc rebuilt the state.**
The topology rearrange (scattered `~/prospector-prod` + `~/prospector-store` → consolidated
`~/prospector/{dev,prod,store}`) is the one class of change with no test to lean on: it touches the working
tree, the scheduler's `WorkingDirectory`, `deploy.sh`, and two checkouts at once. Code errored mid-rearrange.
Recovery worked *because the design had been ratified in a decision doc before the crash*: a **brand-new
thread reconstructed the entire state from disk** — reading the actual worktree layout, the installed plist's
`WorkingDirectory`, `deploy.sh`'s default, the store location — diffed it against the ratified target, and
produced an accurate gap list (the `deploy.sh` default still read `~/prospector-prod`, which would fail
"no git worktree" on a machine whose worktree is `~/prospector/prod`). The fix (`23c02f5`) closed exactly
that gap. The lesson is mechanical, not moral: **spec-first is triggered by *untested state*, not abstract
complexity** — the tell is "does it touch state no test covers (filesystem, scheduler, git structure)," and
that is precisely the shape where a mid-flight crash leaves the worst mess and where the written record earns
its keep. (This very session is the same shape one turn up: a hung thread, exited, and the work picks up
cleanly from disk because the record is whole.)

**The adversarial-panel finds — six catches, each by *reading*, not by the suite.** The stretch's slices went
through adversarial review that caught what green CI structurally cannot:
- **`registry/` omitted from the backup tree list.** The build note listed `events/ snapshots/ ingest/
  baselines/ runs/` — omitting the fund-identity objects, which reindex never rebuilds. Following the note as
  written would have left fund identity un-backed-up. Corrected in `FOSSIL_TREES`; `verify_restore` now
  reports the fund-object count so the gap stays visible.
- **First-sight seeding would have paged ~11 baskets.** The rebalance note's "no prior snapshot → faults that
  basket" was a nuisance-alarm generator on the first tick — caught before it shipped, corrected to
  seed-silently.
- **A stale runbook with teeth (doc-drift, class 9).** A runbook still told operators to put machine-local
  config in the *tracked* file *after* the overlay mechanism changed — following it would have **aborted the
  next deploy**. A documentation-vs-mechanism disagreement where the doc wins at the worst moment, catchable
  only by adversarial reading. This is the standing argument for lineage-checking docs against the mechanism
  they describe.
- **Config-in-the-tracked-file broke a test.** The same machine-local edit, left uncommitted in the dev
  clone, put HDD paths into the tracked `config/prospector.yaml` and broke
  `test_pros_backup_faults_nonzero_when_no_targets_configured` (which pins the shipped `backup.targets: []`).
  The broken test was the *symptom* that drove the overlay decision — the seam paying for itself loudly.
- **Two clones is vigilance, not isolation.** The first deploy-from-tag (a second full clone) produced the
  failure it invites the moment it existed: the owner edited dev, ran production, and *couldn't tell why
  nothing changed* — plus two stores ("which is live?"). Diagnosed as discipline-by-vigilance and replaced
  with the worktree (mechanism).
- **The CI false-green guard bit on its own setup.** Two catches: the lockfile was gitignored, so
  `uv sync --locked` had nothing to lock against (`1ff2609` un-ignored `uv.lock`); and the default sync
  skipped 3 dashboard tests — a partial green, the exact false-gate the note flagged — fixed by `--extra
  dashboard` for 0 skips (`92a22fb`).

**Green-on-synthetic surfaced again, on real media — the mtime re-copy.** The incremental backup's
skip-if-unchanged check (`_needs_copy`, size/mtime) re-copied unchanged files every run on the real HDDs,
because **exFAT/FAT timestamp granularity** is coarser than the source filesystem's — the mtime comparison
that held on the dev disk failed on the deployment media. Fixed by widening the incremental window to 2s
(`f4bc36b`). The signature project failure (green on synthetic, broken on real) reappearing one grain
deeper — this time on the *backup* layer, and only catchable by running against the real drives.

**Mechanism over vigilance — the through-line of every slice.** The branch-protection ruleset (no bypass),
`deploy.sh` refusing non-tags, the worktree dissolving the two-clones confusion, the config-hash over the
*merged* result, the blessing marker turning an unplugged drive into a loud fault, one-plist-so-absence-is-
unambiguous: every one converts a discipline-you-remember into a structure-that-holds. A 20-year personal
system cannot depend on the operator never being tired; whenever the choice was between a rule and a
mechanism, the mechanism won.

**Fail-loud is the default, and the dangerous bugs are the silent few.** The blessing marker (unplugged drive
→ fault, never a phantom-path write), best-effort-but-loud (missing drive exits non-zero), the fault-taxonomy
fix (advisories counted-and-surfaced, live-lead ones page): the codebase's dominant instinct is to fault
rather than mis-roll, so a finding's severity tracks *how silently it fails*. The backup's own worst outcome —
a backup that copied but won't restore — is ruled out by making `verify-restore` a first-class command and the
restore test a checklist step: an untested backup is a hope, not a backup.

**A wiring slice reuses the frozen substrate — it never re-fetches.** Rebalance reads the holdings §9e already
froze this tick (pull-if-absent, no double-fetch, no silent dependency on dispersion having run); the backup
is a pure *read* of the store; the heartbeat rides an actual run. The pattern: new capability composes over
the fossil record already captured, so it adds no new fetch surface and inherits the freeze discipline for
free — the same reason a payload must be captured richly up front (you can't backfill what you didn't record).

---

## Part 3 — Where it stands, and what's open

**v1 is build-complete and deployed.** Both spawners live (xcorr paging, dispersion in shadow burn-in), the
§10 sender honest, the fossil store code-backed to dual HDDs, the 576-test suite a mechanical merge gate, the
runner able to run itself off a worktree pinned at `v1.0.2` it can't accidentally un-pin, and the dead-man
armed by an OK/DEGRADED heartbeat.

**Verification owed — prove it the way the CI gate was proven: watch it work once, don't assume.** These are
owner/on-Mini steps, not code:
- *The autonomy holds* — watch the first *scheduled* (not manual) run fire on its own (launchd log **and** a
  new run in the store).
- *The dead-man's human loop works* — stop the LaunchAgent for a cycle, confirm the heartbeat does **not**
  arrive, and confirm the calendar backstop catches the absence. The M7 analog of "watch the gate actually
  block."
- *The backup is usable, not merely copied* — bless the two HDDs, first backup, then `pros store
  verify-restore` with counts matching the live store (`2026-07-12-mac-backup-activation-checklist.md`).
- *Concurrent read* — the dashboard reads cleanly (WAL) while a scheduled run writes.

**Named follow-ups (not blocking):**
- *Teach `pros store reindex` to rebuild the `funds` table* from `registry/funds/*.json`, so a fossils-only
  restore recovers fund identity too. Until then the `.backup` registry copy (also on the drives) is the
  instant restore, so nothing is lost — only the reindex-from-fossils path is currently incomplete for funds.
- *N9 SOI-corroboration cadence gate* and *E2 flapping-fault window* — both pinned by `xfail(strict)` tests
  that flip to a loud XPASS the day the fix lands. Zero cost today. (Both are M7-hardening / deferred.)
- *Doc debt* — DRIFT-1/2 and C.2 (regenerate ARCHITECTURE's "what's built" from the wired set as the single
  source of truth).
- *Stale-branch cleanup* (~4 merged branches) and the non-blocking Node-20 CI action bump.

**Deferred — M7-hardening (named, earned when a real pain lands, not before):** infra-as-code / reproducible
provisioning of the Mini; WAL-checkpoint-out for read-only-media serving; **offsite backup** (S3/Backblaze as
a third copy — the two HDDs cover disk-death, not fire/theft; the rsync/`.backup`-to-targets mechanism extends
to an S3 target trivially); bit-rot checksums.

**The line to hold (echoing the design seat):** build-complete is a finish line *and* a starting line. What
finished is the *instrument*; what starts is the multi-year run that turns existence-proofs into rates. None
of the open scientific questions — the unmeasured false-discovery rate, dispersion still n=1, flow-vs-
structure — resolve by building. The build seat's immediate job is done; the posture now is **let it run**,
confirm the autonomy holds, and fold the doc layer (spec rev 15) once the running state is confirmed real.
