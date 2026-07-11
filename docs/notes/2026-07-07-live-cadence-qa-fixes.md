# Fix plan — live-cadence QA findings (for the Code seat)

*Design-thread action plan, 2026-07-07. Derived from Claude Science's follow-up review
(`prospector_followup_review_2026-07-07.md`) — that review is the **evidence** (file:line,
reproductions, the prior-findings status table). This is the **ordered plan**: priority, the fix for
each (with design-thread refinements), and the regression test each fix must carry. Cite this + the
review + the relevant decision record when handing work back. Goal: address **all** findings — each
below has an explicit disposition (fix-now / deferred-with-reason / §10-criterion / doc-pass).*

---

## The governing frame — why the fixes are shaped this way (read first)

The three confirmed BUGs (N1, N2, N3) and N8 are **one shape**: an invariant the code *states in prose*
but *does not enforce in mechanism* — read-only §11 (N1), "two cold runs identical" (N2), no-fabrication
§3 (N3), "ambiguous exhibit → surface for review" (N8). Each was invisible because the test exercised
the **easy version** of the invariant (a writable store, two separate fresh stores, no duplicate date,
no ambiguous exhibit).

So two rules apply to every fix below:
1. **Convert the invariant from prose to mechanism** — make it un-violatable, not just documented.
2. **Land the regression test that *attempts the violation*** — not the easy case. A fix without its
   violation-test has not closed the hole; it's the test discipline that let these through, and the
   test is the durable fix. (This is the `fires-not-called` discipline one level up: prove the
   invariant *can't be broken*, not that it holds when nothing challenges it.)

Claude Science is generating regression-test patches for N1/N2/N3 — integrate those; write the
equivalent violation-test for the rest.

---

## Tier 1 — damage the archive; land BEFORE the next real tick

**N1 · dashboard read-only firewall violated** (`dashboard/app.py:61,64,65`; `registry.py:63-69`,
`runlog.py:44-45`, `resolution.py:97-98`). Rendering the dashboard flips the store to WAL, runs
CREATE-TABLE DDL, and commits 3× — and crashes on a `chmod 0444` store (the natural OS enforcement).
**Fix:** open the viewer's connection immutably — `sqlite3.connect(f"file:{path}?mode=ro&immutable=1",
uri=True)` — and add a `readonly=True` path to `Registry` (and the `RunLog`/`ResolutionMachine`
constructors the viewer touches) that **skips the WAL PRAGMA, the DDL `executescript`, and every
commit**. The point is to make the read-only CONTRACT enforced by the substrate, not asserted in a
comment — and read-only-mounting then *works* (the enforcement you want) instead of crashing.
**Test:** render the whole shell against a `chmod 0444` / immutable store and assert it renders *and*
that the connection cannot write (a write attempt raises). Fix this one first.

**N2 · tick is not idempotent on the same store** (`runner/runner.py`, `_load_prior_mf_snapshot`). A
second `pros run` on the same UTC day re-emits `launch.unverified` + `resolution.failed` with fresh
UUIDs (phase-one is "ALWAYS emit"; prior-mf is selected from dates strictly `< today`). Corrupts the
append-only fossil `launch-lag` and §9f read from. **Idempotency is the precondition for append-only** —
without it the record is append-*duplicates*-only, and you can't later tell a real duplicate from a
re-run artifact. Note the sharp interaction: the soft-fault path *deliberately invites a manual re-run*,
so this fix is what makes "re-run after the fault clears" safe. **Fix:** make the "ALWAYS emit"
phase-one passes idempotent per `(series_id, detected_at)` — check the record for an existing
`launch.unverified` before emitting (or gate the launch pass on "not already emitted this date").
Config-honesty and xcorr are already state-change-gated (idempotent) — scope the fix to the launch /
two-phase emission. **Test:** replace the two-fresh-stores test with a **same-store double-run** that
asserts event equality (run twice → identical event set; three runs → no growth).

---

## Tier 2 — live-path correctness; land WITH Tier 1 (same paths just shipped)

**N3 · price panel fabricates a cross-observation on a duplicate date** (`ingest/prices.py:103-113,408`).
`build_panel` rejects dup *tickers* but silently accepts dup *dates* → non-unique index → outer-join
broadcast fabricates a correlation observation (violates prices.py's own §3 no-fabrication invariant).
**Fix (do both):** `frame = frame.drop_duplicates(subset=["date"], keep="last")` in `_tidy` (handles a
benign vendor dup, matches same-day-repull "latest supersedes") **and** `assert panel.index.is_unique`
in `build_panel` as the loud backstop that faults as hard as the dup-ticker case already does.
**Test:** a ticker body with two rows for one date → dedupes (or faults), never fabricates.

**N4 + N7 · get the retry set right for Tiingo's cap model** (`ingest/prices.py:83-85,322-324,349-360`).
One fix, two directions. The backoff was transplanted from `EdgarClient` and carried SEC's *per-second*
assumption into Tiingo's *per-hour* cap (50/hr), where a short sleep can't reopen the window and each
429 retry *spends another request* (12×3 = 36 extra pulls — accelerates exhaustion). Meanwhile the
retry set *excludes* the transient errors backoff exists for (a routine 5xx / socket-timeout over 12
pulls hits the final raise on attempt one and silently drops a ticker). **Fix — the correct set for a
per-hour source:** retry `{500,502,503,504, connection/read-timeout}` with short backoff (transient,
clears); **do not** within-tick-retry a 429 (honor `Retry-After` if present, else soft-fault the ticker
and let the next tick's hour handle it); **drop 403** (an auth 403 never clears on retry). Mirror the
same set-correction in `edgar.py` for the 5xx/timeout half. **Test:** a fetch returning 503-then-200
recovers; a 429 soft-faults without a 36-request retry storm; a 403 does not retry.

**N8 · ambiguous-exhibit fault is silently swallowed** (`edgar.py:295-300`, `runner.py:519-520`).
`resolve_soi_target`'s bare `except → None` collapses the *ambiguous-exhibit fault* (which the design
says must surface for manual review) into an indistinguishable not-yet — so an ambiguous filing
silently re-fetches every tick until the 180-day horizon and never surfaces (your 07-06 SOI doc says
"observe it once" — right now you can't). The bare except also swallows real programming errors (a
`KeyError` on a submissions-shape change) as not-yets. Same "refuse-to-guess → fault" discipline as
§9b/§9d, defeated by a too-broad except; on the wired §9d path. **Fix:** return a **typed marker** that
distinguishes ambiguous-fault from not-yet, emit an `ingest.soi` fault on ambiguity, and **narrow the
except** so programming errors surface instead of masquerading as not-yets. **Test:** an ambiguous
(>1-candidate) exhibit emits an `ingest.soi` fault and is not silently re-fetched.

---

## Tier 3 — dashboard honesty; ONE pass with N1 (same files)

**N5 · config path hardcoded, no env override** (`dashboard/app.py:30,56`). Mirror the store:
`Path(os.environ.get("PROSPECTOR_CONFIG", "config/prospector.yaml"))` + `if not path.is_file():
st.warning(...); return` — graceful degrade instead of an unhandled `FileNotFoundError` under a
container WORKDIR / systemd unit. **Test:** missing config → warning, not a crash.

**N10 · INERT `off-thesis-real` lead surfaces in the "Active leads — real evidence" panel**
(`dashboard/views.py:65-71`). `active_nonshadow` filters status+shadow, never verdict, so an inert
disposition renders as a live actionable signal — the "state-as-signal" dishonesty the read-only
surface exists to prevent. **Fix:** exclude or visually demote `off-thesis-real` from
`rank_active_leads`. **Test:** an off-thesis-real lead does not appear in the priority panel.
(INFERRED — hinges on the oracle emitting the verdict without a paired `.reverted`; verify the trigger.)

---

## Tier 4 — cheap, in the same batch

- **N6 · `_run_sensors` prologue outside a soft-fault boundary** (`runner.py:201-224`). A non-integer
  `identity.retry_days`, or a registry-init failure, escapes to the single backstop and blinds the
  *entire* sensor+ingest phase — the opposite of "one fund's 404 never blinds the others." **Fix
  (cheapest):** validate `retry_days` as int at config-load (catches it earlier than a boundary);
  optionally wrap the prologue in its own soft-fault boundary. **Test:** a bad `retry_days` faults at
  load, not mid-tick.
- **H4 · plain `REAL ESTATE INVESTMENT TRUSTS` alias** — add the one-line entry to `gics_industry_alias`
  → Real Estate. Only synthetically reachable today (the real fixtures render it under CORPORATE BONDS),
  but a cheap safeguard. **Test:** the synthetic plain-header fixture resolves, doesn't fault.
- **H2 · SPDR source `ext="csv"`** → `ext="xlsx"` (mislabels the frozen fossil only; harmless to parsing).
- **S3 · `SERIES_ID_RE`/`_LEAD_RE` `^…$` admits trailing `\n`** → use `\Z` or `fullmatch`.
- **report.py · `acute_crises: []` → IndexError** — the empty-list case still isn't covered above line 99;
  guard it.
- **Ledger note · `_load_prior_mf_snapshot` lexical date compare** (`d.name < current_date`) — correct
  only while every dir is `YYYY-MM-DD`; a one-line `datetime.fromisoformat` parse makes the ordering
  intent explicit and safe against any other naming.

---

## Deferred — NOT now (dispositioned, with reason)

- **N9 · SOI corroboration pass has no cadence gate** (`runner.py:497-524`) — 2 SEC requests per
  unresolved launch per tick for up to 180 days. **Defer to M7:** cadence throttling *is* M7's job
  (the docstring already names weekly), and it costs **nothing today** — the dormant pile is empty, so
  it's 2×0 requests. Gate it when M7 lands or when N (unresolved launches) grows, not before.

## §10 acceptance criterion — build INTO the step-4 sender (not a now-fix)

- **C.1 · recurring-fault push = the nuisance-alarm your own smoke-detector brief predicts (§2.4 GPWS).**
  `_compute_push` returns `changed_leads or faults`, so a *persistent* fault pushes every tick — the
  alarm that fires on noise trains you to disable it. Inert today (NullNotifier). **Acceptance criterion
  for §10:** push once on a *new* fault (a fault absent from the prior tick's fault set), then fall
  silent into the weekly heartbeat until it clears or changes. The dead-man already covers "silence ≠
  healthy," so every-tick fault pushes buy only alarm fatigue. Write this into the §10 spec now so it's
  built in, not bolted on.

## Doc pass — owed, SEPARATE (not code; the batch checkpoint)

- **C.2 · inverted doc drift** — the `run_tick`/`_run_sensors` docstrings say "thin spine … launch
  only" while xcorr/mandate/SOI are wired; `ARCHITECTURE.md` is stale by a milestone (~1,900 LOC, cites
  rev12/M4/470-tests). Regenerate "what's built" from the actual wired set. Fold into the owed doc pass
  alongside the **§5 refresh** (now materially behind — the whole runner arc + live firing) and the
  **three-register cleanup** (label written/queued/aspirational; status lives only in §5).

---

## Completeness — every finding has a home

| Finding | Disposition |
|---|---|
| N1 read-only firewall | **Tier 1** — fix first, OS-enforced + violation-test |
| N2 non-idempotent tick | **Tier 1** — dedup ALWAYS-emit passes + same-store test |
| N3 fabricated observation | **Tier 2** — dedupe + assert + dup-date test |
| N4 + N7 retry set (Tiingo cap / 5xx-timeout) | **Tier 2** — one corrected retry set |
| N8 silent ambiguous-exhibit | **Tier 2** — typed marker + fault + narrow except |
| N5 config path | **Tier 3** — env-override + guard |
| N10 off-thesis-real in active panel | **Tier 3** — demote/exclude |
| N6 prologue soft-fault gap | **Tier 4** — config-load validate |
| H4 plain-REIT alias | **Tier 4** — one-line alias |
| H2 ext label · S3 regex · report.py empty-list · date-sort | **Tier 4** — cheap sweeps |
| N9 SOI cadence gate | **Deferred → M7** (0 cost today) |
| C.1 nuisance-alarm | **§10 acceptance criterion** (into the sender) |
| C.2 doc drift + §5 + three-register | **Doc pass** (owed, separate) |

---

## Sequencing

Tiers 1–3 + the Tier-4 cheaps land as **one arc** — they cluster on the runner / prices / dashboard you
just shipped — each fix carrying its violation-test (integrate Science's N1/N2/N3 patches). Then the
**owed doc pass** (C.2 + §5 + three-register). Then **§9e**. §10 carries C.1 as an acceptance criterion
when the sender lands; N9 waits for M7. Nothing here is aspirational — it's the queue, ordered by what
threatens the archive first.
