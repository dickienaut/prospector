# Prospector regression tests — N4, N5, N6, N7, N8, N9, N10

Seven findings from the 2026-07-07 follow-up review (`prospector_followup_review_2026-07-07.md`),
turned into regression tests. Companion to the earlier N1/N2/N3 set — together these cover all ten
findings. Every finding below was **verified by running the code first** — three of them (N6, N8, N10)
were labelled INFERRED in the review, so each was reproduced end-to-end before a test was written.

Validated against the live snapshot (repo tarball fetched 2026-07-07, 175 files). Environment:
Python 3.12, the repo's own deps + streamlit (for any dashboard AppTest — not needed by this set).

## Status matrix (against code as shipped)

| Test file | Finding | Class | Bug tests (RED) | Guard tests (GREEN) |
|---|---|---|---|---|
| `test_runner_prologue_faults.py` | **N6** | BUG (fault isolation) | 2 | — |
| `test_soi_ambiguous_fault.py` | **N8** | BUG (silent failure) | 1 | 2 |
| `test_dashboard_offthesis_rank.py` | **N10** | BUG (misrepresentation) | 1 | 1 |
| `test_prices_retry_transient.py` | **N7** | SMELL (missing retry) | 2 | — |
| `test_prices_retry_tiingo_cap.py` | **N4** | ASSUMPTION (retry policy) | 2 | — |
| `test_dashboard_config_path.py` | **N5** | ASSUMPTION (hardcoded path) | 2 | — |
| `test_soi_corroboration_cadence.py` | **N9** | SMELL (deferred design) | 1 (xfail) | — |

"Guard tests" pass today on purpose — they pin the *complement* of each bug (the lead stays in its
correct home; a genuine not-yet stays silent) so a careless fix can't go green by deleting behaviour.

Against the code as shipped: **10 RED, 3 GREEN guards, 1 XFAIL**. After
`reference_fixes_all_N1-N10.diff`, all go green (full suite **488 passed, 1 skipped, 1 xfailed** — N9
stays xfail by design; see below).

## How to run

```bash
python -m pytest tests/test_runner_prologue_faults.py \
                 tests/test_soi_ambiguous_fault.py \
                 tests/test_dashboard_offthesis_rank.py \
                 tests/test_prices_retry_transient.py \
                 tests/test_prices_retry_tiingo_cap.py \
                 tests/test_dashboard_config_path.py \
                 tests/test_soi_corroboration_cadence.py -v
```

House convention followed exactly: `tests/` is a package and no test imports a sibling test module,
so the two runner tests (`test_runner_prologue_faults.py`) are **self-contained** (own
`_deps`/`_edgar`/`_fetch_mf_only` harness), mirroring `test_runner_mandate.py`/`_xcorr.py`. The views
test reuses the local `_state` helper from `test_dashboard_views.py`.

---

## What each test asserts

### N6 — `test_runner_prologue_faults.py` (BUG)

`_run_sensors` promises per-unit fault granularity ("one fund's 404 never blinds the others"), but its
**prologue runs outside every try/except**:

```python
retry_days = int((deps.cfg.get("identity") or {}).get("retry_days", 10))   # raises on "ten"
machine = ResolutionMachine(..., FundRegistry(...), ...)
_panel = _build_sector_panel(...)
```

Verified at the `run_tick` level: a typo in the *retry-window* config (`identity.retry_days: "ten"`)
throws before the first sensor boundary, escapes to the backstop as **one `subsystem="runner"` fatal
fault**, and records **zero launches** — the entire sensor+ingest phase blinded by a value only the
retry queue uses. `test_bad_retry_days_does_not_blind_the_whole_sensor_phase` asserts the launch still
records; `test_bad_retry_days_is_a_scoped_fault_not_a_runner_fatal` asserts the fault localizes
(config/identity), not the catch-all backstop.

### N8 — `test_soi_ambiguous_fault.py` (BUG, silent failure)

