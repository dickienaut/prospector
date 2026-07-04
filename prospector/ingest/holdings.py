"""Holdings ingest — freeze the constituent substrate (spec §3, §4d). The keystone: it unblocks
dispersion (§4b), rebalance (§4d), and the launch corroboration slice (§4c).

The live feed is the issuer daily holdings file (SPDR publishes a per-ticker CSV of a Select Sector
fund's constituents + weights); the quarterly EDGAR NPORT-P is the authoritative cross-check and the
point-in-time historical record (that parser is a deferred thin signature here — see
parse_nport_holdings and docs/decisions/2026-07-03-dispersion-shadow-first.md).

The §3 discipline, mirrored verbatim from ingest/prices.py:
- Every raw response body is FROZEN via write_atomic under ingest/holdings/{series_id}/{date}/ BEFORE
  anything parses it. A parse failure still leaves the frozen body on disk for the postmortem.
- The membership frame is a pure function of the frozen bytes, so load_frozen re-parses byte-identical
  substrate and reruns are offline after one pull.
- A missing row is a missing row (no fabrication); cash/derivative rows are kept AS RECORDED.

Identity (the HECO rule, §2/§5 CONTRACT). A basket is keyed on the fund's **SEC series id**; the pull
FETCHES by ticker (SPDR's URL is a source/display attribute) but FREEZES and KEYS by series_id — the
same discipline as prices' "a source quirk never leaks past the URL builder." **Constituents are
individual equities, not funds:** they carry a name + issuer identifier (CUSIP/ISIN) only, are never
run through the FundRegistry (they'd fail SERIES_ID_RE), and never key a lead. The basket is the
identity; the constituents are payload content.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
import openpyxl
import pandas as pd

from prospector.primitives.atomic import write_atomic
from prospector.store.layout import StoreLayout

# SPDR daily holdings endpoint. VERIFIED against a real file (2026-07-03): SSGA serves this as an
# **xlsx**, not a CSV (the earlier `.csv` assumption was never exercised against a real download — a
# synthetic CSV fixture hid it). `parse_spdr_holdings` reads either format. PRIMARY-SOURCE CAVEAT for
# §4c: the real daily file for an ACTIVE/thematic fund (e.g. TEKX) leaves the `Sector` column blank
# ("-") — it discloses holdings but not GICS sectors — so file-sector-derived concentration yields an
# empty set and the honest disposition is `sectors_unresolved` (tag unresolved, never guess). See
# docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md.
SPDR_URL_TEMPLATE = ("https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/"
                     "etfs/us/holdings-daily-us-en-{symbol}.xlsx")

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# The tidy membership frame's columns.
MEMBER_COLUMNS = ("name", "identifier", "weight", "sector")


class HoldingsIngestError(Exception):
    """Typed holdings-ingest failure: a non-2xx HTTP status (`status` set when known), an unknown
    source, or a body the parser cannot read (no header row / no weight column)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class MembershipSnapshot:
    """A basket's weight-covering membership as of a date. Keyed on the basket's series_id; the
    members are constituent equities (name + identifier + weight fraction + sector string), never
    funds. `coverage_actual` is the fraction of total basket weight the truncated list captures
    (>= coverage_target by construction)."""

    series_id: str
    ticker: str
    as_of: str
    source: str
    members: list[dict]
    coverage_target: float
    coverage_actual: float

    def identifiers(self) -> list[str]:
        """The constituent identifiers, membership order (weight desc). These are the panel column
        keys the dispersion sensor correlates — never tickers, never series ids."""
        return [m["identifier"] for m in self.members]


def _parse_weight(raw: str) -> float | None:
    """SPDR weights are percentages (e.g. '13.45%' or '13.45'); return the fraction (0.1345), or
    None when the cell is not numeric (a footer/disclaimer line rather than a holding). The trailing
    '%' is stripped either way — SPDR daily files are always in percent, so we always divide by 100."""
    cell = raw.strip().rstrip("%").replace(",", "").strip()
    if not cell:
        return None
    try:
        return float(cell) / 100.0
    except ValueError:
        return None


