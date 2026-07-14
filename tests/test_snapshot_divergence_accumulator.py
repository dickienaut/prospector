"""SNAP-01 — the snapshot-divergence fault must reach the §10 faults accumulator (cold-read QA, 2026-07-14).

`write_snapshot`'s divergence guard (fold/snapshots.py) emits its fault by calling `fault_sink(...)`.
The runner wires `fault_sink=store.append` (runner.py::_materialize_snapshots), so the fault is WRITTEN
TO THE STORE but never appended to the run's `faults` accumulator. Everything downstream reads the
accumulator: the email scan-line count (`_partition_faults(ctx['faults'])`), the push decision
(`_compute_push` reads only `faults`), and the next tick's prior-fault comparand (`runlog.faults`). So a
snapshot divergence — 'a backdated event or a nondeterministic fold (invariant break)', a genuine
data-integrity break the docstring says MUST be loud — is surfaced in the store yet counted 0 and NEVER
pages. This is the exact split-path bug `_emit_fault`'s own docstring names ("'0 faults this run' beside
nine that fired"), re-opened on the snapshot layer, and the one raw `store.append({'type':'fault'})` the
§10 taxonomy left in the tree.

Why the existing suite misses it: test_snapshot_divergence.py drives a real divergence but passes
`fault_sink=faults.append` — a plain list standing in for the accumulator — and asserts the sink is
CALLED. Production wires `store.append`, which does not reach the accumulator. The fixture makes the
split path look unified (the project's signature failure mode).

This test drives the REAL runner seam `_materialize_snapshots` (where `fault_sink=store.append` is wired)
over a SHADOW dispersion lead in burn-in. Shadow leads are excluded from `page_worthy` by design, so the
divergence fault is the SOLE page-worthy signal in the tick — making the "silently dropped alarm" visible
without a coincident state change masking it.

BEHAVIOUR asserted (implementation-agnostic): after a divergent snapshot is materialized through the
runner seam, the divergence appears in the `faults` accumulator (so it is counted) AND drives a push via
the real `_compute_push`. The test does NOT assert HOW the fault reaches the accumulator (route the sink
through `_emit_fault`, append directly, whatever) — only that count + page see it. RED on m6, GREEN on fix.
"""

import json
import pytest
from pathlib import Path
from types import SimpleNamespace

from prospector.fold.fold import fold
from prospector.fold.snapshots import write_snapshot
from prospector.runner import runner as R
from prospector.store.event_store import EventStore

NOW = "2026-07-14T13:00:00Z"


def _divergence_faults(faults):
    return [f for f in faults if f.get("subsystem") == "snapshot" and "diverged" in str(f.get("message", ""))]


def test_snapshot_divergence_reaches_the_faults_accumulator_and_pages(layout, registry):
    store = EventStore(layout, registry, clock=lambda: NOW)
    lead = "disp-abcdef0123"                       # a SHADOW dispersion lead (never page-worthy itself)
    store.append({"ts": NOW, "lead": lead, "type": "lead.spawned",
                  "payload": {"kind": "dispersion", "series_id": "S1", "shadow": True}, "schema": 1})
    folded = fold(registry.events_for_lead(lead))
    assert folded.get("shadow") is True           # guard: this lead is excluded from page_worthy

    # Seed a DIVERGENT snapshot at (lead, NOW): a different status forces state_changed=True (so
    # should_snapshot saves this tick) while the on-disk state differs from the fold — tripping the
    # divergence guard when the runner re-materializes at the SAME (lead, NOW).
    diverged = dict(folded); diverged["status"] = "reverted"
    write_snapshot(layout, registry, lead, diverged, "seed_divergent", NOW)

    deps = SimpleNamespace(cfg={}, registry=registry, layout=layout)
    faults = []
    changed_leads, page_worthy = R._materialize_snapshots(deps, store, NOW, faults)

    # Precondition the isolation depends on: the shadow lead contributes NO page_worthy entry, so the
    # divergence fault is the only thing that could page.
    assert page_worthy == {}, f"expected no page-worthy state change (shadow), got {page_worthy}"

    # (1) COUNTED: the divergence is in the accumulator the email scan-line and runlog read.
    assert len(_divergence_faults(faults)) == 1, (
        "snapshot divergence did not reach the `faults` accumulator — it went only to store.append, "
        "so the tick's fault count and the next tick's comparand are blind to a data-integrity break")

    # (2) PAGES: with the divergence in the accumulator it drives a push (a data-integrity invariant
    # break MUST page). prior_faults empty -> a NEW page-worthy fault.
    assert R._compute_push(page_worthy, faults, []) is True, (
        "a snapshot-divergence invariant break did not trigger a push — the dead-man is silent on the "
        "exact class of break it exists to catch")
