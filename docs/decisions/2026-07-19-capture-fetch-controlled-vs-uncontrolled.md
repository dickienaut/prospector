# A failed discourse-capture fetch: controlled-source → operational, open-web → advisory (§8a)

**Date:** 2026-07-19
**Status:** ratified (design thread — Design originated the analysis; the owner chose the host-split disposition).
**Touches:** the §8a fault taxonomy (CONTRACT) as applied to `capture.fetch`, and the capture fetch User-Agent.
**Supersedes:** the blanket-`operational` choice for capture-fetch faults in the M6 build note
(`docs/notes/2026-07-13-m6-discourse-capture-build-note.md` §3c).

## The finding

M6 capture was armed 2026-07-18. Its first scheduled tick (`2026-07-18T22:30:04Z`) emitted **5
`capture.fetch → HTTP 403` operational faults** — from `aiolux.com`, `etf.com`, and two
`sec.gov/Archives/…424b5.htm`. Two distinct problems, one root (no host awareness in the capture path):

- **The SEC 403s are a real, fixable gap.** Capture fetches every URL with a generic browser UA
  (`_FETCH_UA`) and never sends `edgar.user_agent` — the declared identity the rest of the system sends and
  that SEC requires (`ingest/edgar.py`: "SEC 403s undeclared ones"). Capture was 403'd by SEC for exactly the
  reason the EdgarClient would be without its header.
- **The open-web 403s are not a breakage.** `etf.com` / `aiolux.com` are commentary hosts that decline
  automated fetches — bot-blocking, the expected (and rising) cost of scraping the open web. Classifying them
  `operational` pages the owner and — because `email_render` sets **Health: DEGRADED** on *any* operational
  fault — holds Health DEGRADED every week for as long as any discourse URL 403s (≈ always). That is the GPWS
  "cried-wolf → learn to ignore the alarm" failure the §8a taxonomy exists to prevent, reappearing on the
  newest subsystem.

The M6 build note (§3c) deliberately set capture-fetch faults `operational`. That ruling was made **before
anyone had watched capture meet a bot-blocking host** — the open-web 403 base rate is new information the
choice did not have. This record supersedes it *with that data*, not as a misconfiguration fix.

## The decision — severity by right-to-expect-success

**A failed fetch's severity depends on whether we had a right to expect success.** Stated as a principle, not
a host list, so it generalizes past these three URLs to whatever capture fetches next:

- **Controlled source** — a host we fetch with a **declared identity** (SEC/EDGAR via `edgar.user_agent`). We
  had a right to expect success; a failure is a real anomaly → **`operational` (pages).**
- **Uncontrolled / open web** — a commentary host that owes an automated client nothing. No expectation of
  success; a 403/block is expected friction → **`review-advisory`** (surfaced and counted in the heartbeat,
  **never pages, never DEGRADEs health**).

Capture is **write-only** (`test_never_read_wall`; nothing in v1 reads a capture), and the page-fetch is the
*supplementary* layer — the `web_search_tool_result` blocks are fetched **server-side by Anthropic** and banked
regardless of our client's fetch. So an open-web fetch miss loses only the page-text **bonus**, not the
discourse substrate: nothing operational is broken — which is exactly the `review-advisory` definition ("the
sensor correctly punting; nothing structurally broken"), already the disposition of mandate/SOI
extraction-unreliable.

## Two changes, one seam

`is_controlled_host(url)` (`ingest/capture.py`): sec.gov exact-or-subdomain; a look-alike like
`sec.gov.evil.com` is uncontrolled; an unknown/hostless URL defaults uncontrolled — the safe don't-page
direction. This single predicate drives both:

- **Fix A (UA):** `_default_fetch` sends `edgar.user_agent` to controlled hosts, the generic capture UA
  elsewhere. sec.gov capture-fetches now carry the declared identity → they succeed, or a *persistent* SEC 403
  despite proper identity is a genuine anomaly, handled by Fix B.
- **Fix B (disposition):** the single capture-fetch emit site (`runner/runner.py`) sets `category` by
  `is_controlled_host`. The advisory carries `on_live_lead=False` (the default), so it surfaces-without-paging
  with **no `_advisory_reporter` plumbing** (the `lead=` field is orthogonal to paging). The stable suppression
  key `capture.fetch:{status}` is unchanged (§10).

## Boundary / what did not change

- **`capture.search` failures stay `operational`** — the Anthropic web_search API is a controlled, paid
  source; a search failure is a real break.
- **`capture.budget` / `capture.query_drift` faults stay `operational`** — a tripped guard is a real event,
  not open-web friction.
- **No scraping arms race.** The correct response to "open-web fetching only gets harder" is to *accept* the
  403s as friction (advisory) — never UA-rotation, scraping services, or evasion (that breaches the
  primary-source ethos and chases a losing game). v1 banks what it robustly can (the search blocks); leaning
  on those over the fragile page-fetch is a v2 design question, not built here.

## Anti-fitting

A rising open-web 403 rate NEVER motivates loosening or tightening `is_controlled_host`. The controlled set is
`edgar.user_agent`-scoped **by construction** (the sources we send a declared identity to); it changes only if
a new blessed, identity-carrying source is added — a deliberate decision, never a reaction to a fault rate.
