# §10 — the email sender (heartbeat/dead-man + state-change/fault push, nuisance-suppressed)

*Decision record, 2026-07-10. Implements the build note `docs/2026-07-10-10-email-sender-build-note.md`
against behavior spec **§8a** (rev14). The build note is deliberately a build note, not a design doc — §10's
design was already ratified; this records what landed and pins the choices. Completes the M5 outputs: the
runner now not only DECIDES to push, it SENDS.*

## What landed

- **`prospector/runner/notify.py`** — a real **`SmtpNotifier`** beside the unchanged `NullNotifier`. It
  templates the runner's folds (`email_render`) into the §8a heartbeat / state-change / fault emails and
  sends them over SMTP with an app-password. The password lives in a local **`_Secret`** redaction holder
  (str/repr → `<redacted>`; a copy of `ingest.prices._Secret`, kept here so `runner` never imports `ingest`
  for a holder). `send` is an **injectable transport seam** (default `_smtp_send`, STARTTLS/SSL) so tests
  exercise render+dispatch with no socket. A send failure **raises** — `run_tick` catches it as a soft
  `notify` fault, so a broken sender never loses the run-log. Plus a pure `smtp_config(cfg)` reader (None
  when unconfigured; click-free — the env-read + fail-fast live in the CLI).
- **`prospector/runner/email_render.py`** — a NEW **pure** module (no smtplib, no store writes;
  unit-tested without a browser/socket, same discipline as `dashboard/export.py`). `build_context` gathers
  every §8a fold ONCE via the SAME `dashboard/views.*` view-models the board-snapshot and dashboard render
  (share shapes, never a second copy that can drift); `render_push` / `render_heartbeat` template
  `(subject, body)`. Deterministic — a pure function of the context, the **no-LLM CONTRACT**.
- **`prospector/runner/runner.py`** — `_compute_push` gains the §10 **nuisance-alarm suppression**;
  `_load_prior_faults` reads the comparand from the fossil; `run_tick` builds the email context and
  dispatches the push and/or the weekly heartbeat inside the resilient `finally`.
- **`prospector/runner/deps.py`** — `heartbeat: bool = False` (whether this tick also fires the weekly
  heartbeat). **`prospector/cli/main.py`** — `pros run --heartbeat/--weekly`; the notifier is built from
  `email.*` + `PROSPECTOR_SMTP_PASSWORD`, fail-fast/fallback. **`config/prospector.yaml`** — the `email:`
  block expanded (`smtp_host/port/security/from`), with the secret documented as env-only.

## The two ratified forks (design thread — build to them, not re-adjudicated)

1. **Transport = SMTP app-password, not SES.** Portable, no AWS/domain-verification step, works from the Mac
   mini today. DEFAULT-class config (host/port/from/to/security); the app-password is a **secret**
   (`PROSPECTOR_SMTP_PASSWORD`, env-only from the git-ignored `.env`, never config/committed/logged) —
   handled exactly like the Tiingo token. SES defers with M7's deploy target if ever wanted.
