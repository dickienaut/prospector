# Machine-local config lives in an untracked overlay; the config hash covers the merged result

*Decision record, 2026-07-12. Implements the untracked-overlay "clean answer" that
`2026-07-12-production-worktree-and-deploy.md` named and deferred ("must fold into the config-hash /
config-honesty CONTRACT"). Amends the config-honesty CONTRACT (spec §5) — the hash is now over the
**effective merged** config. Supersedes that record's deploy.sh stash/pop machine-config preservation
(now unnecessary). Design thread concurring.*

## The problem it fixes

Machine-local **paths** — this Mac's absolute `store.root` and its HDD `backup.targets` — lived as a
**working-tree override in the *tracked* `config/prospector.yaml`** (as did the deployment's EDGAR contact),
and `deploy.sh` preserved them across each tag checkout with a `git stash`/`pop` dance. One-machine specifics
have no more business in the shared repo than the SMTP password does (which correctly lives only in `.env`).
The seam showed its cost concretely: the same edit, left uncommitted in the dev clone, put HDD paths into the
tracked file and **broke a test** (`test_pros_backup_faults_nonzero_when_no_targets_configured`, which asserts
the shipped `backup.targets: []`).

## The decision

**Machine-local config lives in an untracked `config/prospector.local.yaml` overlay, deep-merged over the
tracked config at load.** The config analog of `.env`: gitignored, never committed, per-machine.

- **One choke point.** `load_config(path)` loads the tracked YAML, then — if a **sibling**
  `prospector.local.yaml` exists (resolved as `Path(path).with_name(...)`, never a fixed cwd path) —
  deep-merges it over the base (dicts recurse; scalars **and lists** replace wholesale, so `backup.targets`
  overrides rather than appends). Absent overlay → the base unchanged. Applied **uniformly** — the live
  runner, the CLI, and the backtest all read one merged config, so the backtest's frozen-price read and its
  per-run write stay rooted at the same `store.root`. This is safe because backtest write-isolation is
  *structural* (`StoreLayout kind="backtest"` + `backtest_run_root`), independent of `store.root`'s value —
  a `store.root` override cannot leak a backtest write into the live `events/` tree.

- **The CONTRACT fold (config honesty §5): the hash covers the EFFECTIVE MERGED config.** The single
  sha256 in `load_config` is computed *after* the merge, so `config.changed` fossilizes exactly the config
  a run used, and a machine-local change **does** emit `config.changed` — correctly, because machine-local
  config is real, **non-secret** config; recording it (paths, contact) is honest. This is the dividing line
  that puts config in the overlay and secrets in `.env`: an API token or SMTP password must *never* be
  fossilized, so it stays env-only and never enters config; a store path or backup target *should* be
  fossilized when it changes, so it lives in config (tracked or overlay).

- **`deploy.sh` drops the stash/pop.** An untracked, gitignored file is invisible to `git checkout --detach`,
  so the overlay survives every deploy with zero gymnastics and zero risk of a silent machine-config wipe.

## Migration (no spurious `config.changed`)

The overlay is populated with the machine's *current effective* values and the tracked file is reset to its
defaults, so the **effective merged config is byte-identical** and the hash does not move — the first run
after migration emits nothing. (`test_overlay_migration_preserves_hash_when_effective_config_is_identical`
pins this.) The overlay captures the two **per-machine paths** — `store.root` and `backup.targets`. The third
override, `edgar.user_agent`, is **not** machine-specific (it is the deployment's SEC contact, invariant across
the owner's machines), so it is set as the **tracked default** (`lyle@alphalabsengineering.com`) rather than
overlaid — same effective value, so the migration still moves no hash. The rule that falls out: the overlay is
for values that genuinely differ *per machine* (paths); deployment identity belongs in the tracked config;
secrets belong in `.env`.

## Scope / what this is not

A config-*loading* change plus its CONTRACT fold. It does not touch the store format, the firewall, the
runner order, or the deploy-from-tag CONTRACT. Secrets management is unchanged — `.env` remains the only home
for `TIINGO_API_TOKEN` / `PROSPECTOR_SMTP_PASSWORD`, never config.
