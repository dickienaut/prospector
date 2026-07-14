# M6 discourse-capture — QA review of branch `m6-discourse-capture`

**Reviewed:** branch `m6-discourse-capture` (unmerged) vs `main`, fresh-eyes QA read, 2026-07-13.
**Seat:** Claude Science (QA) → for the Claude Code (implementation) seat.
**Scope:** `ingest/capture.py` (new, 281 LOC), the runner wiring (`_run_capture`/`_capture_due`/`_capture_meta`,
~148 changed LOC in `runner/runner.py`), the budget guard, deps/cli/dashboard/store wiring, `test_capture.py`.
**Branch health:** full suite **597 passed, 1 skipped, 2 xfailed** — green. The `moto` skip and the two
xfails (N9 cadence gate, my §10 E2 flapping case) are pre-existing/expected.

**Bottom line:** the build is careful and the design is sound — the write-only wall, the disabled-unless-armed
gating, the per-lead weekly gate, the secret handling, and the budget counter all hold up under a cold read
and against the real data shapes they consume. **One HIGH-value finding** (a nuisance-alarm risk on the exact
alarm layer the project has twice been bitten on), **one LOW/latent gap**, and several **verified-good**
notes that would otherwise look like review gaps. Everything below is reproduced against the real code.

---

## HIGH — `capture.query_drift` will fire on every capture if the web_search API normalizes the query at all

**Where:** `runner/runner.py:994-998`
```python
issued = res.get("query_issued")
if issued is not None and issued != query:   # §6 no-LLM-authorship: fault loud on divergence
    _emit_fault(store, "capture.query_drift", f"provider issued {issued!r} != templated {query!r}",
                now, faults, lead=lead, key="capture.query_drift")
```

**The assumption:** that the query string the model puts on the `web_search` tool call
(`server_tool_use.input.query`) is **byte-identical** to our templated query. The comparison is exact — no
`.strip()`, no normalization.

**Why it's fragile on real data.** Our query never reaches the tool call directly. It's embedded as
*instruction text inside a prose prompt* (`capture._prompt`: "Use the web_search tool to run this exact
search query, verbatim… {query}"), and the model then decides what string to place in the tool-call `query`
field. `tool_choice={"type":"tool","name":"web_search"}` forces the model to **use** the tool — it does
**not** guarantee the `query` field is a verbatim copy of our text. A live model is free to trim trailing
whitespace, collapse doubled spaces, normalize smart quotes/unicode, drop a trailing period, or re-case. Any
one of those makes `issued != query` **true on every capture**, and `capture.query_drift` fires every tick a
capture runs.

**Why that's the worst possible place for it.** This is precisely the GPWS "cried wolf" failure mode the
smoke-detector brief §2.4 names and that this project has *already been bitten by twice on the alarm layer*
(the §10 nuisance-suppression bug, caught in QA). A `query_drift` fault that fires on benign normalization
trains the operator to ignore the one fault that is supposed to mean "the no-LLM-authorship wall was
breached — the model rewrote our search." An alarm that cries wolf on the determinism guard defeats the
determinism guard.

**Why the test suite misses it.** `test_capture.py`'s fake provider (`_fake_call`, line 34) constructs the
tool call by literally echoing our query back: `input={"query": query}` where
`query = body["messages"][0]["content"].splitlines()[1]`. So `query_issued == query` **by fixture
construction** — the test guarantees the ideal the real API does not. Same shape as H1/H4/§10: green against
a synthetic fixture that hard-codes the happy path, silent on the real substrate.

**Suggested handling (design call, not a prescription):**
- **Compare on a normalized form** — `issued.strip() != query.strip()`, or a light canonicalization
  (collapse internal whitespace, NFC-normalize) applied to BOTH sides before the `!=`. This keeps the guard
  meaningful (a genuinely *reworded* query — added/removed/reordered terms — still trips it) while not
  faulting on cosmetic normalization. Keep the raw `query_issued` in the blob for forensics either way (it
  already is).
- Or, if byte-exactness is truly the contract, **prove it holds** against the live API first (one real
  armed call, compare bytes) before shipping the strict `!=` — otherwise the guard's first real-world act is
  to page. I can't make that call from here (the API isn't reachable offline and capture is unarmed), which
  is exactly why I'm flagging it rather than asserting the outcome.

This is a one-line fix either way; the value is in catching it before capture is armed and the alarm goes off
on day one.

---

## LOW / latent — the monthly-USD cap silently stops enforcing if `unit_price_usd` is unset

