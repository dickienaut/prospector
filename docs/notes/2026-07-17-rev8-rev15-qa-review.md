# QA cold-read: rev8 state-of-project + rev15 build spec (and a docs-organization read)

**Reviewer:** QA seat (cold read from repo of record) · **Verified against `main` @ `5cf0b62`**, 2026-07-17
**Method:** fetched the branch by API, diffed each rev against its predecessor in `history/`, and **verified every load-bearing claim against the actual code + a real pytest collection** — not against the doc's own account.

---

## Part 1 — Does the newest rev read right? (rev8 state, rev15 spec)

**Verdict: both are accurate and well-made. Claims check out against code. One low-severity number is stale; two small map-lag items. No cry-wolf, no over-claim.**

### What Code did (from git, not the prose)
- `e7a4c0a4` state **rev7 → rev8** ("v1 build-complete, register-transit")
- `d9ce81b3` spec **rev14 → rev15** ("fold the ratified M5/M7 sensor-and-alarm arc") — **+22 / −7 lines**, a surgical fold, not a rewrite
- `15cea0f4` (latest, 07-17 10:37) — **doc-drift correction**: "M6 capture is BUILT" — annotated in-place as `§9 correction (2026-07-17)`

### Load-bearing claims — VERIFIED GOOD against the code
| Claim in rev8/rev15 | Checked against | Result |
|---|---|---|
| M6 discourse capture is BUILT (the 07-17 correction) | `prospector/ingest/capture.py` (14.4 KB), runner phase-5 `_run_capture` | **TRUE** — fully wired, ships `disabled` unless budget+provider injected; budget cap, stable fault keys, `query_drift` guard all present |
| rebalance runner-wired (last M4 sensor) | `_run_rebalance` in runner.py | **TRUE** — silent accretion sensor, no lead of its own |
| M7 autonomy core built (launchd + dead-man) | `ops/` = plist, run.sh, deploy.sh, install/uninstall | **TRUE** — files present |
| suite is green and offline | real `pytest` run | **TRUE** — `639 passed, 1 skipped, 2 xfailed` |
| spec fold is amend-not-regenerate | rev14→rev15 diff | **TRUE** — changelog block + per-section CONTRACT annotations, correction dated in-place |

The **"instrument is done; the measurement hasn't started"** framing is the strongest thing in rev8 — it holds the built/validated line honestly (dispersion firing is n=1, FDR unmeasured, dead-man arms only on activation) and explicitly resists the re-synthesis-into-a-plan drift for the v2 aspirational items. That is exactly the register discipline the doc claims for itself.

### FINDINGS

**D1 — test count is stated wrong, with false precision · LOW (doc-drift, conservative direction)**
rev8 §5.2 says **"BUILT (634 tests, all offline)"**. Real collection on `main @ 5cf0b62` is **642** (`639 passed + 1 skipped + 2 xfailed`). The `tests/` tree was last touched **2026-07-15**, ~1.5 days *before* the rev8 commit — so 642 was already the count when "634" was written; this is not "tests added since." rev7 honestly hedged ("~554 tests"); rev8 dropped the tilde and gave a wrong *exact* number. Low severity (it under-claims — no cry-wolf), but on a system whose entire discipline is "the number matches the code," a test count that disagrees with its own tree is the drift pattern worth naming. **Fix:** `642 tests` (or `~640`), and consider a one-line make-target so the rev ritual reads the number from `pytest --collect-only` rather than typing it.

**D2 — INDEX lags the newest canon · LOW (map-lags-territory, the INDEX's own named failure mode)**
`docs/INDEX.md` does not yet name **`METHOD.md`** (minted `6ea132e3`, after the INDEX pass) nor the **`2026-07-16-agent-identity-split-and-merge-gate.md`** decision. The INDEX's closing line says "a map that lags the territory is the exact failure mode the whole project fights" — so this is self-flagged by construction. **Fix:** add METHOD.md to the "Law" / cold-start section (it is now the canonical four-seat doc; the `history/…how-we-work` lineage was correctly retired), and list the identity-split decision in the trail.

**Nothing missing or wrongly added in the rev bodies themselves.** Section structure is stable (state 6/6, spec 17/17); all deltas are within-section and each is backed by a decision record that exists on disk. The M6 correction was the one real drift and Code already caught and dated it.

---

## Part 2 — A better way to organize/author the docs?

**Short version: the *structure* is already very good — better than most funded teams. The pain you feel ("a rev is a major undertaking because they interleave") is not a taxonomy problem; it is a *synthesis-by-hand* problem. Don't reorganize. Reduce the manual coupling at rev time.**

What's already right (keep all of it): the four-kind taxonomy (Contract / Decision / State / Notes) with three explicit lifetimes; live docs at the root, superseded revs in `history/`; amend-never-regenerate for contracts; the fixed rev-advance ritual; the bug archive split into doctrine (`README`) vs register (`INDEX`) with two grep axes. The `INDEX.md` is the standout — it *is* the front door done properly.

The actual friction, and targeted fixes:

1. **The two rolling docs interleave because the coupling is re-derived by hand each rev.** The spec (CONTRACTs) and the state doc (registers) both restate the same build/queued/deferred status in prose, so advancing one means hand-reconciling the other. **Fix: make the register a single generated source of truth.** One small `docs/status.yaml` (or a table) keyed by section → `{register: built|queued|deferred|aspirational, evidence: <decision-file>, test: <nodeid>}`. Both the spec's status lines and the state doc's §5.2 render *from it*. A rev then edits data, not two prose bodies, and they cannot disagree.

2. **The status claims aren't mechanically tied to the code.** D1 happened because "634" is typed. **Fix: a `make rev-check`** that (a) reads the real `pytest --collect-only` count, (b) greps that each "BUILT" section's `evidence:` decision file exists, (c) verifies each named module path is present. This is the doc-layer version of what your CI already does for code — it makes doc-drift a failing check, not a QA catch. (I just ran this by hand; it found D1 and D2. It should be a script, not a seat.)

3. **`notes/` is 45 files and mixes four things** (QA findings, build-notes, slice-specs, guidance/handoffs). It's the one folder growing without a sub-shape. **Fix (optional, low urgency):** either date-shard or split `notes/qa/`, `notes/build/`, `notes/spec-drafts/`, `notes/guidance/`. The bug archive already earned its `qa/` subfolder this way; `notes/` is next.

4. **Authoring: keep the ritual, automate its checklist.** Your rev-advance ritual (drop new rev at root, `git mv` old to `history/`, update INDEX + pointers) is correct but manual, which is why the INDEX lagged (D2). **Fix:** a `make advance-rev SPEC=rev16` that does the `git mv`, stubs the changelog entry, and prints the INDEX/CLAUDE.md/ARCHITECTURE.md pointer lines to update. Ritual stays human-decided; the mechanical steps stop being forgettable.

**The one thing NOT to do:** don't collapse the four kinds or flatten `history/`. The lifetime separation (fossil vs amended vs re-synthesized) is what makes the C-130-style lifetime archive actually usable for latent-bug hunts. The cost you're paying is the price of that discipline; the fixes above cut the cost without giving up the property.

---

*Scope note: this review verifies the *docs against the code as of `5cf0b62`*. It does not re-litigate the design decisions the revs fold (those are ratified in `decisions/`); it checks that the revs report them faithfully. They do, with the two low-severity drift items above.*
