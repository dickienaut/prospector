# Mac backup activation checklist (2026-07-12)

*The hands-on-Mac steps to activate `pros backup` on the Mini. The **code** is built and CI-green
(`store/backup.py`, `pros backup`, `pros store verify-restore` — see
`docs/decisions/2026-07-12-store-durability-backup.md`); this is the part that can't be done from a phone:
attaching + blessing the two HDDs, the first real backup, and the one-time restore test. Do it once, now,
while the store is small. ~20 minutes, mostly copy-paste.*

**Substitute your real values** for the two placeholders throughout:
- `HD1`, `HD2` → your drive volume names (whatever they mount as under `/Volumes/`).
- Run everything from the repo root on the Mini (`cd` there first so `config/` and `.env` resolve).

---

## 1. Attach and identify the two drives

Plug in both HDDs, then confirm the OS sees them:

```sh
ls -1 /Volumes/            # both drives should appear by name
```

Decide a target subdir on each drive (a folder ON the drive, so the store doesn't sit at the volume root):

```sh
mkdir -p "/Volumes/HD1/prospector"
mkdir -p "/Volumes/HD2/prospector"
```

## 2. Bless each drive (the fail-loud marker — the load-bearing step)

`pros backup` refuses to write to a target that doesn't carry the blessing marker. This is what makes an
**unplugged drive fault loudly** instead of silently "backing up" onto the internal disk. Create the marker
once per drive:

```sh
touch "/Volumes/HD1/prospector/.prospector-backup-target"
touch "/Volumes/HD2/prospector/.prospector-backup-target"
```

(The marker is just a sentinel file; its contents don't matter. If a drive is ever reformatted, re-bless it.)

## 3. Point the config at the targets

Edit `config/prospector.yaml`, the `backup:` block, and set both target paths:

```yaml
backup:
  targets:
    - /Volumes/HD1/prospector
    - /Volumes/HD2/prospector
  marker: .prospector-backup-target
```

> Changing config is honest by design: the next `pros run` will emit a `config.changed` fossil with the diff
> before any sensor runs. That's expected — it's the record noting you configured backups.

## 4. First backup — and read the output

```sh
uv run pros backup
```

Expected (one line per target, both `registry=ok`, no `FAULT` lines):

```
/Volumes/HD1/prospector: copied=<N> skipped=0 bytes=<B> registry=ok
/Volumes/HD2/prospector: copied=<N> skipped=0 bytes=<B> registry=ok
```

Sanity checks:
- **Run it again** — the second run should show `copied=0 skipped=<N>` on both (incremental; nothing new to
  copy). That proves the incremental mirror works.
- **Prove the fail-loud guard** (optional but worth doing once): eject `HD2` and run `uv run pros backup`
  again. HD1 should still get the data, and the command should **exit non-zero** with a
  `FAULT /Volumes/HD2/prospector: not mounted-and-blessed …` line. That's the dead-drive alarm working —
  a missing drive faults loudly, it never silently skips. Re-attach HD2 and re-run to reconcile.

## 5. [CRITICAL] Prove the restore — a backup you've never restored from is a hope

Run the restore test against one drive's backup and compare the counts to the live store:

```sh
uv run pros store verify-restore /Volumes/HD1/prospector
```

Expected:

```
restored from /Volumes/HD1/prospector: leads=<L> events=<E> snapshots=<S> fund_objects=<F> skipped=0
spot-check: compare these to the live store (`pros lead list` / `pros store reindex`)
```

Now compare against the **live** store:

```sh
uv run pros lead list          # eyeball the lead count vs. `leads=<L>` above
uv run pros store reindex      # prints events_indexed / snapshots_indexed — should match E / S
```

If the restored `events`/`snapshots`/`fund_objects` match the live store and `skipped=0`, the backup is
**usable**, not merely copied. This is the step that rules out the worst outcome — discovering a broken
backup *after* the disk dies.

> What this proves: `verify-restore` rebuilds a throwaway store from the backed-up **fossils alone**
> (via reindex), so a clean result means the fossils are complete and self-sufficient even if the
> `registry.sqlite` copy were also lost. (Known gap, by design: reindex rebuilds the lead record but not the
> **funds table** — fund identity restores instantly from the `.backup` registry copy on the drive, which is
> also backed up. Teaching reindex to rebuild funds from `registry/funds/*.json` is a named follow-up.)

## 6. Cadence (interim, until the M7 scheduler)

The clean cadence — "back up after every run" — lands with the **M7 autonomy core** (the LaunchAgent wrapper
runs `uv run pros run && uv run pros backup`). Until that slice is activated, keep the record current one of
two ways:

- **Manual** — run `uv run pros backup` yourself after each `uv run pros run`. Simple; fine for now.
- **Standalone timer** — a small `com.prospector.backup.plist` LaunchAgent on its own schedule. Defer this
  to the M7 session (it shares the launchd wrapper/PATH/`.env` gotchas the M7 checklist will cover) rather
  than building a throwaway now.

## 7. Done when

- [ ] Both drives blessed; `config/prospector.yaml` `backup.targets` set to both.
- [ ] `pros backup` writes to both (`registry=ok`, no `FAULT`); a second run is fully incremental.
- [ ] Ejecting a drive makes `pros backup` fault loudly (non-zero) while the other drive still gets the data.
- [ ] `pros store verify-restore` counts match the live store, `skipped=0`.

After this, the record is on **both HDDs** and **proven restorable**. Disk-death is covered; fire/theft
(offsite) stays deferred M7-hardening.
