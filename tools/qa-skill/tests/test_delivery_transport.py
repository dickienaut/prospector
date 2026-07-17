"""Step 5 (injectable transport): the ACCEPT path of deliver_qa_findings_pr,
exercised end to end with NO network and NO token.

Before this, the only offline coverage of deliver_qa_findings_pr was its
rejection paths (test_provenance_gate.py) — the network-free half. The accept
path (a well-formed delivery actually creating a branch/commit/PR) could only be
tested against live GitHub, so it wasn't. The `transport=` seam closes that gap:
a fake transport(method, path, payload) -> dict stands in for the HTTP layer, so
a full successful delivery can be asserted deterministically.

These assert the BEHAVIOUR of a successful delivery — the request SEQUENCE, that
the provenance/procedure stamp lands in the body, that base_sha is not re-fetched
when supplied — not the implementation. Pure in-process; CI-collectable via the
existing testpaths.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kernel  # noqa: E402

SHA = "b" * 40


class RecordingTransport:
    """A fake HTTP transport that records every call and returns plausible
    GitHub JSON per endpoint. Never touches the network."""

    def __init__(self):
        self.calls = []          # list of (method, path)
        self.bodies = []         # list of (method, path, payload)

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path))
        self.bodies.append((method, path, payload))
        if path.startswith("/git/ref/heads/"):
            return {"object": {"sha": SHA}}
        if path == "/git/blobs":
            return {"sha": "blobsha"}
        if path == "/git/trees":
            return {"sha": "treesha"}
        if path == "/git/commits":
            return {"sha": "c" * 40}
        if path == "/pulls":
            return {"number": 123, "html_url": "https://example/pr/123"}
        return {}


def _deliver(tmp_path, transport, **over):
    note = tmp_path / "finding.md"        # non-.diff -> hygiene gate skipped
    note.write_text("a finding\n")
    kw = dict(head_branch="qa/test", files={"docs/notes/x.md": str(note)},
              title="t", body="the body", base_sha=SHA, reviewed_sha=SHA,
              transport=transport)
    kw.update(over)
    return kernel.deliver_qa_findings_pr(**kw)


def test_accept_path_runs_offline_without_token(tmp_path, monkeypatch):
    """A well-formed delivery completes with no GITHUB_TOKEN and no network."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    t = RecordingTransport()
    res = _deliver(tmp_path, t)
    assert res["pr_number"] == 123
    assert res["provenance_enforced"] is True


def test_accept_path_issues_calls_in_order(tmp_path, monkeypatch):
    """The mutating sequence is branch -> blob -> tree -> commit -> ref -> PR."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    t = RecordingTransport()
    _deliver(tmp_path, t, labels=["qa-findings"])
    methods_paths = t.calls
    # order of the mutating spine (labels last)
    spine = [(m, p) for (m, p) in methods_paths
             if p in ("/git/refs", "/git/blobs", "/git/trees", "/git/commits", "/pulls")
             or p.startswith("/git/refs/heads/")]
    assert spine == [
        ("POST", "/git/refs"),
        ("POST", "/git/blobs"),
        ("POST", "/git/trees"),
        ("POST", "/git/commits"),
        ("PATCH", "/git/refs/heads/qa/test"),
        ("POST", "/pulls"),
    ]
    assert ("POST", "/issues/123/labels") in methods_paths


def test_supplied_base_sha_is_not_refetched(tmp_path, monkeypatch):
    """When base_sha is passed, deliver must NOT GET the ref (no read either)."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    t = RecordingTransport()
    _deliver(tmp_path, t)
    assert not any(m == "GET" for (m, p) in t.calls)


def test_provenance_and_procedure_land_in_pr_body(tmp_path, monkeypatch):
    """The PR body sent to /pulls carries the provenance stamp; and when
    repo_root is supplied, the procedure (catalog-vs-repo) block too."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    # repo_root pointing at this checkout's own tools/qa-skill so procedure_stamp
    # has a source to compare against (MATCH or DRIFT, either renders a block).
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    t = RecordingTransport()
    _deliver(tmp_path, t, repo_root=repo_root)
    pulls = [pl for (m, p, pl) in t.bodies if p == "/pulls"]
    assert len(pulls) == 1
    body = pulls[0]["body"]
    assert "QA provenance" in body
    assert "QA procedure" in body      # the step-4 block, exercised through delivery