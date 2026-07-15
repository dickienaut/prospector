# The activation checklist — design note (2026-07-15)

*An **ideation capture**, not the checklist itself. Records the design of the on-Mini activation checklist so
the thinking isn't lost before it's built. **To be built at the rev15 fold**, after the lock PR lands — by
then the item set is final rather than moving underneath it. Filed to `notes/`: this describes and designs,
it doesn't ratify. **Caveat (blind-seat):** the draft item set in §4 was gathered from the design thread's
reading of the build notes (M7 autonomy core, store durability, the lock decision record, M6 capture, the
CAP-DRIFT decision); **verify every item against those notes and the real code when building** — the register
row is the pointer, not the spec, and the same applies here.*

---

## 1. Why it exists — the test harness for the human-in-the-loop

The project's own rule: **spec-first is triggered by state no test covers.** The on-Mini set is *definitionally*
that state — it is the residue left after CI and QA have each done everything they structurally can. CI proves
the code; QA proves it against the real substrate in a sandbox; neither can reach the Mac mini's launchd, its
mounted HDDs, its `.env`, its macOS-only deploy path, or the calendar reminder in the operator's pocket.

So this is not process weight bolted onto a tested system. **Every other layer of this project got a
mechanical gate; this layer has no harness, so it gets a human one.** Right now those items are scattered
across six build notes as prose asides — which is exactly how a verification item quietly decays into an
assumption. The checklist is the harness for the only seat that can execute them: the human.

The precedent that makes the shape obvious: this is the **T.O. / 781** pattern, and the project has been
reaching for it since the CAMS conversation. Aircraft don't get launched on intent.

## 2. Design properties (the load-bearing three)

**(a) Every item is a challenge–response with an OBSERVED VALUE, never an action.** Not *"bless the HDDs"* but
*"Blessing markers — PRESENT, both targets."* Not *"verify the dead-man"* but *"Heartbeat, suppressed cycle —
NOT RECEIVED; calendar backstop — FIRED 22:07."* This is the whole trick: **an action item can be checked off
by a tired person who meant to do it; an observation item can only be completed by looking at something.** The
response is a readback of reality, and it is what gets recorded.

**(b) Cross-check: every critical item wants two independent witnesses.** A single source can lie. The pairs
already exist in the material — the first scheduled run is proven by the *launchd log* **and** a *new run event
in the store* (two systems that don't know about each other agreeing); the lock is proven by `lock-path`
resolving identically from *both checkouts*; the dead-man is proven by the heartbeat's *absence* **and** the
backstop *firing*. Where an item has only one witness, that is a weakness **in the item**, worth noticing —
not just a gap in the checklist.

**(c) No-go gates vs advisory.** Mark each. A no-go gate blocks arming: **capture does not arm until the live
byte-compare passes**; **the dead-man is not armed until its silence has been proven to get noticed**; the
backup is not trusted until a restore has actually been performed. Advisory items are recorded but don't
block. Without the distinction, everything is equally important, which means nothing is.

## 3. Two artifacts, not one

- **The blank checklist = the T.O.** Lives versioned in `ops/`, amended when a slice adds an item. It is the
  procedure.
- **The completed run = the 781.** Each *execution* produces a dated completion record — **observed values,
  not ticks** — filed as a fossil. Append-only discipline applied to activation.

This answers the question that will actually matter in two years: *did we ever really prove the dead-man, or
did we only mean to?* A tick can't answer that. `run 8f3a2 fired 2026-07-16T22:00:03Z unattended; launchd log
line 47` can.

## 4. Draft item set (gathered from the scattered notes — **verify each against its source when building**)

| # | Item | Response (the observed value) | Witnesses | Gate? |
|---|------|-------------------------------|-----------|-------|
| 1 | First **unattended** scheduled run | run id + ts, no manual trigger | launchd log · a new run event in the store | **GATE** (autonomy) |
| 2 | Mini stays awake | sleep disabled / wakes scheduled | `pmset -g` output | advisory (launchd wake is the backstop) |
| 3 | Heartbeat arrives on cadence, legible | email received; reads OK/DEGRADED + last-run date | the email · the folded `heartbeat.sent` | **GATE** |
| 4 | Dead-man's **human loop** | heartbeat NOT received on a suppressed cycle; backstop fired at *ts* | the absence · the calendar reminder firing | **GATE** (dead-man armed) |
| 5 | Calendar backstop **exists** | recurring reminder present, timed after the expected heartbeat | the calendar itself | **GATE** |
| 6 | Concurrent read | dashboard renders cleanly *during* a scheduled write | dashboard · the run completing | advisory |
| 7 | HDD blessing markers | PRESENT, both targets | marker file on each drive | **GATE** (backup) |
| 8 | First backup | completes to both targets | exit status · files on the drives | **GATE** |
| 9 | `verify-restore` | reindex succeeds; counts match the live store | command output · spot-check counts | **GATE** (an untested backup is a hope) |
| 10 | `deploy.sh` refusal under a held lock | refuses, nonzero, the message | shell observation | **GATE** |
| 11 | Dual `lock-path` identity | identical path from **both** checkouts | `pros store lock-path` in dev · in prod | **GATE** (the assumption the dev-side lock stands on — **closes DEPLOY-OVERLAY-DRIFT**, the one gap the deploy lock cannot verify from inside a single checkout) |
| 12 | API key present | fail-fast does **not** fire | **both** checkouts' `.env` | **GATE** (capture) |
| 13 | Budget number set | `capture.monthly_budget_usd` = *value* | the merged config | **GATE** (capture) |
| 14 | Armed byte-compare | issued == query, byte-exact, on **one** live call | the comparison itself | **GATE** (capture does not arm until this passes) |

**Item 5 is the purest one in the set** — and worth stating in the checklist's own header as the reason it
exists: *the calendar backstop lives entirely outside the system. Nothing in git can confirm it.* A machine
cannot check it, so a human must, on a list, on purpose.

## 5. Scope — activation, not ritual

This is an **activation checklist**: run **once at arming**, and re-run after a rebuild, a migration, or a
macOS upgrade. A much smaller subset re-runs after any deploy that touches `ops/`. **It is not a daily
ceremony.** Grow into the rigor, not the weight — the CAMS caution applies to this artifact more than any
other, because checklists are precisely where good process becomes sign-off theater.

## 6. Its own maintenance gate

Mirroring the register's: **a slice isn't done until its on-Mini items are in the checklist.** Otherwise the
checklist drifts into class 9 like anything else — and **a stale checklist is worse than none, because it
certifies the wrong things.**

## 7. Timing

Build it **with the rev15 fold**, after the lock PR lands: rev15 records the state, the checklist proves it,
and the item set is final by then instead of moving. The two belong in one session — both are *"make the
record match the territory at the v1 milestone."*
