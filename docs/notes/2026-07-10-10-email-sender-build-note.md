# §10 — the email sender: build note (2026-07-10)

*Build note for Claude Code (implementation seat). **Deliberately a build note, not a design doc** — §10's
design is already ratified and scattered across docs you've already got; this assembles it and pins the two
open forks the design thread just settled. The behavior spec is **§8a** (rev 14); this does not repeat it.
The decision record lands when built (like §9e / §8b). Governing CONTRACT: read-only/no-execution, the push
boundary already built in §9e.*

---

## 1. What this is (one line)

Replace `NullNotifier` with a real email sender: a **weekly heartbeat/dead-man** + **immediate state-change
and fault pushes**, rendered as **deterministic templating of folds** (no generated prose), with **nuisance-
alarm suppression** built in. Completes the M5 outputs.

## 2. What is already decided — do NOT re-adjudicate

- **The behavior is fully specced in §8a.** Weekly heartbeat fires *regardless of activity* (the dead-man:
  the subject encodes state, so silence past 7 days unambiguously means *broken*, never calm). Immediate
  push on any state change (lead entered/reverted, promotion, `mandate.changed`) and on any `fault`. Subject
  forms `[PROS] heartbeat — N active, M shadow, …` / `[PROS] state change: …` / `[PROS] FAULT: …`. Body:
  scan stats, active-leads digest (one line each), shadow-panel summary, manual-resolution queue if
  non-empty, faults, the over-ceiling banner while breached. Build to §8a; it is a target, not a gap.
- **The push *decision* is already built and gate-verified (§9e) — the sender does NOT re-decide it.**
  `_compute_push` already fires on non-shadow state changes and faults, shadow-suppressed, regression-tested
  (a shadow-only tick → `pushed=False`; xcorr+shadow → `pushed=True` because of xcorr). **The sender is a
  dumb templater**: it renders what the runner already decided to push. Do not put push/suppress *logic* in
  the sender — that decision lives in the runner, by the shadow-push finding. The sender's inputs are "this
  run pushed (or is the weekly heartbeat)" + the folds to render.
- **Rendering is deterministic templating of folds — no LLM, no generated prose.** Honest by construction
  (CLAUDE.md). The template is a pure function of the fold state; reuse the existing view-model /
  `render_markdown`-style layer where it fits (the board-snapshot export already renders these same folds —
  share shapes, don't duplicate).

## 3. The nuisance-alarm suppression CONTRACT (the one thing §10 owns beyond plumbing)

**Push once on a *new* fault, then fall to the heartbeat until it clears or changes** (C.1, filed as a §10
acceptance criterion). This is the one place the architecture-as-is would train the operator to ignore the
alarm — the GPWS/Protector failure mode. A fault that recurs every tick must **not** page every tick: the
*first* occurrence of a new/changed fault pushes; while the same fault persists unchanged, it rides the
weekly heartbeat (visible, not silent), and pushes again only when it *clears* or *changes*. Same
push-once-on-a-new-state, then-heartbeat discipline the state-change push already follows — applied to the
fault stream. **Test the violation:** a fault repeating across N ticks yields **one** push, not N; a *new*
fault after it pushes; a cleared fault pushes (or is reflected in the next heartbeat). Do not let a
"suppress recurring faults" implementation swallow a *changed* fault.

## 4. The two forks — RATIFIED by the design thread (build to these)

1. **Transport = SMTP (app-password), not SES.** Portable, no infra dependency, works from the Mac mini
   today; no AWS tie or domain-verification step. SES would couple §10 to M7's deploy target — deferred with
   M7 if ever wanted. **DEFAULT-class** (config: SMTP host/port/from/to; the app-password is a **secret** —
   handle it exactly like the Tiingo token: env var from the git-ignored `.env`, never config, never
   committed, never in an exception/URL/repr). Fail fast with a clear error if the sender is configured but
   the password is unset (mirror the Tiingo `ClickException` pattern).
2. **Build now; the dead-man arms at M7.** Build §10's plumbing now, but the **weekly heartbeat/dead-man is
   only meaningful once the runner is *scheduled*** — a dead-man on a manually-invoked runner tells you
   nothing (silence just means you didn't run `pros run`). So: build and wire the sender now (state-change
   and fault pushes work immediately on a manual run); the heartbeat cadence + the "silence = broken"
   guarantee **do not truly arm until M7 schedules the runner.** Note this explicitly in the code and the
   decision record — do not claim a live dead-man before there is a scheduler behind it.

## 5. Also closes (flag in the record)

The **paid-Tiingo-sub lapse-risk dead-man.** A dead/expired Tiingo key silently empties the panel via soft
faults; the 7-day dead-man catches it — **but only once the sender exists** (and, per §4, truly only once M7
schedules it). §10 is the piece that makes that failure mode catchable.

## 6. Deferred / named (not §10)

- **M7 scheduling** (the dead-man's real arming) — the runner leaves manual `pros run` for cron.
- **SES transport** — only if M7's deploy target makes it worthwhile; SMTP is the v1 answer.
- Everything already on the deferred list (M6 capture, 3b, broader coverage, foreign resolution, coverage-gap
  surfacing) is unchanged.

## 7. "Done" for this slice

`NullNotifier` replaced; state-change and fault pushes render from the folds and send over SMTP on a real
`pros run`; the nuisance-suppression (new-fault-then-heartbeat) is enforced **with its violation-test**;
the heartbeat template renders (its *cadence* awaits M7); the secret is env-only and fail-fast; suite green
plus the §10 tests. **Not** "the dead-man is live" — that arms at M7.
