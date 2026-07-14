"""M6 discourse capture — the last v1 build slice (spec §6 CONTRACT; build note
docs/notes/2026-07-13-m6-discourse-capture-build-note.md).

v1 **captures discourse, never interprets it**: at a structural hit it freezes ONLY raw web_search
result blocks + fetched page text, so v2's retrospective interpretation has an archive to thaw
backward through ("late-arriving meaning is free", applied to the discourse stream). It is a
**write-only substrate** — nothing in v1 reads a capture (enforced by the never-read-wall test).

THE WALL (CLAUDE.md "No LLM text as data (v1)"): no model-authored prose is EVER persisted. The
provider is the Anthropic Messages API `web_search` server tool (owner decision); we keep ONLY the
`web_search_tool_result` blocks verbatim and the fetched page text — the model's `text` blocks are
structurally dropped here and never reach the store. That the wall is a filter on BLOCK TYPE (not a
promise about content) is what makes it testable.

DETERMINISM / no-LLM-authorship (§6): query construction is OUR templating (`build_queries`), never
the model's. We force the model to run our verbatim query (`tool_choice`) and record the query it
ACTUALLY issued so the runner can fault on divergence — the query text carries no timestamps/randomness,
so identical lead metadata → identical query set.

FETCH is ours, not the model's: after a search returns result URLs, we `fetch_page` the top-M URLs
directly (httpx + `html_to_text`) — deterministic (our code selects the URLs) and it keeps the metered
unit exactly `searches` (a fetch costs ~nothing and never counts against the budget). A per-URL fetch
failure is a soft fault; the partial capture is still stored.

Model↔tool pairing: the default model (`claude-haiku-4-5`, config `capture.model`) is a mechanical
fetch-only caller, so it pairs with the BASIC `web_search_20250305` tool variant (the dynamic-filtering
`web_search_20260209` requires an Opus/Sonnet-tier model; dynamic filtering is irrelevant here since we
keep the raw result blocks, not a model summary).

Provider + budget are the OWNER's (build note §4): the API key is `.env`-only (`ANTHROPIC_API_KEY`),
handled exactly like the Tiingo token — wrapped in `_Secret` so it can never stringify into the fossil
record; the spend is capped by config (`capture.max_searches_per_week`, `capture.monthly_budget_usd`).
"""

from __future__ import annotations

from typing import Callable

import httpx

from prospector.ingest.prospectus import html_to_text
from prospector.primitives.atomic import write_json_atomic
from prospector.store.envelope import parse_ts
from prospector.store.layout import StoreLayout, ts_compact

__all__ = ["CaptureError", "CaptureProvider", "CaptureBudget", "PROVIDER",
           "build_queries", "top_urls", "capture_prefix", "write_query_blob", "period_keys"]

PROVIDER = "anthropic:web_search"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# The BASIC web_search variant — pairs with the cheap fetch-only model (see the module docstring).
SEARCH_TOOL_VERSION = "web_search_20250305"
_MAX_TOKENS = 1024  # the model only orchestrates one forced search; its prose is discarded
_FETCH_UA = "Mozilla/5.0 (compatible; Prospector/1.0; discourse-capture)"


