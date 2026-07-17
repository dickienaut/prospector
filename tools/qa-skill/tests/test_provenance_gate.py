"""Membrane control: the provenance TRUTH gate in ``deliver_qa_findings_pr``.

These are QA's own negative controls, lifted out of a dead session and into the
repo so the checker is checked by something other than itself. They assert the
BEHAVIOUR of the gate, not its implementation: a findings PR that does not bind
to the exact commit QA fetched+read+tested must be REFUSED before anything is
pushed.

All three rejection paths are network-free: when ``base_sha`` is supplied the
function never resolves the ref over the wire, and the reviewed_sha guards raise
before the first request. (The *accept* path does reach the network and is
covered separately once injectable transport lands — see
test_membrane_controls.py for the network-free half that can run today.)

RED/GREEN target:
  * RED  — against a kernel where the ``reviewed_sha is None`` guard is opt-in
           (the historical ``if reviewed_sha is not None:`` shape): the None
           case would fall through and attempt a push instead of raising.
  * GREEN — against the shipped kernel (``if reviewed_sha is None: raise``).
"""
import os
import sys

import pytest

# Import the RELOCATED skill kernel as source (tools/qa-skill/kernel.py), the
# parent of this tests/ package. stdlib-only at import time, so CI needs no
# extra deps to collect this module.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kernel  # noqa: E402

_DUMMY_SHA = "a" * 40  # a syntactically valid 40-hex base so no ref lookup fires


def _deliver(reviewed_sha):
    """Call the delivery gate with a fixed base_sha (network-free) and the
    given reviewed_sha. Any real push is unreachable past the guards under test."""
    return kernel.deliver_qa_findings_pr(
        head_branch="qa/does-not-exist",
        files={"docs/notes/_x.md": "x"},
        title="t",
        body="b",
        base_branch="main",
        base_sha=_DUMMY_SHA,
        reviewed_sha=reviewed_sha,
    )


def test_omitted_reviewed_sha_is_refused_not_pushed():
    """Absence is a hard refusal: a findings PR cannot stamp a commit it never
    bound to. The message must say the delivery did not happen."""
    with pytest.raises(ValueError) as ei:
        _deliver(reviewed_sha=None)
    assert "reviewed_sha is REQUIRED" in str(ei.value)


def test_malformed_reviewed_sha_is_refused():
    """A non-40-hex reviewed_sha cannot be a commit; refuse before pushing."""
    with pytest.raises(ValueError) as ei:
        _deliver(reviewed_sha="not-a-real-sha")
    assert "40-hex" in str(ei.value)


def test_reviewed_sha_not_matching_base_is_refused():
    """Valid hex but != base head: the branch moved between review and delivery,
    so the stamp would name a commit QA never saw. Refuse (provenance mismatch)."""
    with pytest.raises(RuntimeError) as ei:
        _deliver(reviewed_sha="b" * 40)
    assert "PROVENANCE MISMATCH" in str(ei.value)
