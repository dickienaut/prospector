"""The Firewall (CLAUDE.md), enforced across the WHOLE package — one rule, one home.

    "Never add code that reads the detector's bucket or `portfolio.yaml`."
    "Do not import anything from the sibling repo's `models/` (capacity and opacity — forbidden)."

WHY THIS REPLACES THE PER-MODULE TESTS. The firewall was guarded by two hand-maintained allowlists —
`test_runner.py::test_runner_firewall_never_reads_portfolio` (4 named runner modules) and
`test_dashboard_views.py::test_dashboard_firewall_never_reads_portfolio` (2 dashboard files). Six of
the package's ~54 modules. A new sensor reading `portfolio.yaml` passed CI. An allowlist that must be
edited whenever a module is added is the "one rule, prose asking two homes to stay in sync" defect the
register already knows twice over (M7-DASH-01, PAGE-WORTHY-MIRROR) — so the allowlists are gone and
this sweep is the single home. Found by the 2026-07-20 Build read of CLAUDE.md.

WHY IT PARSES INSTEAD OF GREPPING. A text grep over the package fails immediately, and not on a
violation: `prospector/dashboard/export.py` **states the firewall in its module docstring**, naming
`portfolio.yaml` to say it never reads it. Several READMEs do the same. So the scan must separate
**code that reads** from **prose that names** — it walks the AST, ignores comments (absent from the AST
by construction) and docstrings (prose), and inspects what is left: real string literals and real
imports. `open("portfolio.yaml")` is caught; a docstring promising never to open it is not.

WHAT IT CANNOT CHECK, STATED HONESTLY. The detector's **bucket name does not appear in this repo** — by
design — so there is nothing to grep for. The structural proxy: S3 access is confined to the one module
that takes its bucket from config, so no other module can reach *any* bucket, the detector's included.
That is a real invariant, and it is weaker than a name check; the spec's stronger claim ("credentials
*unable* to read the detector's bucket — enforced at IAM, not convention") lives outside this repo and
outside CI. See docs/notes/2026-07-20-claude-md-consolidation-build-seat-findings.md §3.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "prospector"

# The forbidden portfolio-side artifact. This file is under tests/, and the sweep only walks
# prospector/, so naming it here is not self-incriminating — no cleverness needed.
PORTFOLIO_FILE = "portfolio.yaml"

# The sibling repo. Its NAME is expected throughout the package in provenance headers (a vendoring
# requirement — "keep the provenance headers"), so only real IMPORT statements are forbidden, never
# mentions. That distinction is the whole reason this is an AST walk.
SIBLING_ROOTS = ("prophit_skunkworks", "ltee_archive")

# The only module permitted to construct an S3 client, and it reads its bucket from config.
S3_OWNER = "store/s3_sync.py"


def _modules() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """id() of every string node that is a docstring — prose, not code."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _string_literals(source: str) -> list[str]:
    """Every string literal in real code — docstrings excluded, comments absent from the AST."""
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip]


def _imported_roots(source: str) -> list[str]:
    """Top-level package of every import — `from a.b import c` -> "a", `import x.y` -> "x"."""
    roots = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.append(node.module.split(".")[0])
    return roots


# --- the sweep -----------------------------------------------------------------------------------

def test_no_module_reads_the_portfolio_file():
    offenders = [str(p.relative_to(PACKAGE)) for p in _modules()
                 if any(PORTFOLIO_FILE in s for s in _string_literals(p.read_text(encoding="utf-8")))]
    assert offenders == [], f"firewall: these modules reference {PORTFOLIO_FILE} in code: {offenders}"


def test_no_module_imports_from_the_sibling_repo():
    offenders = []
    for p in _modules():
        roots = _imported_roots(p.read_text(encoding="utf-8"))
        if any(r in SIBLING_ROOTS for r in roots):
            offenders.append(str(p.relative_to(PACKAGE)))
    assert offenders == [], f"firewall: sibling-repo imports (capacity and opacity): {offenders}"


