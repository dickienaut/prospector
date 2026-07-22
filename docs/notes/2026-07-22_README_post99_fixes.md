# Post-#99 sweep — reference tests + fixes (F1, F5, F3)

**Reviewed commit:** `6eccdabf542258da399fb578a56f76ee6bec42a8` (main, spec rev 17, v1.0.6)
**Author:** Prospector QA (cold-read; proposes, does not merge)
**Design ruling of record:** F1+F5 are one class — *state-collapse* (a sentinel that fuses
distinguishable, differently-actionable states; N8 is the charter). F1 is the unfixed remainder of
N8's own named example; F5 is the same shape in `_isolation_args`. Rule applied: *when a function
returns a sentinel, enumerate every state that maps to it, and split any two that are distinguishable
AND differently actionable.* F3 is a two-part fix (extend the gate + state the residual honestly).
Sequencing: F1 first, F5 immediately behind, F3 rides with them.

## What ships
- **Reference fix:** `post99_sweep_fixes.diff` — a single `git apply`-clean unified diff, 5 files, 11
  hunks. Verified `git apply --check` on a pristine checkout of `6eccdabf`.
- **3 new RED regression tests**, shipped `@pytest.mark.xfail(strict=True)` so today's branch gate is
  green; each flips to a loud **XPASS(strict)** the moment the implementer applies the diff (the signal
  that the fix landed and the marker should be removed).

## Membrane (QA's own generate-and-check, re-runnable)
`verify_red_green(branch_shape, [3 tests], post99_sweep_fixes.diff)` →
`red_ok=True, apply_clean=True, applied=True, green_ok=True, membrane_ok=True`.
Diff hygiene: `clean=True`, 0 violations, 5 files, 11 hunks.

Full suite:
- **Delivered-branch shape** (main + 3 xfail tests, no fix): **710 passed, 6 xfailed** offline;
  `test_run_lock` (1) fails ONLY for lack of an editable install — confirmed identical on pristine and
  green (7 passed) under `pip install -e .` (CI parity). Gate is green on CI.
- **Reference-fix shape** (diff applied): green. The fix INVERTS the existing
  `test_latest_soi_missing_columns_returns_none` (renamed) to the corrected contract; that inversion is
  part of the diff, so the suite stays green after apply.

---

