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

SOI-target resolution (§9b): `resolve_soi_target` finds *which* accession + *which exhibit
document within it* carries a fund's current GICS-industry-grouped Schedule of Investments
(`latest_soi` picks the accession by form priority; `filing_index` + `resolve_soi_document`
pick the non-primary exhibit). It returns coordinates only — the runner's deferred pass (§9d,
step 3) fetches the bytes and hands them to `sensors/soi.scan`. The parse lives in ingest/soi.py.
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

# The SOI family (§9b): forms that render a GICS-industry-grouped Schedule of Investments. ORDER IS
# PRIORITY, not just membership — `latest_soi` returns the newest of the FIRST non-empty tier, so an
# NPORT-EX is preferred over a newer N-CSR/N-CSRS. The reader (ingest/soi.py) is verified ONLY against
# NPORT-EX; a newest-by-date rule could route it an unverified N-CSR report structure — the exact
# flag-don't-guess violation the module forbids. N-PORT (the non-EX XML) carries NO GICS grouping and
# must never be listed here.
SOI_FORMS = ("NPORT-EX", "N-CSR", "N-CSRS")

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0
# throttle/refusal (429/403 — SEC's cap is per-second, so a short backoff can clear them) PLUS transient
# 5xx (N7 mirror: submissions/SOI are fetched every tick and had the identical gap — a routine 502/503/504
# behind SEC's edge raised on attempt 1 and silently dropped the fetch). A transport/timeout error
# (EdgarError status None — the httpx.HTTPError catch) is retried too. Anything else is a real error.
_RETRY_STATUSES = (429, 403, 500, 502, 503, 504)


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


