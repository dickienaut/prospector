"""EDGAR client — the identity substrate's only network surface (spec §2, §3).

Resolution flow (CONTRACT — the HECO rule, §2): ticker → EDGAR series/class lookup
(company_tickers_mf.json) → confirm a prospectus-family filing exists (submissions) → the
caller writes the registry entry keyed on series_id. Tickers are display-only attributes;
nothing downstream may anchor to one.

Failures come back as typed ResolutionFailure values, never raised and never silently dropped
(§2 failed-resolution CONTRACT): the caller emits `resolution.failed` onto `_system` and runs
the retry-then-manual queue. The two-phase launch (§4c) consumes the same values — detection
already happened (`launch.unverified`, `detected_at`), so a resolution failure here delays
verification, never the launch timestamp.

SEC fair access: a declared User-Agent (undeclared UAs are 403'd) and a hard request-rate cap
(config `edgar.max_requests_per_sec`, DEFAULT 8 — safety margin under SEC's 10/s), with
exponential backoff on 429/403 before raising a typed EdgarError.

Freeze the substrate (§3): when `persist` is wired, every successful raw response body is
handed over BEFORE parsing (the runner points it at layout.edgar_path(date, name) +
write_atomic; tests wire a recorder).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable

import httpx

MF_TICKERS_URL = "https://www.sec.gov/files/company_tickers_mf.json"
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# The prospectus family (§2): a registry entry requires at least one of these on file.
PROSPECTUS_FORMS = ("485BPOS", "485APOS", "497", "N-1A")

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0
_RETRY_STATUSES = (429, 403)  # throttle/refusal — back off and retry; anything else is real


class EdgarError(Exception):
    """Typed EDGAR failure: a non-2xx HTTP status (`status` set when known), including 429/403
    that persisted through the capped retries. Fetch callables raise this with `status` so the
    backoff loop can tell throttling from a genuine error."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Resolution:
    """A successful §2 lookup — the raw material for a registry entry (never the entry itself:
    first_seen/verified_at/category_draft belong to the identity layer, not the wire)."""
    series_id: str
    class_ids: list[str]
    cik: int
    name: str  # trust name from submissions (registry `issuer`), not the fund's marketing name
    prospectus_accession: str
    ticker: str


@dataclass(frozen=True)
class ResolutionFailure:
    """A failed §2 lookup — countable, never silent (failed-resolution CONTRACT)."""
    ticker: str
    reason: str  # 'not_in_mf_map' | 'no_prospectus' | 'http_error'
    detail: str


