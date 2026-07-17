import os

REPO = "dickienaut/prospector"


def fetch_prospector_branch(branch="main", dest_dir=None):
    """Fetch dickienaut/prospector at <branch> via the authenticated GitHub
    tarball API, unpack into the workspace, and report the tree.

    Returns {dest, branch, commit_sha, n_files, test_files, has_pyproject}.
    commit_sha is the EXACT 40-hex commit whose bytes were reviewed (parsed
    from the tarball root dir {owner}-{repo}-{sha}); stamp it on every finding
    so the reviewed code-of-record is a verifiable fact, not a claim. The code
    of record is this fetched tree — never the local working folder, never the
    state-of-project doc.
    """
    import io, tarfile, tempfile
    import requests

    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{REPO}/tarball/{branch}"
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()

    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix=f"prospector_{branch.replace('/', '_')}_")
    os.makedirs(dest_dir, exist_ok=True)

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tf:
        members = tf.getnames()
        try:
            tf.extractall(dest_dir, filter="data")  # py>=3.12 safe extraction
        except TypeError:
            tf.extractall(dest_dir)  # older pythons lack the filter kwarg

    # GitHub tarballs nest everything under a single top dir {owner}-{repo}-{sha}
    top = sorted(set(m.split("/")[0] for m in members if m))
    root = os.path.join(dest_dir, top[0]) if len(top) == 1 else dest_dir

    commit_sha = None
    if len(top) == 1:
        tok = top[0].rsplit("-", 1)[-1].lower()
        if len(tok) == 40 and all(c in "0123456789abcdef" for c in tok):
            commit_sha = tok

    all_files = []
    for base, _dirs, files in os.walk(root):
        for f in files:
            all_files.append(os.path.relpath(os.path.join(base, f), root))

    test_files = sorted(f for f in all_files
                        if os.path.basename(f).startswith("test_")
                        and f.endswith(".py"))
    has_pyproject = any(f == "pyproject.toml" for f in all_files)

    return {
        "dest": root,
        "branch": branch,
        "commit_sha": commit_sha,
        "n_files": len(all_files),
        "test_files": test_files,
        "has_pyproject": has_pyproject,
    }


def provenance_stamp(fetch_result, branch=None, commit_sha=None):
    """Render the QA-provenance block for a findings PR body / review note.
    Pass a fetch_prospector_branch() result, or branch+commit_sha directly.
    Mechanizes 'go to the primary source' as a verifiable artifact: the human
    and the implementer can confirm WHICH commit QA read.
    """
    if fetch_result:
        branch = branch or fetch_result.get("branch")
        commit_sha = commit_sha or fetch_result.get("commit_sha")
    sha = commit_sha or "UNKNOWN"
    br = branch or "?"
    return (f"> **QA provenance** \u2014 reviewed `{REPO}` @ `{sha}` "
            f"(ref `{br}`). Findings and the reference `.diff` were derived "
            f"from and verified against this exact commit.")