class CaptureError(Exception):
    """A capture provider failure: a non-2xx HTTP status (`status` set when known) from the web_search
    POST or a page fetch, or a transport error (`status` None). Carries `status` so the runner can key
    the soft fault on the stable (kind, status) instead of the URL-bearing message (§10 suppression)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class _Secret:
    """Opaque token holder — its str/repr are '<redacted>' so `ANTHROPIC_API_KEY` can never stringify
    into a repr, vars() dump, traceback-locals, or the append-only fossil record. Read `.value` ONLY
    inside the request-header builder. (Mirrors ingest.prices._Secret — the same wall for the same reason.)"""

    __slots__ = ("_value",)

    def __init__(self, value: str | None):
        self._value = value

    def __repr__(self) -> str:
        return "<redacted>"

    __str__ = __repr__

    @property
    def value(self) -> str | None:
        return self._value


# --- deterministic query construction (§6 — OUR templating, no LLM authorship) ------------------

def build_queries(meta: dict, k: int, top_n: int) -> list[str]:
    """The K deterministic templated queries for one capture, from lead metadata — display name, then
    concentration industries, then top-N constituent names (§6). Ordered, de-duplicated, truncated to K,
    empties dropped. NO timestamps/randomness — identical `meta` → identical list (the determinism
    CONTRACT). Fewer than K when the metadata is thin is honest, not a bug (a fresh lead may carry only
    a display name)."""
    out: list[str] = []

    def add(q) -> None:
        q = (q or "").strip()
        if q and q not in out:
            out.append(q)

    add(meta.get("display"))
    for industry in meta.get("industries") or []:
        add(industry)
    for name in (meta.get("constituents") or [])[:top_n]:
        add(name)
    return out[:k]


def top_urls(result_blocks: list, m: int) -> list[str]:
    """The first M distinct result URLs across the web_search_tool_result blocks (deterministic
    selection — OUR code picks which URLs to fetch, never the model). An error result block (its
    `content` is an error dict, not a list) contributes nothing."""
    urls: list[str] = []
    for block in result_blocks:
        content = block.get("content") if isinstance(block, dict) else None
        if not isinstance(content, list):
            continue  # a web_search_tool_result_error carries a dict content — no URLs
        for item in content:
            url = item.get("url") if isinstance(item, dict) else None
            if url and url not in urls:
                urls.append(url)
    return urls[:m]


# --- store paths (this module + StoreLayout.captures_path are the ONLY captures/ touchers) ------

def capture_prefix(lead: str, ts: str) -> str:
    """The relative store prefix for one capture, `captures/{lead}/{ts_compact}` — doubles as the S3
    key prefix (recorded on the `capture.stored` event as `s3_prefix`, the fold's index into the blobs)."""
    return f"captures/{lead}/{ts_compact(ts)}"


def write_query_blob(layout: StoreLayout, lead: str, ts: str, n: int, obj: dict) -> str:
    """Freeze one query's capture as `captures/{lead}/{ts}/query_{n}.json` (atomic, SHA-256-verified —
    the store's write discipline). Returns the SHA-256. Index-less like ingest/: the `capture.stored`
    event is the queryable index; the blob stays on disk/S3."""
    return write_json_atomic(layout.captures_path(lead, ts, f"query_{n}.json"), obj)


# --- persisted budget counter (survives restarts; visible to the dashboard) --------------------

_BUDGET_DDL = """
CREATE TABLE IF NOT EXISTS capture_budget (
    window      TEXT NOT NULL,   -- 'week' | 'month'
    period      TEXT NOT NULL,   -- ISO week '2026-W28' (searches cap) | month '2026-07' (usd estimate)
    searches    INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT,
    PRIMARY KEY (window, period)
);
"""


def period_keys(ts: str) -> tuple[str, str]:
    """(ISO-week key, calendar-month key) for a tick's `ts` — the two budget windows. The search cap is
    per ISO week; the USD estimate is per calendar month (build note §3b)."""
    dt = parse_ts(ts)
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}", f"{dt.year:04d}-{dt.month:02d}"


class CaptureBudget:
    """The persisted weekly/monthly search counter (build note §3b: count-based primary, stored not
    in-memory — it must survive restarts and be visible to the dashboard). A module-owned working table
    on the shared registry connection (the `runs`/`funds`/`resolution_queue` precedent — registry.py's
    vendored DDL stays frozen). A read-only surface never issues DDL/commit (N1)."""

    def __init__(self, registry):
        self.registry = registry
        if not getattr(registry, "readonly", False):
            registry.conn.executescript(_BUDGET_DDL)
            registry.conn.commit()

    def count(self, window: str, period: str) -> int:
        row = self.registry.conn.execute(
            "SELECT searches FROM capture_budget WHERE window = ? AND period = ?",
            (window, period)).fetchone()
        return int(row["searches"]) if row else 0

    def record_search(self, week_period: str, month_period: str, now: str | None = None) -> None:
        """Durably increment BOTH windows by one search (commit) — the counter is the metered truth, so
        it is written the moment a search is issued, before its results are stored."""
        for window, period in (("week", week_period), ("month", month_period)):
            self.registry.conn.execute(
                "INSERT INTO capture_budget (window, period, searches, updated_at) VALUES (?, ?, 1, ?) "
                "ON CONFLICT(window, period) DO UPDATE SET "
                "searches = searches + 1, updated_at = excluded.updated_at",
                (window, period, now))
        self.registry.conn.commit()