S3_CLIENT_ROOTS = ("boto3", "botocore", "s3transfer")
# The import roots that construct or drive an S3 client. `boto3` is the convenience wrapper, but it is a
# thin layer over `botocore` (its always-installed engine: `from botocore.session import get_session;
# get_session().create_client("s3")` builds a fully functional client with get_object/list_objects_v2 and
# imports root `botocore`, not `boto3`), and `s3transfer` (also a boto3 dep) drives uploads/downloads. A
# root-only check for `boto3` was EVADED by the botocore path (F3, proven green). Forbidding all three
# closes the standard alternates.
#
# STATED HONESTLY (the tiering the CLAUDE.md consolidation established): this is a PROXY with NAMED GAPS,
# not a capability boundary. An import-root check cannot catch a bare bucket-name string with no import,
# nor a client reached through a not-yet-enumerated third dep. The real wall is IAM — "credentials unable
# to read the detector's bucket," enforced outside this repo and outside CI (spec §; consolidation §3).
# This gate is the cheap in-repo tripwire under that wall, not a substitute for it.

def test_s3_access_is_confined_to_the_one_configured_module():
    # The structural proxy for "never read the detector's bucket": if only the config-driven module can
    # build an S3 client, no other module can reach any bucket at all. Checks every S3-capable import
    # root (see S3_CLIENT_ROOTS), not just the boto3 convenience wrapper.
    offenders = [str(p.relative_to(PACKAGE)) for p in _modules()
                 if any(r in S3_CLIENT_ROOTS for r in _imported_roots(p.read_text(encoding="utf-8")))
                 and str(p.relative_to(PACKAGE)) != S3_OWNER]
    assert offenders == [], f"firewall: only {S3_OWNER} may construct an S3 client; found {offenders}"


def test_the_sweep_actually_covers_the_package():
    # A sweep that silently globs nothing passes vacuously — the failure mode a gate must not have.
    # Guards the SCOPE, not the rule: if the package is reorganised out from under this file, fail loud.
    mods = _modules()
    assert len(mods) >= 40, f"sweep found only {len(mods)} modules — has the package moved?"
    assert (PACKAGE / S3_OWNER).exists(), f"{S3_OWNER} not found — update S3_OWNER"


# --- negative controls: prove the gate bites ------------------------------------------------------
# A gate that has never rejected is observationally identical to no gate. These feed the same checkers
# sources that DO violate, and assert they are caught — and, just as load-bearing, that the prose forms
# the package really contains are NOT caught (the false-positive that would make the sweep unadoptable).

def test_gate_bites_on_a_real_portfolio_read():
    violating = 'import yaml\ndef load():\n    return yaml.safe_load(open("portfolio.yaml"))\n'
    assert any(PORTFOLIO_FILE in s for s in _string_literals(violating))


def test_gate_does_not_bite_on_a_firewall_docstring_or_comment():
    # `prospector/dashboard/export.py` really does name portfolio.yaml in its docstring, to promise it
    # never reads it. A text grep fails here; this is why the scan parses.
    prose = ('"""Firewall — never a portfolio / `portfolio.yaml` / trade path."""\n'
             "# also never portfolio.yaml\n"
             "X = 1\n")
    assert not any(PORTFOLIO_FILE in s for s in _string_literals(prose))


def test_gate_bites_on_a_sibling_import_but_not_a_provenance_header():
    assert "ltee_archive" in _imported_roots("from ltee_archive.models import Thing\n")
    provenance = '"""Ported from prophit_skunkworks/ltee_archive/ — keep this header."""\nX = 1\n'
    assert not any(r in SIBLING_ROOTS for r in _imported_roots(provenance))


def test_gate_bites_on_an_unauthorised_s3_client():
    assert "boto3" in _imported_roots("import boto3\nc = boto3.client('s3')\n")
    # ...and not on the docstring mention in ingest/prospectus.py ("boring infrastructure like boto3").
    assert "boto3" not in _imported_roots('"""bs4 is infrastructure, like numpy / SQLite / boto3."""\n')


def test_gate_bites_on_the_botocore_s3_evasion():
    # F3: reaching S3 via botocore (boto3's always-installed engine) imports root `botocore`, NOT `boto3`
    # — the boto3-only check was blind to it (proven: a botocore-session client planted in a non-owner
    # module left the sweep green). A working client with zero `boto3` string. The gate must catch it.
    evasion = "from botocore.session import get_session\nc = get_session().create_client('s3')\n"
    roots = _imported_roots(evasion)
    assert "boto3" not in roots                      # the blind spot: no boto3 root at all
    assert any(r in S3_CLIENT_ROOTS for r in roots)  # ...but S3_CLIENT_ROOTS catches botocore
    # s3transfer (also a boto3 dep, drives multipart transfers) is likewise covered.
    assert any(r in S3_CLIENT_ROOTS for r in _imported_roots("import s3transfer\n"))
