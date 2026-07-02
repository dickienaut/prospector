"""Price ingest — freeze the substrate (spec §3).

Daily EOD adjusted closes for the correlation grid (the 11 sector ETFs + SPY) and, later,
basket constituents. One primary + one fallback source, pinned in config (`prices.primary` /
`prices.fallback`; DEFAULT primary yahoo — Stooq's CSV endpoint currently sits behind a
JavaScript proof-of-work gate a polite HTTP client cannot pass, see the config note). The
source is recorded per row AND per panel column, so a future flip back is data-honest.

The §3 discipline, in order:
- Every raw response body is FROZEN via write_atomic under ingest/prices/{source}/{date}/
  BEFORE anything parses it — persist raw pulls before computing anything. A parse failure
  still leaves the frozen body on disk for the postmortem.
- The tidy frame is a pure function of the frozen body (no client-side range filtering), so
  `load_frozen` re-parses byte-identical substrate and backtest reruns are offline after one
  pull. Window slicing belongs to the caller.
- Missing rows stay missing: no forward-fill anywhere, and `build_panel`'s outer join keeps a
  late-listed fund's leading NaN (XLC listed 2018-06 is the live example).

Tickers here are display/column attributes for price math only — identity keys on SEC series
IDs (§2, the HECO rule), and a source quirk (Stooq wants lowercase + ".us") never leaks past
the URL builder.
"""

from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx
import numpy as np
import pandas as pd

from prospector.primitives.atomic import write_atomic
from prospector.store.layout import StoreLayout

YAHOO_URL_TEMPLATE = ("https://query1.finance.yahoo.com/v8/finance/chart/"
                      "{symbol}?period1={period1}&period2={period2}&interval=1d")
STOOQ_URL_TEMPLATE = "https://stooq.com/q/d/l/?s={symbol}&i=d"

# Stooq's US-listing symbol quirk (config `prices.stooq_suffix` documents it): xlu -> xlu.us.
STOOQ_SUFFIX = ".us"

# Plain browser-ish UA: Yahoo serves the chart API to browsers; bare library UAs get blocked.
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# ~1.45 actual (365.25 calendar / 252 trading) rounded up to 1.5 for market holidays and the
# extra price day the first return consumes. Deliberately generous: over-pulling is cheap,
# an under-warmed baseline silently corrupts every z it feeds (§4a).
CALENDAR_PER_TRADING_DAY = 1.5

TIDY_COLUMNS = ("date", "ticker", "close_adj", "source")


