"""Negative controls for procedure_stamp (step 4: the QA-skill drift stamp).

The stamp's job is to make it VISIBLE, in a findings PR body, when the QA skill
that produced the finding (the catalog copy the seat loaded) differs from the
reviewed repo source at tools/qa-skill/. If the stamp stopped discriminating —
reported MATCH regardless, or lost the per-file kernel/SKILL split — a finding
produced by an unpublished/drifted membrane would ship looking clean.

These assert BEHAVIOUR (MATCH vs DRIFT, per file), not wording, and are proven
to discriminate: RED if the stamp is neutered, GREEN against the shipped one.
Pure file reads — network-free, CI-collectable like the membrane controls.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kernel  # noqa: E402


def _make(tmp_path, skill_cat, kern_cat, skill_repo, kern_repo):
    """Build a catalog dir and a repo_root (with tools/qa-skill/) from bytes."""
    cat = tmp_path / "catalog"
    cat.mkdir()
    (cat / "SKILL.md").write_bytes(skill_cat)
    (cat / "kernel.py").write_bytes(kern_cat)
    rqs = tmp_path / "repo" / "tools" / "qa-skill"
    rqs.mkdir(parents=True)
    (rqs / "SKILL.md").write_bytes(skill_repo)
    (rqs / "kernel.py").write_bytes(kern_repo)
    return str(tmp_path / "repo"), str(cat)


def test_identical_copies_report_match(tmp_path):
    """Catalog == repo for both files -> MATCH, no DRIFT."""
    repo, cat = _make(tmp_path, b"S\n", b"K\n", b"S\n", b"K\n")
    out = kernel.procedure_stamp(repo, catalog_dir=cat)
    assert "MATCH" in out
    assert "DRIFT" not in out


def test_kernel_drift_is_flagged_and_named(tmp_path):
    """A kernel.py that differs must be flagged DRIFT and named specifically —
    this is the case that says 'distrust the finding, the gates were unreviewed'.
    SKILL.md, unchanged, must still read MATCH (the per-file split is the point)."""
    repo, cat = _make(tmp_path, b"S\n", b"K-catalog\n", b"S\n", b"K-repo\n")
    out = kernel.procedure_stamp(repo, catalog_dir=cat)
    assert "DRIFT" in out
    assert "kernel.py" in out
    assert "SKILL.md`: MATCH" in out            # per-file: prose unchanged
    assert "distrust the finding" in out         # the load-bearing warning


def test_skill_drift_is_flagged_independently(tmp_path):
    """A SKILL.md drift alone must be caught too (per-file, not all-or-nothing)."""
    repo, cat = _make(tmp_path, b"S-catalog\n", b"K\n", b"S-repo\n", b"K\n")
    out = kernel.procedure_stamp(repo, catalog_dir=cat)
    assert "DRIFT" in out
    assert "SKILL.md" in out
    assert "kernel.py`: MATCH" in out


def test_both_copies_missing_returns_empty(tmp_path):
    """Neither copy readable -> empty string (never blocks delivery, never lies)."""
    assert kernel.procedure_stamp("/nonexistent", catalog_dir="/also-nope") == ""