def procedure_stamp(repo_root, catalog_dir=None):
    """Render the QA-PROCEDURE drift block: per-file sha256 of the QA skill's
    operative files (SKILL.md + kernel.py) as they run in THIS session (the
    'catalog' copy the seat loaded) vs the repo SOURCE at tools/qa-skill/ in the
    reviewed tree. Returns a markdown blockquote to append to the provenance
    block, or "" if neither copy can be read.

    Warn-loud, NEVER block. The skill is the review membrane; refusing to
    deliver on drift would mean a drifted skill = no QA run and the fix needs a
    publish (friction on the wrong side). A DRIFT line instead makes it visible
    where review already happens (the PR body).

    SKILL.md and kernel.py are hashed SEPARATELY and on purpose: a kernel.py
    drift means the RED/GREEN + provenance gates that produced the finding you
    are reading were themselves unreviewed \u2014 distrust the FINDING, not just the
    skill \u2014 whereas a SKILL.md prose drift is comparatively benign. Every defect
    this skill ever shipped was kernel gate-logic, not prose.

    catalog_dir defaults to the directory THIS kernel.py runs from (resolved via
    a sibling function's source file, which works whether or not __file__ is set
    on a kernel plugin). repo_root is a fetch_prospector_branch()['dest']; the
    source is read from <repo_root>/tools/qa-skill/. Pure file reads + hashlib \u2014
    network-free, so it is CI-testable exactly like the membrane controls.
    """
    import hashlib, inspect
    if catalog_dir is None:
        catalog_dir = os.path.dirname(os.path.abspath(
            inspect.getsourcefile(provenance_stamp)))
    repo_dir = os.path.join(repo_root, "tools", "qa-skill")

    def _sha(path):
        try:
            return hashlib.sha256(open(path, "rb").read()).hexdigest()
        except OSError:
            return None

    rows, drift = [], False
    saw_any = False
    for fname in ("SKILL.md", "kernel.py"):
        cat = _sha(os.path.join(catalog_dir, fname))
        repo = _sha(os.path.join(repo_dir, fname))
        if cat is None and repo is None:
            continue
        saw_any = True
        if cat and repo and cat == repo:
            rows.append(f">   - `{fname}`: MATCH (`{cat[:12]}`)")
        else:
            drift = True
            rows.append(f">   - `{fname}`: **DRIFT** \u2014 catalog "
                        f"`{(cat or 'MISSING')[:12]}` vs repo `{(repo or 'MISSING')[:12]}`")
    if not saw_any:
        return ""

    head = ("> **QA procedure** \u2014 the skill that produced this finding, "
            "catalog (this session) vs repo source `tools/qa-skill/`:")
    if drift:
        rows.append(
            "> \u26a0 **DRIFT: the operative QA gates were not the reviewed source.** "
            "A `kernel.py` drift means the RED/GREEN and provenance gates that vetted "
            "this finding are unreviewed \u2014 distrust the finding itself, not just the "
            "skill. Reconcile via a `tools/qa-skill/` PR + republish, then re-deliver.")
    return "\n".join([head] + rows)


def qa_git_env():
    """os.environ copy with host global/system gitconfig neutralised, so
    `git apply` works in any sandbox (the host ~/.gitconfig is often
    unreadable). Used by verify_red_green; exposed for direct git calls too.
    """
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def check_diff_hygiene(diff_path):
    """Lint a reference .diff for the polluted-patch failure class (the v1
    lesson: recursive diff -ru over trees leaked __pycache__ binary noise and
    non-applicable pros_new/pros_fix prefixes). A findings PR must ship a
    single git-apply-clean per-file diff -u with a/ b/ labels, source files
    only. Returns {clean, violations:[(line_no,reason,snippet)], files_touched,
    n_hunks}. Wire it as an un-skippable delivery gate, not an eyeball check.
    """
    text = open(diff_path, "r", errors="replace").read()
    violations, files_touched, n_hunks = [], [], 0
    bad_tokens = ("__pycache__", ".pyc", ".egg-info", "/.git/", ".DS_Store")
    for i, line in enumerate(text.splitlines(), 1):
        if line.startswith("@@"):
            n_hunks += 1
        if line.startswith("--- "):
            tgt = line[4:].split("\t")[0].strip()
            if tgt != "/dev/null" and not tgt.startswith("a/"):
                violations.append((i, "old-file header not 'a/...' or /dev/null", tgt))
        if line.startswith("+++ "):
            tgt = line[4:].split("\t")[0].strip()
            if tgt != "/dev/null" and not tgt.startswith("b/"):
                violations.append((i, "new-file header not 'b/...' or /dev/null", tgt))
            elif tgt.startswith("b/"):
                files_touched.append(tgt[2:])
        if line.startswith("Binary files"):
            violations.append((i, "binary hunk (source-only diffs expected)", line[:80]))
        if line.startswith(("---", "+++", "diff ")):
            for tok in bad_tokens:
                if tok in line:
                    violations.append((i, f"build-artifact path ({tok})", line[:80]))
    return {"clean": not violations, "violations": violations,
            "files_touched": sorted(set(files_touched)), "n_hunks": n_hunks}


