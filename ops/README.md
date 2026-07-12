# ops/ — the M7 autonomy core (scheduled runner)

*Makes the monitor **autonomous**: it runs itself on a schedule (launchd), backs up the fossil store after
each run, and the weekly heartbeat arms the §8a dead-man ("silence > 7 days = broken"). Design:
`docs/notes/2026-07-11-m7-autonomy-core-scheduling.md`; ratified in
`docs/decisions/2026-07-12-m7-autonomy-core.md`. These files are **inert until you run `install.sh` on the
Mini** — nothing here executes on its own.*

## What's here

| file | what it is |
|---|---|
| `run.sh` | The wrapper launchd invokes. `cd`s to the repo root, fixes `PATH` for `uv`, then runs `pros run` (with `--heartbeat` on Sundays) `&& pros backup`. The one debuggable script. |
| `com.prospector.run.plist` | The LaunchAgent **template** (`__PLACEHOLDERS__`). `install.sh` fills it in. |
| `install.sh` | Substitutes the template, validates it (`plutil -lint`), installs to `~/Library/LaunchAgents/`, and `launchctl bootstrap`s it. Idempotent. |
| `uninstall.sh` | `launchctl bootout` + removes the installed plist. |

## The deploy-from-tag shape — do this, not "checkout the tag"

**The scheduler runs from a *separate production checkout* pinned at the `v1.0.0` tag — never your dev clone
on `main`.** If the running copy and the dev copy are the same directory, `git checkout v1.0.0` and "keep
developing on `main`" collide, and dev churn can break the live monitor. Keep them apart:

```sh
# one-time: a production clone, pinned at the release tag
git clone <repo-url> ~/prospector-prod
cd ~/prospector-prod
git checkout v1.0.0            # the runner deploys from the tag, not main HEAD
# your DEV clone stays elsewhere (e.g. ~/Documents/coding/prospector on main) — untouched by the scheduler
```

The plist's `WorkingDirectory` and `run.sh` path both point at `~/prospector-prod`. To ship a new release
later: cut the new tag, `git fetch && git checkout <tag>` in `~/prospector-prod`, done — `main` never touches
production. (`v1.0.0` is cut when v1 is build-complete — i.e. after this milestone is activated.)

## Activation runbook (on the Mini)

1. **Production checkout** at the tag (above). Everything below runs in `~/prospector-prod`.
2. **`.env`** in that directory — `TIINGO_API_TOKEN` and `PROSPECTOR_SMTP_PASSWORD` are required (the run
   fails fast without them); `edgar.user_agent` lives in `config/prospector.yaml`. `uv sync` once so the venv
   exists.
3. **Backups first** — attach + bless the two HDDs and set `backup.targets` per
   `docs/notes/2026-07-12-mac-backup-activation-checklist.md`. Until then `pros backup` (and so `run.sh`)
   **faults loudly** — by design, never a silent no-op.
4. **Install the schedule** — pick the **LOCAL** time equal to `schedule.daily_utc` (22:30 UTC, after US
   close). Example if the Mini is US-Eastern (UTC−4/−5): `18 30`.
   ```sh
   ./ops/install.sh 18 30      # <LOCAL_HOUR> <LOCAL_MINUTE>
   ```
5. **Keep the Mini awake** — it's a server. Disable system sleep (Energy settings) or schedule wakes with
   `pmset`. launchd's run-on-wake is then a backstop, not the primary mechanism.
6. **Calendar backstop** (the weak dead-man's human loop) — a recurring reminder just after the expected
   weekly heartbeat: *"Prospector heartbeat — did it arrive?"* Email there → dismiss; absent → investigate.
   This is what converts "hope I notice silence" into "a reminder makes me check."

## Acceptance — done when (prove it, don't assume)

- **It runs itself:** the scheduled fire lands with no manual trigger — confirm via the launchd log
  (`~/Library/Logs/com.prospector.run.{out,err}.log`) **and** a new `runs/` entry in the store.
- **The heartbeat is legible:** the weekly email arrives with explicit **health (OK / DEGRADED)** and the
  **last-run date**.
- **The dead-man's human loop works:** stop the agent for a cycle (`./ops/uninstall.sh`), confirm the
  heartbeat does *not* arrive when expected, and confirm you'd catch it (the calendar reminder / you notice).
  The M7 analog of "watch the CI gate actually block." Re-install after.
- **Concurrent read:** the dashboard reads cleanly while a scheduled run writes (WAL mode — a verification).

## Operate

```sh
launchctl print gui/$(id -u)/com.prospector.run     # status / next fire / last exit code
launchctl kickstart -k gui/$(id -u)/com.prospector.run   # force a run now (debugging only — not a cadence surface)
./ops/uninstall.sh                                   # stop it
```

**Deferred (M7-hardening, not this slice):** infra-as-code provisioning of the Mini, WAL-checkpoint-out for
read-only-media serving, offsite backup (S3/Backblaze), the SOI cadence gate. They land when a real pain
earns them.
