# snapshot-divergence-accumulator-bypass — a data-integrity alarm that is counted 0 and never pages

*Bug record, 2026-07-14. Status: **fixed** (reference patch drafted, pending land). Class: §1.7
nuisance-alarm/GPWS · §1.3 invariant-stated-in-prose-not-mechanism · §1.4 test-passes-for-wrong-reason ·
§1.8 fails-silently. Branch `m6-discourse-capture` @ `4739b528bc`.*

- **Symptom.** A snapshot **divergence** — an existing `(lead, ts)` snapshot whose state differs from the
  freshly-folded state (ignoring `reason`), i.e. a backdated event or a non-deterministic fold: a genuine
  data-integrity invariant break — is written to the store as a `_system` fault but **never reaches the
  run's `faults` accumulator.** So the tick's fault count reads 0 beside a fault that fired, `_compute_push`
  returns False (no page), and the next tick's prior-fault comparand is blind to it. Reproduced end-to-end
  through the real runner seam, no network: divergence on a shadow lead → accumulator = 0, store = 1,
  `_compute_push({}, faults, [])` = **False**. HIGH severity — a silent-fail on the alarm layer itself.

- **Root cause.** `_materialize_snapshots` (`prospector/runner/runner.py`, the §9 step-6 seam) calls
  `write_snapshot(..., fault_sink=store.append)`. The divergence guard in `write_snapshot`
  (`prospector/fold/snapshots.py`) emits its fault by calling `fault_sink(event)` and **returning normally**
  — it is not an exception, so the surrounding `except` in `_materialize_snapshots` never sees it. The sink is
  wired straight to `store.append`, which persists the event but does **not** append to the `faults` list the
  scan-line count, `_compute_push`, and `runlog.faults` all read. This is the *exact* split-path the
  `_emit_fault` docstring names as the bug that once "showed '0 faults this run' beside nine that fired" — the
  one remaining raw `store.append({"type":"fault"})` the §10 fault-taxonomy cleanup left in the tree.

- **Fix.** Route the divergence sink **through `_emit_fault`** so it lands in the accumulator (which also
  writes the store event, so the fossil record is unchanged). One surgical change in `_materialize_snapshots`;
  the guard in `write_snapshot` is untouched (it still takes any `fault_sink`, so a pure caller with no sink
  still raises). **Rejected:** teaching `_compute_push`/the scan-line to re-read the store for `_system`
  faults — that would re-unify the split path by widening every reader instead of fixing the one writer, and
  leaves the raw-append anti-pattern in place for the next site to copy.

- **Regression test.** `tests/test_snapshot_divergence_accumulator.py::test_snapshot_divergence_reaches_the_
  faults_accumulator_and_pages`. Drives the **real** `_materialize_snapshots` seam (where `fault_sink=
  store.append` is wired) over a **shadow** dispersion lead in burn-in — shadow leads are excluded from
  `page_worthy` by design, so the divergence fault is the *sole* page-worthy signal, isolating the dropped
  alarm without a coincident state change masking it. Asserts BEHAVIOUR, not mechanism: the divergence appears
  in the `faults` accumulator (counted) AND drives `_compute_push` → True (pages). RED on the branch
  (accumulator empty, `assert 0 == 1`); GREEN after the patch. Full suite 600 passed / 1 skipped / 3 xfailed.

- **Why the suite missed it (class §1.4).** `tests/test_snapshot_divergence.py::test_rewrite_with_different_
  state_and_sink_emits_one_fault` drives a real divergence but passes `fault_sink=faults.append` — a plain
  list standing in for the accumulator — and asserts the sink is *called*. Production wires `store.append`,
  which does not reach the accumulator. The fixture made the split path look unified: the test certifies "the
  sink fires", which is true and irrelevant; the bug is *which* sink is wired.

- **Rule born.** Reinforces the §8a fault-taxonomy rule (**every fault routes through `_emit_fault` into the
  accumulator; never a raw `store.append({"type":"fault"})`**) — this bug is that rule re-opened on the
  snapshot layer, so the entry's value is the tag, not a new rule. Candidate hardening (for the design seat, if
  ratified): make the rule un-violatable in mechanism (class §1.3) — e.g. a store wrapper that refuses a
  `type=="fault"` append except via `_emit_fault` — so a future sink cannot re-introduce the bypass.

- **References.** `notes/m6_deep_review_findings_qa.md` (SNAP-01, the full finding + reproduction),
  `notes/PROSPECTOR_M6_REVIEW_TESTS_README_QA.md` (the RED-first test package + `m6_review_fixes.diff`).
  Sibling bugs by class: E1, E2, C.1, fault-taxonomy count-lie (§1.7); N1, N2, N8, B3 (§1.3).