def _rows_from_body(body: bytes) -> list[list[str]]:
    """The holdings file's rows as lists of string cells, from EITHER a real SSGA **xlsx** (the live
    format — zip magic `PK\\x03\\x04`) or a CSV (the synthetic fixtures / any csv source). xlsx cells
    are stringified (None → "") so the one downstream header-find + row logic is format-agnostic; the
    Weight cell arrives as a number there (e.g. 7.06), which `_parse_weight` handles like "7.06%"."""
    if body[:4] == b"PK\x03\x04":  # xlsx is a zip; the CSV path never begins with this
        wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        ws = wb.active
        return [["" if c is None else str(c) for c in row] for row in ws.iter_rows(values_only=True)]
    text = body.decode("utf-8-sig", errors="replace")  # SPDR CSVs can carry a UTF-8 BOM
    return list(csv.reader(io.StringIO(text)))


def parse_spdr_holdings(body: bytes, ticker: str) -> pd.DataFrame:
    """Parse a SPDR daily holdings file (xlsx — the real SSGA format — or CSV) into a tidy membership
    frame [name, identifier, weight, sector], sorted by weight desc. Robust to the file's shape: a
    multi-line preamble (fund name / ticker / 'As of' date / blank), the header row, the holdings,
    then a footer/disclaimer.

    We locate the header by content (the row carrying both 'Name' and 'Weight'), then read data rows
    until a blank line or a row with no numeric weight (the footer) — so preamble and disclaimer are
    skipped without a magic skiprows count. Cash/derivative rows are KEPT as recorded (§3: a holding
    is a holding). The `Sector` value is kept AS RECORDED too — including SSGA's "-" placeholder for
    active funds that disclose no GICS sector; `sector_concentration` (§4c) treats "-"/"" as
    unresolved. Raise HoldingsIngestError on a body with no recognizable header/weight column."""
    rows = _rows_from_body(body)

    header_idx = None
    col: dict[str, int] = {}
    for i, row in enumerate(rows):
        norm = [c.strip().lower() for c in row]
        if "name" in norm and "weight" in norm:
            header_idx = i
            col = {c.strip().lower(): idx for idx, c in enumerate(row)}
            break
    if header_idx is None:
        raise HoldingsIngestError(f"no holdings header (Name/Weight) in body for {ticker}")

    name_i, weight_i = col["name"], col["weight"]
    ident_i = col.get("identifier")
    sector_i = col.get("sector")

    members = []
    for row in rows[header_idx + 1:]:
        if not any(c.strip() for c in row):
            break  # blank line separates holdings from the footer/disclaimer
        if len(row) <= weight_i:
            continue  # a short footer line, not a holding
        weight = _parse_weight(row[weight_i])
        if weight is None:
            continue  # non-numeric weight => a disclaimer row, skip (never fabricate)
        name = row[name_i].strip()
        identifier = row[ident_i].strip() if ident_i is not None and len(row) > ident_i else ""
        sector = row[sector_i].strip() if sector_i is not None and len(row) > sector_i else ""
        members.append({"name": name, "identifier": identifier, "weight": weight, "sector": sector})

    if not members:
        raise HoldingsIngestError(f"header found but no holdings rows in body for {ticker}")

    frame = pd.DataFrame(members, columns=list(MEMBER_COLUMNS))
    # Stable order: weight desc, then name — the canonical order the coverage cut and the payload use.
    return frame.sort_values(["weight", "name"], ascending=[False, True]).reset_index(drop=True)


def parse_nport_holdings(body: bytes) -> pd.DataFrame:
    """Parse a quarterly EDGAR NPORT-P body into the same tidy membership frame — the AUTHORITATIVE
    cross-check and the point-in-time historical record for the dispersion PIT backtest (§3b, test 6).

    DEFERRED (thin signature only). The PIT backtest and its delisted-constituent price-coverage
    measurement are a later slice (see docs/decisions/2026-07-03-dispersion-shadow-first.md); the
    dispersion sensor's pure pipeline is written membership-agnostic so this can drive it later with
    no sensor change. Until then, the live burn-in uses parse_spdr_holdings only."""
    raise NotImplementedError(
        "NPORT-P parsing is the deferred PIT slice (§3b); see the dispersion-shadow-first decision")