def verify_red_green(repo_root, test_paths, diff_path, python_bin=None,
                     extra_pytest_args=None):
    """The generate-and-check membrane applied to QA's OWN finding: prove, as a
    re-runnable script, that the RED test actually fails on the unfixed tree
    (the bug is real) and passes once the reference .diff is applied (the fix
    resolves it). This is what makes a finding self-checking instead of a
    claim, and it closes the meta-bug-#4 hole (a test that passes for the wrong
    reason) inside the QA seat.

    Runs pytest with --runxfail so a shipped xfail(strict=True) marker reports
    its UNDERLYING result. repo_root is left pristine; the fix is applied to a
    throwaway copy. Returns a dict incl. membrane_ok (True only when
    red_ok AND apply_clean AND applied AND green_ok). Verified to discriminate:
    a no-op fix -> green_ok False; a never-RED test -> red_ok False.
    """
    import subprocess, shutil, sys, tempfile
    python_bin = python_bin or sys.executable
    if isinstance(test_paths, str):
        test_paths = [test_paths]
    test_paths = list(test_paths)
    genv = qa_git_env()

    def run_pytest(root):
        cmd = [python_bin, "-m", "pytest", "--runxfail", "-q",
               *(extra_pytest_args or []), *test_paths]
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, env=genv)
        return p.returncode, (p.stdout + p.stderr)[-1500:]

    red_rc, red_report = run_pytest(repo_root)
    red_ok = red_rc == 1  # pytest exit 1 == tests failed (the bug is present)

    green_root = tempfile.mkdtemp(prefix="qa_green_")
    dst = os.path.join(green_root, "tree")
    shutil.copytree(repo_root, dst)
    chk = subprocess.run(["git", "apply", "--check", diff_path], cwd=dst,
                         capture_output=True, text=True, env=genv)
    apply_clean = chk.returncode == 0
    green_rc = green_report = green_ok = None
    applied = False
    if apply_clean:
        ap = subprocess.run(["git", "apply", diff_path], cwd=dst,
                            capture_output=True, text=True, env=genv)
        applied = ap.returncode == 0
        if applied:
            green_rc, green_report = run_pytest(dst)
            green_ok = green_rc == 0
    shutil.rmtree(green_root, ignore_errors=True)

    return {"membrane_ok": bool(red_ok and apply_clean and applied and green_ok),
            "red_ok": red_ok, "red_rc": red_rc, "red_report": red_report,
            "apply_clean": apply_clean,
            "apply_err": (chk.stderr[-400:] if not apply_clean else ""),
            "applied": applied, "green_ok": green_ok, "green_rc": green_rc,
            "green_report": green_report}


