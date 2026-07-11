"""§10 fault taxonomy — operational faults page; manual-review advisories are counted + surfaced but do
NOT page, EXCEPT an advisory on a fund touching a live (active, non-shadow) lead (the risk-owner's call).

The bug this closes: the mandate/SOI extraction-unreliable faults were written straight to the store
(bypassing the runner's per-tick `faults` list), so the email counted '0 faults this run' beside nine that
fired AND they never reached `_compute_push`. The fix is the shadow-push shape one layer down — one
accumulator (every fault in `faults`, categorized), page-worthiness filtered at the push decision. These
tests pin the decision (`_compute_push`/`_page_worthy_faults`) and the routing (`_advisory_reporter` computes
`on_live_lead` via the shared forward-hash `watching_leads`). Offline; no store, no socket.
"""

import prospector.runner.runner as rr
from prospector.runner.runner import _advisory_reporter, _compute_push, _page_worthy_faults


def _fault(subsystem="ingest.prices", message="boom", *, category="operational", series_id=None,
           on_live_lead=False, key=None) -> dict:
    return {"subsystem": subsystem, "message": message, "key": key, "category": category,
            "series_id": series_id, "on_live_lead": on_live_lead}


OP = _fault()                                                              # operational (something broke)
ADV = _fault("mandate", "unreliable — manual review", category="review-advisory", series_id="S1")
ADV_LIVE = _fault("mandate", "unreliable — manual review", category="review-advisory",
                  series_id="S2", on_live_lead=True)


# === the page-worthy filter (the alarm-posture taxonomy) ============================================

def test_page_worthy_keeps_operational_and_live_lead_advisories_only():
    assert _page_worthy_faults([OP, ADV, ADV_LIVE]) == [OP, ADV_LIVE]      # the non-live advisory drops
    assert _page_worthy_faults([ADV]) == []                                # a lone non-live advisory: none
    assert _page_worthy_faults([_fault(category="whatever")]) == [_fault(category="whatever")]  # unknown->op


# === _compute_push over the taxonomy ================================================================

def test_operational_fault_pages_advisory_does_not():
    assert _compute_push({}, [OP], []) is True                 # a NEW operational fault pages
    assert _compute_push({}, [ADV], []) is False               # a manual-review advisory does NOT page
    assert _compute_push({}, [ADV_LIVE], []) is True           # ... unless its fund touches a live lead


def test_a_state_change_still_pages_regardless_of_fault_class():
    assert _compute_push({"ld_x": ["status"]}, [ADV], []) is True   # page_worthy leads win


def test_advisory_flood_never_pages_even_recurring():
    # The iShares combined-prospectus wave: nine non-live advisories, every tick. It must never page —
    # and a *new* batch (different prior) still doesn't, because none are page-worthy.
    flood = [ADV] * 9
    assert _compute_push({}, flood, []) is False
    assert _compute_push({}, flood, flood) is False
    assert _compute_push({}, flood, [OP]) is False             # even vs an unrelated prior operational fault


def test_operational_suppression_runs_over_the_page_worthy_subset():
    # A recurring operational fault pages once then suppresses — and an advisory riding alongside neither
    # adds to nor masks that page-worthy signature (the advisory is filtered out of the comparand).
    assert _compute_push({}, [OP], [OP]) is False              # identical operational fault: suppressed
    assert _compute_push({}, [OP, ADV], [OP, ADV]) is False    # advisory doesn't perturb the page-worthy sig
    assert _compute_push({}, [OP, ADV], [OP]) is False         # adding a non-page-worthy advisory != a change
    changed_op = _fault(message="different")
    assert _compute_push({}, [changed_op], [OP]) is True       # a CHANGED operational fault still pages


# === the reporter computes on_live_lead (routing via watching_leads) ================================

class _NoopStore:
    def append(self, event):  # _emit_fault ignores the return; the fossil write is not under test here
        return None


def test_advisory_reporter_tags_on_live_lead_from_watching_leads(monkeypatch):
    # The reporter routes an advisory through the ONE accumulator and computes page-worthiness where the
    # lead context lives. Monkeypatch the shared forward-hash so the test pins the wiring, not the hash.
    monkeypatch.setattr(rr, "watching_leads",
                        lambda series_id, universe, active: ["ld-live"] if series_id == "S_LIVE" else [])
    faults: list = []
    report = _advisory_reporter(_NoopStore(), "2026-07-10T00:00:00Z", faults,
                                universe_ids=["S_LIVE", "S_DEAD"], active_ids=["ld-live"])

    report("mandate", "unreliable — manual review", "S_DEAD", extra={"accession": "0001-..."})
    report("soi", "unreliable — manual review", "S_LIVE")

    dead, live = faults
    assert dead["category"] == "review-advisory" and dead["on_live_lead"] is False
    assert live["category"] == "review-advisory" and live["on_live_lead"] is True
    # And the push decision reflects it: the live-lead one is page-worthy, the other is not.
    assert _compute_push({}, [dead], []) is False and _compute_push({}, [live], []) is True
