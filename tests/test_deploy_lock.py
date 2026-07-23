"""F4 — the deploy.sh lock-contention rc-capture, proven by driving the REAL script (prove-the-gate-bites).

`ops/deploy.sh` takes the single-writer lock (M7-04) around the checkout + `uv sync` and must map the
lock-run's exit to the right message: contention (`pros store lock-run` exits 75 = EX_TEMPFAIL) → "a
scheduled tick is in flight" + exit 4; a mutation failure → "deploy mutation … failed" + exit 4; success
→ "deployed" + exit 0.

The rc-capture regressed once (DEPLOY-LOCK-MSG, `docs/bugs/INDEX.md`): the historical
`if ! ( … ); then rc=$?` reads the NEGATION's status (0 whenever the branch runs), so the 75 test never
matched and real contention was mislabeled a broken checkout. The fix is `( … ) || rc=$?`. This guards it
by running the real script with a stubbed `uv` — **RED against the negated-compound form** (which returns
exit 0 / "deployed" for BOTH the 75 and 1 cases), **GREEN against the current form**. The gate was found
by RUNNING a gate, not a test (item-10, 2026-07-19); this is the owed regression test.

Sandbox: git operates on a bare `origin` + a dev repo + a prod worktree entirely under `tmp_path` — no
network (the fetch is from a local path). The REAL `deploy.sh` is COPIED into the fake repo so its
`REPO=$(git rev-parse --show-toplevel)` resolves to the sandbox, never the working repo. (QA's note that
git can refuse the macOS system tmpdir did not reproduce here; `tmp_path` is used for portability, and CI
runs on Linux.)
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SH = REPO_ROOT / "ops" / "deploy.sh"
TAG = "v0.0.0-test"


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=test", *args],
                   cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def deploy_env(tmp_path):
    """A self-contained git sandbox deploy.sh can run against: a bare origin, a dev repo carrying a release
    TAG (pushed to origin so `fetch --tags origin` resolves), a prod worktree at the tag, and the REAL
    `ops/deploy.sh` copied inside the dev repo. Returns (dev_dir, prod_dir)."""
    origin, dev, prod = tmp_path / "origin.git", tmp_path / "dev", tmp_path / "prod"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", str(dev)], check=True)
    (dev / "README").write_text("sandbox\n")
    _git(dev, "add", "-A")
    _git(dev, "commit", "-q", "-m", "init")
    _git(dev, "remote", "add", "origin", str(origin))
    _git(dev, "push", "-q", "origin", "HEAD:refs/heads/main")
    _git(dev, "tag", TAG)
    _git(dev, "push", "-q", "origin", TAG)
    _git(dev, "worktree", "add", "-q", str(prod), TAG)
    (dev / "ops").mkdir()
    shutil.copy(DEPLOY_SH, dev / "ops" / "deploy.sh")
    return dev, prod


def _run_deploy(dev, prod, tmp_path, uv_exit, ref=TAG):
    """Run the sandbox deploy.sh with a stub `uv` that exits `uv_exit` (standing in for
    `pros store lock-run`, so the lock/checkout/uv-sync never actually run), returning
    (exit_code, combined_output)."""
    stubbin = tmp_path / f"stubbin_{uv_exit}_{ref}"
    stubbin.mkdir()
    uv = stubbin / "uv"
    uv.write_text(f"#!/bin/sh\nexit {uv_exit}\n")
    uv.chmod(0o755)
    env = {**os.environ, "PATH": f"{stubbin}{os.pathsep}{os.environ['PATH']}",
           "PROSPECTOR_PROD": str(prod)}
    p = subprocess.run(["bash", "ops/deploy.sh", ref], cwd=str(dev), env=env,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


@pytest.mark.parametrize("uv_exit, want_exit, want_msg", [
    (75, 4, "a scheduled tick is in flight"),   # CONTENTION — the DEPLOY-LOCK-MSG regression path
    (1, 4, "deploy mutation"),                   # a genuine mutation failure under the lock
    (0, 0, "deployed"),                          # success
])
def test_deploy_maps_the_lock_run_exit_to_the_right_message(deploy_env, tmp_path, uv_exit, want_exit,
                                                            want_msg):
    dev, prod = deploy_env
    rc, out = _run_deploy(dev, prod, tmp_path, uv_exit)
    assert rc == want_exit, f"uv exit {uv_exit}: deploy exit {rc} (want {want_exit})\n{out}"
    assert want_msg in out, f"uv exit {uv_exit}: '{want_msg}' not in output\n{out}"


def test_deploy_refuses_a_non_tag_ref(deploy_env, tmp_path):
    # The tag-only mechanism (exit 2): a branch/SHA is refused before the lock step, so production can
    # never be pinned to a moving ref. Guards that invariant alongside the rc-capture (deploy.sh had no
    # test at all before this file).
    dev, prod = deploy_env
    rc, out = _run_deploy(dev, prod, tmp_path, 0, ref="main")  # a branch, not a tag
    assert rc == 2 and "is not a tag" in out, out
