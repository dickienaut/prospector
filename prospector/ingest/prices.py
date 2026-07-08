"""Price ingest — freeze the substrate (spec §3).

Daily EOD adjusted closes for the correlation grid (the 11 sector ETFs + SPY) and, later,
basket constituents. One primary + one fallback source, pinned in config (`prices.primary` /
`prices.fallback`; DEFAULT primary tiingo — Yahoo's chart endpoint now sits behind a
TLS-fingerprint bot challenge a polite HTTP client cannot pass; Stooq's CSV endpoint sits behind
a JavaScript proof-of-work gate; see the config note + docs/decisions/2026-07-07-tiingo-price-source.md).
The source is recorded per row AND per panel column, so a future flip back is data-honest.

The §3 discipline, in order:
- Every raw response body is FROZEN via write_atomic under ingest/prices/{source}/{date}/
  BEFORE anything parses it — persist raw pulls before computing anything. A parse failure
  still leaves the frozen body on disk for the postmortem.
- The tidy frame is a pure function of the frozen body (no client-side range filtering), so
  `load_frozen` re-parses byte-identical substrate and backtest reruns are offline after one
  pull. Window slicing belongs to the caller.
- Missing rows stay missing: no forward-fill anywhere, and `build_panel`'s outer join keeps a
  late-listed fund's leading NaN (XLC listed 2018-06 is the live example).

Adjusted closes are RETROACTIVELY MUTABLE (CRSP methodology): each new distribution re-scales the
WHOLE historical series, so a past date's `adjClose` shifts slightly on every re-pull. This is why
ingest/prices/ is dated substrate, NOT the append-only record — a re-pull of the same date legitimately
differs. The effect on returns is a tiny uniform re-scaling (consecutive-day ratios are preserved
except at the ex-date, and by a small amount), so it is negligible for correlation/departure detection
(xcorr re-pulls each tick and is self-consistent within a run). It bites only backtest bit-reproducibility
(a months-later re-run uses a slightly re-adjusted history unless that run's exact panel is frozen).

Fair access (mirrors EdgarClient §2/§3): a hard request-rate cap (config
`prices.max_requests_per_sec`) spaces pulls, and 429/403 (throttle/refusal) get exponential
backoff before a fault. Yahoo publishes no limit and 429s aggressively — a bare 12-ticker burst
trips it, and without backoff a transient 429 faults the whole panel. The backoff wraps only the
fetch; the freeze still happens in `pull` AFTER a successful fetch, so a fetch that never succeeds
leaves nothing frozen (fetch-fail stays distinct from parse-fail — §3).

Tickers here are display/column attributes for price math only — identity keys on SEC series
IDs (§2, the HECO rule), and a source quirk (Stooq wants lowercase + ".us") never leaks past
the URL builder.
"""

from __future__ import annotations

import io
import json
import math
import time
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
# Tiingo EOD daily prices (JSON). The token rides the Authorization HEADER (never the query) — a URL
# lands in PriceIngestError messages -> the append-only fossil record, so a query token would be an
# UNFIXABLE leak (see _tiingo_headers). The range is server-side and inclusive of BOTH ends.
TIINGO_URL_TEMPLATE = ("https://api.tiingo.com/tiingo/daily/{symbol}/prices"
                       "?startDate={start}&endDate={end}&format=json")

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

