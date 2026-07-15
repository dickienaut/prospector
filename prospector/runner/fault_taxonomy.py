"""§10 fault-taxonomy — the ONE definition of which faults drive a page (the alarm-posture CONTRACT).

Lifted here (PAGE-WORTHY-MIRROR, class 3) so the two consumers share a single implementation instead of two
byte-identical copies kept in sync by prose:
  - the push DECISION — `runner._compute_push` (does this tick page?);
  - the email SUBJECT — `email_render.push_subject` (does the subject read FAULT or state-change?).

They must agree — a fault-driven push whose subject reads `state change: …` mislabels the alarm on the one
line §8a makes load-bearing. `runner` imports `email_render` (build_context/render_push), so email_render
cannot import back without a cycle; a neutral third home both import from resolves that, and makes drift
impossible BY CONSTRUCTION — the invariant stops being representable rather than being caught.

Deliberately NO agreement test: post-lift there is one implementation, so `runner._page_worthy_faults(x) ==
email_render._page_worthy(x)` would assert `f(x) == f(x)` — the exact tautology this repo disposed as
LOCK-TEST-TAUT. The structure is the guard. The consumers keep their own behaviour tests (that `_compute_push`
and `push_subject` use this predicate correctly), which remain meaningful.
"""

from __future__ import annotations


def page_worthy_faults(faults: list) -> list:
    """The faults that DRIVE a page (§10 alarm-posture taxonomy, CONTRACT). `operational` faults always
    (something broke — a failed fetch, a tripped guard, a degenerate matrix). `review-advisory` faults ONLY
    when their fund touches a live lead (`on_live_lead`) — a held/watched fund quietly rewording its mandate
    is the one advisory worth interrupting for; every other advisory (a new-launch fund's unreadable
    prospectus — the sensor correctly punting, nothing broken) is counted + surfaced but does NOT page. A
    fault with no/unknown `category` is treated as operational (the fail-safe default: an unrecognized fault
    must not silently escape the alarm). Only an explicit `review-advisory` is held back.

    THE single source of truth: both the push decision (`runner._compute_push`) and the email subject
    (`email_render.push_subject`) import this — so the count/subject and the push decision cannot diverge."""
    return [f for f in faults
            if f.get("category", "operational") != "review-advisory" or f.get("on_live_lead")]