@dataclass(frozen=True)
class SoiTarget:
    """Coordinates for a fund's current SOI document (§9b): which accession, and which exhibit document
    WITHIN it carries the GICS-industry-grouped Schedule of Investments — NOT the NPORT-EX
    `primaryDocument` (`primary_doc.xml`, the N-PORT XML, which carries no GICS). The runner's deferred
    pass (§9d, step 3) fetches `primary_doc` for `accession` via `EdgarClient.filing_text` and hands the
    bytes to `sensors/soi.scan`'s `fetch_body` seam."""
    cik: int
    accession: str
    primary_doc: str   # the resolved sector-bearing exhibit .htm, NEVER primary_doc.xml
    form: str
    filing_date: str


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
        # N7 mirror: a transport/timeout error becomes an EdgarError with status None (URL-only), so the
        # retry loop can treat it as transient rather than letting it escape uncaught mid-tick.
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
        except httpx.HTTPError as e:
            raise EdgarError(f"GET {url} failed: {type(e).__name__}") from None
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
                # None = a transport/timeout error (the httpx.HTTPError catch) — transient, retry it (N7).
                retryable = e.status in _RETRY_STATUSES or e.status is None
                if retryable and attempt < _MAX_ATTEMPTS:
                    self._sleep(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
                    continue
                if retryable:
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

    def filing_index(self, cik: int, accession: str) -> dict:
        """An accession's file manifest (`index.json`) from EDGAR Archives — rate-limited and frozen via
        `persist` like every other pull (§3). The SOI-bearing document is a NON-primary exhibit within an
        NPORT-EX accession (its `primaryDocument` is `primary_doc.xml`, the GICS-less N-PORT XML), so the
        exhibit `.htm` must be resolved from this manifest — see `resolve_soi_document` (§9b)."""
        acc = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/index.json"
        return json.loads(self._get(url, f"{acc}_index.json"))


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


def prospectus_history(submissions: dict) -> list[dict]:
    """All prospectus-family filings in a submissions dict, NEWEST-FIRST, each as
    `{accession, primary_doc, form, filing_date}`. `latest_prospectus` is effectively `[0]`; the mandate
    frozen-prior walk (§9c) uses the rest to find the most-recent filing it holds FROZEN. `recent` is
    newest-first, so preserving that order keeps this consistent with `latest_prospectus`."""
    try:
        recent = submissions["filings"]["recent"]
        forms, dates = recent["form"], recent["filingDate"]
        accs, docs = recent["accessionNumber"], recent["primaryDocument"]
    except (KeyError, TypeError):
        return []
    return [{"accession": str(accs[i]), "primary_doc": str(docs[i]),
             "form": str(forms[i]), "filing_date": str(dates[i])}
            for i, form in enumerate(forms) if form in PROSPECTUS_FORMS]


def latest_soi(submissions: dict) -> dict | None:
    """The SOI-bearing filing to fetch, as `{accession, primary_doc, form, filing_date}` — or None if
    there is none. Mirrors `latest_prospectus`, but with a FORM-PRIORITY rule instead of pure
    newest-by-date: walk `SOI_FORMS` in order and return the newest filing of the FIRST form-tier that
    has any filing (NPORT-EX preferred; N-CSR/N-CSRS fallback only). The reader is verified solely
    against NPORT-EX, so a slightly older NPORT-EX beats a newer N-CSR — a date rule would silently route
    the parser an unverified report structure (flag-don't-guess, §9b). Within a tier, `recent` is
    newest-first, so strict `>` on filing date keeps the later filing on a same-day tie (as
    latest_prospectus).

    `primary_doc` is EDGAR's `primaryDocument` — for NPORT-EX that is `primary_doc.xml` (no GICS); the
    caller resolves the sector-bearing exhibit via `filing_index` + `resolve_soi_document`."""
    try:
        recent = submissions["filings"]["recent"]
        forms, dates = recent["form"], recent["filingDate"]
        accs, docs = recent["accessionNumber"], recent["primaryDocument"]
    except (KeyError, TypeError):
        return None
    for tier in SOI_FORMS:  # priority order, not newest-across-all-forms
        best: int | None = None
        for i, form in enumerate(forms):
            if form == tier and (best is None or dates[i] > dates[best]):
                best = i
        if best is not None:
            return {"accession": str(accs[best]), "primary_doc": str(docs[best]),
                    "form": str(forms[best]), "filing_date": str(dates[best])}
    return None


def resolve_soi_document(index: dict) -> str | None:
    """The sector-bearing SOI HTML exhibit within an accession's `index.json`, or None to FAULT.
    Manifest shape: `{"directory": {"item": [{"name": ..., "type": ...}, ...]}}`. Keep the `.htm`/`.html`
    items, drop the `{acc}-index.htm` cover page and any `primary_doc.*` (the N-PORT XML). EXACTLY ONE
    survivor -> it (the real TEKX exhibit is `NPORT_J9C7_54705771_0725.htm`); ZERO or MORE THAN ONE ->
    None, refusing to guess (the anchor-ambiguity discipline, ingest/soi.py). The caller turns a None
    into a fault / not-yet, NEVER a wrong document — a wrong exhibit is a wrong sector set (§9b)."""
    try:
        items = index["directory"]["item"]
    except (KeyError, TypeError):
        return None
    candidates: list[str] = []
    for it in items:
        name = str(it.get("name", "")) if isinstance(it, dict) else ""
        low = name.lower()
        if not (low.endswith(".htm") or low.endswith(".html")):
            continue
        if low.endswith("-index.htm") or low.endswith("-index.html"):
            continue
        if low.startswith("primary_doc."):
            continue
        candidates.append(name)
    return candidates[0] if len(candidates) == 1 else None


# N8: the four outcomes the deferred SOI pass must be able to TELL APART. The old bare `None` collapsed
# three of them — a genuine not-yet, an ambiguous exhibit (which the design says surface for manual
# review), and a swallowed exception — into one indistinguishable value, so an ambiguous filing was
# silently re-fetched every tick until the 180-day horizon and never surfaced. `classify_soi_target`
# returns the reason; `resolve_soi_target` stays a thin target-only wrapper so its callers/tests are
# unchanged. AMBIGUOUS and ERROR are FAULTS the runner surfaces; NOT_YET stays silent.
SOI_RESOLVED = "resolved"      # coordinates found
SOI_NOT_YET = "not_yet"        # no SOI filing indexed yet — silent, re-attempt next cycle
SOI_AMBIGUOUS = "ambiguous"    # SOI filing EXISTS but its exhibit is not uniquely resolvable — FAULT
SOI_ERROR = "error"            # a network/parse error — FAULT (never swallowed as a not-yet)


def classify_soi_target(cik: int, client: EdgarClient) -> "tuple[SoiTarget | None, str]":
    """Resolve a fund's SOI coordinates AND say WHICH outcome it is (N8): `(target, reason)` where
    `reason` ∈ {SOI_RESOLVED, SOI_NOT_YET, SOI_AMBIGUOUS, SOI_ERROR}. Ambiguous (the filing is there but
    the exhibit can't be uniquely resolved) and error are FAULTS the runner must surface — never silent
    not-yets that re-fetch forever. Still never raises up the deferred-pass pipeline (countable-failure
    discipline): a failure is reported via the reason, not an exception (a swallowed exception — e.g. a
    submissions-shape change — becomes SOI_ERROR and surfaces, instead of masquerading as a not-yet)."""
    try:
        subs = client.submissions(int(cik))
        soi = latest_soi(subs)
        if soi is None:
            return None, SOI_NOT_YET
        index = client.filing_index(int(cik), soi["accession"])
        doc = resolve_soi_document(index)
        if doc is None:
            return None, SOI_AMBIGUOUS  # the filing exists; the exhibit is ambiguous -> surface it
        return SoiTarget(cik=int(cik), accession=soi["accession"], primary_doc=doc,
                         form=soi["form"], filing_date=soi["filing_date"]), SOI_RESOLVED
    except Exception:
        return None, SOI_ERROR


def resolve_soi_target(cik: int, client: EdgarClient) -> SoiTarget | None:
    """Resolve a fund's current SOI document coordinates (target only; see `classify_soi_target` for the
    reason a None carries). Returns a `SoiTarget`, or None for any non-resolved outcome. Unchanged
    contract — kept for the ticker-only / test callers that don't need the reason."""
    target, _reason = classify_soi_target(cik, client)
    return target


def _aggregate_class_ids(mf_data: list, idx: dict, cik: int, series_id: str) -> list[str]:
    """All class ids for a (cik, series) in the MF map — multi-class funds aggregate, including
    sibling classes listed under other symbols (§2). Order-preserving, de-duplicated."""
    class_ids: list[str] = []
    for row in mf_data:
        if int(row[idx["cik"]]) == cik and str(row[idx["seriesId"]]) == series_id:
            class_id = str(row[idx["classId"]])
            if class_id not in class_ids:
                class_ids.append(class_id)
    return class_ids


def confirm_prospectus(subs: dict, cik: int) -> tuple[str | None, str, str]:
    """Confirm a prospectus-family filing exists (§2), as `(accession, "", "")` for the newest one in
    `filings.recent`; or `(None, reason, detail)` when there is none. `recent` is newest-first, so
    strict `>` on filing date keeps the later filing on a same-day tie.

    B1 (known limitation): the submissions doc is per-CIK with NO series/class dimension, so the picked
    accession is the TRUST's newest prospectus, not proven to cover the resolved series. Series-scoped
    confirmation needs the filing's SERIES/CLASS header (filing-text ingest — deferred, the mandate-diff
    gate); until then identity is series-keyed (cik/class from the series, resolve_series) but the
    prospectus accession is registrant-level. See docs/decisions/2026-07-06-identity-integrity.md.

    B2: `filings.recent` holds only the newest ~1000 filings; older ones live in `filings.files[]` pages
    we do not yet paginate. If such pages exist and no prospectus is in `recent`, the answer is
    INCONCLUSIVE — return reason 'older_filings_unread', never a silent 'no_prospectus' that would
    wrongly queue a long-lived registrant. Following the pages is the named deferral."""
    recent = subs["filings"]["recent"]
    forms, dates, accs = recent["form"], recent["filingDate"], recent["accessionNumber"]
    best: int | None = None
    for i, form in enumerate(forms):
        if form in PROSPECTUS_FORMS and (best is None or dates[i] > dates[best]):
            best = i
    if best is not None:
        return str(accs[best]), "", ""
    if subs["filings"].get("files"):  # older filing pages exist, unread (B2 — pagination deferred)
        return (None, "older_filings_unread",
                f"CIK{cik:010d} has no prospectus in filings.recent, but older filing pages exist "
                f"(filings.files[]) not yet paginated (B2) — resolution deferred, not absent")
    return (None, "no_prospectus", f"CIK{cik:010d} has no {'/'.join(PROSPECTUS_FORMS)} filing")


def resolve_ticker(ticker: str, client: EdgarClient) -> Resolution | ResolutionFailure:
    """The §2 resolution flow (CONTRACT): ticker → series/class lookup → confirm a prospectus
    filing exists. Matching is case-insensitive; the returned ticker is EDGAR's canonical
    symbol. Returns a typed failure instead of raising — a failed resolution must never
    silently drop the fund (§2 failed-resolution path; §10 tests 1-2).

    A symbol mapping to MORE THAN ONE (cik, series) is AMBIGUOUS -> `ambiguous_symbol` fault, never a
    silent `matches[0]` pick by document order (the reused-ticker trap). The launch path sidesteps this
    entirely by resolving on the DETECTED series id (`resolve_series`, I1); this guards the ticker-only
    callers (manual/CLI)."""
    want = ticker.upper()
    # Broad excepts are deliberate: ANY HTTP or parse error must become a countable
    # ResolutionFailure('http_error'), never an exception up the launch pipeline.
    try:
        mf = client.mf_tickers()
        idx = {f: i for i, f in enumerate(mf["fields"])}
        matches = [row for row in mf["data"] if str(row[idx["symbol"]]).upper() == want]
        distinct = {(int(r[idx["cik"]]), str(r[idx["seriesId"]])) for r in matches}
    except Exception as e:
        return ResolutionFailure(ticker=ticker, reason="http_error",
                                 detail=f"mf ticker map: {e}")
    if not matches:
        return ResolutionFailure(ticker=ticker, reason="not_in_mf_map",
                                 detail=f"{want} absent from {MF_TICKERS_URL}")
    if len(distinct) > 1:
        pairs = "; ".join(f"CIK{c:010d}:{s}" for c, s in sorted(distinct))
        return ResolutionFailure(
            ticker=ticker, reason="ambiguous_symbol",
            detail=f"{want} maps to multiple (cik, series): {pairs} — refusing to guess "
                   f"(resolve on the detected series id)")
    cik, series_id = next(iter(distinct))
    symbol = str(matches[0][idx["symbol"]])
    class_ids = _aggregate_class_ids(mf["data"], idx, cik, series_id)
    try:
        subs = client.submissions(cik)
        name = str(subs["name"])
        accession, reason, detail = confirm_prospectus(subs, cik)
    except Exception as e:
        return ResolutionFailure(ticker=ticker, reason="http_error",
                                 detail=f"submissions CIK{cik:010d}: {e}")
    if accession is None:
        return ResolutionFailure(ticker=ticker, reason=reason, detail=detail)
    return Resolution(series_id=series_id, class_ids=class_ids, cik=cik, name=name,
                      prospectus_accession=accession, ticker=symbol)


def resolve_series(series_id: str, ticker: str, client: EdgarClient) -> Resolution | ResolutionFailure:
    """The §2 resolution flow keyed on the DETECTED series id, NOT re-derived from the ticker (I1,
    CONTRACT §2/§4c). The launch sensor already knows the exact series (the frozen mf-map diff pair),
    and everything downstream keys on the series id — so identity attaches to THAT series and EDGAR only
    VERIFIES it (cik, classes, a prospectus exists), never re-answers "which series is this ticker?",
    which on a reused ticker (the HECO case) `matches[0]` can get wrong. `ticker` is display-only,
    carried onto the Resolution. Returns a typed failure, never raises — the auto path enqueues for
    retry (`register_launch`)."""
    try:
        mf = client.mf_tickers()
        idx = {f: i for i, f in enumerate(mf["fields"])}
        rows = [r for r in mf["data"] if str(r[idx["seriesId"]]) == series_id]
        cik = int(rows[0][idx["cik"]]) if rows else 0
        class_ids = _aggregate_class_ids(mf["data"], idx, cik, series_id) if rows else []
    except Exception as e:
        return ResolutionFailure(ticker=ticker, reason="http_error",
                                 detail=f"mf ticker map: {e}")
    if not rows:
        return ResolutionFailure(ticker=ticker, reason="not_in_mf_map",
                                 detail=f"series {series_id} absent from {MF_TICKERS_URL}")
    try:
        subs = client.submissions(cik)
        name = str(subs["name"])
        accession, reason, detail = confirm_prospectus(subs, cik)
    except Exception as e:
        return ResolutionFailure(ticker=ticker, reason="http_error",
                                 detail=f"submissions CIK{cik:010d}: {e}")
    if accession is None:
        return ResolutionFailure(ticker=ticker, reason=reason, detail=detail)
    return Resolution(series_id=series_id, class_ids=class_ids, cik=cik, name=name,
                      prospectus_accession=accession, ticker=ticker.upper())