# Fair-access retry policy: 3 attempts, exponential backoff (1s, 2s). The set below is corrected for a
# real fetch, NOT copied verbatim from EdgarClient (whose SEC assumptions differ — see N4/N7):
#  - N7: transient 5xx (500/502/503/504 — routine behind a load balancer) ARE retried; previously they
#    raised on attempt 1 and silently dropped a ticker's column for the whole tick (a NaN §3 can't fill).
#    Transport/timeout errors (a PriceIngestError with status None — the httpx.HTTPError catch) are also
#    retried, same reason.
#  - N4b: 403 is an auth/entitlement refusal (expired/invalid token) that never clears on retry — it is
#    NOT in this set, so it raises at once.
#  - N4a: 429 is retried for per-SECOND-capped sources (yahoo/stooq), but a per-HOUR-capped source
#    (tiingo, 50/hr — `_Source.hourly_cap`) FAILS FAST on 429: a 1-2s backoff cannot reopen an hourly
#    window and each retry just spends another of the budget (see _fetch_with_retry).
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0
_RETRY_STATUSES = (429, 500, 502, 503, 504)  # back off and retry; anything else is a real error


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
    # N3: a duplicate calendar date would give build_panel a non-unique DatetimeIndex, and the outer
    # join would then BROADCAST a co-listed ticker's value onto both rows — a fabricated cross-observation
    # (§3, no-fabrication). Latest row supersedes (append-only re-pull semantics: a same-day re-pull's
    # newer print wins). build_panel keeps a loud is_unique backstop for any frame not built through here.
    frame = frame.drop_duplicates(subset=["date"], keep="last")
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
    """Parse a Stooq daily CSV body (Date,Open,High,Low,Close,Volume). Reads `Close` as close_adj —
    but whether Stooq's `Close` is split/dividend-ADJUSTED is UNVERIFIED (P1): it is assumed, never
    proven against a known corporate action, unlike Yahoo's `adjclose`. `guard_live_source` fails
    Stooq closed as a LIVE source until a recorded-real split fixture proves adjustment (config
    `prices.stooq_adjusted_verified`). Kept working for the fallback flip even while gated (config)."""
    try:
        table = pd.read_csv(io.BytesIO(body))
        dates = pd.to_datetime(table["Date"], errors="coerce")
        closes = pd.to_numeric(table["Close"], errors="coerce")
    except (KeyError, ValueError) as e:  # ParserError/EmptyDataError are ValueErrors
        raise PriceIngestError(f"unparseable stooq body for {ticker}: {e}") from e
    return _tidy(dates.to_numpy(), closes.to_numpy(dtype="float64"), ticker, "stooq")


def parse_tiingo(body: bytes, ticker: str) -> pd.DataFrame:
    """Parse a Tiingo EOD JSON array: [{date, close, adjClose, splitFactor, ...}, ...]. Reads
    `adjClose` as close_adj — the P1-correct split/dividend-ADJUSTED field, NOT raw `close`
    (verified against the NVDA-2024 10:1 split; see tests/test_prices_split.py). Null-adjClose rows
    are DROPPED, never filled (§3).

    Body-shape discrimination is deliberate: a `dict` (Tiingo's error shape, e.g. {"detail": ...},
    INCLUDING an empty {}) is NEVER rows — raise, never let it pass as a clean empty frame. A non-list
    non-dict is unparseable. An empty list [] is valid 'no rows' -> an empty tidy frame -> the runner's
    per-ticker SOFT fault (never a fabricated column, §9g)."""
    try:
        data = json.loads(body)
    except (ValueError, TypeError) as e:
        raise PriceIngestError(f"unparseable tiingo body for {ticker}: {e}") from e
    if isinstance(data, dict):
        raise PriceIngestError(f"tiingo error payload for {ticker}: {data.get('detail', data)}")
    if not isinstance(data, list):
        raise PriceIngestError(f"unparseable tiingo body for {ticker}: not a JSON array")
    try:
        kept = []
        for row in data:                    # [] flows straight through to an empty tidy frame
            adj = row["adjClose"]            # a missing key -> typed 'unparseable', never a bare KeyError
            if adj is None:                  # null adjClose carries no price -> drop, never fill (§3)
                continue
            # .date() BEFORE _tidy so the frame carries NAIVE UTC-calendar datetime64 — byte-identical
            # dtype to parse_yahoo. Feeding the raw ISO8601 'Z' string would yield tz-AWARE datetime64
            # and raise "Cannot compare tz-naive and tz-aware" the moment it meets a naive column
            # (build_panel's outer join / xcorr index math). fromisoformat needs '+00:00', not 'Z'.
            d = datetime.fromisoformat(str(row["date"]).replace("Z", "+00:00")).date()
            kept.append((d, float(adj)))
    except (KeyError, TypeError, ValueError) as e:
        raise PriceIngestError(f"unparseable tiingo body for {ticker}: {e}") from e
    return _tidy((d for d, _ in kept), (c for _, c in kept), ticker, "tiingo")


