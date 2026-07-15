# Prospector QA — Cold Review of PR #67 and PR #66

**Reviewed:** the two most recent code-change pull requests, both open/unmerged, both based on `main` @ `0ac09fa90d4d`. Code of record = the authenticated GitHub tarball of each branch — not the local working tree, not the state-of-project doc, and **not the PR body's own claims** (the body says what Code believes it did; this review confirms it against the actual code and real data).

| PR | Title | Branch @ head |
|----|-------|---------------|
| **#67** | Tier-4 sweep — close the low-severity tail (v1 free-standing) | `tier4-sweep` @ `e07399563b88` |
| **#66** | feat(store): single-writer lock + deploy coordination — close M7-04/M7-06 | `m7-04-06-single-writer-lock` @ `7c1f36ed3f6f` |

(PR #64 — my own findings-trail from the previous run — was skipped per instruction. Note #65 has since merged the fix for my M7-DASH-01 finding.)

**Baselines (env `prospector`, py3.12.13, `PYTHONPATH=.`, repo-root CWD):**
- main @ `0ac09fa9`: **622 passed, 1 skipped, 2 xfailed**
- `tier4-sweep`: **629 passed** (+7 = the 7 new violation tests)
- `m7-04-06-single-writer-lock`: **629 passed** (+7 = the new `test_run_lock.py`)

**Method.** A green suite is not the evidence — over synthetic fixtures it is this project's signature false-pass. Every verdict below is backed by a reproduction driving the **real** code path over a recorded-real or runner-faithful substrate: the real TEKX SPDR holdings file; a real on-disk `EventStore`/`Registry`; **two real OS processes** contending for one lock; the actual code run under `python -O` (which strips `assert`); a real `SIGKILL` crash-recovery.

---

## Verdict summary

**PR #67 — all 11 claims CONFIRMED-CLOSED.** Five real fixes verified on real substrate; and — the part that needed independent scrutiny — all **six "already-fixed-on-main" drift-corrections confirmed genuinely closed on main** (no false ✅; the drift was false-*open*, the safe direction, exactly as Code asserted).

**PR #66 — all 6 concurrency checks CONFIRMED-CLOSED,** including the two-process mutual-exclusion, the acquire seam, no-side-effects-on-refusal, and the self-flagged macOS deviation (the sanity-check Code asked for: it holds).

**Both PRs are sound and merge-ready on the merits.** Deconfliction: they touch **disjoint regions** of `registry.py` (#66 adds one `busy_timeout` PRAGMA in `__init__`; #67 changes the two upload-bookkeeping methods) — **no merge conflict** whichever lands first.

The cold read surfaced **three new findings, all LOW/latent** — none blocks either merge. One is worth acting on: a latent loud→silent inversion sitting on the very H3 fix #67 is proud of; I've shipped a RED test + reference patch for it.

| ID | Sev | PR | One-line | Actionable |
|----|-----|-----|----------|-----------|
| **H3-DECOY** | **LOW (latent)** | #67 | prefix header match is first-match-wins → a `Weighted Average Life` decoy column shadows the real `Weight` column silently (bites when the universe extends to bond funds) | **Yes — test + patch in this branch** |
| LOCK-TEST-TAUT | LOW | #66 | the `busy_timeout` test is tautological (CPython's `connect(timeout=5.0)` default already yields 5000) — passes even with the PRAGMA deleted | Test-integrity fix (recommend) |
| DEPLOY-OVERLAY-DRIFT | LOW (residual) | #66 | deploy locks from the dev checkout on the premise dev/prod resolve `store.root` identically; drift in the untracked `prospector.local.yaml` overlay would lock the wrong store silently | Design-acknowledged; on-Mini check |

---

## PR #67 — Tier-4 sweep

### The five real fixes (each shipped with a violation test) — all CONFIRMED-CLOSED

- **H3 (header match by prefix).** `holdings._col` now matches header columns by `startswith`, so the `Weight (%)` issuer variant resolves where exact membership faulted. On the **real TEKX xlsx** both trees parse identically (n=35, top weight 0.0706 — regression-safe); `Weight (%)` FAULTS on main and PARSES on branch; a genuinely-alien header (`Security/Pct/Symbol`) FAULTS on **both** trees — no loud→silent inversion. *(But see H3-DECOY below — the prefix match has a latent hole the mandatory-negative test doesn't cover.)*
- **S5 (`pd.isna` guard).** Guards added before every str-cast of sector (`launch_corroboration.py:69-70`), ticker and identifier (`rebalance.py:81-82, 94-96`). Real-shaped frame with a `np.nan` sector: main yields a phantom `'nan'` bucket, branch yields only the real sector. A NaN-ticker row carrying a real identifier is correctly **kept** (the fix targets `NaN→'nan'` only, not real rows).
- **lag-lexical-sort.** `cross_stream_lag` now sorts T1 spawns by `parse_ts` (`launch_corroboration.py:241`), symmetric with T2. With a `.5Z` spawn that sorts lexically-first but chronologically-second, main picks the wrong spawn (lag 9.5s) and branch picks the true-earliest (10.0s).
- **sql-assert (fail-closed under `python -O`).** `pending_uploads`/`mark_uploaded` (`registry.py:143-158`) now select SQL by literal-dict lookup keyed on table. **Verified under `python -O`** (`__debug__=False`, assert stripped): on main the injection string reaches SQLite (`ProgrammingError`/`OperationalError`); on branch both raise `KeyError` — fail-closed under both `-O` and normal.
- **BK-MSG-01 (my finding from the last review).** The "retry once the drive is healthy" hint is now gated on `isinstance(e, OSError)` (`backup.py:238-239`). Injecting a `KeyError` into the copy path: main mislabels it a drive fault; branch says "unexpected error — investigate" and carries the real class name. Injecting an `OSError`: branch **still** gives the drive hint — the discriminator did not over-narrow.

### The six drift-corrections (claimed already-fixed on main) — all independently CONFIRMED-CLOSED on main

This was the claim I would not take on trust: a "was already fixed" disposition that closes a register row ✅ while the defect is actually live would *hide* a real defect (the dangerous, false-*closed* direction). For each, the defect was confirmed genuinely closed on main, with the citing line and a reproduction that the pre-fix form actually failed:

- **H2 (`ext="xlsx"`).** `_rows_from_body` dispatches on **magic bytes** (`PK\x03\x04`), not filename — so the `ext` value is not even load-bearing for reading; legacy `.csv`-named xlsx fossils still read. Byte-identical to main. False-open.
- **H4 (REIT alias).** `config/prospector.yaml:279-280` carries the `Real Estate Investment Trusts → Real Estate` alias; `soi._build_table` layers it on the canonical table. Plain `REAL ESTATE INVESTMENT TRUSTS` rolls up **with** the alias and to `None` **without** it (confirming the alias is what closes it).
- **S3 (`\Z`-anchored ID regexes).** `SERIES_ID_RE`/`CLASS_ID_RE`/`_LEAD_RE` end in `\Z`, which rejects a trailing newline that the old `$` form admitted (`'S000006415\n'` matches under `$`, is rejected under `\Z`).
- **report.py (empty acute_crises).** `((stress_validation or {}).get('acute_crises') or [{}])[0]` — the pre-fix `sv.get('acute_crises',[{}])[0]` genuinely `IndexError`s on a present-but-empty list (a get-default does not apply when the key is present).
- **edgar-matches[0] (ambiguous symbol).** `edgar.py:400-404` returns `ResolutionFailure('ambiguous_symbol')` *before* the `matches[0]` pick when a symbol maps to >1 distinct `(cik, series)`. Fires only on genuine ambiguity (an unambiguous symbol takes a different, non-ambiguity path).
- **ledger-datesort (parsed date compare).** `runner.py:170` compares `date.fromisoformat(name)` rather than lexically, so a basic-ISO `20260709` dir is correctly seen as a prior of `2026-07-10` where a lexical `name < current` filter would miss it.

### NEW — H3-DECOY (LOW, latent) · verified by my own hand + fix shipped

**`prospector/ingest/holdings.py` — `_col` (lines ~146-156), used to locate the weight column.** The H3 fix made `_col` match by prefix and **first-match-wins**. A decoy column whose name merely *starts with* `"weight"` — e.g. **`Weighted Average Life`, a standard column on SPDR fixed-income (bond ETF) holdings files** — placed before the real `Weight` column is read *as* the weight, silently, with no fault. It then passes the H1 weight-sum sanity band and flows downstream. That is the exact **loud→silent severity inversion** the sweep's own build-note ground-rule names as its one design line — and the shipped mandatory-negative test only covers a *fully-alien* header, not a prefix-decoy collision.

**Reproduced by my own hand** on the branch code of record:
```
header: Name,Weighted Average Life,Weight,Sector   rows: ACME,55,60,…  BETA,45,40,…
  main (exact membership): weights [0.60, 0.40]  — the real Weight column
  tier4-sweep (prefix):    weights [0.55, 0.45]  — the DECOY column, NO fault
```
**Latent, not live:** the real TEKX equity-ETF fixture has `Weight` as its only weight-prefixed column (idx 4), so the current universe never triggers it. It would bite the moment the universe extends to bond funds — which is a plausible near-term direction for a dispersion engine.

**Fix (shipped in this branch, Option-2 — QA proposes, implementer applies):** `h3_decoy_fix.diff` makes `_col` prefer an **exact** match over a prefix match, and faults loud when >1 weight-prefixed column is present with no exact `Weight` — the same fail-loud-not-silent rule the prefix match itself is meant to protect. RED-first tests in `test_holdings_weight_decoy.py` drive the **real** `parse_spdr_holdings` (decoy-before-real header on a real-shaped body), plus an over-correction guard (single `Weight` and the `Weight (%)` variant both still parse). RED against `tier4-sweep` (1 xfail) → GREEN against the fix (1 XPASS-strict); full suite **630 passed / 1 skip / 2 xfail** on the fix tree, zero regressions.

**Sequencing:** the patch targets the H3 code, which lives on `tier4-sweep` — `git apply --check` is **clean on `tier4-sweep`** and (correctly) **does not apply on main** (main has no H3 fix yet). So it is a **follow-on to #67**: fold it into #67 before merge, or apply to main after #67 lands.

---

## PR #66 — single-writer lock + deploy coordination

New file `prospector/store/run_lock.py` (an advisory `fcntl.flock` on `<store.root>/run.lock`), acquired by `pros run` and by `deploy.sh` via a new `pros store lock-run`. All six checks CONFIRMED-CLOSED — and because a lock's whole value is that it *actually excludes*, these were run as real cross-process reproductions, not readings:

1. **Excludes a second writer** — two real OS processes against one store: holder = `pros store lock-run … sleep 45`; a concurrent `pros run` **refused, exit 1**, "another tick holds …/run.lock — refusing to start a second writer". After releasing, the same `pros run` exited 0 and wrote fossils. (The in-suite tests use an in-process `CliRunner`, which does *not* prove cross-process exclusion — this real two-process run is the load-bearing evidence.)
2. **Acquired at the right seam** — the four config fail-fast validations all raise *above* the lock (`main.py` ~246-284); the lock is at ~301, `Registry(...)` (first store-writer) at 306. Proven: with the lock held by another process, a **misconfigured** run returned the *config* error, not the lock error — so validation precedes the lock.
3. **No side effects on refusal** — after the blocked run, the store contained **only** `run.lock`: no `registry.sqlite`, no `runs/`, no `events/`. Pages-no-one holds structurally (the notifier's send path runs only inside `run_tick`, past the lock).
4. **`busy_timeout=5000` on the writer only** — set on the writer path (`registry.py:89`, after WAL, before DDL); the `readonly=True` branch returns *before* it, and the `mode=ro` reader still rejects writes (N1's read-only firewall intact). *(But the test guarding this is tautological — see LOCK-TEST-TAUT.)*
5. **The macOS deviation (the sanity-check Code asked for) — holds.** The build note specified shell `flock -n`; macOS has no `flock(1)`, so Code used `pros store lock-run` (runtime `fcntl.flock`). Verified all three surfaces (`run`, `lock-run`, `lock-path`) derive the lockfile from **one** config path: with `store.root` in config and no `--store`, `pros store lock-path` printed the path, a `lock-run` holding it made `pros run` refuse *naming that exact path*. This is truer to the note's "one lockfile both sides derive identically" than a separate shell primitive would have been.
6. **Crash-safety** — the lock is advisory `flock` (never a lockfile-by-existence; the file is never unlinked). Reproduced: acquire in a subprocess → same-store acquire refused → `SIGKILL` the holder (no chance to release) → the **next acquire succeeded immediately**, no recovery step. A crashed holder cannot wedge the runner; the persisting `run.lock` file is harmless. This is what makes the documented `launchctl kickstart -k` escape hatch safe by construction.

### NEW — LOCK-TEST-TAUT (LOW, test-integrity) · green-for-the-wrong-reason
**`tests/test_run_lock.py:64-65`.** The test asserts `registry.conn PRAGMA busy_timeout == 5000` — but CPython's `sqlite3.connect(timeout=5.0)` **default** already makes every connection report 5000. So the test **passes identically with the PRAGMA line (`registry.py:89`) deleted**, and passes identically on the read-only connection. It verifies neither that our code sets the writer's timeout nor the "writer-specifically, not the reader" claim it appears to guard. **The production code is correct** (PRAGMA on writer only; reader stays `mode=ro`) and the PRAGMA even adds belt value if the connect default ever changed — this is a test-integrity gap, not a live bug: a future regression that dropped the writer's `busy_timeout` would leave this test blind. A behaviour-asserting version sets `connect(timeout=0)` on a probe and asserts the writer reads 5000 (from the PRAGMA) while an equivalently-probed reader reads 0. Same green-on-synthetic pattern as the codebase's recurring class, one layer down — worth tightening but not a merge blocker.

### NEW — DEPLOY-OVERLAY-DRIFT (LOW, residual, design-acknowledged) · NOT introduced by this PR
**`ops/deploy.sh:61-65` + `config.py:45-53` (the per-checkout `prospector.local.yaml` overlay).** The deploy takes the lock via `pros store lock-run` **from the dev checkout**, on the premise that dev and prod resolve `store.root` to the *same* external store. But `store.root` lives in the per-checkout, untracked, gitignored `prospector.local.yaml` overlay. If those overlays ever drift between checkouts, a deploy would lock the **wrong** store and could proceed (checkout + `uv sync`) during a live tick, silently — the bad direction (a lock that guards nothing is worse than one that's visibly broken). The decision doc explicitly names this as the one gap the mechanism cannot verify from inside itself and scopes it to an **on-Mini check**: run `pros store lock-path` from *both* checkouts and assert the paths are identical. Not reproducible in a single-checkout sandbox — flagged so that on-Mini verification is not lost. The in-repo path derivation itself is correct (check #5).

---

## Recommendation

1. **Both PRs are correct and merge-ready on the merits** — every fix and every concurrency guarantee verified on real substrate; no regressions; no merge conflict between them. The merge stays your call; I don't merge.
2. **H3-DECOY** — a RED-first test + `git apply`-clean reference patch are in this branch. It's a **follow-on to #67** (targets the H3 code on `tier4-sweep`; applies clean there, not on main). Fold into #67 before merge, or apply to main after #67 lands.
3. **LOCK-TEST-TAUT** — recommend tightening the `busy_timeout` test to assert behaviour (probe with `connect(timeout=0)`); the production code needs no change. Trivial; fold into #66 or a follow-up.
4. **DEPLOY-OVERLAY-DRIFT** — no code change; carry the on-Mini `lock-path`-equality check into the deploy runbook so it isn't lost.

The headline: **both PRs do exactly what they claim, verified on real data — and #67's harder meta-claim (six rows already fixed on main) held up under independent check with no false close.** The one latent hole (H3-DECOY) sits on the very fix the sweep is proud of, and it's caught before the universe grows into it.
