"""Dispersion sensor — the intra-basket fracture detector (spec §4b).

Where xcorr (§4a) watches whether two *baskets* decouple, dispersion watches a *single basket*
fracture from within: its weight-covering constituents split into two blocks that correlate tightly
inside and loosely across. The pipeline, each stage a pure function over pandas/numpy so the whole
thing is testable without a store, a network, or a clock:

    constituent prices --returns--> daily returns
        --corr_matrix_at(63)--> n x n constituent correlation over the trailing window
        --spectral_bipartition--> two blocks (2nd eigenvector sign — the "fracture")
        --cluster_quality--> Q = mean(within-cluster corr) - mean(between-cluster corr)
        --dispersion_z(252)--> (Q_t - baseline mean) / baseline std, baseline ending t-1

Entry/exit is the shared Schmitt trigger (sensors/schmitt.py), z_in 2.5 / z_out 1.0 (DEFAULT,
config). Q is NOT Fisher-transformed — unlike a pair correlation, Q is already a difference of means
with no hard bound at ±1 to stabilise, and spec §4b baselines Q directly.

SHIPS SHADOW (CONTRACT §4b): every lead spawns with shadow=True until the human flips
`dispersion.paging: true` (a config change → config.changed). active_nonshadow excludes it from
ceiling/paging/digest by construction, so a calibration miss can flood the record, never the oracle.

GENEROUS PAYLOAD (CONTRACT §4b, rev8): the dispersion.tick payload banks the substrate for the
deferred v2 proto-cluster / pseudo-ETF layer (spec Appendix B) — full constituent membership + each
name's sub-cluster assignment + the correlation structure, not just the scalar Q. You cannot backfill
a payload you did not capture (append-only forced-ordering, §5), so we capture it richly now even
though nothing interprets it until v2. See docs/decisions/2026-07-03-dispersion-payload-generous.md.

Provenance note (Appendix A): the bipartition is pure numpy.linalg.eigh — the right-capacity form at
this n. Do not reach for a spectral-clustering library or a fancy graph cut; "same idea at the wrong
capacity" (§4a) applies one level down.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd

from prospector.sensors import schmitt, xcorr

# --- pure pipeline -----------------------------------------------------------


def constituent_returns(prices_panel: pd.DataFrame) -> pd.DataFrame:
    """Daily returns of a basket's constituent close panel (columns = constituent identifiers).
    Reuses xcorr.daily_returns verbatim — the same market-neutral price math, one level down."""
    return xcorr.daily_returns(prices_panel)


def corr_matrix_at(returns: pd.DataFrame, as_of, window: int) -> pd.DataFrame:
    """The n x n constituent correlation matrix over the `window` returns ending at `as_of`.
    A constituent without a full window of observations (a late-listed or delisted name, or one
    missing prices) is DROPPED from that day's matrix — the sensor correlates only what it can price,
    honestly, never fabricating a fill (§3). Returns an empty frame when fewer than two names are
    fully warmed (no matrix defined)."""
    sub = returns.loc[:as_of].tail(window)
    if len(sub) < window:
        return pd.DataFrame()
    full = sub.columns[sub.notna().sum() == window]  # only fully-observed constituents
    sub = sub[full]
    if sub.shape[1] < 2:
        return pd.DataFrame()
    return sub.corr()


def spectral_bipartition(corr_matrix: pd.DataFrame) -> dict[str, int]:
    """Split the constituents into two blocks by the SIGN of the second eigenvector of the
    correlation matrix. The leading eigenvector is the common (sector) factor everything loads on;
    the second is the dominant *contrast* between the names — exactly the fracture the sensor hunts.
    Pure numpy.linalg.eigh (symmetric, real), O(n^3), trivial at this n.

    DETERMINISM: an eigenvector's sign is arbitrary from eigh, which would make the cluster labels
    (and any SHA-256 of the payload) unstable. Canonicalize by fixing the sign so the FIRST column —
    the top-weighted member, since the matrix is built in membership (weight-desc) order — lands in
    cluster 0. (A near-zero second eigenvector — no real split — yields a degenerate one-block
    labelling whose Q is NaN, correctly read as no signal.)"""
    ids = list(corr_matrix.columns)
    m = corr_matrix.to_numpy()
    _, vecs = np.linalg.eigh(m)          # ascending eigenvalue; last col = leading eigenvector
    second = vecs[:, -2]                 # the contrast axis
    labels = (second > 0.0).astype(int)  # two blocks
    if labels[0] == 1:                   # canonicalize: top-weighted member (col 0) -> cluster 0
        labels = 1 - labels
    return {ids[i]: int(labels[i]) for i in range(len(ids))}


def _within_between(corr_matrix: pd.DataFrame, labels: dict[str, int]):
    """Return (within_by_cluster, between_mean, member_within): the mean within-cluster correlation
    per cluster, the mean cross-cluster correlation, and each member's mean correlation to its own
    cluster-mates (used to pick a medoid). Shared by cluster_quality and the payload builder so the
    two can never disagree."""
    ids = list(corr_matrix.columns)
    m = corr_matrix.to_numpy()
    idx_by_cluster: dict[int, list[int]] = {}
    for i, cid in enumerate(ids):
        idx_by_cluster.setdefault(labels[cid], []).append(i)

    within: dict[int, float] = {}
    member_within: dict[str, float] = {}
    for cluster, idxs in idx_by_cluster.items():
        pair_vals = []
        for pos_a, a in enumerate(idxs):
            others = [m[a, b] for pos_b, b in enumerate(idxs) if pos_b != pos_a]
            member_within[ids[a]] = float(np.mean(others)) if others else float("nan")
            for b in idxs[pos_a + 1:]:
                pair_vals.append(m[a, b])
        within[cluster] = float(np.mean(pair_vals)) if pair_vals else float("nan")

    between_vals = [m[i, j] for i in range(len(ids)) for j in range(i + 1, len(ids))
                    if labels[ids[i]] != labels[ids[j]]]
    between = float(np.mean(between_vals)) if between_vals else float("nan")
    return within, between, member_within


def cluster_quality(corr_matrix: pd.DataFrame, labels: dict[str, int]) -> float:
    """Q = mean(within-cluster corr) - mean(between-cluster corr). NaN on a degenerate split (an
    empty cluster: no within OR no between pairs) — no fracture measured, like a warmup NaN."""
    within, between, _ = _within_between(corr_matrix, labels)
    within_vals = [v for v in within.values() if not math.isnan(v)]
    if len(within) < 2 or math.isnan(between) or not within_vals:
        return float("nan")
    return float(np.mean(within_vals) - between)


def dispersion_q_series(returns: pd.DataFrame, window: int, min_constituents: int,
                        method: str = "spectral") -> pd.Series:
    """Q_t for every date whose matrix is fully warmed and carries >= min_constituents names.
    Membership is fixed within a run (point-in-time membership reconstruction is the deferred §3b
    slice); a live runner needs only the trailing baseline_days+1 of this series, but the function
    computes the whole index for offline calibration."""
    q = {}
    for as_of in returns.index:
        corr = corr_matrix_at(returns, as_of, window)
        if corr.empty or corr.shape[1] < min_constituents:
            q[as_of] = float("nan")
            continue
        labels = _bipartition(corr, method)
        q[as_of] = cluster_quality(corr, labels)
    return pd.Series(q).sort_index()


def dispersion_z(q_series: pd.Series, baseline_window: int) -> pd.Series:
    """Departure z of Q against its own trailing baseline — reuses xcorr.departure_z verbatim (the
    (Q_t - rolling_mean.shift(1)) / rolling_std.shift(1) machinery, same .shift(1) exclusion and
    std==0 -> NaN handling). Q is NOT Fisher-transformed (§4b)."""
    z = xcorr.departure_z(q_series.to_frame(name="Q"), baseline_window)
    return z["Q"]


def _bipartition(corr_matrix: pd.DataFrame, method: str) -> dict[str, int]:
    if method == "spectral":
        return spectral_bipartition(corr_matrix)
    raise ValueError(f"unknown dispersion bipartition method: {method!r} (only 'spectral' in v1)")


def dispersion_lead_id(series_id: str) -> str:
    """Lead id for a basket's dispersion lead: a short hash of the basket's SEC series id (never a
    ticker, never a constituent — §2/§5 CONTRACT), spawner-prefixed. Mirrors xcorr_lead_id."""
    return "disp-" + hashlib.sha256(f"disp|{series_id}".encode("utf-8")).hexdigest()[:10]


# --- generous payload (CONTRACT §4b, rev8) -----------------------------------


def _round(x, nd: int = 6):
    """Round for a stable SHA-256, and convert NaN/inf -> None. canonical_json uses
    allow_nan=False, so a bare NaN in the payload would be REJECTED at write time — every float in
    the payload passes through here."""
    if x is None:
        return None
    xf = float(x)
    if math.isnan(xf) or math.isinf(xf):
        return None
    return round(xf, nd)


def dispersion_tick_payload(series_id: str, ticker: str, display: str, as_of: str, shadow: bool,
                            z: float, q: float, corr_matrix: pd.DataFrame, labels: dict[str, int],
                            members: list[dict], q_baseline: dict, cfg_dispersion: dict) -> dict:
    """Assemble the generous dispersion.tick payload — the rev8 §4b CONTRACT. Carries, beyond the
    scalar Q: full constituent membership with each name's sub-cluster assignment; per-cluster
    centroids (medoid + weight + within-corr); and the constituent correlation structure at the
    detail the `correlation_detail` knob selects (full matrix / top-K pairs / summaries only).
    A scalar-only tick would permanently blind the deferred v2 proto-cluster layer to WHICH names
    formed the cluster and HOW they cohered."""
    ids = list(corr_matrix.columns)
    weight_by_id = {m["identifier"]: m.get("weight") for m in members}
    name_by_id = {m["identifier"]: m.get("name") for m in members}
    within, between, member_within = _within_between(corr_matrix, labels)

    # Per-cluster membership + centroid (medoid = the member most correlated to its own cluster).
    clusters = []
    for cluster in sorted(set(labels.values())):
        cluster_ids = [i for i in ids if labels[i] == cluster]
        cmembers = [{"name": name_by_id.get(i), "identifier": i, "weight": _round(weight_by_id.get(i))}
                    for i in cluster_ids]
        cmembers.sort(key=lambda mm: (-(mm["weight"] or 0.0), mm["identifier"]))
        medoid = max(cluster_ids, key=lambda i: (member_within.get(i, float("-inf"))
                                                 if not math.isnan(member_within.get(i, float("nan")))
                                                 else float("-inf")), default=None)
        clusters.append({
            "id": cluster,
            "weight_sum": _round(sum((weight_by_id.get(i) or 0.0) for i in cluster_ids)),
            "mean_within_corr": _round(within.get(cluster)),
            "medoid": medoid,
            "members": cmembers,
        })

    correlation = {
        "detail": cfg_dispersion["correlation_detail"],
        "within_cluster": {str(c): _round(v) for c, v in within.items()},
        "between_cluster": _round(between),
    }
    detail = cfg_dispersion["correlation_detail"]
    if detail in ("full", "topk"):
        m = corr_matrix.to_numpy()
        pairs = [{"a": ids[i], "b": ids[j], "corr": _round(m[i, j])}
                 for i in range(len(ids)) for j in range(i + 1, len(ids))]
        pairs.sort(key=lambda p: (-abs(p["corr"] or 0.0), p["a"], p["b"]))
        correlation["top_pairs"] = pairs[:int(cfg_dispersion["correlation_top_k"])]
    if detail == "full":
        correlation["matrix"] = {
            "labels": ids,
            "values": [[_round(v) for v in row] for row in corr_matrix.to_numpy().tolist()],
        }

    return {
        "spawner": "dispersion",
        "display": display,
        "series_id": series_id,
        "ticker": ticker,
        "as_of": as_of,
        "shadow": shadow,
        "z": _round(z),
        "q": _round(q),
        "q_baseline": {"mean": _round(q_baseline.get("mean")), "std": _round(q_baseline.get("std")),
                       "window": q_baseline.get("window")},
        "window_days": int(cfg_dispersion["window_days"]),
        "method": cfg_dispersion["method"] + "_bipartition",
        "n_constituents": len(ids),
        "split_membership": {i: labels[i] for i in ids},
        "clusters": clusters,
        "correlation": correlation,
    }


# --- driver (§9: stateless per run, reconstruct trigger state from the record) -----------------


def scan(series_id: str, ticker: str, membership, prices_panel: pd.DataFrame, cfg: dict, now: str,
         last_event_type: str | None, emit, tick_due: bool = False, display: str | None = None) -> dict:
    """One per-basket dispersion pass. `membership` is the MembershipSnapshot (name/identifier/weight
    per constituent); `prices_panel` is the constituent close panel (columns = identifiers).
    `last_event_type` is the basket lead's last TRIGGER-relevant event type (§9 reconstruction);
    `emit` is an EventStore.append-shaped callable (tests wire a recorder, the M5 runner the store);
    `tick_due` is the runner's weekly-cadence signal (the tick cadence lives in the runner, §4/§9).

    Emits: on entry, a shadow-wired `lead.spawned` + the generous `dispersion.tick`; while active and
    a tick is due, a `dispersion.tick`; on exit, a `dispersion.reverted`."""
    dcfg = cfg["dispersion"]
    returns = constituent_returns(prices_panel)
    q_series = dispersion_q_series(returns, int(dcfg["window_days"]), int(dcfg["min_constituents"]),
                                   dcfg["method"])
    z_series = dispersion_z(q_series, int(dcfg["baseline_days"]))
    z_valid = z_series.dropna()
    if z_valid.empty:
        return {"edge": None, "z": None, "q": None, "as_of": None, "n_constituents": 0}

    as_of_ts = z_valid.index[-1]
    as_of = as_of_ts.date().isoformat() if hasattr(as_of_ts, "date") else str(as_of_ts)
    z = float(z_valid.iloc[-1])
    q = float(q_series.loc[as_of_ts])

    state = schmitt.state_from_last_event_type(last_event_type)
    new_state, edge = schmitt.step(state, z, float(dcfg["z_in"]), float(dcfg["z_out"]))

    lead_id = dispersion_lead_id(series_id)
    shadow = not bool(dcfg["paging"])
    disp = display or f"{ticker} split"

    def _tick_event():
        corr = corr_matrix_at(returns, as_of_ts, int(dcfg["window_days"]))
        labels = _bipartition(corr, dcfg["method"])
        baseline = {
            "mean": float(q_series.rolling(int(dcfg["baseline_days"]),
                                           min_periods=int(dcfg["baseline_days"]))
                          .mean().shift(1).loc[as_of_ts]),
            "std": float(q_series.rolling(int(dcfg["baseline_days"]),
                                          min_periods=int(dcfg["baseline_days"]))
                         .std().shift(1).loc[as_of_ts]),
            "window": int(dcfg["baseline_days"]),
        }
        payload = dispersion_tick_payload(series_id, ticker, disp, as_of, shadow, z, q, corr, labels,
                                          membership.members, baseline, dcfg)
        return {"ts": now, "lead": lead_id, "type": "dispersion.tick", "payload": payload,
                "schema": 1}

    if edge == "entered":
        emit({"ts": now, "lead": lead_id, "type": "lead.spawned",
              "payload": {"spawner": "dispersion", "display": disp, "series_id": series_id,
                          "ticker": ticker, "shadow": shadow, "spawned_at": now}, "schema": 1})
        emit(_tick_event())
    elif edge == "exited":
        emit({"ts": now, "lead": lead_id, "type": "dispersion.reverted",
              "payload": {"display": disp, "series_id": series_id, "z": _round(z), "as_of": as_of},
              "schema": 1})
    elif new_state == schmitt.ACTIVE and tick_due:
        emit(_tick_event())

    return {"edge": edge, "z": z, "q": q, "as_of": as_of, "n_constituents": len(membership.members)}
