"""Mandate sensor — prospectus mandate-diff (spec §4d, milestone 4).

The audit half of §4d: a watched fund files a new prospectus, and the sensor asks whether the fund
rewrote its *stated strategy* (audit = detection — the staleness check and the drift signal are one
mechanism). Like rebalance it is a pure **accretion** sensor — no Schmitt, no lead of its own; a real
strategy change accretes `mandate.changed` onto every live lead touching the fund (else `_system`), a
SILENT corroboration the human adjudicates cosmetic-vs-substantive. It never pages, and it never
claims a change is *meaningful* — only that the strategy text moved.

Routing reuses rebalance verbatim (forward-hash, CONTRACT §4d). The extraction/diff lives in
`ingest/prospectus.py` (bs4 on the structure side only). This module orchestrates: detect a new
filing, fetch+freeze it, diff the strategy section against the prior frozen filing, and route the
outcome:
  - reliable & changed   -> `mandate.changed` onto the live leads (else `_system`)
  - extraction unreliable -> a `fault` on `_system` for manual review (NO mandate.changed — a false
                             change claim is worse than a missed one; the extraction-unreliable fallback)
  - reliable & unchanged  -> nothing
  - supplement / SAI (not a full prospectus) -> nothing: a 497 sticker or an SAI carries no strategy
                             section by construction, so it is not a mandate-diff event (the standing
                             prospectus remains the fund's mandate). Skipping it is what cuts the
                             extraction-unreliable *noise* from what was never a full prospectus, and
                             refusing to diff AGAINST one stops a sticker-as-prior contaminating the
                             next real diff (docs/decisions/2026-07-18-mandate-supplement-not-a-prospectus.md).

Runner note (§9, M5+): `prior_accession` is the last prospectus the sensor has ON FILE for the fund —
i.e. the most recent frozen accession — NOT necessarily the registry's `prospectus_accession` (which
an identity-resolution pass may have already advanced to the new filing). Passing the frozen prior
keeps the diff correct regardless of intra-run ordering; the sensor's state is its frozen blobs.
"""

from __future__ import annotations

from typing import Callable, Iterable

from prospector.ingest.prospectus import ProspectusIngest, diff_mandate, is_prospectus_supplement
from prospector.sensors.rebalance import watching_leads
from prospector.store.envelope import SYSTEM_LEAD


def scan(series_id: str, ticker: str, cik: int,
         current_accession: str | None, current_doc: str | None, prior_accession: str | None,
         universe_series_ids: Iterable[str], active_lead_ids: Iterable[str],
         prospectus: ProspectusIngest, cfg: dict, now: str,
         emit: Callable[[dict], object], report_advisory: Callable[..., None]) -> dict:
    """One per-fund mandate-diff pass. `current_accession`/`current_doc` are the fund's latest
    prospectus (from `edgar.latest_prospectus`); `prior_accession` is the last filing on file (the
    prior frozen accession). Returns a summary; emits nothing when there is no new filing or the
    strategy is unchanged. `emit` writes the normal `mandate.changed` accretion; `report_advisory`
    (§10) raises the extraction-unreliable REVIEW-ADVISORY through the runner's ONE fault accumulator
    — never a raw fault write (that bypass was the split-path bug)."""
    if not current_accession:
        return {"action": "none", "reason": "no prospectus filing on record"}

    # Establish/refresh the baseline: the current filing must be frozen (idempotent, freeze-before-diff).
    freshly_frozen = False
    if not prospectus.has_frozen(series_id, current_accession):
        prospectus.pull(series_id, cik, current_accession, current_doc)
        freshly_frozen = True

    # No new filing since the prior we hold -> nothing to diff.
    if current_accession == prior_accession:
        return {"action": "baseline" if freshly_frozen else "none", "accession": current_accession}

    # A new filing. We can only diff if we hold the PRIOR filing's blob; otherwise the current filing
    # is a fresh baseline (we missed the prior — start the record from here rather than guess).
    if not (prior_accession and prospectus.has_frozen(series_id, prior_accession)):
        return {"action": "baseline", "accession": current_accession,
                "reason": "no prior prospectus on file to diff against"}

    # A 497 sticker or an SAI is NOT a full prospectus (no strategy section by construction), so it is
    # not a mandate-diff event: the standing prospectus remains the fund's mandate. SKIP a supplement
    # current — flagging it extraction-unreliable was the review-advisory noise — and never diff AGAINST
    # a supplement prior (a sticker frozen last cycle would contaminate this filing's diff). The §4d
    # extraction-unreliable fault stays for a real full prospectus we genuinely cannot parse.
    current_body = prospectus.load_frozen(series_id, current_accession)
    if is_prospectus_supplement(current_body):
        return {"action": "supplement", "accession": current_accession}
    prior_body = prospectus.load_frozen(series_id, prior_accession)
    if is_prospectus_supplement(prior_body):
        return {"action": "baseline", "accession": current_accession,
                "reason": "prior on file is a supplement, not a full prospectus"}

    d = diff_mandate(prior_body, current_body, cfg)

    if not d["reliable"]:
        # Flag, don't diff: a false mandate.changed is worse than a missed one (§4d extraction-unreliable).
        # §10: a REVIEW-ADVISORY (the sensor correctly PUNTED — nothing broke). Routed through the runner's
        # fault-reporter so it lands in the ONE accumulator, is counted + surfaced, and pages ONLY if this
        # fund touches a live lead (the reporter computes on_live_lead). NEVER a raw fault write.
        report_advisory("mandate",
                        f"new prospectus {current_accession} for {series_id}: strategy-section "
                        f"extraction unreliable ({d['reason']}) — manual review",
                        series_id, extra={"ticker": ticker, "accession": current_accession})
        return {"action": "flagged_unreliable", "reason": d["reason"], "accession": current_accession}

    if not d["changed"]:
        return {"action": "unchanged", "accession": current_accession}

    targets = watching_leads(series_id, universe_series_ids, active_lead_ids)
    leads = targets or [SYSTEM_LEAD]  # no live lead touches it -> recorded on _system, kept not surfaced
    payload = {"series_id": series_id, "ticker": ticker,
               "prior_accession": prior_accession, "current_accession": current_accession,
               "summary": d["summary"]}
    for lead in leads:
        emit({"ts": now, "lead": lead, "type": "mandate.changed", "payload": payload, "schema": 1})

    return {"action": "mandate_changed", "targets": targets, "emitted_to": leads,
            "accession": current_accession}
