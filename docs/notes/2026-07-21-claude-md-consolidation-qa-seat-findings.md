# CLAUDE.md consolidation — QA-seat findings (2026-07-21)

*The third of three independent reads (Design / Build / **QA**), to be reconciled into the consolidation
rev. Design's read is `2026-07-16-claude-md-consolidation-design-seat-findings.md`; Build's is
`2026-07-20-claude-md-consolidation-build-seat-findings.md`, extended by its two 7/20 orphan-sort notes.
This one answers the lane Design's §6 assigned QA — **claims that can't be checked, rules with no
mechanism, overclaims** — and the two residuals both seats handed forward by name: the **firewall
enforcement ledger** (Design: "the finding I'd most want Code and QA to check independently"; Build
corrected it to allowlists) and **Category D's true size** (Build: "the residual I'd most want QA's read
to attack").*

*Read against `CLAUDE.md` (299 lines) and `docs/spec.md` (rev 16) at main `a8010d61d1ab94f47247cfc66a14ba877821778d` — the current head, **not** the `c8d2d42` both prior reads used; the four-day gap is itself a finding (Q-1). QA's distinguishing power is that it can RUN the code and read the live repo state, so where the other seats inferred a mechanism, this read **exercised** it. Every finding names the file, line, command, or API response that establishes it, and says so where it could not be checked.*

---

## 0. On the two prior reads

**Both are sound, and the orphan-sort's central result holds under verification: the consolidation is delete-and-point, not fold-then-delete.** I re-ran Build's Category-D hunt against the full spec sections (not the grep hits) and reached the same floor it did — NPORT-P survivor-bias is essentially the only true partial. Detail in §3, because "I checked the residual you flagged and it holds" is a result, not filler.

Two places this read **diverges** — and per both seats' rule, divergence is the signal:

- **The squash-merge finding has flipped since Build wrote it, and QA's job is to say so.** Build's orphan-sort §3 (7/20) reported `allow_squash_merge: true` and called disabling it "the cheapest mechanism win available." At current main it is **`false`** — the recommendation landed. M-5 is now genuine mechanism. A read that shipped Build's note verbatim would hand the owner a stale worklist item. Detail in §2.
- **The firewall overclaim is real, is mechanically demonstrable, and the fix-template already ships in the repo.** Both seats reasoned about it; I planted the violation and watched CI accept it. Detail in §1 — this is the finding I'd rank first in the whole exercise.

---

## 1. The firewall — proven not to bite (the headline)

Design tiered the three firewall clauses and flagged the IAM claim as read from a stale snapshot. Build corrected the ledger: the grep tests exist, but they are **allowlists over 6 of 54 modules**, and proposed replacing them with a package-wide sweep. **I verified the correction and then did the thing only QA can: I made the wall fail to fire.**

**The demonstration (mechanism, not inference).** On a throwaway copy of main I appended a `portfolio.yaml` read to `prospector/sensors/soi.py` — a real module, un-allowlisted, exactly where a "read the portfolio for sector context" drift would land:

```
# planted in prospector/sensors/soi.py (NOT in any firewall test's allowlist)
def _drift_probe():
    import pathlib
    return pathlib.Path("config/portfolio.yaml")   # the forbidden read
```

Result:

```
tests/test_runner.py::test_runner_firewall_never_reads_portfolio            PASSED
tests/test_dashboard_views.py::test_dashboard_firewall_never_reads_portfolio PASSED
```

**Both firewall tests pass. CI is green on a module that reads `portfolio.yaml`.** The constitution's strongest claim — *"Never add code that reads the detector's bucket or `portfolio.yaml`"* — is enforced over `runner.{deps,notify,runlog,runner}` and `dashboard.{views,app}` and **nothing else**. `find prospector -name "*.py"` returns 54; the two allowlists name 6.

**The fix-template is already in the tree — this is the sharp part.** `tests/test_capture.py::test_never_read_wall_only_capture_writer_touches_capture_blobs` walls a rule of the *identical class* (nothing outside the capture writer locates a capture blob) with the right shape:

```python
for py in pkg_dir.rglob("*.py"):        # a SWEEP, all 54 modules
    if py == writer: continue
    assert ".captures_path(" not in py.read_text(...)
```