class EdgarClient:
    def __init__(self, user_agent: str, fetch: Callable[[str, dict], bytes] | None = None,
                 max_per_sec: float = 8.0, clock: Callable[[], float] | None = None,
                 sleep: Callable[[float], None] | None = None,
                 persist: Callable[[str, bytes], None] | None = None):
        """`fetch` is (url, headers) -> bytes, raising EdgarError with `status` on non-2xx
        (tests close one over fixtures); the default uses httpx. `clock`/`sleep` are injectable
        for testing the limiter (defaults: time.monotonic/time.sleep). `persist` is
        (name, content) -> None for raw-response persistence (§3)."""
        if not user_agent or not user_agent.strip():
            raise ValueError("EDGAR requires a declared User-Agent (SEC 403s undeclared ones)")
        if max_per_sec <= 0:
            raise ValueError(f"max_per_sec must be positive, got {max_per_sec!r}")
        self.user_agent = user_agent
        self._fetch = fetch if fetch is not None else self._default_fetch
        self._min_interval = 1.0 / max_per_sec
        self._clock = clock if clock is not None else time.monotonic
        self._sleep = sleep if sleep is not None else time.sleep
        self._persist = persist
        self._last_start: float | None = None

    def _default_fetch(self, url: str, headers: dict) -> bytes:
        resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
        if resp.status_code != 200:
            raise EdgarError(f"GET {url} -> HTTP {resp.status_code}", status=resp.status_code)
        return resp.content

    def _throttle(self) -> None:
        """Min-interval limiter: request starts are spaced >= 1/max_per_sec apart."""
        now = self._clock()
        if self._last_start is not None:
            due = self._last_start + self._min_interval
            if now < due:
                self._sleep(due - now)
                # Injected sleeps need not advance the injected clock; either way the request
                # occupies its scheduled slot, so spacing never compresses below the interval.
                now = max(self._clock(), due)
        self._last_start = now

    def _get(self, url: str, name: str) -> bytes:
        headers = {"User-Agent": self.user_agent}
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            self._throttle()
            try:
                body = self._fetch(url, headers)
            except EdgarError as e:
                if e.status in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS:
                    self._sleep(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
                    continue
                if e.status in _RETRY_STATUSES:
                    raise EdgarError(f"GET {url} failed after {_MAX_ATTEMPTS} attempts "
                                     f"(HTTP {e.status})", status=e.status) from e
                raise
            if self._persist is not None:
                self._persist(name, body)  # freeze the substrate before parsing (§3)
            return body
        raise AssertionError("unreachable: the retry loop returns or raises")

    def mf_tickers(self) -> dict:
        """The SEC mutual-fund/ETF ticker map: {fields: [cik, seriesId, classId, symbol],
        data: [[...]]}. SPY is absent by nature, not omission — a UIT has no series ID."""
        return json.loads(self._get(MF_TICKERS_URL, "company_tickers_mf.json"))

    def submissions(self, cik: int) -> dict:
        """A registrant's filing history from data.sec.gov (columnar `filings.recent`)."""
        url = SUBMISSIONS_URL_TEMPLATE.format(cik=cik)
        return json.loads(self._get(url, f"CIK{cik:010d}.json"))

    def filing_text(self, cik: int, accession: str, primary_doc: str) -> bytes:
        """Fetch a filing's primary document (the prospectus HTML) from EDGAR Archives — rate-limited
        and frozen via `persist` like every other pull (§3). The Archives path drops the accession's
        dashes. Returns raw bytes; parsing/extraction is the caller's job (mandate-diff, §4d)."""
        acc = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{primary_doc}"
        return self._get(url, f"{acc}_{primary_doc}")


def latest_prospectus(submissions: dict) -> dict | None:
    """The most-recent prospectus-family filing in a submissions dict, as
    `{accession, primary_doc, form, filing_date}` — or None if there is none.

    Same PROSPECTUS_FORMS + newest-first rule `resolve_ticker` uses to pick the prospectus accession,
    but it also returns `primaryDocument` (the Archives filename) so the mandate-diff (§4d) can fetch
    the document text. `recent` is newest-first, so strict `>` keeps the earlier index (the later
    filing) on same-day ties — identical to resolve_ticker."""
    try:
        recent = submissions["filings"]["recent"]
        forms, dates = recent["form"], recent["filingDate"]
        accs, docs = recent["accessionNumber"], recent["primaryDocument"]
    except (KeyError, TypeError):
        return None
    best: int | None = None
    for i, form in enumerate(forms):
        if form in PROSPECTUS_FORMS and (best is None or dates[i] > dates[best]):
            best = i
    if best is None:
        return None
    return {"accession": str(accs[best]), "primary_doc": str(docs[best]),
            "form": str(forms[best]), "filing_date": str(dates[best])}


def resolve_ticker(ticker: str, client: EdgarClient) -> Resolution | ResolutionFailure:
    """The §2 resolution flow (CONTRACT): ticker → series/class lookup → confirm a prospectus
    filing exists. Matching is case-insensitive; the returned ticker is EDGAR's canonical
    symbol. Returns a typed failure instead of raising — a failed resolution must never
    silently drop the fund (§2 failed-resolution path; §10 tests 1-2)."""
    want = ticker.upper()
    # Broad excepts are deliberate: ANY HTTP or parse error must become a countable
    # ResolutionFailure('http_error'), never an exception up the launch pipeline.
    try:
        mf = client.mf_tickers()
        idx = {f: i for i, f in enumerate(mf["fields"])}
        matches = [row for row in mf["data"] if str(row[idx["symbol"]]).upper() == want]
        if matches:
            cik = int(matches[0][idx["cik"]])
            series_id = str(matches[0][idx["seriesId"]])
            symbol = str(matches[0][idx["symbol"]])
            # ALL class rows for the matched (cik, seriesId): multi-class funds aggregate,
            # including sibling classes listed under other symbols.
            class_ids: list[str] = []
            for row in mf["data"]:
                if int(row[idx["cik"]]) == cik and str(row[idx["seriesId"]]) == series_id:
                    class_id = str(row[idx["classId"]])
                    if class_id not in class_ids:
                        class_ids.append(class_id)
    except Exception as e:
        return ResolutionFailure(ticker=ticker, reason="http_error",
                                 detail=f"mf ticker map: {e}")
    if not matches:
        return ResolutionFailure(ticker=ticker, reason="not_in_mf_map",
                                 detail=f"{want} absent from {MF_TICKERS_URL}")
    try:
        subs = client.submissions(cik)
        name = str(subs["name"])
        recent = subs["filings"]["recent"]
        forms, dates = recent["form"], recent["filingDate"]
        # Most recent prospectus-family filing; `recent` is newest-first, so strict > keeps
        # the earlier index (the later filing) on same-day ties.
        best: int | None = None
        for i, form in enumerate(forms):
            if form in PROSPECTUS_FORMS and (best is None or dates[i] > dates[best]):
                best = i
        accession = None if best is None else str(recent["accessionNumber"][best])
    except Exception as e:
        return ResolutionFailure(ticker=ticker, reason="http_error",
                                 detail=f"submissions CIK{cik:010d}: {e}")
    if accession is None:
        return ResolutionFailure(
            ticker=ticker, reason="no_prospectus",
            detail=f"CIK{cik:010d} has no {'/'.join(PROSPECTUS_FORMS)} filing")
    return Resolution(series_id=series_id, class_ids=class_ids, cik=cik, name=name,
                      prospectus_accession=accession, ticker=symbol)
