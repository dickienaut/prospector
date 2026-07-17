"""Step 6 (delivery-path guards): every refusal in deliver_qa_findings_pr must
fire BEFORE any mutating call reaches the transport. "Nothing was pushed" is the
claim each guard's error message makes; these make it mechanical.

The provenance-gate tests (test_provenance_gate.py) already prove the guards
RAISE. What they could not prove — because there was no transport seam — is that
the raise happens before a branch/blob/commit is created. A guard that validated
AFTER writing a blob would still raise, still read as "refused", and still have
littered the remote. With the injectable transport we assert the strong form:
when a guard trips, the transport recorded ZERO mutating calls.

A mutating call is any POST/PATCH/PUT/DELETE. A GET (base_sha resolution) is a
read and is allowed before a guard fires. Assertions are on BEHAVIOUR (refused +
nothing mutated), not messages.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kernel  # noqa: E402

SHA = "b" * 40
OTHER_SHA = "a" * 40
MUTATING = {"POST", "PATCH", "PUT", "DELETE"}


class RecordingTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path))
        if path.startswith("/git/ref/heads/"):
            return {"object": {"sha": SHA}}   # for the base_sha=None read path
        if path == "/git/blobs":
            return {"sha": "blobsha"}
        if path == "/git/trees":
            return {"sha": "treesha"}
        if path == "/git/commits":
            return {"sha": "c" * 40}
        if path == "/pulls":
            return {"number": 1, "html_url": "u"}
        return {}

    def mutations(self):
        return [(m, p) for (m, p) in self.calls if m in MUTATING]


def _base_kw(tmp_path, transport, **over):
    note = tmp_path / "finding.md"
    note.write_text("a finding\n")
    kw = dict(head_branch="qa/test", files={"docs/notes/x.md": str(note)},
              title="t", body="b", base_sha=SHA, reviewed_sha=SHA,
              transport=transport)
    kw.update(over)
    return kw


def test_missing_reviewed_sha_pushes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    t = RecordingTransport()
    kw = _base_kw(tmp_path, t, reviewed_sha=None)
    with pytest.raises(ValueError):
        kernel.deliver_qa_findings_pr(**kw)
    assert t.mutations() == []


def test_malformed_reviewed_sha_pushes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    t = RecordingTransport()
    kw = _base_kw(tmp_path, t, reviewed_sha="not-a-sha")
    with pytest.raises(ValueError):
        kernel.deliver_qa_findings_pr(**kw)
    assert t.mutations() == []


def test_mismatched_reviewed_sha_pushes_nothing(tmp_path, monkeypatch):
    """reviewed_sha != base_sha (branch moved between review and delivery)."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    t = RecordingTransport()
    kw = _base_kw(tmp_path, t, reviewed_sha=OTHER_SHA, base_sha=SHA)
    with pytest.raises(RuntimeError):
        kernel.deliver_qa_findings_pr(**kw)
    assert t.mutations() == []


def test_non_qa_branch_pushes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    t = RecordingTransport()
    kw = _base_kw(tmp_path, t, head_branch="main")
    with pytest.raises(ValueError):
        kernel.deliver_qa_findings_pr(**kw)
    assert t.mutations() == []


def test_dirty_diff_pushes_nothing(tmp_path, monkeypatch):
    """A .diff failing hygiene must refuse before touching the remote."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    # a dirty diff: headers lack a/ b/ labels and reference a build artifact ->
    # check_diff_hygiene flags it (it lints '--- '/'+++ ' header lines).
    bad = tmp_path / "bad.diff"
    bad.write_text(
        "diff -ru pros_old/__pycache__/x.pyc pros_new/__pycache__/x.pyc\n"
        "--- pros_old/mod.py\n"
        "+++ pros_new/mod.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n")
    t = RecordingTransport()
    kw = _base_kw(tmp_path, t, files={"docs/notes/bad.diff": str(bad)})
    with pytest.raises(ValueError):
        kernel.deliver_qa_findings_pr(**kw)
    assert t.mutations() == []


def test_clean_delivery_does_mutate(tmp_path, monkeypatch):
    """Control: with every guard satisfied, the transport DOES mutate — proving
    the empty-mutations assertions above are the guards firing, not a transport
    that never mutates."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    t = RecordingTransport()
    kw = _base_kw(tmp_path, t)
    res = kernel.deliver_qa_findings_pr(**kw)
    assert res["pr_number"] == 1
    assert t.mutations()  # non-empty: the happy path really does write