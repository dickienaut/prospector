"""Membrane control: ``verify_red_green`` must DISCRIMINATE.

The RED/GREEN membrane is what makes a QA finding self-checking rather than a
claim — it proves the RED test fails on the unfixed tree (the bug is real) and
passes once the reference .diff is applied (the fix resolves it). A membrane
that says "ok" no matter what is worse than none: it launders a bad finding.

So the control is not "does it pass on a good finding" — it is "does it FAIL on
the two ways a finding can be wrong":

  * a test that never goes RED (passes on the unfixed tree)   -> red_ok False
  * a fix that is a no-op (RED test still fails after apply)  -> green_ok False

These run ``git apply`` + pytest on throwaway trees. No network. This is the
half of the CI gate that can land as soon as the skill has a testable home;
the delivery-path guards that mock the network wait for injectable transport.

RED/GREEN target:
  * RED  — against a kernel whose membrane returns membrane_ok unconditionally
           (or omits the red_ok / green_ok discriminators): both asserts below
           would see membrane_ok True and fail.
  * GREEN — against the shipped kernel (membrane_ok = red_ok AND apply_clean
           AND applied AND green_ok).
"""
import os
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kernel  # noqa: E402


def _seed_git_env():
    """qa_git_env() neutralises the global/system gitconfig so ``git apply`` works
    in any sandbox — but that also removes any configured committer identity, and
    a CI runner may have none to auto-derive. Set an explicit identity for the
    throwaway ``git commit`` so this fixture is hermetic and does not depend on
    the runner's git config (green-here-red-in-CI is exactly what we hunt)."""
    env = kernel.qa_git_env()
    env.update(
        GIT_AUTHOR_NAME="qa-test", GIT_AUTHOR_EMAIL="qa-test@example.invalid",
        GIT_COMMITTER_NAME="qa-test", GIT_COMMITTER_EMAIL="qa-test@example.invalid",
    )
    return env


def _git_init(root, env):
    # Mirror the house convention: tests/ is a package (empty __init__.py). This
    # makes pytest insert the REPO ROOT onto sys.path (the first parent without
    # __init__.py), so a code-under-test module at the repo root imports the same
    # way it does in the real prospector suite. Without it pytest would insert
    # tests/ instead and the import would fail — a fixture artifact, not a bug.
    open(os.path.join(root, "tests", "__init__.py"), "w").close()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=root, check=True, env=env)


def _write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(textwrap.dedent(text))


def test_membrane_fails_a_never_red_test(tmp_path):
    """A test that passes on the UNFIXED tree is not a reproduction. The membrane
    must report red_ok False (and therefore membrane_ok False), whatever the diff."""
    repo = tmp_path / "repo"
    repo.mkdir()
    # a test that passes right now — never RED
    _write(str(repo), "tests/test_thing.py", """
        def test_always_passes():
            assert 1 + 1 == 2
    """)
    genv = _seed_git_env()
    _git_init(str(repo), genv)
    # a diff that changes an unrelated file (applies clean, irrelevant to the test)
    diff = tmp_path / "fix.diff"
    diff.write_text(
        "--- a/tests/test_thing.py\n"
        "+++ b/tests/test_thing.py\n"
        "@@ -1,2 +1,3 @@\n"
        " \n"
        " def test_always_passes():\n"
        "+    # touched\n"
        "     assert 1 + 1 == 2\n"
    )
    res = kernel.verify_red_green(str(repo), ["tests/test_thing.py"], str(diff))
    assert res["red_ok"] is False, res
    assert res["membrane_ok"] is False, res


def test_membrane_fails_a_no_op_fix(tmp_path):
    """A RED test with a fix that does not resolve it must report green_ok False.
    Here the test asserts on a value the diff never changes, so it stays RED after
    apply — a no-op fix. membrane_ok must be False."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(str(repo), "value.py", "ANSWER = 1\n")
    # RED now: expects 42, code says 1
    _write(str(repo), "tests/test_value.py", """
        import value
        def test_answer_is_42():
            assert value.ANSWER == 42
    """)
    genv = _seed_git_env()
    _git_init(str(repo), genv)
    # no-op fix: touches a comment, does NOT change ANSWER
    diff = tmp_path / "fix.diff"
    diff.write_text(
        "--- a/value.py\n"
        "+++ b/value.py\n"
        "@@ -1 +1,2 @@\n"
        "+# not the fix\n"
        " ANSWER = 1\n"
    )
    res = kernel.verify_red_green(str(repo), ["tests/test_value.py"], str(diff))
    assert res["red_ok"] is True, res          # the bug IS real (test is RED)
    assert res["green_ok"] is False, res       # but the fix does not resolve it
    assert res["membrane_ok"] is False, res


def test_membrane_passes_a_real_red_then_green(tmp_path):
    """Positive control: a genuinely RED test + a fix that resolves it -> membrane_ok."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(str(repo), "value.py", "ANSWER = 1\n")
    _write(str(repo), "tests/test_value.py", """
        import value
        def test_answer_is_42():
            assert value.ANSWER == 42
    """)
    genv = _seed_git_env()
    _git_init(str(repo), genv)
    diff = tmp_path / "fix.diff"
    diff.write_text(
        "--- a/value.py\n"
        "+++ b/value.py\n"
        "@@ -1 +1 @@\n"
        "-ANSWER = 1\n"
        "+ANSWER = 42\n"
    )
    res = kernel.verify_red_green(str(repo), ["tests/test_value.py"], str(diff))
    assert res["membrane_ok"] is True, res
