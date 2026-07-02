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

import re
from datetime import date

import yaml

# A short token (like 'ai', 'gas', 'oil') is a substring of many unrelated words ('ai' ⊂ 'retail',
# 'entertainment'; 'gas' ⊂ 'megastore') — a raw substring test would forge cross-sector bridges and
# inflate the structural fraction. So a substring shorter than this must additionally land on a word
# boundary. Longer tokens keep plain substring matching, which is what makes legitimate stems work
# ('electric' ⊂ 'electricity', 'util' ⊂ 'utilities', 'reit' ⊂ 'reits').
_MIN_FREE_SUBSTRING = 4


def load_launches(path) -> list[dict]:
    """Load the curated launch table. Dates stay ISO strings; each row carries ticker,
    detected_at, and concentration_industries (the EDGAR-verified fields)."""
    doc = yaml.safe_load(open(path)) or {}
    return list(doc.get("launches", []))


def keyword_match(industries: list[str], sector_keywords: list[str]) -> bool:
    """True if any industry string and any sector keyword overlap as a case-insensitive
    substring in EITHER direction, with a word-boundary guard on short tokens (see
    _MIN_FREE_SUBSTRING). So 'electric' matches 'electricity' and 'reit' matches 'reits', but the
    2-char 'ai' matches only a standalone 'ai' — never 'retail' or 'entertainment'. 'ai' still does
    not match 'artificial intelligence' (no consecutive a-i); the launch table lists such terms as
    separate industries when both should bridge. Crude, deterministic, reviewable — the whole
    scorer is meant to be auditable by eye, not clever."""
    lows_i = [str(s).lower() for s in industries]
    lows_k = [str(s).lower() for s in sector_keywords]
    for i in lows_i:
        for k in lows_k:
            if _substr_match(k, i) or _substr_match(i, k):
                return True
    return False


def _substr_match(short: str, long: str) -> bool:
    """`short` is accepted inside `long` if it is a substring AND either long enough to be
    specific on its own or landing on a word boundary (so 'ai' ⊄ 'retail')."""
    if short not in long:
        return False
    if len(short) >= _MIN_FREE_SUBSTRING:
        return True
    return re.search(rf"\b{re.escape(short)}\b", long) is not None


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
