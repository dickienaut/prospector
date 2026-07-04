"""SOI sensor — the deferred pass that RESOLVES `sectors_unresolved` from the industry-grouped Schedule
of Investments (spec §4c; design docs/2026-07-04-soi-derived-sector-concentration.md).

The launch-corroboration hook records a launch `sectors_unresolved → dormant` when its daily holdings
file carries no GICS sectors (every active thematic ETF, per primary-source review). This sensor is that
state's RESOLVER: when the fund's first industry-grouped SOI lands, it derives `{sector: weight}` from
the filing (ingest/soi.py), thresholds it with the SAME frozen `corroboration.sector_min_weight`, and
routes the launch through the SAME overlap/accrete/lag path as the holdings source
(`launch_corroboration.route_corroboration`). Because that path preserves the launch's original
`detected_at` as T2, deriving sectors from a later SOI reaches back without corrupting the lag — the
deferred reach-back the corroboration hook already implements.

Like mandate/rebalance it is a pure **accretion** sensor — no Schmitt, no lead of its own; a corroborating
SOI accretes a `launch`/`match` onto every live lead it overlaps (else records dormant on `_system`). It
NEVER spawns a lead (rev7). The outcomes mirror the mandate sensor's discipline:
  - extraction unreliable (fund block not isolable / unknown industry / reconcile miss) -> a `fault` on
    `_system` for manual review, NEVER a wrong sector set (a false sector claim is worse than a missed one)
  - reliable & overlaps a live lead -> `launch`/`match` accretes onto it (the cross-stream lag attaches)
  - reliable & no overlap -> `dormant_no_match` on `_system` (surveyable, first-class)

Routing reuses the rebalance forward-hash (`lead_sectors` builds `active_lead_sectors` upstream, exactly
as the holdings path does). The LIVE fetch — which NPORT-EX/N-CSR accession + document carries the SOI —
is the deferred M5 slice (tied to EdgarClient); here the bytes arrive via `fetch_body` (the runner wires
it to EdgarClient; tests pass a fixture-reading thunk) or are already frozen on file.
"""

from __future__ import annotations

from typing import Callable, Mapping

from prospector.ingest.soi import SoiIngest, dominant_sectors, extract_soi_sectors
from prospector.sensors.launch_corroboration import route_corroboration
from prospector.store.envelope import SYSTEM_LEAD


def scan(launch: Mapping, accession: str, fund_anchor: str,
         active_lead_sectors: Mapping[str, frozenset[str]],
         soi: SoiIngest, cfg: dict, now: str, emit: Callable[[dict], object],
         *, fetch_body: Callable[[], bytes] | None = None) -> dict:
    """One deferred SOI-corroboration pass for a launch. `launch` is the launch record ({series_id,
    ticker, name?, detected_at, unverified_ref?}); `accession` is the SOI filing's accession;
    `fund_anchor` selects the fund's block within a multi-fund filing (its name/ticker). `active_lead_
    sectors` is the `lead_sectors(...)` map. The SOI bytes come from the frozen blob if present, else
    from `fetch_body()` (frozen before parsing). Returns a summary."""
    series_id = launch["series_id"]
    ticker = launch.get("ticker")

    # Freeze-before-parse (§3), idempotent. No blob and no fetch seam -> nothing to do yet (the M5 runner
    # supplies fetch_body; until then this is a no-op rather than a guess).
    if soi.has_frozen(series_id, accession):
        body = soi.load_frozen(series_id, accession)
    elif fetch_body is not None:
        body = soi.freeze(series_id, accession, fetch_body())
    else:
        return {"action": "none", "reason": "no SOI on file and no fetch provided",
                "accession": accession}

    res = extract_soi_sectors(body, cfg, fund_anchor)

    if not res["reliable"]:
        # Flag, don't guess: a false sector set is worse than a missed one (the §4d extraction-unreliable
        # discipline, shared with the mandate sensor).
        emit({"ts": now, "lead": SYSTEM_LEAD, "type": "fault",
              "payload": {"subsystem": "soi", "series_id": series_id, "ticker": ticker,
                          "accession": accession,
                          "message": (f"SOI {accession} for {series_id}: sector extraction unreliable "
                                      f"({res['reason']}) — manual review")},
              "schema": 1})
        return {"action": "flagged_unreliable", "reason": res["reason"], "accession": accession}

    sectors = dominant_sectors(res["sectors"], float(cfg["corroboration"]["sector_min_weight"]))

    # The deferred reach-back: detected_at is preserved as T2 (the lag measures to detection, not to the
    # SOI's as-of), and the resolving filing is recorded on the payload for provenance.
    base = {"series_id": series_id, "ticker": ticker, "detected_at": launch["detected_at"],
            "unverified_ref": launch.get("unverified_ref"),
            "soi_accession": accession, "soi_as_of": res["as_of"]}
    return route_corroboration(base, sectors, active_lead_sectors, now, emit)
