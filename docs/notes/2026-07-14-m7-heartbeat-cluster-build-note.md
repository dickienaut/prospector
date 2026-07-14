# M7 heartbeat cluster — build note & handoff (M7-01, M7-03 now; M7-02 next)

*Build note, 2026-07-14. Captures the design-thread rulings + the implementation plan for the M6
deep-review heartbeat findings, so the build can resume on another machine (this note is the durable
carrier — the plan otherwise lived only in a chat session). Branch: `qa/m7-heartbeat-cluster` off
`origin/main` (975d4ee, includes PR #55). Seat: Claude Code.*

## Where the QA-findings work stands
- **PR #55 (merged)** — SNAP-01, R1, R4 (rebalance/snapshot alarm routing).
- **PR #56 (open)** — BK-1 + BK-2 (backup §7 hardening: mid-copy failure recorded; mtime-window aliasing tiebreak).
- **PR #57 (open)** — decision record: backup health → ONE fault channel (fold→heartbeat); checksum build deferred.
- **This slice** — M7 heartbeat cluster. Ship **M7-01 + M7-03** as one cluster PR now; **M7-02** (backup.stale) as the immediate follow-up.

## Ruling 1 — M7-01 (keystone): `heartbeat.sent` is a folded event, not a sidecar
"Last heartbeat sent" lives in the append-only record as a `heartbeat.sent` event on the `_system` stream. "Last sent" is a FOLD over it. NOT a JSON sidecar / config value (that is a parallel state store — refused).
- **Catch-up:** each tick, the heartbeat fires if `now - last_heartbeat_sent >= cadence` (default 7d), read from the fold. After a multi-day outage it sends **ONE** heartbeat (a catch-up, not a replay storm); that send emits a fresh `heartbeat.sent`; the clock resets. The gap stays visible in the record for forensics.
- **CRITICAL EDGE:** `heartbeat.sent` is emitted **only on send SUCCESS** (after the SMTP hand-off returns clean), never on attempt — a failed send must not advance the clock (else the dead-man goes quiet believing it spoke).
- **One source of truth:** the dead-man's "silence > 7d = broken" reads the SAME folded fact the sender writes — one clock feeding both the send decision and the health assessment.
- Sweeps **M7-05**: moving the decision into the runner on a UTC gap-check kills the `run.sh` local-weekday dependency and retires `schedule.weekly_day` as dead config.

## Ruling 2 — M7-02 (follow-up): option (i), a last-success marker on the target
Backup health surfaces as a fault the runner folds (settled in PR #57's decision record). Mechanism = **(i)**: backup writes a **last-success marker to the external target**; each tick the RUNNER reads it and emits a `backup.stale` fault into the fold if the newest backup is too old. Chosen over (ii) relax read-only posture and (iii) reorder-into-tick because it's the only option that adds the *necessary* mechanism without spending a CONTRACT — and it measures the honest thing ("is there a fresh successful backup on the drive"), not a process self-report.
Three guardrails for the M7-02 build:
1. **Marker written only on VERIFIED backup success** (after the copy completes + integrity step if present), same discipline as `heartbeat.sent` — never on attempt.
2. **Freshness threshold is a DEFAULT keyed to the run cadence** (`backup.max_age`, a small multiple of the tick interval — one skipped run doesn't cry stale; a genuinely-behind drive faults within a cadence or two). `backup.stale` carries a **stable §10 suppression key** (per-target) so it pages once then rides the heartbeat.
3. **Missing marker counts as stale** — never-backed-up / unmounted reads as `backup.stale` too (missing-because-never-succeeded and stale-because-behind are the same actionable fact: no fresh backup, go look).

## Locked defaults (Plan agent's ambiguities, resolved)
- `heartbeat.sent` home = **`_system` events stream** (run-log is a disposable index a reindex can't rebuild; `_system` is the infra-event home for `config.changed`/`fault`; statelessness demands fossil recovery). Blessed by Ruling 1.
- **Keep `--heartbeat`** as a manual force-send override (`send = deps.heartbeat or heartbeat_is_due(...)`), tagged `trigger="manual"`. Scheduler no longer passes it.
- **Remove `schedule.weekly_day`** (dead config after M7-05).
- **One cadence knob** `schedule.heartbeat_cadence_days: 7` (feeds both send cadence and the §8a floor).

## Verified code facts (grounding)
- `EventStore.append` honors an explicit envelope `ts` — the injected `clock` is used only for the `ingested_at` bookkeeping column, "never for the envelope ts" (`event_store.py:52-53`). So `record_heartbeat_sent(store, ts)` seeds a dated fossil correctly.
- `registry.events_by_type(type)` returns rows `ORDER BY ts, event_id` (`registry.py:111-113`) → `[-1]` is newest.
- `runner.py` already imports `SYSTEM_LEAD, parse_ts` (`from prospector.store.envelope`); no new imports needed for the two functions.

## Implementation checklist (M7-01 + M7-03) — file → change → why
1. **`prospector/fold/fold.py` V1_TYPES (~25-33)** — add `"heartbeat.sent"` (vocabulary honesty; `_apply` no-ops it via the `elif type_ in V1_TYPES: pass` arm).
2. **`config/prospector.yaml` schedule (387-389)** — add `heartbeat_cadence_days: 7` (DEFAULT); remove `weekly_day`; update the "keys reserved" comment (schedule is now used).
3. **`prospector/dashboard/views.py`** — add:
   ```python
   def last_heartbeat_sent(registry) -> str | None:
       rows = registry.events_by_type("heartbeat.sent")
       return rows[-1]["ts"] if rows else None
   ```
   and repoint `heartbeat(runs, now, last_heartbeat_sent=None, *, floor_days=7)` so ok/broken keys on `last_heartbeat_sent` (NOT `runs[0].ts` — that's the M7-03 tautology), with fields `{ok, ever_sent, last_sent_ts, silence_days, floor_days, catch_up, reason, last_run_ts, last_run_date}`. `runs` supplies only the informational last-run line. Never-sent → ok False. `catch_up = silence > floor_days`.
4. **`prospector/runner/runner.py`** — add module-level `heartbeat_is_due(registry, now, cfg)` (cadence from `cfg["schedule"]["heartbeat_cadence_days"]` default 7; never-sent → due; unparseable prior → due) and `record_heartbeat_sent(store, ts, *, trigger="cadence")` (appends the `_system` `heartbeat.sent` envelope). Interface MUST match `tests/test_runner_heartbeat_catchup.py` (imports both from `runner`).
5. **`prospector/runner/runner.py` run_tick (~329-351)** — `send_heartbeat = deps.heartbeat or heartbeat_is_due(deps.registry, now, deps.cfg)`; use it in place of `deps.heartbeat`; on a CLEAN `deps.notifier.heartbeat(ctx)` return, call `record_heartbeat_sent(store, now, trigger="manual" if deps.heartbeat else "cadence")` INSIDE the try, so a raising send skips the record (clock doesn't advance).
6. **`prospector/runner/email_render.py` build_context (~57)** — `last_sent = views.last_heartbeat_sent(registry)`; `cadence = int((cfg.get("schedule") or {}).get("heartbeat_cadence_days", 7))`; `hb = views.heartbeat(runs, now, last_sent, floor_days=cadence)`. (At render time this is the PRIOR send — the record happens after the notifier call — so the email honestly shows the bridged gap.)
7. **`prospector/runner/email_render.py` _body (~163)** — replace the tautological `hb_state` line (M7-03): `first heartbeat` / `on cadence — prior heartbeat Nd ago` / `CATCH-UP — prior heartbeat Nd ago (> Md cadence; an outage was bridged)`.
8. **`prospector/dashboard/export.py:197` and `app.py:81`** — fold `views.last_heartbeat_sent(registry)` and pass it into `views.heartbeat(...)`.
9. **`ops/run.sh` (~27-34)** — drop the `if [ "$(date +%u)" -eq 7 ]` branch; always `uv run pros run`; note the runner now owns the cadence (UTC catch-up). `--heartbeat` stays as a manual affordance.
10. **`ops/com.prospector.run.plist`** — NO change (daily `StartCalendarInterval`, no weekday key; the daily tick is what evaluates `heartbeat_is_due`).

## Tests (RED-first) — run with `uv run python -m pytest` (NOT `uv run pytest` — anaconda shadows it)
- **`tests/test_runner_heartbeat_catchup.py`** — remove the `xfail(strict=True)` marker; update the STATUS docstring to "landed"; add a never-sent (empty registry) → `heartbeat_is_due` True case ahead of the existing 8d-stale→True / 1d→False cases.
- **New run_tick tests** (reuse `_deps`/`_tick` + `NullNotifier`): catch-up sends exactly ONE (seed `heartbeat.sent` 8d ago, one quiet tick w/o `--heartbeat` → `len(heartbeats)==1`, exactly one new `heartbeat.sent` at now); within-cadence does NOT resend; **FAILED send does not advance the clock** (raising notifier → no new `heartbeat.sent`, a `notify.heartbeat` fault recorded, still due next tick); success writes exactly one fact at `now` (+ `event_counts["heartbeat.sent"]==1`).
- **`tests/test_dashboard_views.py`** — `last_heartbeat_sent` newest-wins; `heartbeat(..., last_heartbeat_sent=None)` ok False; 3d→ok; 8d→ok False + catch_up True.
- **`tests/test_email_render.py`** — update `_ctx` heartbeat default to the new shape; assert CATCH-UP body after a gap, on-cadence body, first-send body; realign `test_build_context_gathers_the_view_model_folds` to seed a `heartbeat.sent`.

## To resume on the Mini
`git fetch origin && git switch qa/m7-heartbeat-cluster` (this note + branch are pushed). Then execute the checklist above, RED-first tests first. Baseline suite on this branch: **593 passed / 3 skipped / 6 xfailed** (same-venv). After M7-01+M7-03 the `test_runner_heartbeat_catchup.py` xfail flips to a real pass (−1 xfail) plus the new tests.