**Where:** `runner/runner.py:980-987`
```python
mo = budget.count("month", month_key)
if unit_price and mo * unit_price >= float(budget_usd):   # <- gated on `unit_price` being truthy
    ... pause ...
```
`unit_price = float(cap.get("unit_price_usd") or 0.0)`. If a future config sets `monthly_budget_usd` (arming
capture) but leaves `unit_price_usd` null/0, the USD cap evaluates `if 0.0 and …` → **never enforces**. Only
the weekly *count* cap (`max_searches_per_week`) then protects spend.

**Severity is LOW because** the shipped config sets `unit_price_usd: 0.01`, and rev7/the build note are
explicit that the **count** cap is the primary hard limit (searches are "exactly countable"; USD is an
"estimate"). So this is defensible-by-design, not a bug. But it's a silent degradation: the operator who
zeroes `unit_price_usd` (e.g. "I'll track cost elsewhere") loses the dollar ceiling with no signal. A
one-line guard — fault or warn if `monthly_budget_usd` is set while `unit_price_usd` is falsy — would make
the degradation loud instead of silent, matching the project's "never a silent skip" discipline.

---

## Verified good (so these don't read as unreviewed)

Each of these was a plausible failure site I checked against the real code / real data and found **correct**:

- **The per-lead weekly gate round-trips.** `_capture_due` reads `state["capture_inventory"]`; `fold()` DOES
  populate it from `capture.stored` events (fold.py:172-177, recording `ts`). Verified end-to-end: a stored
  capture makes the lead not-due at 3 days, due at 8 days, due when never captured. The gate is not dead —
  leads do not re-capture every tick.
- **`_capture_meta` matches the real dispersion payload.** It reads `clusters[].members[].{name,weight}`.
  The real `dispersion_tick_payload` (dispersion.py:179+) produces exactly that shape. Verified: a real
  payload → `_capture_meta` extracts `['Apple Inc','Microsoft Corp','Exxon Mobil']` weight-desc. (This was
  my prime "assumption without evidence" suspect — it holds.)
- **The budget cap can't overshoot the weekly limit.** The check is `count >= max` BEFORE issuing, and
  `record_search` commits the increment the moment a search is issued (before results are stored) — so the
  count is the metered truth even if a later step faults. Reproduced via `test_budget_breach_pauses_and_faults`.
- **The write-only wall is enforced by a grep test** (`test_never_read_wall_only_capture_writer_touches_
  capture_blobs`), same shape as the portfolio-firewall tests. `_capture_meta` reads event *payloads*, never
  a capture blob — the wall holds.
- **The prose wall is a testable block-type filter.** `CaptureProvider.search` keeps only
  `web_search_tool_result` blocks and drops `text` blocks; `test_provider_search_keeps_only_result_blocks_
  drops_prose` asserts the model prose never reaches the store.
- **Secret handling mirrors the Tiingo `_Secret` discipline** — `ANTHROPIC_API_KEY` wrapped, redacted
  repr/str, read only in the header builder, never interpolated into an error message.
- **Capture faults already carry the §10 stable key.** Every capture fault emits with a stable,
  message-independent suppression key: the status-bearing sites use `key=f"capture.search:{status}"` /
  `f"capture.fetch:{status}"` (via `CaptureError.status`), and the fixed-input sites use a literal key
  (`key="capture.query_drift"`, `key="capture.budget:searches"`/`:usd`) since they have no status to key on.
  Either way the suppression key is independent of the URL/query-bearing message — the fault-suppression fix
  from the last QA round propagated into new code. Good.
- **Disabled-unless-armed holds, and fails fast.** Provider is `None` unless `monthly_budget_usd` set AND
  `ANTHROPIC_API_KEY` present; cli raises loudly if budget is set but key is missing (main.py:245-250).
- **Shadow leads never capture** (`active_nonshadow_lead_ids`, asserted by `test_shadow_leads_never_capture`)
  — burn-in leads don't spend budget.

---

## Note for the record

The one finding is, again, on the **alarm layer** — the third time in this project that the reviewable risk
isn't the happy-path machinery (which is well-built and well-tested) but a fault/alarm that a synthetic
fixture proves benign and real data would make cry wolf. The determinism *guard* is a good idea; a
byte-exact guard on a string that round-trips through a live model is the fragile way to implement it. Worth
settling before capture is armed — the failure mode is silent until the first real search, then it's daily.

I can draft a RED-first regression test (a fake provider that normalizes the echoed query — trailing space /
smart quote — asserting no `query_drift` fault fires) plus the one-line normalized-compare fix, in the same
RED/GREEN + git-apply-able-diff convention as the §10 and N-series work. Say the word.