# --- the provider (Anthropic Messages API web_search + our own page fetch) ----------------------

class CaptureProvider:
    """The Anthropic `web_search` provider, shaped like `EdgarClient`/`PriceIngest`: DI `call`/`fetch`
    seams so the whole thing runs OFFLINE under the test network guard (tests close the seams over
    recorded fixtures; production uses httpx). `search` forces our verbatim query and returns ONLY the
    raw result blocks + the query the model actually issued (prose dropped — the wall). `fetch_page`
    GETs a URL and extracts its text."""

    def __init__(self, api_key: str | None, model: str = "claude-haiku-4-5", *,
                 call: Callable[[dict], dict] | None = None,
                 fetch: Callable[[str], bytes] | None = None,
                 tool_version: str = SEARCH_TOOL_VERSION, max_tokens: int = _MAX_TOKENS):
        self._api_key = _Secret(api_key)
        self.model = model
        self.tool_version = tool_version
        self.max_tokens = max_tokens
        self._call = call if call is not None else self._default_call
        self._fetch = fetch if fetch is not None else self._default_fetch

    # -- web_search -----------------------------------------------------------

    @staticmethod
    def _prompt(query: str) -> str:
        # Minimal fetch-only prompt: run OUR exact query, nothing else. The determinism guard does not
        # rest on the prompt (we validate the issued query downstream) — this just steers a clean call.
        return ("Use the web_search tool to run this exact search query, verbatim, and nothing else:\n"
                f"{query}\n"
                "Do not add, remove, or reword any terms. Do not run any other search.")

    def _search_body(self, query: str) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": self._prompt(query)}],
            "tools": [{"type": self.tool_version, "name": "web_search", "max_uses": 1}],
            "tool_choice": {"type": "tool", "name": "web_search"},  # force OUR query (determinism lever)
        }

    def search(self, query: str) -> dict:
        """Run one web_search for `query`. Returns `{query, query_issued, result_blocks}` where
        `result_blocks` is the list of `web_search_tool_result` blocks VERBATIM and `query_issued` is
        the query the model actually put on the tool call (for the runner's divergence fault). The
        model's `text` blocks are ignored HERE and never returned — the wall."""
        resp = self._call(self._search_body(query))
        query_issued: str | None = None
        result_blocks: list = []
        for block in resp.get("content", []) or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "server_tool_use" and block.get("name") == "web_search":
                query_issued = (block.get("input") or {}).get("query")
            elif btype == "web_search_tool_result":
                result_blocks.append(block)  # verbatim — the frozen substrate
            # every other block type (notably `text`, the model's prose) is DROPPED (the wall)
        return {"query": query, "query_issued": query_issued, "result_blocks": result_blocks}

    def _default_call(self, body: dict) -> dict:
        key = self._api_key.value
        if not key:
            raise CaptureError("ANTHROPIC_API_KEY unset — refusing capture")
        headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION,
                   "content-type": "application/json"}
        try:
            resp = httpx.post(ANTHROPIC_MESSAGES_URL, headers=headers, json=body, timeout=60.0)
        except httpx.HTTPError as e:  # transport/timeout -> status None (transient), never leaks the key
            raise CaptureError(f"web_search POST failed: {type(e).__name__}") from None
        if resp.status_code != 200:
            raise CaptureError(f"web_search -> HTTP {resp.status_code}", status=resp.status_code)
        return resp.json()

    # -- page fetch (OUR fetch of the top-M URLs; deterministic, unmetered) ---

    def fetch_page(self, url: str) -> str:
        """GET `url` and return its extracted page text (`html_to_text`) — the frozen substrate for the
        top-M result URLs (§6). Raises `CaptureError` (with `.status`) on failure so the runner soft-faults
        and stores a partial capture rather than killing the whole capture over one URL."""
        return html_to_text(self._fetch(url))

    def _default_fetch(self, url: str) -> bytes:
        try:
            resp = httpx.get(url, headers={"User-Agent": _FETCH_UA}, timeout=30.0,
                             follow_redirects=True)
        except httpx.HTTPError as e:
            raise CaptureError(f"fetch {url} failed: {type(e).__name__}") from None
        if resp.status_code != 200:
            raise CaptureError(f"fetch {url} -> HTTP {resp.status_code}", status=resp.status_code)
        return resp.content