def deliver_qa_findings_pr(head_branch, files, title, body,
                           base_branch="main", base_sha=None, labels=None,
                           author_name=None, author_email=None,
                           draft=False, provenance=None, reviewed_sha=None,
                           repo_root=None, transport=None):
    """Deliver a QA finding-set to dickienaut/prospector as a qa/* branch + PR.

    Option 2 (QA PROPOSES, implementer APPLIES): the PR carries RED-first tests
    + the reference patch AS A .diff + per-finding records; NOT the applied
    source change, so every fix gets a second independent read. QA never merges
    and never pushes to a protected branch.

    Enforced discipline (contract, not token limits):
      * head_branch MUST start with "qa/".
      * Opens a PR; NEVER merges (no merge call exists here).
      * DELIVERY GATE: every *.diff in `files` is run through
        check_diff_hygiene(); a dirty diff raises before anything is pushed.
      * Provenance PRESENCE: a QA-provenance block (reviewed @ commit) is
        always prepended to the PR body from base_branch+base_sha (pass
        provenance=... to override the text). You cannot ship without a stamp.
      * Provenance TRUTH (reviewed_sha is REQUIRED): reviewed_sha is the
        commit_sha you fetched+read+ran the membrane against. The call RAISES
        if it is omitted, is not 40-hex, or does not equal the resolved base_sha
        (the branch head at delivery) — refusing to stamp a commit QA never
        saw if the branch moved between review and delivery. This is the
        mechanism that graduates 'go to the primary source' from a tool to an
        ENFORCED gate: absence is a hard refusal, so there is no presence-only
        escape hatch. Canonical flow: fr = fetch_prospector_branch(BRANCH);
        deliver_qa_findings_pr(..., base_sha=fr["commit_sha"],
        reviewed_sha=fr["commit_sha"]).
      * Commits authored as a distinct QA identity so history shows the seat.

    SAFETY — testing this offline: this function makes LIVE GitHub writes
    (creates a branch, commit, and PR). Pass `transport=` to exercise every
    gate and the full request SEQUENCE without touching the network. transport
    is a callable transport(method, path, payload) -> dict, dropped in where the
    live HTTP `_req` would go; a fake that records its calls lets a test assert
    that (a) the provenance/hygiene gates raise BEFORE any mutating call, and
    (b) the accept path issues the right calls in the right order. When
    transport is None the live `requests`-backed transport is used and real
    GitHub writes happen — the default, for real deliveries.

    This replaces the old sys.modules["requests"] monkey-patch: the body used to
    do a local `import requests`, so an attribute patch escaped to
    api.github.com and once created a real branch + PR that had to be cleaned up.
    The seam is now an explicit parameter, not a global — no import to outwit.
    (For an integration smoke test you can still point base_branch/head_branch
    at a throwaway fork with transport=None.)

    files: {repo_relative_path: local_fs_path}. Read with open(rb) in THIS env.
    Returns {pr_number, pr_url, branch, commit, files, base_branch, base_sha,
             diff_hygiene}.
    """
    import base64

    if not head_branch.startswith("qa/"):
        raise ValueError("head_branch must start with 'qa/' \u2014 QA pushes review "
                         "branches only, never main or a base branch.")
    author_name = author_name or "Prospector-QA"
    author_email = author_email or "prospector-qa@users.noreply.github.com"

    # DELIVERY GATE: lint every .diff before touching the remote.
    hygiene = {}
    for repo_path, local_path in sorted(files.items()):
        if repo_path.endswith(".diff") or repo_path.endswith(".patch"):
            h = check_diff_hygiene(local_path)
            hygiene[repo_path] = h
            if not h["clean"]:
                raise ValueError(
                    f"diff hygiene FAILED for {repo_path}: {h['violations'][:5]} "
                    "\u2014 ship a single per-file `diff -u` with a/ b/ labels, "
                    "source files only. Nothing was pushed.")

    # TRANSPORT SEAM (step 5): an injected transport(method, path, payload) -> dict
    # stands in for the live HTTP layer, so every gate and the full request
    # SEQUENCE can be exercised offline (see tests/test_delivery_transport.py).
    # When transport is None we build the real requests-backed transport HERE \u2014
    # so a tokenless, transport-injected test never trips the token guard, and a
    # local `import requests` no longer exists for a monkey-patch to escape past.
    if transport is None:
        import requests
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise RuntimeError("GITHUB_TOKEN not set \u2014 cannot reach the repo.")
        api = f"https://api.github.com/repos/{REPO}"
        H = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28"}

        def _req(method, path, payload=None):
            r = requests.request(method, api + path, headers=H, json=payload, timeout=60)
            if r.status_code >= 400:
                raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
            return r.json() if r.text else {}
    else:
        _req = transport

    if base_sha is None:
        base_sha = _req("GET", f"/git/ref/heads/{base_branch}")["object"]["sha"]

    # PROVENANCE TRUTH GATE (rule #3, ENFORCED): a findings PR must bind to the
    # exact commit QA fetched, read, and ran the membrane against. Absence is a
    # HARD REFUSAL, not an opt-out — delivering on a presence-only stamp was the
    # doc-drift failure class (a PR confidently naming a commit QA never saw).
    if reviewed_sha is None:
        raise ValueError(
            "reviewed_sha is REQUIRED: name the exact commit QA fetched+read+tested "
            "(fetch_prospector_branch(...)['commit_sha']). A findings PR cannot stamp "
            "a commit it never bound to. Nothing was pushed.")
    rs = reviewed_sha.strip().lower()
    bs = (base_sha or "").strip().lower()
    if len(rs) != 40 or any(c not in "0123456789abcdef" for c in rs):
        raise ValueError(f"reviewed_sha {reviewed_sha!r} is not a 40-hex commit.")
    if rs != bs:
        raise RuntimeError(
            f"PROVENANCE MISMATCH: QA reviewed {rs} but {base_branch} head is now "
            f"{bs}. The branch moved between review and delivery; the stamp would "
            f"name a commit QA never saw. Re-fetch {base_branch}, re-run the membrane "
            f"against the new head, then deliver. Nothing was pushed.")

    # Prepend provenance to the PR body (SHA-stamp every finding set). A FALSY
    # provenance (None OR the empty string) falls back to the auto-stamp, so an
    # explicitly passed provenance="" cannot silently suppress it: presence is
    # enforced — you cannot ship a findings PR with no stamp. (A bare truthy
    # `if provenance:` guard on the prepend was the original hole — it dropped
    # an empty override instead of replacing it with the default.)
    if not provenance:
        provenance = provenance_stamp(None, branch=base_branch, commit_sha=base_sha)
    # PROCEDURE DRIFT (warn-loud, never block): append the catalog-vs-repo hash
    # block when the reviewed tree is available, so a finding produced by an
    # unpublished/drifted skill announces that fact in the PR body. repo_root is
    # the fetch_prospector_branch()['dest']; skipped silently if not supplied
    # (an older caller) so delivery is never blocked on the stamp's absence.
    if repo_root:
        proc = procedure_stamp(repo_root)
        if proc:
            provenance = f"{provenance}\n>\n{proc}"
    body = f"{provenance}\n\n{body}"

    # create the qa/* branch off the base head (idempotent: reuse if it exists)
    try:
        _req("POST", "/git/refs", {"ref": f"refs/heads/{head_branch}", "sha": base_sha})
    except RuntimeError as e:
        if "422" not in str(e):
            raise  # 422 == ref exists; any other error is real

    tree_items = []
    for repo_path, local_path in sorted(files.items()):
        content = open(local_path, "rb").read()
        blob = _req("POST", "/git/blobs",
                    {"content": base64.b64encode(content).decode(), "encoding": "base64"})
        tree_items.append({"path": repo_path, "mode": "100644", "type": "blob",
                           "sha": blob["sha"]})
    tree = _req("POST", "/git/trees", {"base_tree": base_sha, "tree": tree_items})
    ident = {"name": author_name, "email": author_email}
    commit = _req("POST", "/git/commits",
                  {"message": title + ("\n\n" + body.split("\n")[0] if body else ""),
                   "tree": tree["sha"], "parents": [base_sha],
                   "author": ident, "committer": ident})
    _req("PATCH", f"/git/refs/heads/{head_branch}", {"sha": commit["sha"]})

    pr = _req("POST", "/pulls", {"title": title, "head": head_branch,
                                 "base": base_branch, "body": body, "draft": draft})
    if labels:
        _req("POST", f"/issues/{pr['number']}/labels", {"labels": labels})

    return {"pr_number": pr["number"], "pr_url": pr["html_url"],
            "branch": head_branch, "commit": commit["sha"],
            "files": sorted(files), "base_branch": base_branch, "base_sha": base_sha,
            "reviewed_sha": reviewed_sha,
            "provenance_enforced": True,  # unreachable past the gate unless bound
            "diff_hygiene": hygiene}
