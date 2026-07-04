"""SOI ingest + GICS-industry-grouped sector derivation — the §4c RESOLVER of `sectors_unresolved`
(design: docs/2026-07-04-soi-derived-sector-concentration.md).

The daily xlsx leaves Sector "-" for an active fund, so holdings-file sector concentration is empty and
a real launch resolves `sectors_unresolved → dormant` (the prior slice). But the sector grouping is
already published by the PRIMARY SOURCE: a fund's periodic EDGAR filing renders a GICS-INDUSTRY-grouped
Schedule of Investments — each holding sits under an industry header carrying that industry's percent of
net assets (`SOFTWARE — 38.7%`, `ELECTRIC UTILITIES — 6.4%`). Sector concentration therefore comes
DIRECTLY from parsing those headers and rolling industry → GICS sector through the frozen
`gics_industry_sector` table (config). No per-ticker classifier, no third-party feed (a bought sector
feed would breach the primary-source wall) — the correction of the prior note's convergent-prior error.

**Three jobs, three owners (same line the mandate-diff draws, §4d):**
  - **BeautifulSoup owns STRUCTURE** — `html_to_text` (reused from ingest/prospectus.py) turns the messy
    DFIN/ArcReporting filing markup into navigable text with each industry header on its own line.
  - **This module owns MEANING** — which fund's block, which industry, and the industry→sector rollup.
  - **The human owns SIGNIFICANCE** — whether a resulting overlap means anything (the overlap + verdict).

**Multi-fund isolation is MANDATORY (verified against the real TEKX NPORT-EX).** The filing is a
multi-fund trust report (TEKX, DECO, HECO, …) and the SAME industry headers recur in every fund's block,
so we isolate the TARGET fund's section (its titled `SCHEDULE OF INVESTMENTS` → its `COMMON STOCKS — N%`
→ `TOTAL COMMON STOCKS`) before parsing. Scanning the whole document would blend six funds' industries.

**Extraction-unreliable → fault, never a wrong sector set (the §4d discipline).** When the fund block
isn't isolable, an industry header is absent from the frozen table (unknown industry), or the parsed
industry weights don't RECONCILE to the `COMMON STOCKS — N%` header within tolerance, we return
`reliable: False` with a `reason` and the caller (sensors/soi.py) flags a `fault` for manual review. The
reconcile check already earned its keep: a first-draft all-uppercase regex silently dropped GICS
`SPECIALIZED REITs` (lowercase `s`), and the 96.4%-vs-99.2% mismatch caught it.

Live EDGAR fetch (which accession/document to pull) is DEFERRED to M5 (tied to EdgarClient) — see the
decision doc. This module is the READER + freeze/read side; tests drive it on hand-frozen fixtures.
"""

from __future__ import annotations

import re
from typing import Mapping

from prospector.ingest.prospectus import html_to_text
from prospector.primitives.atomic import write_atomic

_FROZEN_NAME = "soi.htm"  # the raw industry-grouped SOI HTML, frozen per accession (blob-per-accession, §7)

# Industry/total header line: "<NAME> — <N.N>%". The separator is an em/en dash (as filed) OR a
# space-padded hyphen — NOT a bare hyphen, so a hyphen INSIDE a name ("MULTI-UTILITIES") is never
# mistaken for the separator. Names may be mixed-case ("SPECIALIZED REITs"), so the class allows both.
_HEADER_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 &,/'().\-]*?)(?:\s*[—–]\s*|\s+-\s+)(?P<pct>\d+(?:\.\d+)?)\s*%$")

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})")


