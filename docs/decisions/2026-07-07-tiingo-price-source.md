# Pivot the live price source to Tiingo EOD — Yahoo is bot-blocked by TLS fingerprint

*Decision record, 2026-07-07. Makes `tiingo` the primary price source (`prices.primary`), with a
verified-adjusted-close P-guard. DEFAULT-level config + a new secret-handling pattern; the design thread
ratified the pivot and confirmed nothing here needs a CONTRACT amendment.*

## Why Yahoo had to go (the diagnosis)

The first live `pros run` faulted on all 12 Yahoo price pulls with `HTTP 429`. We shipped a throttle +
429/403 backoff (`docs/decisions/2026-07-07-prices-throttle-backoff.md`) — correct hygiene — but a re-run
still 429'd, just slower. A full empirical probe settled it:

| Client | Result |
|---|---|
| httpx (UA only) | 429 `Too Many Requests` (HTML, no Retry-After) |
| httpx + session cookie (`A3`) | 429 |
| httpx + cookie + crumb | 429 — and `getcrumb` **itself** was challenged |
| curl, HTTP/1.1 and HTTP/2 (negotiated) | 429 |
| **Chrome, same machine, same IP** | **200, expected JSON** |

So it is **not** a rate-limit and **not** a cookie/crumb gap — it is Yahoo's edge **bot-challenge keyed on
the client's TLS/handshake fingerprint**. A real browser passes; any generic HTTP client (httpx, curl) is
walled regardless of UA, cookies, crumb, or HTTP version. This refuted two earlier hypotheses: the
cookie/crumb handshake (dead — `getcrumb` is itself challenged) and "move fetching to a VPS" (a datacenter
IP is challenged *more* aggressively; the residential-IP + browser is the *working* combination). Beating it
would need a browser-impersonating client (`curl_cffi`) — an arms-race + scraping-evasion posture at odds
with this repo's primary-source ethos. The design thread ratified pivoting the **source** instead.

## Tiingo EOD — a source we're authorized to call

Tiingo's `/tiingo/daily/{symbol}/prices` is a clean, documented JSON API on a free tier (owner's account:
50 req/hr · 1000/day · 500 unique symbols/month · ~1 GB/month, ETFs+SPY covered, `adjClose` = EOD Composite,
30+ yr history). No fingerprint games. Registered in `ingest/prices.py` as a third source alongside
yahoo/stooq (both stay registered — per-row `source` tags keep a future flip-back data-honest; no
auto-fallback is built, the runner reads `prices.primary` only).

## The secret: header, never URL; behind a redaction holder

The Tiingo token is a real secret (the repo's first). Decisions:
- **Delivery:** env `TIINGO_API_TOKEN` from a git-ignored `.env`, read at CLI startup. Nothing loads `.env`
  natively, so `cli/main.py` gains a tiny zero-dependency `_load_dotenv()` (setdefault semantics — an
  explicit export wins). Never stored in config.
- **Transport:** the token rides the `Authorization: Token <token>` **header**, never the query string.
  This is load-bearing: `PriceIngestError` messages embed the URL and land in the **append-only fossil
  record** (`_system` fault events) — a query-string token would be an *unfixable* leak.
- **In memory:** the token is wrapped in a `_Secret` holder whose `str`/`repr` are `<redacted>`, read only
  inside `_tiingo_headers`. So `repr(ingest)` / `vars(ingest)` / a traceback cannot stringify it.
- **Defence in depth:** `follow_redirects=False` on the fetch (a 3xx must never forward `Authorization` to a
  redirect target, nor freeze a request-echoing body); exceptions are URL-only (never carry the headers
  dict); the CLI fails fast with a `ClickException` if `primary==tiingo` and the token is unset (a missing
  token would otherwise silently soft-fault all 12 pulls and empty the panel).
- **Fixture gate:** the recorded-real fixture was captured with auth in the header, so no token entered the
  body; asserted absent at capture time and re-checked by a pre-commit grep.

## Verify-then-trust: the P-guard, earned in this PR (not on faith)

`guard_live_source` is generalized to a table `_ADJ_VERIFIED_FLAG = {stooq, tiingo}` with a message
**parameterized on source+flag** (a stooq-worded raise for a tiingo trip would be a permanently wrong
fossil). Yahoo is absent → always allowed. Tiingo is gated on `prices.tiingo_adjusted_verified`, flipped
`true` in this same PR **because a real proof ships with it**: the recorded-real NVDA 2024-06-10 10:1 split
fixture. `test_tiingo_adjclose_continuous_across_nvda_split` is falsifying by construction — three legs on
the same rows: (1) `adjClose` continuous across the ex-date; (2) the raw `close` in the same body **does**
break ~10× there (proving the parser selected the adjusted field — asserted on `|log-ratio|`, since a 10:1
forward split is a price *drop*, not a jump); (3) `splitFactor`=10 on the 2024-06-10 row. Categorically
better than Stooq (an assumed-adjusted close with nothing to check it against): here the corporate-action
truth ships **with** the prices.

**Also caught (a HIGH correctness edge):** `parse_tiingo` converts the ISO8601 `date` to a **tz-naive**
calendar date (`.date()` before `_tidy`) — matching `parse_yahoo`'s dtype. Feeding the raw `Z` string yields
tz-aware `datetime64` and raises "Cannot compare tz-naive and tz-aware" the moment a tiingo column meets a
naive one in `build_panel`'s outer join. Pinned by a dtype-parity test.

## Scope guardrails (named, NOT built)

- **Corporate-actions feeds (Distribution/Splits) are a verification instrument, not a build target.**
  Because we consume `adjClose` (Tiingo pre-adjusts), we never compute adjustments off raw closes — so the
  dividend and forward-split feeds feed *nothing* in this system. Do NOT build a sensor around them; the only
  use of split data is the one-time `splitFactor` verification above. A raw-actions use is filed as an idea,
  never queued (same class of guardrail as the proto-cluster v2 wall).
- **§9e constituent-price vertical** would blow the free tier's **500 unique symbols/month** (a ~40-name
  basket × several baskets reaches 500; unique-symbol accounting is cumulative). Needs a paid plan or a
  different feed — that sizing belongs to whoever thaws §9e. This PR is the 12-ticker sector grid only.