## F1 · HIGH · `tests/test_submissions_shape_drift.py`
**Bug:** `edgar.latest_soi`/`latest_prospectus`/`prospectus_history` caught `(KeyError, TypeError)` on a
drifted `submissions["filings"]["recent"]` shape and returned a bare `None`/`[]` —
INDISTINGUISHABLE from "this registrant genuinely has no such filing". Two harms: (1)
`classify_soi_target`'s docstring promised a shape change "becomes SOI_ERROR and surfaces, instead of
masquerading as a not-yet" — false, because the KeyError was eaten one layer below its `except
Exception` handler, so a drift returned SOI_NOT_YET (silent); (2) the mandate runner's `cur =
latest_prospectus(subs); if cur is None: continue` silently skipped EVERY watched fund on a drift
(fleet-wide dormancy, zero faults). GPWS nuisance-inverse: not a false alarm, a *silenced* one.

**RED (on `6eccdabf`, `--runxfail`):**
- `test_drift_and_absence_are_distinguishable_and_drift_surfaces` — absence returns None/[]; a drifted
  dict must RAISE. Fails: the drift returns None/[] like absence.
- `test_soi_shape_drift_surfaces_as_error_not_not_yet` — `classify_soi_target` on a drift must be
  SOI_ERROR. Fails: returns SOI_NOT_YET.

**GREEN (fix applied):** a shared `_recent_columns(submissions)` helper (single home for the shape
split) returns empty lists for genuine absence and RAISES `SubmissionsShapeError` (an `EdgarError`
subclass, so existing `except EdgarError` sites still catch it) on a drift. The three helpers call it.
The SOI path auto-corrects (raise propagates to `classify_soi_target`'s `except Exception` → SOI_ERROR,
docstring now true). The mandate runner catches `SubmissionsShapeError` BEFORE the generic `except`,
emitting ONE operational fault with a **drift-scoped `key="submissions_shape"`** — a fleet-wide drift
pages once, not once-per-fund (§10 volatile-message discipline), and stays per-fund (§9g, no `break`).

**Asserts behaviour, not implementation:** any fix that makes a drift raise an `EdgarError`-family error
while absence stays None/[] satisfies the tests (the specific subclass name is not asserted).

**Deferred (empirical, not code — Design's pagination third-state lead):** `filings.files[]` overflow
(submissions paginated; older filings on a second page the shape-guard reads as well-formed → a
`None`/`[]` that IS the right shape but INCOMPLETE). Not reproducible from code shape alone; carried as a
standing `xfail(strict=True)` contract question to Design, NOT fixed here. *(To be added as a 4th xfail
test in this file if Design confirms it wants the contract pinned — flagged, not assumed.)*

## F5 · MED · `tests/test_mandate_prior_coverage_symmetry.py`
**Bug:** `mandate.scan` vetted the CURRENT filing's coverage (`_coverage_verdict` → review on
`complete:False`) but passed the PRIOR coverage straight to `_isolation_args`, which branches only on
`len(series)<=1`. So a prior whose header FETCH FAILED (`series_classes` → `complete:False`) was treated
as single-fund → `(None,None)` → whole-doc extraction, while the current side isolated its block. For a
NON-FIRST fund in a multi-fund filing, whole-doc returns the FIRST fund's strategy → a `reliable=True,
changed=True` diff from the asymmetry alone → a spurious `mandate.changed` written permanently to the
append-only store. Design: "an asymmetric diff is a false diff."

**RED:** `test_prior_header_fetch_failure_does_not_fabricate_a_mandate_change` — real Goldman body
(`S000106341`, 2nd fund), IDENTICAL bytes both sides, prior header fetch raises `EdgarError`. Asserts NO
`mandate.changed`. Fails: emits one (the isolate-vs-whole-doc artifact). NOT an era bug — headers are
fetched on-demand, accession-keyed; the trigger is a transient fetch failure, which the test models.

**GREEN (fix applied):** `scan` vets the prior's `complete` flag with the same discipline as the current
side FIRST; on `complete:False` it routes to a review-advisory ("prior coverage unverifiable — cannot
diff symmetrically") and returns `flagged_unreliable`, never a whole-doc fallback.

## F3 · MED · `tests/test_firewall_s3_botocore_evasion.py`
**Bug:** #127's S3-confinement gate (`test_firewall.py::test_s3_access_is_confined_to_the_one_configured_module`)
forbade only import root `boto3`. `from botocore.session import get_session;
get_session().create_client("s3")` builds a working S3 client with root `botocore` (a boto3 hard dep,
always installed) and zero `boto3` strings — the sweep stayed green. Not load-bearing today
(`s3.bucket: null`); the real wall is IAM, outside the repo.

**RED:** `test_s3_confinement_predicate_catches_the_botocore_path` — the botocore module has no `boto3`
root, yet the gate's forbidden-root set must flag it. Fails on the boto3-only check.

**GREEN (fix applied, two-part per Design):** (1) `S3_CLIENT_ROOTS = ("boto3","botocore","s3transfer")`;
the confinement check flags any of them outside `store/s3_sync.py` (verified: no non-owner module imports
botocore/s3transfer today, so the real tree stays green). (2) The check's comment now STATES the residual
honestly — a proxy with named gaps (a bare bucket-name string defeats any import-based check; IAM is the
real boundary), not a capability wall. A new negative control (`test_gate_bites_on_the_botocore_s3_evasion`)
locks the botocore+s3transfer paths in.

---
## Not in this set (Code's at convenience — test-integrity, LOW)
- **F2** `test_mandate_sensor.py:260-266` — `_run` harness hard-codes `category:"review-advisory"`,
  making the `:410/:417` category asserts tautological (production is correct via real `_advisory_reporter`).
- **F4** `ops/deploy.sh` `) || rc=$?` rc-capture is correct but has no shell-out regression guard.
Both are test-hardening, not correctness bugs; left for the implementer to schedule.