def _yahoo_url(ticker: str, start: str, end: str) -> str:
    # period2 is an exclusive upper bound on bar timestamps; +1 day makes `end` inclusive.
    return YAHOO_URL_TEMPLATE.format(symbol=ticker.upper(), period1=_epoch(start),
                                     period2=_epoch(end) + 86400)


def _stooq_url(ticker: str, start: str, end: str) -> str:
    # Stooq's endpoint takes no range: full history comes down and freezes whole; the range
    # arguments shape the request only where the source supports it (callers slice).
    return STOOQ_URL_TEMPLATE.format(symbol=ticker.lower() + STOOQ_SUFFIX)


def _tiingo_url(ticker: str, start: str, end: str) -> str:
    # Server-side range, inclusive of BOTH ends — NO Yahoo-style +1-day nudge. Token-free by design.
    return TIINGO_URL_TEMPLATE.format(symbol=ticker.upper(), start=start, end=end)


class _Secret:
    """Opaque token holder: its str/repr are '<redacted>' so the token can never stringify into a
    repr(), vars() dump, traceback-locals, or the append-only fossil record. Read `.value` ONLY inside
    _tiingo_headers. (RunnerDeps holds a PriceIngest, which holds this — never log or pickle RunnerDeps.)"""

    __slots__ = ("_value",)

    def __init__(self, value: str | None):
        self._value = value

    def __repr__(self) -> str:
        return "<redacted>"

    __str__ = __repr__

    @property
    def value(self) -> str | None:
        return self._value


def _default_headers(ingest: "PriceIngest") -> dict:
    # Yahoo/stooq: a plain browser-ish UA, no auth. Unchanged behavior through the source-aware seam.
    return {"User-Agent": BROWSER_UA}


def _tiingo_headers(ingest: "PriceIngest") -> dict:
    """Auth via the Authorization HEADER (never the URL — a URL lands in the fossil record). The token
    is read here and ONLY here, straight into the header dict; it is never interpolated into any log,
    URL, or exception. Missing token -> a FIXED, token-free raise (this flows to the fossil record)."""
    tok = ingest._api_token.value
    if not tok:
        raise PriceIngestError("TIINGO_API_TOKEN unset — refusing tiingo fetch")
    return {"Authorization": f"Token {tok}", "Content-Type": "application/json"}


@dataclass(frozen=True)
class _Source:
    ext: str
    url: Callable[[str, str, str], str]
    parse: Callable[[bytes, str], pd.DataFrame]
    headers: Callable[["PriceIngest"], dict] | None = None  # None -> _default_headers (browser UA)
    hourly_cap: bool = False  # N4a: True when the binding rate cap is per-HOUR (tiingo, 50/hr) — a
    # sub-second backoff cannot reopen the window, so a 429 fails fast (soft-fault to the next tick)
    # rather than spending more of the budget. False (yahoo/stooq) keeps the per-second 429 retry.


_SOURCES = {
    "yahoo": _Source(ext="json", url=_yahoo_url, parse=parse_yahoo),
    "stooq": _Source(ext="csv", url=_stooq_url, parse=parse_stooq),
    # The only source with custom headers: its token rides Authorization (see _tiingo_headers).
    "tiingo": _Source(ext="json", url=_tiingo_url, parse=parse_tiingo, headers=_tiingo_headers,
                      hourly_cap=True),
}


def _source(name: str) -> _Source:
    try:
        return _SOURCES[name]
    except KeyError:
        raise PriceIngestError(
            f"unknown price source {name!r}; known: {sorted(_SOURCES)}") from None