## A property, not a bug: adjClose is retroactively mutable

Reading Tiingo's docs surfaced a real property (documented in `ingest/prices.py`): under CRSP methodology,
each new distribution re-scales the **whole** historical series, so a past date's `adjClose` shifts slightly
on every re-pull. This *validates* classifying `ingest/prices/` as **dated substrate, not the append-only
record** — a re-pull of the same date legitimately differs. The effect on returns is a tiny uniform
re-scaling (consecutive-day ratios preserved except at the ex-date), negligible for correlation/departure
detection (xcorr re-pulls each tick and is self-consistent within a run). It bites only backtest
bit-reproducibility (a months-later re-run uses a slightly re-adjusted history unless that run's exact panel
is frozen). A property to know, not fix — the substrate design already absorbs it.

## Free-tier budget

The runner pulls **12 symbols/tick**, each one server-side-ranged request over the ~2.5-yr warmup
(`required_pull_start`). Binding cap = **50 requests/hour**: nominal 4.2× headroom, worst-case ~1.4× (3×
retry on a throttle storm = 36/hr, and re-runs / `config.changed` re-pulls are additive — there's no
same-day dedup). Keep `max_requests_per_sec: 2` (a *lower* per-second rate is safer against the hourly cap).
An optional skip-if-frozen-today dedup in `pull()` would make re-runs cost 0 — recommended, flagged
out-of-scope. Requests/day, bandwidth, and (for the 12-grid) unique-symbols/month are all >25× comfortable.

## Residual risks

Token leak via repr/exception/redirect → `_Secret` + URL-only exceptions + `follow_redirects=False`
(residual: a debugger reaching `_Secret._value` — inherent, accepted). 50/hr worst-case 1.4× → keep 2/s
+ optional dedup. Mid-life token expiry (401) silently empties the panel via soft faults → caught by the
7-day silence posture (orthogonal fix, not in scope). Flag-flip-on-assumption → structural gate (the split
test is a normal, in-PR, green-before-the-flip test).

## Tests
21 new (offline): parse (adjClose-not-close; **dtype-parity with yahoo**; null-drop; `[]`→empty; `{}`/
`{detail}`→raise; missing-key→typed; non-JSON→raise); pull/secret (**Authorization header, token absent from
URL/path/body**; freeze round-trip; missing-token raises before fetch; **repr/vars omit the token**; yahoo
still sends browser UA; **non-200 freezes nothing**); guard mirrors; the NVDA split proof; CLI missing-token
`ClickException`; `.env` loader semantics. The runner integration tests (`test_runner*.py`) were converted to
exercise the real tiingo path (token + tiingo bodies). Suite: 470 green.
