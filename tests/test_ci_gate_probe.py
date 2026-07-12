"""THROWAWAY — a deliberate CI-gate probe.

Exists only to prove the `main` ruleset blocks a PR whose `test` check is red
(docs/decisions/2026-07-11-ci-and-branch-protection.md, Phase 3). This file and
its PR are deleted immediately after the block is confirmed — it must never
reach `main`.
"""


def test_ci_gate_probe_deliberately_fails():
    # Intentional failure: if the gate works, this PR cannot merge.
    assert False, "deliberate CI-gate probe — expected red; this PR must be blocked"
