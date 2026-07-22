# Post-#99 QA sweep — findings (2026-07-22)

*A cold-read QA sweep of everything merged since PR #99, delivered to the build seat as the independent
deep check its state-of-health survey (`2026-07-21-repo-state-of-health-sweep.md`) invited. Read against
the **fetched repo of record at `main` `6eccdabf542258da399fb578a56f76ee6bec42a8`** (spec **rev 17**,
v1.0.6) — not the local checkout, not the state doc. Base of the sweep = PR #99 (`43c556de`, QA's last
repo read). Delta: **38 merged PRs (#100–#137), 74 files, +7521/−166.***

*Method: four parallel adversarial tracks (mandate B1 stack · capture/EDGAR · ops/firewall/config ·
register/doc-truth), each grounded in reproduction, not reading — every code finding below was **proven
by planting the violation, forcing the error, or diffing real fixtures**, per the standing "prove the
gate bites; a green suite is not evidence" discipline. Baseline suite at current main: **710 passed, 1
skipped, 2 xfailed** (offline, from repo root, package installed editable — last session's
`test_run_lock` env-artifact is gone once the package is installed, confirming it was never a repo
defect).*

*This is the first full-scale sweep run through the delivery path QA hardened on itself — procedure
stamp, `reviewed_sha` truth-gate, injectable transport. It held.*

---

## 0. Verdict

**Healthy, and the heaviest change area is the most defensively built.** The mandate B1 stack — 8 PRs on
the fault/alarm layer, the charter's highest-risk target — is scarred with exactly the hazard it was
built to defend against (`spurious-mandate.changed` is named in the code four times, with a real recorded
incident, MANDATE-MULTIFUND-SECTION), and its guards are correctly ordered. It uses **recorded-real
fixtures**, not synthetic happy-paths. That is the opposite of the fixture-hardcodes-the-happy-path
failure class.

**One HIGH finding, reproduced.** A submissions-shape drift is swallowed as "no filing → dormant" on
both the SOI and mandate paths, and the SOI path's own docstring **claims a guard it does not have**.
This is the GPWS class in its purest form: the alarm that should fire on ingestion breakage is silent
*by tested design*, and a reader trusts a contract that is false.

**Two MED, two LOW, all reproduced** (five findings total: one HIGH, two MED, two LOW). One real
(narrow-trigger) false-`mandate.changed` in multi-fund isolation; one firewall S3 gate blind to the
standard alternate import; two test-integrity items. **The
register is accurate** (every sampled ✅ row's cited test exists; no phantom citations) and the owed work
beyond the code findings is, as the survey said, **documentation** — three stale headline docs.

Nothing here should block; F1 wants a fix before the next live filing season, the rest are unhurried.

---

## 1. Findings, severity-ranked

### F1 · HIGH · confirmed bug + false invariant · a submissions-shape drift goes silently dormant, and the guard-that-isn't lies about it

**`prospector/ingest/edgar.py`: `latest_soi` (:287), `latest_prospectus` (:243), `prospectus_history` (:264); `classify_soi_target` docstring (:346); consumed at `runner.py:944` (mandate) and `runner.py:1250` (SOI).** Introduced pre-#99 but squarely in the swept surface and untouched by it.

All three columnar helpers catch `(KeyError, TypeError)` on `submissions["filings"]["recent"]` and return `None`/`[]`. Their callers read that `None` as **"no filing of this family on record"** — a benign not-yet — with no fault. So a *successful* fetch that returns a **shape-drifted** submissions dict (SEC versions this JSON; a registrant whose filings live only in the unpaginated `files[]` pages) is indistinguishable from a genuinely filing-less registrant. On the mandate path (`runner.py:944`: `cur = latest_prospectus(subs); if cur is None: continue`) this means **every watched fund silently goes dormant on the mandate sensor, fleet-wide, with zero fault emitted** the moment SEC drifts the shape.

The sharp part — and why this is HIGH, not MED — is that the code's own **stated contract says this cannot happen.** `classify_soi_target`'s docstring (`edgar.py:346`):

> *"a swallowed exception — e.g. a submissions-shape change — **becomes SOI_ERROR and surfaces**, instead of masquerading as a not-yet."*

It does not. `latest_soi` eats the `KeyError` one layer *below* the `except Exception: return None, SOI_ERROR` handler, so no exception ever reaches it; `soi is None` takes the `return None, SOI_NOT_YET` branch, and the runner's N8 block (`if reason in (SOI_AMBIGUOUS, SOI_ERROR)`) is skipped. **The docstring's own named example is the exact case that stays silent.** An invariant asserted in prose but false in code is worse than a missing one — a reader (or a future seat) trusts it.

**Reproduced** (offline, real code, current main):
```
drifted = {"filings": {"recentFilings": {...}}}     # fetch SUCCEEDS; SEC renamed the container
classify_soi_target(cik, client) -> (None, 'not_yet')      # docstring promises 'error'; SILENT
latest_prospectus(drifted) -> None                          # runner.py:944 -> 'continue', no fault
# a genuinely filing-less registrant returns IDENTICAL (None, 'not_yet') — indistinguishable
```
And `tests/test_edgar_client.py:496 test_latest_soi_missing_columns_returns_none` **actively locks in the swallow** (`assert latest_soi({"filings": {"recent": {}}}) is None`) — a test pinning a defect as if it were the contract.

**Disposition (ruled by the design seat, code-checked by QA):** surface as an **operational fault**, not a review-advisory — the submissions JSON is a controlled source fetched with declared identity (expectation-of-success → page), and the failure is fleet-wide/systematic, not a one-document judgment. The cry-wolf risk is dissolved by a **drift-scoped suppression key** (`key="submissions_shape"`, not per-fund) so a fleet-wide drift pages **once** and rides the heartbeat — the volatile-message mechanism from the §10 fix, applied correctly. The three helpers gain a distinction between *shape-unparseable* (raise/fault) and *genuinely-absent* (None); one change makes SOI's docstring true for the first time. Belongs in its own register row alongside the fix.

**RED/GREEN feasible:** yes, cleanly. RED: a shape-drifted-but-successful submissions dict asserts `classify_soi_target` returns `SOI_ERROR` (fails today, returns `not_yet`) and the mandate pass emits one `submissions_shape` fault (fails today, emits none). GREEN against the three-helper fix. The fix **inverts** `test_latest_soi_missing_columns_returns_none` — that test going RED is the proof the fix bites; it should be rewritten, not supplemented.

### F5 · MED · confirmed bug · a multi-fund prior whose header fetch fails yields a spurious `mandate.changed` on a non-first fund

**`prospector/sensors/mandate.py:146` (prior-side isolation), via `_isolation_args` (:65) which never inspects `coverage["complete"]`.** Introduced by #130 (fund-block isolation, PR2).

`scan` vets the **current** filing's coverage through `_coverage_verdict`, which correctly maps `complete: False` (header truncated *or unfetchable*) to a `"review"` disposition → a review-advisory, no diff. But the **prior** side (line 146) passes `series_classes(cik, prior_accession)` straight into `_isolation_args`, which branches **only** on `len(series) <= 1` — it never checks `complete`. So when the prior's header fetch raises `EdgarError`, `series_classes` returns `{series: {}, complete: False}`, and `_isolation_args` returns `(None, None)` — **silently identical to a legitimate single-fund prior**. The prior is then extracted **whole-document** while the current isolates its fund's block. For a **non-first** fund in a multi-fund filing, whole-doc extraction returns the *first* fund's strategy section, the isolated current returns *this* fund's — the diff is a change that isn't real.

**Reproduced** on the recorded-real Goldman multi-fund fixture (`goldman_multifund_body_300911.html`, real SGML header covering `S000106340`, `S000106341`):
```
series S000106340 (Core Plus Bond, 1st): reliable=True changed=False   # first fund converges
series S000106341 (Income ETF, 2nd):     reliable=True changed=True    # *** spurious mandate.changed ***
```
— identical bytes on both sides, a false strategy change from the isolation asymmetry alone, which would accrete `mandate.changed` onto any live lead touching that fund.

**Reachability (why MED, not HIGH):** headers are fetched **on-demand, accession-keyed** (`pull_header` → `filing_header(cik, accession)`), so this is **not** a cross-era problem — a "legacy" prior gets its header fetched fresh and comes back `complete: True`, isolation applies symmetrically, no bug. The trigger is narrower: a **transient `EdgarError` on the prior's header fetch** (network/404/503) coincident with a new current filing for a non-first multi-fund fund. Occasional, not fleet-wide — but it fires a real page on noise, the nuisance-alarm class. The existing tests cover the *symmetric* multi-fund diff (both sides isolated, `test_mandate_sensor.py:619-621`); the asymmetric one-side-failed case is the gap.

**RED/GREEN feasible:** yes. RED: drive `scan` with a multi-fund current (header OK) and a prior whose `series_classes` raises `EdgarError`, targeting a non-first fund; assert **no** `mandate.changed` (fails today — emits one). GREEN by making `_isolation_args` (or its caller) treat prior `complete: False` the same way the current side does — a review-advisory, refusing to diff on unverifiable prior coverage rather than silently falling back to whole-doc. Asserts behaviour (no spurious change), not the specific disposition.

### F3 · MED · confirmed gap · the #127 firewall S3-confinement gate is blind to `botocore`

**`tests/test_firewall.py:105` (`test_s3_access_is_confined_to_the_one_configured_module`).** Introduced by #127.

The gate — the structural proxy for the constitution's "never read the detector's bucket" — flags a module only if `"boto3" in _imported_roots(...)`. A module that reaches S3 via `from botocore.session import get_session; get_session().create_client("s3")` imports root **`botocore`**, which is not in the check. `botocore` is boto3's engine (a hard dependency, `botocore>=1.43.x`, always installed) and `create_client("s3")` builds a fully functional client with `get_object`/`list_objects_v2`.

**Reproduced** by plant-and-check on current main:
```
plant `from botocore.session import get_session; ...create_client("s3")` in sensors/xcorr.py
  -> test_s3_access_is_confined... PASSES  (0 occurrences of the string "boto3")
plant `import boto3; boto3.client("s3")` in the same module
  -> test FAILS  (control: the gate bites on boto3)
```
Also evades: `importlib.import_module("boto3")`. Correctly caught (the survey's "aliased boto3" guess was wrong — root-split handles these): `import boto3 as b3`, `from boto3 import client`, `from boto3.session import Session`.

**Severity/context:** MED. Not load-bearing today (`config/prospector.yaml:396` `s3.bucket: null`; boto3 lazily imported, so nothing reaches S3), but it is the constitution's detector-bucket proxy and it's blind to the *standard* alternate import, not an exotic one. This is the same class as last session's firewall allowlist finding, one layer down: **the sweep tests a proxy (the `boto3` root import) rather than the capability (constructing an S3 client), and every proxy has an evasion.** The honest fix is two-part: add `botocore` (and `s3transfer`) to the forbidden roots to close the cheap hole, **and** state the S3 confinement in the docs as *a proxy with named gaps* (a bare bucket-name string with no import defeats any import-based check; IAM is the real wall and is out of repo) — the tiering discipline the CLAUDE.md consolidation just established. Cheap and unhurried.

**RED/GREEN feasible:** yes, trivially. RED: a negative-control module importing `botocore` + `create_client` is asserted caught (fails today). GREEN by adding `botocore`/`s3transfer` to the root set. Assert the capability boundary, plus a docstring/comment naming the residual (string-literal bucket names) so the gate isn't re-overclaimed.

### F2 · LOW · test-integrity · the series_classes review-advisory tests assert the harness's own hard-coded value

**`tests/test_mandate_sensor.py:260-266` (the `_run` harness's fake `report_advisory`), asserted at :410 and :417.** Introduced with the series_classes review branch.

The `_run` harness injects a fake `report_advisory` that appends an event hard-coding `"category": "review-advisory"`. So the assertions `ev["payload"]["category"] == "review-advisory"` at :410/:417 are reading the **test's own stamp**, not a value production produced — they cannot fail on the category regardless of what the real reporter does. A miniature green-on-synthetic living inside a harness.

**Not a production bug** — the *other* assertions in those tests are real (`result["action"] == "flagged_unreliable"` comes from `mandate.scan`; `not any(e["type"] == "mandate.changed")` is a real observation), and the **real** `_advisory_reporter` (`runner.py:152`) genuinely passes `category="review-advisory"`. So production is correct; the test just can't prove the category half. Same class as the prior `busy_timeout` tautology.

**RED/GREEN feasible:** yes, but it's a test-hardening item, not a bug fix — assert that `scan` *calls* `report_advisory` with the review-advisory intent (spy on the call, not the fake's output), or exercise the real reporter. Code's to land at its convenience.

### F4 · LOW · test-integrity · the deploy.sh lock-contention fix has no regression test

**`ops/deploy.sh` (the `) || rc=$?` rc-capture); no test in `tests/` shells out to it.** #119.

The #119 fix is **correct** — I drove the real `deploy.sh` with a stubbed `uv`: contention (exit 75) → exit 4 "a scheduled tick is in flight," failure (1) → exit 4 "deploy mutation failed," success → "deployed"; errexit-safe. And the faithful historical bug (`if ! ( … ); then rc=$?`) reproduces the INDEX-documented "broken checkout" mislabel under contention. But the CLI `lock-run` exit-75 path is the only thing tested (`test_run_lock.py`); the **shell rc-capture that already regressed once** (DEPLOY-LOCK-MSG, caught by the item-10 gate run, not a test) has no regression guard. A future edit to that line could silently re-break it.

**RED/GREEN feasible:** yes — a harness that drives `deploy.sh` with a stub `uv` exiting 75 and asserts the "in flight" message + exit 4 (RED against the buggy negated-compound form, GREEN against current). Sandbox note for whoever lands it: git refuses to operate in the macOS system tmpdir; run the harness under the repo/workspace tree with a bare `origin` for `fetch --tags`. This is the "prove-the-gate-bites" test owed on a fix that was found by *running* a gate rather than testing it.

---

## 2. Verified-good (checked, no defect — so it isn't re-litigated)

- **Mandate B1 stack** — recorded-real fixtures throughout (real 485BPOS, 497 stickers, split-heading TEMA, TOC-shadow VPFF, Goldman multi-fund body + real SGML headers). `html_to_text` derives line breaks from **block structure, not source whitespace** (#118), closing the split-heading and prose-as-heading `mandate.changed` classes it names. B1 over-attribution guard, freeze-before-diff, supplement-skip (#110), and the reliability gate (unreliable → review-advisory, **never** `mandate.changed`) are correctly ordered. The `mandate.changed` emission is genuinely gated behind `reliable and changed`.
- **#114 capture** — SEC identity on fetches + host-split 403 disposition correct; the **never-read wall bites** (planting `.captures_path(` in a non-writer module goes RED); capture ships **disabled by default**; write-only substrate intact.
- **EDGAR retry/identity** — no fail-silent "transient error → no data" path found *within* a successful fetch (the F1 exposure is the shape-drift-on-success case, distinct from network retry, which surfaces correctly).
- **#119 deploy-lock** — fix correct across all three exit paths (see F4 for the missing *test*, not a code defect).
- **config.py overlay (#109)** — hash-after-merge correct (`load_config` hashes **after** `_deep_merge`, asserted two ways incl. a migration-identity test); deep-merge lists-replace-wholesale; **no secrets in the hashed config** (config.py reads only the two YAML files; secrets enter via `cli/main.py::_load_dotenv` into `os.environ`, never merged).
- **store/layout.py** — `ts_compact` ↔ `ts_from_compact` true inverses across microsecond edge cases; same-second instants distinct.
- **cli/main.py** — store-path routing (`--store` > config > `./store`) unchanged; no new run-now surface.
- **#127 firewall** — the whole-package AST sweep (the QA #1 finding from `a8010d61`) is real and **bites** on `portfolio.yaml` reads and sibling-`models/` imports; the sweep-covers-the-package guard (≥40 modules) is present. Only the S3-confinement *sub-check* has the F3 gap.
- **Register (`docs/bugs/INDEX.md`)** — every cited test in the sampled ✅ rows **exists**; no phantom citations, no lingering "(this PR)/pending QA" present-tense staleness. The highest-value register-drift class (a false ✅) is absent.

---

## 3. Documentation drift (the survey's §0 verdict, confirmed at current main)

Three headline docs lag the code — consistent with the reduced-doc-cadence convention, and with the survey's own "owed work is overwhelmingly documentation." All LOW as correctness, but **A3 is a false invariant in the *constitution*** and ranks above the others.

| id | doc | drift at `6eccdabf` | note |
|---|---|---|---|
| **A3** | `CLAUDE.md:21,75` | calls `mandate.changed` *"a deferred defined-next-slice"* | **the entire mandate B1 stack is BUILT and executing** ("runs REAL execution from day one," `runner.py:923`). The constitution describes a shipped, live sensor as deferred — a false invariant, same class as F1's docstring but in the governing doc. |
| **A2** | `CLAUDE.md:6` | *"canonical spec is `docs/spec.md` (rev 15…)"* | spec is **rev 17**. The survey saw rev 16; the code moved to 17 under it. This is the *same* pointer-drift QA flagged at `a8010d61` (then 15-vs-16) — **re-drifted, not fixed.** The CLAUDE.md consolidation (endorsed: drop the version number, keep the pointer) is the fix; this is the third measurement of the same defect. |
| **A4** | `docs/state.md:1` | headline **rev 8, 2026-07-16**, spec "rev 15" | predates the whole mandate arc, SOI corroboration wiring, v1.0.4–6, and the ~710-test suite. The stalest state doc. |
| **A5** | `ARCHITECTURE.md:6` | *"Last updated after the M5 runner arc… live and firing… n=1 and unfalsified"* | predates the mandate B1 arc (M4) and v1.0.4–6. 43 KB, headline two milestones behind. |

---

## 4. Reconciliation — survey items already closed (not re-flagged)

The build survey was written at `eef1d7c`; **#136 ("Tier 0 pre-sweep cleanups") and #137 ("correct the stale rebase note") have since merged**, and **FIREWALL-ALLOWLIST was closed earlier by #127** (before the survey was written). Verified closed at current main, so none of these appear as findings above:

- **A7 / B-2** — CODEOWNERS repoint now cites `docs/decisions/2026-07-16-agent-identity-split-and-merge-gate.md`. **Closed.**
- **P-2** — spec §3b NPORT-P survivor-bias hazard now **co-located** with the stub (`spec.md:79`) — the one Category-D item from QA's `a8010d61` read. **Closed.**
- **B1** — MANDATE-PROSE-HEADING register citation repointed to the tests that exist post-#131. **Closed.**
- **C1** — series_classes `EdgarError` → review-advisory now pinned by `test_mandate_sensor.py:417`. **Closed** (and F2 notes the category-assertion caveat within it — a test-hardening nuance, not a re-open).
- **C2** — the spurious `mandate:None` CFG key is gone; `test_mandate_sensor.py:41` CFG is clean. **Closed.**
- **A6 / P-3** — the stale "Update with rebase" note carries a "Corrected 2026-07-21" bracket. **Closed.**
- **FIREWALL-ALLOWLIST** (QA's #1 at `a8010d61`) — #127's whole-package AST sweep replaced the 6/54 allowlist and **bites** (verified §2). **Closed** — F3 is a *residual sub-check gap*, not a re-open of the allowlist.

---

## 5. What I could not exercise from this seat

Named per the rule-3 ledger, so no seat assumes them checked:

- **The deployed prod tick.** "Against real data" here means the recorded-real fixtures in `tests/fixtures/` + planted/forced reproductions. The prod store on the Mini is not reachable, so the dead-man loop, #114's live 403 disposition against a real controlled host, and the v1.0.6 first-tick result (mandate advisories 3→0, per #134) are read from deploy records, not exercised — the same limit the survey names in its §6.
- **IAM** (F3) — owner-only, uncheckable here; established not load-bearing today (`bucket: null`), not that the policy is correct.
- **F1's live drift.** I reproduced the swallow with a synthetic drifted dict; I cannot confirm which specific future SEC shape-change would trigger it. The mechanism is proven; the specific real-world trigger is a when, not an if.
- **Two sub-tracks' extended sub-checks.** The capture/EDGAR and ops/firewall tracks each abandoned one dependency-gated sub-check (`lxml` XML-parse edge cases; a `moto`-backed live S3 mock) when a shared-env install wedged them. The core checks for both were completed inline without those deps (F1/F3 reproductions above use stdlib only); the abandoned sub-checks were XML-parse-robustness and a live-client S3 read, neither load-bearing to the findings.

---

## 6. If you want patches

Per house convention I've drafted findings only — no PR, no repo write. Each of F1, F5, F3, F4 has a clean RED-first regression test + `git apply`-able reference patch behind it (the reproductions above are the RED tests in embryo). **F1 is the one to land first** and it carries the design content the fix needs (operational fault, `submissions_shape` suppression key, invert the tested swallow). Say the word and I'll draft the test+patch set the house way — RED against current `6eccdabf`, GREEN against the reference fix, behaviour-asserting, with a per-finding README.