`resolve_soi_target` collapses three outcomes into a bare `None`: a genuine not-yet (no SOI filing), an
**ambiguous exhibit** (`resolve_soi_document` refuses to guess between >1 candidate — the design says
surface it), and a swallowed exception. The runner's `if target is None: continue` treats all three as
not-yet and emits **no fault** — so an ambiguous filing is silently re-fetched every tick until the
180-day horizon and never surfaces. Three-way test: the unit premise (ambiguity → None today) is
pinned GREEN; `test_ambiguous_soi_exhibit_emits_a_fault` is RED (no fault today);
`test_genuine_not_yet_stays_silent` is GREEN and must stay so — proving the fix must *distinguish*, not
fault-on-every-None (which would be the nuisance-alarm failure the smoke-detector brief warns against).

### N10 — `test_dashboard_offthesis_rank.py` (BUG, misrepresentation)

`rank_active_leads` (the top-of-page "Active leads — the real evidence" panel) filters through
`active_nonshadow`, which keys on **status + shadow only, never verdict** (the fold treats verdict as
display-only — a `verdict` event sets `state["verdict"]` without touching `state["status"]`). So a lead
that is active + non-shadow + `verdict="off-thesis-real"` — the one verdict defined as INERT, with its
own read-only `macro_catalog` home and a CLAUDE.md "never a trade/tilt trigger" CONTRACT — surfaces in
the priority actionable list. RED: the off-thesis lead ranks. The guard test keeps it in the
macro_catalog so a fix demotes rather than drops it.

### N7 — `test_prices_retry_transient.py` (SMELL, missing retry)

`_fetch_with_retry` retried only `(429, 403)`. A transient 5xx (502/503/504 — routine behind a load
balancer) or a socket timeout hit the final `raise` on attempt 1, silently dropping that ticker's
column for the whole tick (a NaN the outer join can't fill — §3). RED: a 503-then-200 sequence is
dropped instead of recovered. Behaviour-asserting (retry then succeed), so it doesn't lock in a
specific status set.

### N4 — `test_prices_retry_tiingo_cap.py` (ASSUMPTION, retry policy) — DESIGN DECISION

The retry constants were copied from `EdgarClient`, whose cap is per-SECOND. Tiingo's binding cap is
**50 requests/HOUR**. Two consequences: (N4a) a 429 retried within 1-2s can't reopen an hourly window —
each retry burns another of the 50/hour, so the "backoff" accelerates exhaustion; (N4b) a 403 is an
auth refusal that never clears on retry. RED today (both retried 3×). **These encode a policy the team
hasn't committed to** — flagged as decision tests. The reference fix is **source-aware** (adds
`_Source.hourly_cap`, True only for tiingo) so per-second sources (yahoo/stooq) keep retrying 429; the
test targets the tiingo rate model specifically via that seam.

### N5 — `test_dashboard_config_path.py` (ASSUMPTION, hardcoded relative path)

`app.py` reads `_CONFIG_PATH = Path("config") / "prospector.yaml"` — a CWD-relative path with no env
override and no existence guard, so `main()` raises a raw `FileNotFoundError` from any working directory
except the repo root. The asymmetry is the tell: the **store** path one line above is both
env-overridable (`PROSPECTOR_STORE`) *and* degrades with a friendly `st.warning`; the config path has
neither. Verified by reproducing the crash from a temp CWD (traceback at `app.py:56` →
`load_config`). This is also *why the existing `test_dashboard_app.py` smoke passes* — pytest runs from
the repo root, so the relative path resolves by accident of CWD, exactly the hidden assumption N5 names.
Both tests drive the real `app.py` via AppTest from a non-root CWD:
`test_missing_config_degrades_gracefully` (RED: raw exception today; a fix must degrade like the store
path) and `test_config_path_is_env_overridable` (RED today: a `PROSPECTOR_CONFIG` env var is ignored).
The seed constructs a `ResolutionMachine` while the store is writable — runner-faithful, so the test
isolates the config path rather than tripping the read-only-store table requirement (the same seeding
lesson from the N1 dashboard test).