# adjClose-trust table (P1): a source listed here is fail-closed as a LIVE source until its config
# bool proves its adjusted-close field is verified against a known corporate action. A source NOT here
# (yahoo — genuinely-adjusted `adjclose`) is always allowed. Add a source ONLY alongside a recorded-
# real split proof (stooq: never verified; tiingo: verified 2026-07-07 by the NVDA-2024 10:1 split test).
_ADJ_VERIFIED_FLAG = {"stooq": "stooq_adjusted_verified", "tiingo": "tiingo_adjusted_verified"}


def guard_live_source(source: str, cfg: dict) -> None:
    """P1 fail-closed guard (§3): refuse a source as LIVE until its adjusted-close field is verified.
    An unadjusted close silently corrupts every return across a split/dividend — the base of the whole
    sensor stack — so a source whose `close` is only ASSUMED adjusted must never go live until a
    recorded-real split fixture proves it (config `prices.{source}_adjusted_verified`). Yahoo (and any
    source absent from `_ADJ_VERIFIED_FLAG`) passes. The message is PARAMETERIZED on source+flag: a
    stooq-worded raise for a tiingo trip would be a permanently wrong, un-editable fossil. Raises loud,
    on purpose: a silent wrong-return base is exactly what P1 guards against."""
    flag = _ADJ_VERIFIED_FLAG.get(source)
    if flag and not bool((cfg.get("prices") or {}).get(flag, False)):
        raise PriceIngestError(
            f"P1: {source} is not a verified adjusted-close source (prices.{flag} is false) — "
            f"refusing it as a live source; its `close` may be unadjusted, which corrupts every "
            f"return across a split. Verify against a known split, then flip the flag.")