class SoiIngest:
    """Freeze the industry-grouped SOI per accession under ingest/soi/{series_id}/{accession}/ (§7),
    mirroring ProspectusIngest — the derived sector concentration is then a pure function of the frozen
    bytes (extract-on-read), so a later, better parser re-reads old filings with no stored staleness.

    The freeze/read side is what's built now; the LIVE fetch (which NPORT-EX/N-CSR accession + document
    carries the SOI) is the deferred M5 slice, tied to EdgarClient. `freeze` is the write primitive that
    the M5 fetch and the by-hand fixture drop both go through."""

    def __init__(self, layout):
        self._layout = layout

    def freeze(self, series_id: str, accession: str, body: bytes) -> bytes:
        """Freeze raw SOI bytes before any parsing (§3). Same-accession re-freeze overwrites (ingest/ is
        dated substrate, not the append-only events/ record)."""
        write_atomic(self._layout.soi_path(series_id, accession, _FROZEN_NAME), body)
        return body

    def has_frozen(self, series_id: str, accession: str) -> bool:
        return self._layout.soi_path(series_id, accession, _FROZEN_NAME).exists()

    def load_frozen(self, series_id: str, accession: str) -> bytes:
        return self._layout.soi_path(series_id, accession, _FROZEN_NAME).read_bytes()


# --- STRUCTURE helpers (bs4's text output; no meaning decided here) -----------------------------

def _is_caps(line: str) -> bool:
    """A fund-title line is ALL-CAPS (letters present, no lowercase). Distinguishes the wrapped caps
    fund name ("STATE STREET GALAXY TRANSFORMATIVE TECH ACCELERATORS" / "ETF") from the "Table of
    Contents" nav link that precedes it."""
    return bool(re.search(r"[A-Z]", line)) and not re.search(r"[a-z]", line)


def _norm(s: str) -> str:
    """Normalize an industry / fund name for matching: uppercase, "&"→"AND", and every run of
    non-alphanumerics collapsed to a single space. So the filing's "OIL, GAS & CONSUMABLE FUELS",
    "SPECIALIZED REITs", and "INDEPENDENT POWER & RENEWABLE ELECTRICITY PRODUCERS" match the frozen
    table's canonical keys regardless of punctuation, ampersand-vs-and, or the REITs lowercase `s`."""
    return re.sub(r"[^A-Z0-9]+", " ", s.upper().replace("&", " AND ")).strip()


def _fund_blocks(lines: list[str], section_header: str) -> list[tuple[str, int]]:
    """Every PRIMARY per-fund SOI section, as `(caps_fund_title, header_line_index)`. A section header
    line ends with the (case-insensitive) `section_header` ("schedule of investments" — also matches
    "consolidated schedule of investments"); a PRIMARY page is one whose next line is NOT "(continued)",
    so each fund contributes exactly one block (its first page, where the COMMON STOCKS block lives). The
    title is the run of ALL-CAPS lines immediately above the header (the wrapped fund name)."""
    sh = section_header.lower()
    blocks: list[tuple[str, int]] = []
    for i, l in enumerate(lines):
        if not l.lower().endswith(sh):
            continue
        nxt = lines[i + 1].lower() if i + 1 < len(lines) else ""
        if "continued" in nxt:  # continuation page, not a fresh fund block
            continue
        parts = []
        j = i - 1
        while j >= 0 and _is_caps(lines[j]):
            parts.append(lines[j])
            j -= 1
        blocks.append((" ".join(reversed(parts)), i))
    return blocks


def _parse_as_of(line: str) -> str | None:
    """Parse a filing date line ("January 31, 2026 (Unaudited)") to ISO "2026-01-31". None if absent."""
    m = _DATE_RE.search(line)
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"


# --- MEANING: derive {sector: weight} from the target fund's SOI (never significance) ------------