I planted a `.captures_path(` token into the same `soi.py` and ran that test: **it fails**, correctly, naming the offending module. So the repo contains, side by side, two walls of the same class enforced at opposite strengths — a full-sweep wall for capture blobs, a 6-of-54 allowlist for the portfolio firewall — and the constitution states both as absolute. Build's "~5 lines" estimate is generous: the sweep is a copy of a test that already exists and passes.

**Two further corrections to the ledger, both mechanically checked:**

1. **The detector-bucket clause has zero enforcement of any kind.** `grep -rin "detector.*bucket" tests/` → 0. Neither an allowlist nor a sweep. Design tiered it "mechanism" (separate repo → no import path); that is real *architecture* for the separate-repo half, but for the "reads the bucket" half within this repo there is no test at all.
2. **The IAM claim is not currently load-bearing — confirmed from config, not the policy.** `config/prospector.yaml:396` sets `s3.bucket: null`, and `prospector/store/s3_sync.py:11` documents boto3 as lazily imported so a `bucket=None` run "never touch[es] AWS machinery at all." Whatever the IAM posture (still owner-only, uncheckable from here), **nothing reaches S3 today**, so the firewall's S3 half rests on capability-absence, not IAM. This matches Build §3.3 exactly.

**QA's ruling for the consolidation:** state the firewall clauses with their true tiers, the way METHOD.md rule #3 carries a per-seat ledger — and land the **package-wide sweep** as its own PR *before* the consolidation writes "enforced," so the doc's strongest claim is true when it is written, not aspirational. An overclaimed wall is the exact defect class (overclaim; a gate that has never rejected) the consolidation is fixing everywhere else. Clause 4 — *recommends* a trade — remains correctly prose (you cannot test the absence of a recommendation), and it is the one closest to the real risk: this system talks an operator into a trade long before it places one.

---

## 2. Live repo-state claims — checked against the API today, because they move

Design's §6 gave QA "overclaims"; the sharpest overclaim class is a *mechanism claim the repo state no longer matches*. Two prior seats each found one (Build: firewall allowlist; orphan-sort: squash). Both were right when written. **One has since changed** — which is precisely why a mechanism claim must be re-checked at delivery, not inherited.

| claim in the docs | prior-seat reading | **QA at main `a8010d61`** | verdict |
|---|---|---|---|
| merge is append-only (merge commits, not squash) | orphan-sort §3 (7/20): `allow_squash_merge: true` → "cheapest mechanism win" | **`allow_squash_merge: false`, `allow_rebase_merge: false`, `allow_merge_commit: true`** (GitHub repo API) | **now mechanism — recommendation landed; the constitution can state it true** |
| `main` protected, one code-owner approval, most-recent-push, no bypass | Build C-4: closed | ruleset `main protection` (id 18823846) **active**, rules `[pull_request, required_status_checks, non_fast_forward, deletion]` | **holds** |
| Code cannot self-approve (machine account ≠ code owner) | Design C-4 (false→amending); Build (landed) | CODEOWNERS `* @dickienaut`; QA/Code bot is not an owner | **holds** |
| production deploys from a tag, by mechanism (B-M6) | Build/Design: operative, absent from constitution | `ops/deploy.sh` **refuses any non-tag ref** (`rev-parse --verify refs/tags/<t>^{commit}` or exit) **and** takes the runner's single-writer lock (`pros store lock-run`, exit 75 on contention) | **holds — genuine mechanism** |

**The squash flip is the load-bearing entry.** It changes a consolidation to-do ("disable squash first") into a settled fact ("state the rule; the wall is already up"). Shipping the orphan-sort's §3 recommendation unchanged would have been an overclaim in the *other* direction — telling the owner to do work already done. This is the entry that most justifies QA re-reading the repo rather than the prior notes.

---

## 3. Category D — the residual Build most wanted attacked

Build: *"If D has siblings, this method will not have found them, and that is the residual I'd most want QA's read to attack."* The trap is that a grep phrase-count proves the *topic* resolves, not that the **hazard qualifier is co-located with the rule** — NPORT-P scored `survivor-biased: 1` in the spec too, yet that hit was unrelated context.