### N9 — `test_soi_corroboration_cadence.py` (SMELL, DEFERRED design) — `xfail(strict=True)`

`_run_soi_corroboration` resolves every unresolved launch on every tick (2 SEC requests/launch) for up
to 180 days, with no cadence gate — but **the pass's own docstring names this an "M7 scheduling
concern, not a correctness one"** and defers the weekly gate. Verified: 5 ticks with one pending launch
→ 5 SEC pulls, linear, no gate. Because this is a design decision the author explicitly deferred, the
test is marked `xfail(strict=True)`: it does **not** fail the suite today, and it flips to a loud XPASS
(prompting removal of the marker) the moment the M7 gate lands. Delete the marker to treat N9 as active
now.

---

## `reference_fixes_all_N1-N10.diff` — one complete patch to fully-green

This is a **single complete patch** that takes the live code to all-tests-green: it contains the
earlier N1/N2/N3 fixes **and** the N4/N5/N6/N7/N8/N10 fixes. It supersedes the N1/N2/N3-only diff —
apply this one instead of stacking (the two share hunks in `prices.py`/`app.py` and would conflict).
Nothing here is prescriptive; it exists to prove the tests are satisfiable and to make each finding
concrete.

**Format / how to apply.** Standard unified diff with `a/`…`b/` path prefixes, source files only
(no `__pycache__`/binary noise). Apply from the repo root:

```bash
git apply reference_fixes_all_N1-N10.diff        # or: patch -p1 < reference_fixes_all_N1-N10.diff
```

Verified with `git apply --check` against a pristine checkout, then the full suite (all prior + all 10
new test files — the 7 here plus the 3 from the N1/N2/N3 set) run green on the freshly-patched tree. Files touched (10): `dashboard/{app,views}.py`,
`ingest/{edgar,prices}.py`, `runner/{runner,runlog}.py`, `identity/resolution.py`,
`store/registry.py`, `sensors/launch.py`, `tests/test_dashboard_app.py`. (The patch carries source +
the one required edit to an *existing* test; the new test files are the separate `test_*.py` artifacts
you drop into `tests/`.)

Finding fixes added since the N1/N2/N3 set, one line each:

- **N4** — 403 removed from the retry set (fail fast); `_Source.hourly_cap` (True for tiingo) threads
  into `_fetch_with_retry` so a tiingo 429 fails fast while yahoo/stooq keep per-second 429 retry.
  **N4a broke two existing yahoo-429 tests until the fix was made source-aware** — a reminder that the
  SEC-copied retry policy is baked into the current tests, exactly the assumption N4 is about.
- **N5** — `_CONFIG_PATH` becomes `PROSPECTOR_CONFIG`-overridable + existence-guarded, degrading with
  an `st.warning` exactly like the store path (`test_dashboard_config_path.py`).
- **N6** — wrap the `_run_sensors` prologue: a bad `retry_days` becomes a scoped `config.identity`
  fault + falls back to the default (10), so launch recording is unaffected.
- **N7** — `_RETRY_STATUSES` gains 500/502/503/504.
- **N8** — add `classify_soi_target` returning `(target, reason)` where reason ∈
  {resolved, not_yet, ambiguous, error}; `resolve_soi_target` stays a thin wrapper (existing tests
  unchanged); the runner emits a `soi.corroboration.{ambiguous,error}` fault while a not-yet stays
  silent.
- **N10** — `rank_active_leads` filters out `verdict == "off-thesis-real"` at the panel boundary; the
  lead remains in `macro_catalog`.

## Regression gate

- Full suite **against the fixed tree**: **488 passed, 1 skipped, 1 xfailed** (all 10 new test files —
  the 7 here + the 3 from the N1/N2/N3 set — plus all prior tests, including the two existing yahoo-429
  tests which stay green because the N4 fix is source-aware).
- The new N4/N5/N6/N7/N8/N10 files **against the unfixed tree**: RED bug-reproductions + passing
  complement guards + 1 xfailed (N9) — the intended RED state.
