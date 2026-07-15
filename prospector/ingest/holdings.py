"""Holdings ingest — freeze the constituent substrate (spec §3, §4d). The keystone: it unblocks
dispersion (§4b), rebalance (§4d), and the launch corroboration slice (§4c).

The live feed is the issuer daily holdings file (SPDR publishes a per-ticker xlsx of a Select Sector
fund's constituents + weights — the real SSGA format; see below); the quarterly EDGAR NPORT-P is the
authoritative cross-check and the
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
individual equities, not funds:** they carry a name + issuer identifier (CUSIP/ISIN) + a display
ticker (the §4b price-lookup attribute only — the dispersion panel keys on the CUSIP, HECO one level
down), are never run through the FundRegistry (they'd fail SERIES_ID_RE), and never key a lead. The
basket is the identity; the constituents are payload content.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
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

# The tidy membership frame's columns. `ticker` is the constituent's display symbol — carried ONLY as
# the Tiingo price-lookup attribute for the §4b dispersion vertical (the constituent panel keys on the
# stable `identifier`/CUSIP, NEVER the ticker — HECO one level down; tickers are display-only, §2/§5).
# The SPDR primary file itself supplies the ticker↔CUSIP pairing, so no third-party symbol feed is
# needed (a bought feed would breach the primary-source wall).
# `local_currency` is the SSGA file's own `Local Currency` column — the PRIMARY-SOURCE signal that a
# holding is a FOREIGN (non-USD) listing, whose local ticker may collide with an unrelated US symbol
# (§9e: SIEMENS ENERGY's `ENR` is also NYSE:Energizer). `priceable_members` reads it to exclude foreign
# lines from the §4b price universe — no third-party symbol feed, no wall breach. See
# docs/decisions/2026-07-10-9e-constituent-symbol-resolution.md.
MEMBER_COLUMNS = ("name", "ticker", "identifier", "weight", "sector", "local_currency")

# A full holdings file's parsed FRACTIONAL weights sum to ~1.0 (a whole portfolio). This band is an
# order-of-magnitude sanity gate on _parse_weight's percent assumption, NOT a precise-sum check — cash and
# rounding move the sum a few percent; a percent-vs-fraction UNIT error moves it 100x (H1, the review's
# one silent-failure class). Outside the band -> HoldingsIngestError (a fault), never a silent mis-scale.
_WEIGHT_SUM_MIN, _WEIGHT_SUM_MAX = 0.5, 1.5


class HoldingsIngestError(Exception):
    """Typed holdings-ingest failure: a non-2xx HTTP status (`status` set when known), an unknown
    source, or a body the parser cannot read (no header row / no weight column)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class MembershipSnapshot:
    """A basket's weight-covering membership as of a date. Keyed on the basket's series_id; the
    members are constituent equities (name + display ticker + identifier + weight fraction + sector
    string), never funds. The ticker is the §4b Tiingo price-lookup attribute only; the panel keys on
    the identifier. `coverage_actual` is the fraction of total basket weight the truncated list
    captures (>= coverage_target by construction)."""

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
    frame [name, ticker, identifier, weight, sector], sorted by weight desc. Robust to the file's shape: a
    multi-line preamble (fund name / ticker / 'As of' date / blank), the header row, the holdings,
    then a footer/disclaimer.

    We locate the header by content (the row carrying both 'Name' and 'Weight'), then read data rows
    until a blank line or a row with no numeric weight (the footer) — so preamble and disclaimer are
    skipped without a magic skiprows count. Cash/derivative rows are KEPT as recorded (§3: a holding
    is a holding). The `Sector` value is kept AS RECORDED too — including SSGA's "-" placeholder for
    active funds that disclose no GICS sector; `sector_concentration` (§4c) treats "-"/"" as
    unresolved. Raise HoldingsIngestError on a body with no recognizable header/weight column."""
    rows = _rows_from_body(body)

    def _col(cells, prefix):
        # H3: locate a header column by name, so a known issuer variant like "Weight (%)" resolves — where
        # exact `"weight" in norm` membership faulted with `no holdings header`. A genuinely alien header
        # (no cell starting "name"/"weight") still matches nothing and the row FAULTS: trading the loud
        # fault for a silent misparse of an unknown layout would be a severity inversion.
        #
        # H3-DECOY: prefer an EXACT match over a prefix match, so a decoy column that merely STARTS with the
        # prefix (e.g. "Weighted Average Life", a real SPDR fixed-income column) never shadows the real
        # "Weight" column. Returns the exact-match index if present, else the FIRST prefix match, else None;
        # an ambiguous >1-prefix header with no exact winner is caught loud by `_weight_prefix_count` below.
        prefix_hit = None
        for idx, c in enumerate(cells):
            norm = c.strip().lower()
            if norm == prefix:
                return idx
            if prefix_hit is None and norm.startswith(prefix):
                prefix_hit = idx
        return prefix_hit

    def _weight_prefix_count(cells):
        # H3-DECOY: how many columns start with "weight" when there is NO exact "Weight" column. >1 means
        # the layout is genuinely ambiguous (e.g. "Weighted Average Life" + "Weight (%)") and first-match
        # would silently guess — fault loud instead. An exact "weight" column disambiguates (returns 0).
        if any(c.strip().lower() == "weight" for c in cells):
            return 0
        return sum(1 for c in cells if c.strip().lower().startswith("weight"))

    header_idx = None
    header: list[str] = []
    for i, row in enumerate(rows):
        if _col(row, "name") is not None and _col(row, "weight") is not None:
            header_idx, header = i, row
            break
    if header_idx is None:
        raise HoldingsIngestError(f"no holdings header (Name/Weight) in body for {ticker}")
    if _weight_prefix_count(header) > 1:
        raise HoldingsIngestError(
            f"ambiguous holdings header for {ticker}: multiple columns start with 'weight' and none is "
            f"exactly 'Weight' — refusing to guess the weight column")

    name_i, weight_i = _col(header, "name"), _col(header, "weight")
    ticker_i = _col(header, "ticker")  # §4b: the constituent's Tiingo price-lookup symbol (display-only)
    ident_i = _col(header, "identifier")
    sector_i = _col(header, "sector")
    ccy_i = _col(header, "local currency")  # §9e: USD/foreign gate for the price universe (blank if absent)

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
        ticker = row[ticker_i].strip() if ticker_i is not None and len(row) > ticker_i else ""
        identifier = row[ident_i].strip() if ident_i is not None and len(row) > ident_i else ""
        sector = row[sector_i].strip() if sector_i is not None and len(row) > sector_i else ""
        local_currency = row[ccy_i].strip() if ccy_i is not None and len(row) > ccy_i else ""
        members.append({"name": name, "ticker": ticker, "identifier": identifier,
                        "weight": weight, "sector": sector, "local_currency": local_currency})

    if not members:
        raise HoldingsIngestError(f"header found but no holdings rows in body for {ticker}")

    # Weight-units sanity (H1) — the check that lived only in the test now lives in the parser.
    # _parse_weight always divides by 100 on the belief the file is in PERCENT; a file already expressed
    # in FRACTIONS would be scaled 100x too small — invisible downstream (coverage is scale-invariant) but
    # fatal to the ABSOLUTE sector_min_weight gate (§4c), silently resolving every fund `dormant` and the
    # cross-stream lag would never fire. A full holdings file's fractional weights sum to a whole portfolio
    # (~1.0); an order-of-magnitude miss means the unit assumption is wrong -> fault, never a silent 100x.
    total_weight = sum(m["weight"] for m in members)
    if not (_WEIGHT_SUM_MIN <= total_weight <= _WEIGHT_SUM_MAX):
        raise HoldingsIngestError(
            f"holdings weights for {ticker} sum to {total_weight:.4f}, outside the plausible "
            f"[{_WEIGHT_SUM_MIN}, {_WEIGHT_SUM_MAX}] portfolio band — the percent-vs-fraction unit "
            f"assumption looks wrong (a file already in fractions is silently scaled 100x too small)")

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
        members.append({"name": row["name"], "ticker": row.get("ticker", ""),
                        "identifier": row["identifier"], "weight": float(row["weight"]),
                        "sector": row["sector"], "local_currency": row.get("local_currency", "")})
        if cumulative / total >= coverage:
            break
    return members, cumulative / total


# --- §9e constituent-symbol resolution: the price-universe gate ---------------------------------------
#
# The §4b dispersion vertical prices each constituent by a BARE ticker (Tiingo is queried by symbol),
# then keys the panel on the CUSIP. But the pull trusts the ticker to be a valid, UNIQUE, US-listed
# symbol — and a real SSGA file breaks that (the QA finding: docs/notes/dispersion_foreign_ticker_findings.md).
# The gate below excludes the un-priceable lines AT THE MEMBERSHIP BOUNDARY, before the pull, so the
# basket is priced on its US-listed core and the excluded weight is a REPORTED coverage gap — never a
# silent wrong-series substitution. This is *never-anchor-on-a-ticker* (HECO, §2/§5) one level down; the
# identity key must be enforced end-to-end, not just at the panel. Decision:
# docs/decisions/2026-07-10-9e-constituent-symbol-resolution.md (Option 1 + Option 2, defer Option 3).

# A plausible US common-stock ticker: 1–5 letters + an optional class suffix (BRK.B / BF.B — `_tiingo_
# symbol` later dashes the dot). Rejects the un-priceable forms in a real file: `-`/blank (SSGA's cash &
# derivative sentinel) and internal placeholder codes carrying a digit (e.g. `2670549D`, an ExxonMobil
# line with no tradable US ticker). A digit anywhere breaks the match — no US common-stock ticker has one.
_US_EQUITY_TICKER_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,4})?$")


def _is_priceable_us_equity(member: dict) -> bool:
    """True iff a constituent can be priced by a BARE US ticker on Tiingo (§9e). Excludes, as an honest
    coverage gap (never a guess):

    - **Non-USD `Local Currency`** — a FOREIGN local listing (Siemens Energy's `ENR`, EUR). Its local
      ticker may COLLIDE with an unrelated US symbol (`ENR` is also NYSE:Energizer), so a bare pull
      returns the WRONG company's series, silently — the malignant P1 hazard exclusion defends against.
      A blank/absent currency is NOT treated as foreign (synthetic/CSV fixtures carry no currency column;
      fall back to the ticker-shape gate) — the filter only fires on an explicit non-USD value.
    - **A `MONEY MARKET` name** — a cash sweep line even on the rare chance it carries a real-looking
      ticker (its ~flat NAV would inject a zero-variance column into the correlation matrix). Defense-in-
      depth: SSGA already marks its cash lines with the `-` ticker, which the shape gate below excludes.
      (A broader cash/currency name blocklist is deliberately NOT added — false-positive-prone.)
    - **A ticker that is not a plausible US equity symbol** — `-`/blank or a placeholder code."""
    ccy = (member.get("local_currency") or "").strip().upper()
    if ccy and ccy != "USD":
        return False
    if "MONEY MARKET" in (member.get("name") or "").upper():
        return False
    return bool(_US_EQUITY_TICKER_RE.match((member.get("ticker") or "").strip().upper()))


def priceable_members(members: list[dict]) -> list[dict]:
    """The subset of a weight-covering membership priceable by a bare US ticker — the §9e price-universe
    gate applied at the MEMBERSHIP boundary, BEFORE the constituent price pull. Foreign (non-USD) listings
    and cash/derivative/placeholder lines are dropped; their weight becomes a REPORTED coverage gap (the
    caller recomputes coverage_actual over what actually priced, via `priced_coverage`), never a silent
    wrong substrate (the `ENR` collision) or a fabricated fill. Membership order (weight desc) is
    preserved. Foreign CUSIP/SEDOL→US-symbol resolution (Option 3) is the deferred 'complete' fix; until a
    resolution slice earns it, exclusion-with-a-reported-gap is the honest default. Decision record:
    docs/decisions/2026-07-10-9e-constituent-symbol-resolution.md."""
    return [m for m in members if _is_priceable_us_equity(m)]


def priced_coverage(priceable: list[dict], priced_identifiers: set, total_weight: float) -> float:
    """Honest `coverage_actual` (§9e): the fraction of the basket's TOTAL weight that ACTUALLY priced —
    the priceable members whose CUSIP landed a price column — NOT the pre-pull top-`coverage` weight sum.
    Overstating priced coverage would make the burn-in Q untrustworthy (you would not know what universe
    it was computed on); excluded (foreign/cash) and price-pull-dropped weight is a reported gap. Denom is
    the whole-basket weight (equities + cash), matching `weight_covering_members`."""
    if total_weight <= 0.0:
        return 0.0
    priced = sum(float(m["weight"]) for m in priceable if m["identifier"] in priced_identifiers)
    return priced / total_weight


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
    # H2: the real SSGA daily file is xlsx (parse_spdr_holdings reads it as such), so ext must label the
    # FROZEN fossil path correctly (.xlsx, not .csv) — a fossil-honesty fix, harmless to parsing.
    "spdr": _Source(ext="xlsx", url=_spdr_url, parse=parse_spdr_holdings),
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

    def frozen_dates(self, series_id: str, source: str = "spdr") -> list[str]:
        """The ISO dates for which this basket has a FROZEN holdings pull, OLDEST-FIRST — the substrate
        the §4d rebalance diff enumerates (today's pull vs the most-recent prior). Reads the dated
        partition dirs under ingest/holdings/{series_id}/ directly (the frozen fossils ARE the state —
        no side index), parsing each dir name as a date so a stray non-ISO dir is simply skipped, never
        a crash (mirrors the runner's _load_prior_mf_snapshot date-parse-and-sort). The `source` arg is
        accepted for signature symmetry but the layout partitions by series_id/date only (a fund's
        frozen files live under one series dir regardless of source). Empty when the basket has never
        been pulled — the rebalance first-sight SEED case (seed silently, never a fault)."""
        series_dir = self.frozen_path(series_id, "_d_", "_n_", source).parent.parent  # .../{series_id}/
        if not series_dir.is_dir():
            return []
        dates = []
        for d in series_dir.iterdir():
            if not d.is_dir():
                continue
            try:
                date.fromisoformat(d.name)  # a non-ISO dir is not a dated pull — skip, never crash
            except ValueError:
                continue
            dates.append(d.name)
        return sorted(dates)

    def membership(self, series_id: str, ticker: str, date_: str, coverage: float = 0.90,
                   source: str = "spdr") -> MembershipSnapshot:
        """Load a frozen pull and truncate to the weight-covering membership (§3/§4d) — the input the
        dispersion sensor (§4b) and the rebalance sensor (§4d) consume."""
        holdings = self.load_frozen(series_id, date_, ticker, source)
        members, actual = weight_covering_members(holdings, coverage)
        return MembershipSnapshot(series_id=series_id, ticker=ticker, as_of=date_, source=source,
                                  members=members, coverage_target=coverage, coverage_actual=actual)