**Method:** I screened all 15 CONTRACT hazard-clauses by ≥2 phrasings (Build's own discipline, §4 of the completed sort), which narrowed to four where the rule resolved but the *scar phrasing* was thin, then **read the full spec section around each** rather than trusting the count. Result:

| clause | phrase-count screen | full-section read | verdict |
|---|---|---|---|
| **NPORT-P: never filled with survivor-biased data** | flagged | spec `:67` states the stub is thin; the *hazard* clause is not co-located | **D — confirmed, Build's one** |
| series_ids never in payload (duplication → drift) | flagged (`0` on 3 phrasings) | spec carries it **verbatim**: *"The lead-id already encodes the series_ids; duplicating them in the payload invites drift"* (§4d routing) | **B — resolves** |
| proto-cluster: price-only / cluster-not-name / canary-never-trade | flagged | spec carries all three: *"canary is the **cluster, not the single name**"*, *"observation-only — the canary is never the trade"*, *"firewall discipline transfers wholesale"* | **B — resolves** |
| macro: never a trade/tilt trigger **and** never strip the β (both directions) | flagged | spec carries **both** scars — *"not an alert stream… context for human consultation only"* **and** *"must **never** be used to strip a real macro regime… a multi-factor β would **amputate signal**"* | **B — resolves** |

**QA's ruling: Build's Category-D floor holds. NPORT-P is the only true partial.** Design worried the macro clause "reads like hedging; it isn't" — verified: both directions are in the spec, richly, so the constitution's two-in-one clause is faithful, not hedged. The consolidation is confirmed as **delete-and-point + one surgical spec amendment** (`spec.md` §3b gains the survivor-bias hazard, then the CLAUDE.md line deletes). That is a materially smaller and safer change than the length of CLAUDE.md suggests, and QA's independent hunt is the second read that lets the deletions proceed.

---

## 4. Rules with no mechanism — QA's assigned lane, made concrete

Design's §6 gave QA "rules with no mechanism." Distinct from an *overclaim* (§1): these are rules stated honestly as practice, correct to keep, but a cold seat cannot tell which have a wall behind them. The consolidation should **tier them** — not to weaken any, but so the doc never implies uniform enforcement it lacks. Verified status of each operative rule the constitution carries:

| rule (CLAUDE.md) | enforcement, verified | tier |
|---|---|---|
| tests are offline; a real socket fails the test | `tests/conftest.py` autouse `_no_network` patches `socket.socket.connect` (AF_UNIX exempt) | **mechanism** |
| firewall: never read `portfolio.yaml` | allowlist, 6/54 modules — **proven not to bite** (§1) | **partial — overclaimed** |
| firewall: never read the detector bucket | **nothing** (§1) | **prose (in-repo) + architecture (separate repo)** |
| firewall: never place/size/recommend a trade | capability-absence (place/size); **nothing** (recommend) | **mechanism-adjacent / prose** |
| append-only; a changed mind is a superseding event | event-store write path + no squash (§2) | **mechanism** |
| bare ticker rejected at the write path | registry write-path validators (`identity/`) | **mechanism** |
| config hashed; `config.changed` before any sensor | emitted in the runner; `tests/test_config.py` + runner tests cover the hash/diff | **mechanism (ordering assumed — see below)** |
| no-run-now; `reindex` is repair | design-level; `pros store reindex` rebuilds from the fossil record, computes nothing new | **prose + design** |
| deploy from a tag; single-writer lock | `ops/deploy.sh` (§2) | **mechanism** |
| no auto-tune of thresholds ever | design-level; the stress gate is a frozen absolute, reviewed by hand | **prose (correctly — the point is human-only)** |

**Two I could not fully close, named per the rule-3 ledger so no seat assumes them:**

- **`config.changed` *ordering* ("before any sensor runs").** The emit exists and is tested; that it fires **strictly before the first sensor** I did not find asserted by an ordering test (I found the hash/diff tests, not a sequence test). Likely true in the code path, but "before any sensor" is a claim with no guard I could locate — a candidate for a cheap ordering test, and until then it should not be stated as mechanism.
- **The IAM policy** — owner-only, uncheckable here; established not load-bearing today (§1.2).

---

## 5. Suite baseline at current main — the ground truth the state doc lags

Ran offline, token unset, from repo root (the CWD the tests assume):

```
685 passed, 1 skipped, 2 xfailed, 1 failed  (main a8010d61, 24.6s)
```

**The one failure is an environment artifact, not a repo defect — verified, not assumed.** `tests/test_run_lock.py::test_a_killed_holder_leaves_no_stale_lock` spawns a real subprocess (`subprocess.Popen([sys.executable, "-c", "import prospector..."])`); my tarball baseline did not `uv sync`/pip-install the package, so the child raised `ModuleNotFoundError: No module named 'prospector'`. With the package importable (`PYTHONPATH=repo-root`, or CI's `uv sync`) the import resolves and the test passes. **CI installs the package, so this is green in CI.** Recorded so the consolidation's status claims key off 685+ green, not a scary "1 failed" that is really "QA didn't install the package before spawning a subprocess." (This is itself an instance of the CWD/env-assumption class the skill's step 3 warns about — satisfy it to baseline, note it, never conflate the two.)

---

## 6. What I could not check from this seat

Named per the rule-3 ledger, because QA's unverifiable-claims lane obliges QA to name its *own* blind spots:

- **The IAM policy** (§1.2, §4) — no credentials; established not load-bearing, not that the policy is correct.
- **`config.changed` strict ordering** (§4) — no ordering test found; the code path likely holds but is unguarded.
- **Completeness of the Category-D hunt** (§3) — I read four full sections beyond the phrase screen; a partial whose *topic* I didn't recognize as hazard-bearing is not in my list. Same bound Build named, one layer deeper. The floor (NPORT-P only) is a floor, not a proof of emptiness.
- **The rev-narrative's *attributions*** ("rev12 folds §4c to built") — I checked that each CONTRACT *resolves* and that the pointer is stale (Q-1), not that each historical attribution is factually right. That needs the spec's own changelog, and it is moot if the narrative is deleted per C-1.

---

## Q-1 · The finding that settles C-1, one step further than Build

Build (7/20, at `c8d2d42`): CLAUDE.md says rev 15, `spec.md` says rev 16 — B-1, the re-drift.

**At main `a8010d61` (today) it is still uncorrected**, and the gap is now visible at a glance:

```
CLAUDE.md:4        "The canonical spec is docs/spec.md (rev 15, stated in its header…"
docs/spec.md:1     "# Project Prospector — v1 Build Specification (rev 16)"
```

The opener still narrates rev12 → rev5 and stops before 13/14/15/16. So C-1 is not "should" and not even "observed once" — it is a **standing, uncorrected drift** that both prior reads flagged and that survived four days and at least one further rev. It is the single highest-value edit in the consolidation: **CLAUDE.md keeps the pointer, drops the version number and the narrative** (*"The canonical spec is `docs/spec.md`; read its header for the current rev; earlier revs in `docs/history/`"*), and the changelog moves to the spec's own changelog where it has exactly one home. QA endorses C-1 without reservation, now with the drift measured twice.

---

## Convergence / divergence check (per Design §6)

Design predicted QA would find "claims that can't be checked, rules with no mechanism, overclaims." It did — which Design warned is **weak evidence** (the predicted division is the convergent-prior signature). The entries worth the most reading are where this read is **not** downstream of the others:

- **§1 is convergent in topic, divergent in kind.** All three seats reached the firewall. But Design inferred tiers, Build corrected to an allowlist count, and QA **made it fail** — CI green on a `portfolio.yaml` read. "The wall is an allowlist" and "the wall does not bite, here is the green run" are different orders of evidence, and only the second licenses the doc to stop claiming a uniform wall.
- **§2 (squash flip) is a genuine divergence from Build**, not a convergence: the repo moved under the prior note. This is the one finding no prior read could have — it is a property of *today's* API response.
- **§3 is deliberate convergence, and I flag it as not independent:** I confirmed Build's Category-D floor by re-reading the same spec sections. Treat it as a second read licensing the deletions, not a second opinion that found new D's — it did not, and the honest report is that the floor held.

The value, as both prior seats said, is in the disagreements: the squash setting flipped, and the firewall wall — described identically to the capture wall — does not enforce identically. Both are only visible by reading the live repo, which is QA's lane.