def extract_soi_sectors(body: bytes, cfg: dict, fund_anchor: str) -> dict:
    """Derive `{gics_sector: weight}` (weights as FRACTIONS of net assets, matching the holdings-path
    weight semantics) from the target fund's GICS-industry-grouped Schedule of Investments.

    Returns `{sectors, reliable, reason, as_of}`. `reliable` is False (and `sectors` empty) when the
    fund block can't be isolated, the COMMON STOCKS bracket is missing, an industry header is absent from
    the frozen `gics_industry_sector` table (unknown industry), or the parsed industry weights don't
    reconcile to the `COMMON STOCKS — N%` header within `soi.reconcile_tolerance`. Decides ONLY which
    sectors the fund is in and at what weight; never whether that means anything (the overlap + the human
    do that). `fund_anchor` is the fund's name/ticker used to pick its section (the SOI titles the block
    in caps; a substring match either direction selects it)."""
    soi = cfg["soi"]
    table = {_norm(k): v for k, v in cfg["gics_industry_sector"].items()}
    tol = float(soi.get("reconcile_tolerance", 0.005))
    lines = [ln for ln in html_to_text(body).split("\n") if ln]

    blocks = _fund_blocks(lines, soi["section_header"])
    if not blocks:
        return {"sectors": {}, "reliable": False, "reason": "no schedule-of-investments section found",
                "as_of": None}

    anchor = _norm(fund_anchor)
    start = end = None
    for idx, (title, hdr_i) in enumerate(blocks):
        t = _norm(title)
        if anchor and (anchor in t or t in anchor):
            start = hdr_i
            end = blocks[idx + 1][1] if idx + 1 < len(blocks) else len(lines)
            break
    if start is None:
        return {"sectors": {}, "reliable": False,
                "reason": f"fund section not found for anchor {fund_anchor!r}", "as_of": None}

    as_of = _parse_as_of(lines[start + 1]) if start + 1 < len(lines) else None

    # Isolate the COMMON STOCKS equity block within the fund's section: "COMMON STOCKS — N%" (carries the
    # reconcile total) ... "TOTAL COMMON STOCKS". Sector concentration is over the equity book.
    cs_norm = _norm(soi["common_stocks_header"])
    tcs_pfx = soi["common_stocks_total"].lower()
    cs = cs_total = None
    for i in range(start, end):
        m = _HEADER_RE.match(lines[i])
        if m and _norm(m.group("name")) == cs_norm:
            cs, cs_total = i, float(m.group("pct"))
            break
    if cs is None:
        return {"sectors": {}, "reliable": False,
                "reason": "COMMON STOCKS block header not found in fund section", "as_of": as_of}
    tcs = next((i for i in range(cs + 1, end) if lines[i].lower().startswith(tcs_pfx)), None)
    if tcs is None:
        return {"sectors": {}, "reliable": False,
                "reason": "TOTAL COMMON STOCKS boundary not found (runaway extraction)", "as_of": as_of}

    # Roll each industry header to its GICS sector. An unknown industry -> fault (never a silent mis-roll
    # that would under-count a sector and could flip a threshold).
    sectors: dict[str, float] = {}
    parsed_pct = 0.0
    for i in range(cs + 1, tcs):
        m = _HEADER_RE.match(lines[i])
        if not m:
            continue
        industry = m.group("name")
        sector = table.get(_norm(industry))
        if sector is None:
            return {"sectors": {}, "reliable": False,
                    "reason": f"unknown GICS industry {industry!r} (not in gics_industry_sector)",
                    "as_of": as_of}
        pct = float(m.group("pct"))
        parsed_pct += pct
        sectors[sector] = sectors.get(sector, 0.0) + pct / 100.0

    # RECONCILE: the parsed industry weights must sum to the "COMMON STOCKS — N%" header. A miss means a
    # dropped/misparsed industry (silent under-count) -> flag, don't guess.
    if abs(parsed_pct - cs_total) / 100.0 > tol:
        return {"sectors": {}, "reliable": False,
                "reason": (f"industry weights sum to {parsed_pct:.1f}% but COMMON STOCKS header is "
                           f"{cs_total:.1f}% (> {tol*100:.1f}pp) — a header was missed"),
                "as_of": as_of}

    return {"sectors": sectors, "reliable": True, "reason": "ok", "as_of": as_of}


def dominant_sectors(sectors: Mapping[str, float], min_weight: float) -> frozenset[str]:
    """Threshold a derived `{sector: weight}` map to the frozenset of DOMINANT sectors (weight ≥
    `min_weight`), the exact contract `sensors/launch_corroboration.route_corroboration` consumes. Same
    frozen threshold (`corroboration.sector_min_weight`) as the holdings path — one rule, two sources."""
    return frozenset(s for s, w in sectors.items() if w >= min_weight)