class PriceIngest:
    def __init__(self, layout: StoreLayout, fetch: Callable[[str, dict], bytes] | None = None,
                 clock: Callable[[], str] | None = None, *, max_per_sec: float = 2.0,
                 monotonic: Callable[[], float] | None = None,
                 sleep: Callable[[float], None] | None = None, api_token: str | None = None):
        """`fetch` is (url, headers) -> bytes, raising PriceIngestError with `status` on non-2xx
        (tests close one over synthetic bodies); the default uses httpx with a browser-ish UA.
        `clock` returns the ISO UTC date used to partition frozen pulls under
        ingest/prices/{source}/{date}/ (default: today, UTC).

        `max_per_sec` caps the request rate (config `prices.max_requests_per_sec`, DEFAULT 2 —
        Yahoo publishes no limit and 429s aggressively). `monotonic`/`sleep` are the throttle's
        injectable clock/sleep (defaults time.monotonic/time.sleep) — kept DISTINCT from `clock`,
        which is the ISO-date partitioner, not a wall clock (the two roles must not conflate).

        `api_token` is the Tiingo secret (env TIINGO_API_TOKEN). It is wrapped in a _Secret holder so
        it can never stringify into a repr/vars/traceback/fossil; it is read ONLY in _tiingo_headers.
        None is fine for yahoo/stooq (their source has no `headers` builder that reads it)."""
        if max_per_sec <= 0:
            raise ValueError(f"max_per_sec must be positive, got {max_per_sec!r}")
        self._layout = layout
        self._fetch = fetch if fetch is not None else self._default_fetch
        self._clock = clock if clock is not None else (
            lambda: datetime.now(timezone.utc).date().isoformat())
        self._min_interval = 1.0 / max_per_sec
        self._monotonic = monotonic if monotonic is not None else time.monotonic
        self._sleep = sleep if sleep is not None else time.sleep
        self._last_start: float | None = None
        self._api_token = _Secret(api_token)  # opaque: never repr/log/pickle the token (see _Secret)

    @staticmethod
    def _default_fetch(url: str, headers: dict) -> bytes:
        # follow_redirects=False on purpose: with an auth-bearing header (tiingo), a 3xx must NEVER
        # forward Authorization to a redirect target, and no redirect-target body may become the frozen
        # body. The EOD endpoints don't legitimately redirect, so this only removes a leak/foot-gun.
        # NEVER put `headers` in an exception message — it carries the tiingo token (URL-only below).
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=False)
        except httpx.HTTPError as e:
            raise PriceIngestError(f"GET {url} failed: {type(e).__name__}") from None  # no headers/request
        if resp.status_code != 200:
            raise PriceIngestError(f"GET {url} -> HTTP {resp.status_code}",
                                   status=resp.status_code)
        return resp.content

    def _throttle(self) -> None:
        """Min-interval limiter: request starts are spaced >= 1/max_per_sec apart (verbatim from
        EdgarClient._throttle)."""
        now = self._monotonic()
        if self._last_start is not None:
            due = self._last_start + self._min_interval
            if now < due:
                self._sleep(due - now)
                # Injected sleeps need not advance the injected clock; either way the request
                # occupies its scheduled slot, so spacing never compresses below the interval.
                now = max(self._monotonic(), due)
        self._last_start = now

    def _fetch_with_retry(self, url: str, headers: dict, *, hourly_cap: bool = False) -> bytes:
        """Rate-limited fetch with exponential backoff on transient statuses (the freeze lives in
        `pull`, AFTER a successful fetch, so a fetch that never succeeds leaves nothing frozen:
        fetch-fail stays distinct from parse-fail, §3). NEVER put `headers` in an exception message —
        it carries the tiingo token; every raise here is URL-only.

        `hourly_cap` (N4a): on a per-HOUR-capped source a 429 fails fast (no retry) — a 1-2s backoff
        can't reopen the window and each retry burns another of the budget; the ticker soft-faults to
        the next tick instead. Retryable = the 5xx set OR a transport/timeout error (status None, N7)."""
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            self._throttle()
            try:
                return self._fetch(url, headers)
            except PriceIngestError as e:
                if e.status == 429 and hourly_cap:
                    raise  # per-hour cap: don't spend more of the budget on a window a backoff can't reopen
                # None = a transport/timeout error (the httpx.HTTPError catch) — transient, retry it (N7).
                retryable = e.status in _RETRY_STATUSES or e.status is None
                if retryable and attempt < _MAX_ATTEMPTS:
                    self._sleep(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
                    continue
                if retryable:
                    raise PriceIngestError(f"GET {url} failed after {_MAX_ATTEMPTS} attempts "
                                           f"(HTTP {e.status})", status=e.status) from e
                raise
        raise AssertionError("unreachable: the retry loop returns or raises")

    def frozen_path(self, source: str, date_: str, ticker: str) -> Path:
        return self._layout.prices_path(source, date_, f"{ticker}.{_source(source).ext}")

    def pull(self, ticker: str, source: str, start: str, end: str) -> pd.DataFrame:
        """Fetch [start, end] (ISO dates, end-inclusive where the source supports a range),
        FREEZE the raw body, then parse to the tidy frame. Freeze precedes parse (§3: persist
        raw pulls before computing anything) — a corrupt body still lands on disk. A same-day
        re-pull of the same ticker+source overwrites its frozen file (ingest/ is dated
        substrate, not the append-only events/ record). The fetch is rate-limited + 429/403-retried
        (`_fetch_with_retry`); a fetch that never succeeds raises and freezes nothing.

        Headers are SOURCE-AWARE: yahoo/stooq get a browser UA (`_default_headers`), tiingo gets its
        Authorization token (`_tiingo_headers`) — the token is built into the header dict here and never
        touches the URL or the frozen path."""
        src = _source(source)
        build_headers = src.headers or _default_headers
        body = self._fetch_with_retry(src.url(ticker, start, end), build_headers(self),
                                      hourly_cap=src.hourly_cap)
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
    # N3 backstop: a non-unique date index makes the outer join broadcast values across the dup rows —
    # a fabricated cross-observation (§3). `_tidy` already dedupes per source, so this fires only for a
    # frame built some other way; fault as loudly as the duplicate-ticker guard rather than fabricate.
    if not panel.index.is_unique:
        dups = panel.index[panel.index.duplicated()].unique().tolist()
        raise ValueError(f"duplicate dates in panel index (would fabricate a cross-observation): {dups}")
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