2. **Build now; the dead-man arms at M7.** State-change and fault pushes work immediately on a manual
   `pros run`. The weekly heartbeat *template* is built and tested, but the **silence=broken guarantee only
   truly arms once M7 schedules the runner** — a dead-man on a manually-invoked runner tells you nothing
   (silence just means you didn't run it). This is stated in the code, the email body, and here — **we do
   not claim a live dead-man before there is a scheduler behind it.**

## Load-bearing choices

- **Nuisance-alarm suppression is the one thing §10 owns beyond plumbing (CONTRACT, C.1).** The naive
  `bool(faults)` paged every tick a fault recurred — the GPWS "pull-up that cried wolf" mode that trains the
  operator to ignore the alarm. Now `_compute_push` pages once on a **new or changed** fault, then falls to
  the heartbeat while the SAME fault persists. The comparand is the immediately-prior run's fault set, read
  from the **fossil record** (the run-log FILE's `faults` — the `runs` table indexes only `fault_count`),
  the same "prior from the frozen record, never a cache" discipline as `_load_prior_mf_snapshot`. The
  signature is **message-exact**: any message delta is a *changed* fault and pages — a suppression rule must
  never swallow a changed fault. A *cleared* fault does not page (nothing faulted this tick); it is reflected
  in the next heartbeat. The runlog still records ALL faults (the fossil stays whole) — only the *push
  decision* is suppressed.
- **The sender is a dumb templater; the decision stays in the runner.** The push decision — the §9e
  shadow-push gate AND the §10 nuisance-suppression — lives in `_compute_push`, never in the sender. The
  runner gathers the folds and hands them to the notifier; the notifier renders + transports and never
  re-decides or re-queries the store. This keeps the two CONTRACTs (shadow-excluded-from-paging §4b,
  push-on-change §8a) reconciled in one place.
- **Rendering reuses the view-models — cannot drift from the screen.** `build_context` calls the same
  `views.rank_active_leads / shadow_panel / ceiling_status / heartbeat / manual_queue / registry_health /
  fault_log` the dashboard and the board-snapshot render, so the email and the screen cannot disagree.
- **The heartbeat rides the tick, not a separate read-only send.** `pros run --heartbeat` fires the weekly
  email at the END of a real tick (in the resilient `finally`, so a *faulted* weekly run still sends it) —
  so a heartbeat arriving proves the **whole pipeline** ran, the stronger dead-man. M7's scheduler calls
  `pros run --heartbeat` weekly; the `--heartbeat` flag only ADDS an email to the cadence tick, so the
  no-run-now CONTRACT holds (it never recomputes or captures on demand).
- **Subject priority: FAULT outranks state-change.** When a push carries both, the FAULT subject wins (the
  higher-priority signal). Subjects encode state (`N active, M shadow, K changes`) so silence past the floor
  is unambiguously *broken*, never *calm*.

## CONTRACT invariants (enforced + tested)

- **No LLM text as data** — `email_render` is a pure function of the folds; same context → byte-identical
  output (proven). No model-generated prose is ever rendered or persisted.
- **Secret hygiene** — the app-password is env-only, wrapped in `_Secret`; it never appears in `repr`/`str`
  of the notifier or holder, never in a URL/config/exception (proven). Fail-fast if configured-but-unset.
- **Firewall** — `notify`/`email_render` read only this store's own record (via `views`), import no
  streamlit, touch no portfolio / `portfolio.yaml` / trade path. The runner firewall grep covers them.
- **A broken sender never loses the run-log** — a send/context failure is a soft `notify` fault; the tick
  still writes its run-log and the dead-man still records (a fault email beats silence).

## Also closes (flagged)

The **paid-Tiingo-sub lapse-risk dead-man.** A dead/expired Tiingo key silently empties the panel via soft
faults; the 7-day heartbeat catches it — but only once the sender exists **and** (per fork 2) once M7
schedules it. §10 is the piece that makes that failure mode catchable.

## Deferred / named (not §10)

- **M7 scheduling** — the heartbeat's real arming (the runner leaves manual `pros run` for cron).
- **SES transport** — only if M7's deploy target makes it worthwhile; SMTP is the v1 answer.
- **HTML email** — the v1 body is plain-text/markdown-ish (deterministic, simple); no HTML.
- **Rebalance runner wiring** — a separate M4-into-runner slice (unblocked by §9e), not bundled here.

## Follow-up (QA, same day) — the nuisance-suppression is defeated by a volatile fault message

Claude Science's cold real-data pass found a **HIGH**-severity gap, reproduced end-to-end (not inferred):
`_fault_signature` was **message-exact** (`(subsystem, message)`), which is right only if a persisting fault
renders the *same message* every tick — but the live `ingest.prices` HTTP fault message embeds the fetch
**URL**, and the Tiingo URL carries `?startDate=…&endDate=…` (Yahoo carries `period1`/`period2` epochs),
**both derived from the run date**. So a persistent identical failure (a lapsed Tiingo sub → HTTP 403 — the
*exact* case §10 claims to close) rendered a *different* message every day → a different signature → it
**paged every day**: the GPWS "cried wolf" mode the suppression exists to prevent, silently reopened on the
live-primary path. The suppression *logic* was sound; its *comparand* was wrong for the messages the live
code emits. Third time the project's characteristic pattern surfaced — reads right, passes its tests, breaks
on the real substrate — and the first on the alarm layer itself. The synthetic test used a stable `"boom"`;
no test drove a *price* fault, whose URL moves. (Findings: `docs/email_nuisance_suppression_findings.md`;
package: `docs/PROSPECTOR_FAULT_SUPPRESSION_README.md`.)

**The fix (design-thread-adjudicated Option 1 — separate the suppression key from the display message):**
- **`_emit_fault` gains an optional `key=`** (stored on the fault dict + the fossil payload); **`_fault_
  signature` keys on `(subsystem, key or message)`.** When a fault carries no key it still signatures on its
  message — fully backward-compatible for the many stable-message faults (empty-frame, P1 guard, token-unset,
  SOI reason). The **message keeps the full URL for forensics**; only the *suppression key* is stabilized.
- **The two URL-bearing sites pass a stable `key=f"{ticker}:{status}"`** — the sector-panel pull
  (`_build_sector_panel`) and the per-basket dispersion pull (`_run_dispersion`); `PriceIngestError`/
  `EdgarError` already carry `.status`. A persisting lapsed-sub 403 is now **one** fault, paged once then
  ridden by the heartbeat.
- **Both key dimensions are load-bearing and pinned by tests** — a changed **status** (403→500) pages, and a
  different failing **ticker** (AAPL:403 vs NVDA:403) pages (the design-thread mirror test). So a future
  "coarsen the key to subsystem-only/subsystem+status" refactor **fails a test**, not just a comment. We did
  **not** normalize-inside-`_fault_signature` (regex whack-a-mole, reopens on the next new token) nor coarsen
  to subsystem-only (swallows a genuinely changed fault — the build note's forbidden move).
- **Discoverability for the next implementer:** a one-line convention at `_emit_fault` — *"if a fault message
  can carry a per-tick token (URL, timestamp, reset-epoch, row count), pass a stable `key=`."* It can't force
  future sites, but it puts the requirement where they'll trip over it (the residual Option 1 can't fully
  close without regex whack-a-mole).

**Deferred (named): E2 — the flapping fault.** `_compute_push` compares only to the *immediately-prior* run,
so a fault that clears then returns pages on every recurrence (even with a stable key). The
"escalate-then-fall-silent over an N-day window" shape would cover it; deferred as a design choice and pinned
by `test_flapping_fault_does_not_page_on_every_recurrence` (`xfail(strict=True)`) — it flips to a loud XPASS
the moment the window logic lands. Less severe (a genuinely intermittent fault is arguably worth seeing).

**Doc-lag note:** the design thread folds §10→BUILT and this suppression fix together into the next
state-of-project pass (**rev7**) — the reduced-doc-cadence (update-on-push) working as set, not drift.

## Verification

Full suite **545 passed / 2 xfailed** after the follow-up fix (the volatile-message package + the
ticker-guard test; the 2 xfailed are the pre-existing N9 cadence gate and the deferred E2 flapping case).
The §10 slice itself was **541 passed / 1 xfailed** (+20: `test_email_render.py` render/subjects/body/determinism +
`build_context`; `test_notify_smtp.py` message-shape/redaction/send-failure/`smtp_config`;
`test_runner_notify.py` the nuisance-suppression violation test — a recurring fault pages ONCE not N, a
changed fault pages again, the heartbeat fires regardless of activity and on a faulted tick; the CLI
email-configured-without-password fail-fast). The existing `_compute_push` unit test was updated to the
3-arg signature + the new nuisance semantics; `test_runner_idempotency.py` was unaffected (idempotency is an
*events* invariant — a cold re-run correctly suppresses the second run's identical fault, but the store
events are byte-identical). Manual end-to-end (owner, real app-password in `.env`):
`PROSPECTOR_SMTP_PASSWORD=… uv run pros run --heartbeat`.
