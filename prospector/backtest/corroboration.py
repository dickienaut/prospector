"""Cross-stream corroboration scoring for the backtest precision audit (spec §10 test 5b).

A backtest firing (a pair entering `active`) is auto-scored **structural** if a verified launch
whose concentration industries keyword-match BOTH sides of the pair lands within W months after
the first firing. The sector->keyword map (config `sector_keywords`) and the launch table
(tests/fixtures/backtest/historical_launches.yaml) are both small, static, deterministic, and
reviewable — crude on purpose.

HONESTY CAVEAT (spec §10 test 5b, verbatim spirit): this bakes in "packaged = real". A firing
that reflects a real structural shift the market never wrapped in an ETF scores as junk here.
That is acceptable — packageability is this system's OWN success criterion (it proposes
durable, ownable exposure) — but it is a BIAS, not a truth, and the precision number must be
read with it in mind. The bias direction is conservative: a missing launch can only make
precision look worse (a structural firing scored junk), never better.
"""

from __future__ import annotations

from datetime import date

import yaml


def load_launches(path) -> list[dict]:
    """Load the curated launch table. Dates stay ISO strings; each row carries ticker,
    detected_at, and concentration_industries (the EDGAR-verified fields)."""
    doc = yaml.safe_load(open(path)) or {}
    return list(doc.get("launches", []))


def keyword_match(industries: list[str], sector_keywords: list[str]) -> bool:
    """True if any industry string and any sector keyword overlap as a case-insensitive
    substring in EITHER direction ('semiconductor' matches keyword 'semi', and industry 'ai'
    matches keyword 'ai chips'). Substring, not token — so 'ai' does NOT match 'artificial
    intelligence' (no consecutive a-i); the launch table lists such terms as separate industries
    when both should bridge. Crude, deterministic, reviewable — the whole scorer is meant to be
    auditable by eye, not clever."""
    lows_i = [str(s).lower() for s in industries]
    lows_k = [str(s).lower() for s in sector_keywords]
    for i in lows_i:
        for k in lows_k:
            if k in i or i in k:
                return True
    return False


def add_months(d: date, months: int) -> date:
    """Add calendar months, clamping the day to the target month's length (Jan 31 + 1mo ->
    Feb 28/29). Dependency-free so the backtest has no dateutil requirement."""
    total = (d.month - 1) + months
    year = d.year + total // 12
    month = total % 12 + 1
    # last day of the target month
    if month == 12:
        last = 31
    else:
        last = (date(year, month + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(d.day, last))


def score_firing(pair: tuple[str, str], first_fired: str, launches: list[dict],
                 sector_keywords_map: dict[str, list[str]], window_months: int = 24) -> dict:
    """Score one firing. `first_fired` is the ISO date the pair first entered active. A launch
    corroborates iff its industries keyword-match BOTH sides' keyword lists AND its detected_at
    falls in [first_fired, first_fired + window_months] (inclusive both edges). Returns
    {structural: bool, matches: [{ticker, detected_at}]}."""
    a, b = pair
    kw_a = sector_keywords_map.get(a, [])
    kw_b = sector_keywords_map.get(b, [])
    fired = date.fromisoformat(first_fired)
    window_end = add_months(fired, window_months)
    matches = []
    for launch in launches:
        industries = launch.get("concentration_industries", [])
        if not (keyword_match(industries, kw_a) and keyword_match(industries, kw_b)):
            continue
        detected = date.fromisoformat(str(launch["detected_at"]))
        if fired <= detected <= window_end:
            matches.append({"ticker": launch.get("ticker"),
                            "detected_at": launch["detected_at"]})
    return {"structural": bool(matches), "matches": matches}


def score_all(firings: list[dict], launches: list[dict],
              sector_keywords_map: dict[str, list[str]], window_months: int = 24) -> dict:
    """Score every firing ({pair, first_fired}). Returns {rows: [...], summary: {n_firings,
    n_structural, structural_fraction}}. structural_fraction is 0.0 for an empty firing list."""
    rows = []
    n_structural = 0
    for f in firings:
        scored = score_firing(tuple(f["pair"]), f["first_fired"], launches,
                              sector_keywords_map, window_months)
        n_structural += int(scored["structural"])
        rows.append({"pair": tuple(f["pair"]), "first_fired": f["first_fired"], **scored})
    n = len(firings)
    return {"rows": rows,
            "summary": {"n_firings": n, "n_structural": n_structural,
                        "structural_fraction": (n_structural / n) if n else 0.0}}