class PriceIngestError(Exception):
    """Typed price-ingest failure: a non-2xx HTTP status (`status` set when known), an
    unknown source, or a body the source parser cannot read."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _epoch(day: str) -> int:
    """ISO date -> unix seconds at UTC midnight."""
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _tidy(dates, closes, ticker: str, source: str) -> pd.DataFrame:
    """The tidy frame: [date (datetime64), ticker, close_adj (float), source], sorted by
    date, NaN rows dropped (a missing price is a missing row, never a filled one — §3)."""
    frame = pd.DataFrame({
        "date": pd.to_datetime(list(dates)),
        "ticker": ticker,
        "close_adj": np.asarray(list(closes), dtype="float64"),
        "source": source,
    })
    frame = frame.dropna(subset=["date", "close_adj"])
    return frame.sort_values("date").reset_index(drop=True)


def parse_yahoo(body: bytes, ticker: str) -> pd.DataFrame:
    """Parse a Yahoo v8 chart body: chart.result[0].timestamp (unix seconds, exchange-local
    trading days) x indicators.adjclose[0].adjclose. Date = UTC date of the timestamp. Null
    adjclose entries carry no price -> those rows are dropped, not filled."""
    try:
        chart = json.loads(body)["chart"]
        if chart.get("error"):
            raise PriceIngestError(f"yahoo error payload for {ticker}: {chart['error']}")
        result = chart["result"][0]
        timestamps = result.get("timestamp") or []
        adjclose = result["indicators"]["adjclose"][0]["adjclose"] if timestamps else []
    except PriceIngestError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise PriceIngestError(f"unparseable yahoo body for {ticker}: {e}") from e
    kept = [(datetime.fromtimestamp(t, tz=timezone.utc).date(), float(c))
            for t, c in zip(timestamps, adjclose) if c is not None]
    return _tidy((d for d, _ in kept), (c for _, c in kept), ticker, "yahoo")


def parse_stooq(body: bytes, ticker: str) -> pd.DataFrame:
    """Parse a Stooq daily CSV body (Date,Open,High,Low,Close,Volume; Close is adjusted).
    Kept working for the fallback flip even while the endpoint is gated (config note)."""
    try:
        table = pd.read_csv(io.BytesIO(body))
        dates = pd.to_datetime(table["Date"], errors="coerce")
        closes = pd.to_numeric(table["Close"], errors="coerce")
    except (KeyError, ValueError) as e:  # ParserError/EmptyDataError are ValueErrors
        raise PriceIngestError(f"unparseable stooq body for {ticker}: {e}") from e
    return _tidy(dates.to_numpy(), closes.to_numpy(dtype="float64"), ticker, "stooq")


def _yahoo_url(ticker: str, start: str, end: str) -> str:
    # period2 is an exclusive upper bound on bar timestamps; +1 day makes `end` inclusive.
    return YAHOO_URL_TEMPLATE.format(symbol=ticker.upper(), period1=_epoch(start),
                                     period2=_epoch(end) + 86400)


def _stooq_url(ticker: str, start: str, end: str) -> str:
    # Stooq's endpoint takes no range: full history comes down and freezes whole; the range
    # arguments shape the request only where the source supports it (callers slice).
    return STOOQ_URL_TEMPLATE.format(symbol=ticker.lower() + STOOQ_SUFFIX)


@dataclass(frozen=True)
class _Source:
    ext: str
    url: Callable[[str, str, str], str]
    parse: Callable[[bytes, str], pd.DataFrame]


_SOURCES = {
    "yahoo": _Source(ext="json", url=_yahoo_url, parse=parse_yahoo),
    "stooq": _Source(ext="csv", url=_stooq_url, parse=parse_stooq),
}


def _source(name: str) -> _Source:
    try:
        return _SOURCES[name]
    except KeyError:
        raise PriceIngestError(
            f"unknown price source {name!r}; known: {sorted(_SOURCES)}") from None


class PriceIngest:
    def __init__(self, layout: StoreLayout, fetch: Callable[[str, dict], bytes] | None = None,
                 clock: Callable[[], str] | None = None):
        """`fetch` is (url, headers) -> bytes, raising PriceIngestError on non-2xx (tests
        close one over synthetic bodies); the default uses httpx with a browser-ish UA.
        `clock` returns the ISO UTC date used to partition frozen pulls under
        ingest/prices/{source}/{date}/ (default: today, UTC)."""
        self._layout = layout
        self._fetch = fetch if fetch is not None else self._default_fetch
        self._clock = clock if clock is not None else (
            lambda: datetime.now(timezone.utc).date().isoformat())

    @staticmethod
    def _default_fetch(url: str, headers: dict) -> bytes:
        resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
        if resp.status_code != 200:
            raise PriceIngestError(f"GET {url} -> HTTP {resp.status_code}",
                                   status=resp.status_code)
        return resp.content

    def frozen_path(self, source: str, date_: str, ticker: str) -> Path:
        return self._layout.prices_path(source, date_, f"{ticker}.{_source(source).ext}")

    def pull(self, ticker: str, source: str, start: str, end: str) -> pd.DataFrame:
        """Fetch [start, end] (ISO dates, end-inclusive where the source supports a range),
        FREEZE the raw body, then parse to the tidy frame. Freeze precedes parse (§3: persist
        raw pulls before computing anything) — a corrupt body still lands on disk. A same-day
        re-pull of the same ticker+source overwrites its frozen file (ingest/ is dated
        substrate, not the append-only events/ record)."""
        src = _source(source)
        body = self._fetch(src.url(ticker, start, end), {"User-Agent": BROWSER_UA})
        write_atomic(self.frozen_path(source, self._clock(), ticker), body)
        return src.parse(body, ticker)

    def load_frozen(self, source: str, date: str, ticker: str) -> pd.DataFrame:
        """Re-parse a frozen pull into the identical tidy frame — the frame is a pure
        function of the frozen bytes, so backtest reruns are offline after one pull (§3)."""
        return _source(source).parse(self.frozen_path(source, date, ticker).read_bytes(),
                                     ticker)


def build_panel(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Tidy frames -> wide panel indexed by date, one column per ticker, values close_adj.

    OUTER join: a late-listed fund (XLC, 2018-06) has leading NaN, and any interior gap stays
    NaN — never forward-fill (§3: missing rows stay missing; a filled hole would fabricate a
    correlation observation). Per-ticker source map rides along as panel.attrs['sources']."""
    if not frames:
        raise ValueError("build_panel needs at least one tidy frame")
    columns: list[pd.Series] = []
    sources: dict[str, str] = {}
    for frame in frames:
        if frame.empty:
            raise ValueError("cannot add an empty tidy frame to the panel (no ticker row)")
        ticker = str(frame["ticker"].iloc[0])
        if ticker in sources:
            raise ValueError(f"duplicate ticker in panel input: {ticker}")
        sources[ticker] = str(frame["source"].iloc[0])
        columns.append(frame.set_index("date")["close_adj"].rename(ticker))
    panel = pd.concat(columns, axis=1, join="outer").sort_index()
    panel.attrs["sources"] = sources
    return panel


def warmup_days(cfg: dict) -> int:
    """Trading days of prices needed before the first fully-warmed departure z (§4a chain):
    the beta strip needs baseline_days of returns, the residual correlation needs corr_days
    of residuals, the baseline needs baseline_days of Fisher-z values —
    252 + 63 + 252 = 567 at defaults (config `windows`)."""
    windows = cfg["windows"]
    return int(windows["baseline_days"]) + int(windows["corr_days"]) + int(
        windows["baseline_days"])


def required_pull_start(backtest_from: str, cfg: dict) -> str:
    """Earliest ISO pull date so the backtest window opens fully warmed: `backtest_from`
    minus ceil(warmup_days * CALENDAR_PER_TRADING_DAY) calendar days (heuristic documented at
    the constant). Deterministic arithmetic, no exchange calendar dependency."""
    days = math.ceil(warmup_days(cfg) * CALENDAR_PER_TRADING_DAY)
    return (date.fromisoformat(backtest_from) - timedelta(days=days)).isoformat()