def weight_covering_members(holdings: pd.DataFrame, coverage: float = 0.90) -> tuple[list[dict], float]:
    """The §3/§4d constituent scale bound: the top holdings (weight desc) covering `coverage` of the
    basket's total weight. Returns (members, coverage_actual).

    Include THROUGH the first row whose cumulative weight reaches `coverage` of the total, so the
    captured fraction is always >= the target (never under). Coverage is measured against the sum of
    all parsed weights (equities + cash), so a fund whose weights don't sum to exactly 1.0 (rounding,
    cash) is handled honestly. Bounding at 90% caps the constituent count that feeds the O(n^2)
    dispersion correlation matrix while capturing the fund's economic core."""
    if holdings.empty:
        return [], 0.0
    total = float(holdings["weight"].sum())
    if total <= 0.0:
        return [], 0.0
    ordered = holdings.sort_values(["weight", "name"], ascending=[False, True]).reset_index(drop=True)
    cumulative = 0.0
    members = []
    for _, row in ordered.iterrows():
        cumulative += float(row["weight"])
        members.append({"name": row["name"], "identifier": row["identifier"],
                        "weight": float(row["weight"]), "sector": row["sector"]})
        if cumulative / total >= coverage:
            break
    return members, cumulative / total


@dataclass(frozen=True)
class _Source:
    ext: str
    url: Callable[[str], str]
    parse: Callable[[bytes, str], pd.DataFrame]


def _spdr_url(ticker: str) -> str:
    # SPDR's file name is the lowercased ticker; the quirk stays in the URL builder (never leaks
    # into identity — the freeze path and the snapshot key on the series_id, not this symbol).
    return SPDR_URL_TEMPLATE.format(symbol=ticker.lower())


_SOURCES = {
    "spdr": _Source(ext="csv", url=_spdr_url, parse=parse_spdr_holdings),
}


def _source(name: str) -> _Source:
    try:
        return _SOURCES[name]
    except KeyError:
        raise HoldingsIngestError(
            f"unknown holdings source {name!r}; known: {sorted(_SOURCES)}") from None


class HoldingsIngest:
    def __init__(self, layout: StoreLayout, fetch: Callable[[str, dict], bytes] | None = None,
                 clock: Callable[[], str] | None = None):
        """Same injectable seam as PriceIngest: `fetch` is (url, headers) -> bytes raising
        HoldingsIngestError on non-2xx (tests close one over a fixture body); `clock` returns the ISO
        UTC date partitioning frozen pulls under ingest/holdings/{series_id}/{date}/."""
        self._layout = layout
        self._fetch = fetch if fetch is not None else self._default_fetch
        self._clock = clock if clock is not None else (
            lambda: datetime.now(timezone.utc).date().isoformat())

    @staticmethod
    def _default_fetch(url: str, headers: dict) -> bytes:
        resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
        if resp.status_code != 200:
            raise HoldingsIngestError(f"GET {url} -> HTTP {resp.status_code}", status=resp.status_code)
        return resp.content

    def frozen_path(self, series_id: str, date_: str, ticker: str, source: str = "spdr") -> Path:
        return self._layout.holdings_path(series_id, date_, f"{ticker}.{_source(source).ext}")

    def pull(self, series_id: str, ticker: str, source: str = "spdr") -> pd.DataFrame:
        """Fetch the basket's current holdings, FREEZE the raw body under
        ingest/holdings/{series_id}/{date}/ BEFORE parsing (§3), then parse to the tidy frame. A
        corrupt body still lands on disk. A same-day re-pull overwrites (ingest/ is dated substrate,
        not the append-only events/ record)."""
        src = _source(source)
        body = self._fetch(src.url(ticker), {"User-Agent": BROWSER_UA})
        write_atomic(self.frozen_path(series_id, self._clock(), ticker, source), body)
        return src.parse(body, ticker)

    def load_frozen(self, series_id: str, date_: str, ticker: str, source: str = "spdr") -> pd.DataFrame:
        """Re-parse a frozen pull into the identical tidy frame — the frame is a pure function of the
        frozen bytes, so reruns are offline after one pull (§3)."""
        return _source(source).parse(
            self.frozen_path(series_id, date_, ticker, source).read_bytes(), ticker)

    def membership(self, series_id: str, ticker: str, date_: str, coverage: float = 0.90,
                   source: str = "spdr") -> MembershipSnapshot:
        """Load a frozen pull and truncate to the weight-covering membership (§3/§4d) — the input the
        dispersion sensor (§4b) and the rebalance sensor (§4d) consume."""
        holdings = self.load_frozen(series_id, date_, ticker, source)
        members, actual = weight_covering_members(holdings, coverage)
        return MembershipSnapshot(series_id=series_id, ticker=ticker, as_of=date_, source=source,
                                  members=members, coverage_target=coverage, coverage_actual=actual)
