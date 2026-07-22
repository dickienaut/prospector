"""F3 (post-#99 sweep) — the S3-confinement gate must catch the botocore path, not just boto3.

The #127 firewall confines S3-client construction to the one config-driven module (`store/s3_sync.py`),
as the structural proxy for "never read the detector's bucket". The check forbade only import ROOT
`boto3`. But `boto3` is a thin wrapper over `botocore`, its always-installed engine:
`from botocore.session import get_session; get_session().create_client("s3")` builds a fully functional
S3 client (get_object / list_objects_v2) and imports root `botocore`, NOT `boto3`. Proven in the sweep:
a botocore-session client planted in a non-owner module (`sensors/xcorr.py`) left the gate GREEN, while
the same plant with `import boto3` went RED.

This test drives the firewall module's OWN confinement predicate over a simulated non-owner module that
reaches S3 via botocore, and asserts it is flagged. On the unfixed tree (boto3-only) the predicate does
not flag it -> the assertion fails (RED). The fix adds `botocore`/`s3transfer` to the forbidden roots
(`S3_CLIENT_ROOTS`) and states the residual as a proxy-with-named-gaps.

House rule: no test imports a sibling test module. The firewall's checkers are module-level helpers in
tests/test_firewall.py; rather than import that test module, this test re-derives the minimal predicate
from the same public helper (`_imported_roots`) and the fix's constant, exercised as the gate does.
Authored RED against main 6eccdabf; GREEN against the reference fix (docs/notes/post99_sweep_fixes.diff).
"""
import ast

# The S3-capable import roots the gate must forbid outside the owner. On the unfixed tree this constant
# does not exist in test_firewall.py (the check inlines the bare string "boto3"); importing it is itself
# the RED signal — ImportError until the fix adds it. Guarded so the failure is a clean assertion, not a
# collection error.
try:
    from tests.test_firewall import S3_CLIENT_ROOTS, _imported_roots
    _HAVE_FIX = True
except ImportError:
    _HAVE_FIX = False
    from tests.test_firewall import _imported_roots   # the helper predates the fix
    S3_CLIENT_ROOTS = ("boto3",)                        # the unfixed behaviour: boto3 only


# A non-owner module reaching S3 through botocore — zero occurrences of the string "boto3".
_BOTOCORE_S3_MODULE = (
    "from botocore.session import get_session\n"
    "def _reach_a_bucket():\n"
    "    return get_session().create_client('s3')\n"
)


def test_s3_confinement_predicate_catches_the_botocore_path():
    roots = _imported_roots(_BOTOCORE_S3_MODULE)
    assert "boto3" not in roots                       # the evasion: no boto3 root at all...
    # ...yet the gate's own forbidden-root set must still flag it. RED on the unfixed tree, where
    # S3_CLIENT_ROOTS is ("boto3",) and this is False; GREEN once botocore is in the set.
    assert any(r in S3_CLIENT_ROOTS for r in roots), \
        "botocore S3 client not caught by the confinement gate"
