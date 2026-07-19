# Tiingo News as a capture source — the build seat's read

*2026-07-19. Code's response to Design's `docs/notes/2026-07-19-Tiingo-News-API-as-a-Discourse-Capture-Source`.
A working note for the design thread — the **repo-grounded** view of the proposal, not a ratification. The
decision (adopt / staging / provider) is the design thread's; this is the seat-with-eyes-on-the-machine
flagging what the codebase's own disciplines say about the join.*

## Verdict up front

**Adopt the direction; pilot cheap; but the two things that actually decide it are outside the doc's control
— the Tiingo license answer and our own identity discipline on the ticker join.** Concretely: run Design's
Stage 1 pilot as written, but pilot **Option 1 (snippet-only, no scrape)**, gate everything behind the
licensing answer, and defer the scrape-on-top layer behind a *proven* need.

## What the doc gets right (so it isn't relitigated)

It's decision-ready. The two load-bearing digs a shallow eval would have missed are both here: (a) the
ground-truth that `description` is a one-sentence **snippet, not a body** (so "full text" still means a
fetch), and (b) the license/storage question surfaced honestly as *favorable-but-inferred*. The staged,
pilot-first, falsifiable-benchmark shape matches this project's "engineered to lose" discipline. Tiingo as a
**controlled** source (paid, token-authenticated, cooperative — same class as Tiingo EOD prices, token already
in `.env`) is the principled move away from hostile open-web scraping, exactly the direction the
`2026-07-19-capture-fetch-controlled-vs-uncontrolled.md` decision deferred to "a v2 design question."

## Four repo-grounded flags

### 1. The ticker-query is a class-5 identity trap — the biggest one

Tiingo News is queried **by ticker** (`tickers=enr`). This repo's cardinal rule is **never anchor on a
ticker**: every fund keys on its SEC series id `S######`, a bare ticker is *rejected at the write path*, and
the dispersion vertical keys constituents on **CUSIP end-to-end** precisely because "ENR is a foreign/US
collision" (`CLAUDE.md` Identity; §4b/§9e; bugs I1, B1, 9e-ENR, edgar-`matches[0]`). Querying by bare ticker
reintroduces exactly that collision, and Tiingo's own `tickers[]`/`tags[]` are, by the doc's caveat, "algorithmic
and occasionally noisy." So the discipline must bite at two points:

- **The query ticker is *resolved from our identity layer*** (lead → series-id → current ticker via the
  registry / tick mf-map), never taken as given.
- **The returned `tickers[]`/`tags[]` are frozen as Tiingo *provenance*, never as verified identity.** v2 maps
  them back through *our* identity and treats them as Tiingo's classification, not ground truth (the same
  posture the doc's caveat #6 gestures at — but in this repo it is load-bearing, not a footnote).

There's also a **store-shape** consequence: news is *ticker-indexed*, capture is *lead-indexed*
(`captures/{lead}/{ts}/…`), and one ticker can touch several leads. So ingestion needs a **ticker → series-id →
lead(s) fan-out** — the existing **forward-hash routing** pattern (reuse the lead-id, intersect with active
leads; the shape launch-corroboration and rebalance already use, CONTRACT §4d), never a new ticker-keyed side
index.

### 2. Licensing × append-only is a hard gate, not just diligence

The fossil store is **append-only, never deleted** (`CLAUDE.md` Append-only; §7 frozen substrate). So
"indefinite internal retention" is not a nice-to-have — it is a **prerequisite** for Tiingo data to live in the
store at all. If Tiingo's answer is "internal use, but not indefinitely," that **conflicts with the store's core
discipline**, and the fallback (snippet-only with a TTL) breaks append-only too. So the sales email is the
**first domino**, and it should be framed to sales precisely: *"an indefinite, append-only, never-redistributed
internal archive of API-delivered news JSON."* Owner action; nothing else should be built until it lands.

### 3. "Scraping on top" is the weak layer — and it maps 1:1 onto #114, which is the tell

The scrape-for-bodies step is the **same open-web fetch that 403s**. #114
(`2026-07-19-capture-fetch-controlled-vs-uncontrolled.md`) already classifies it: Tiingo API host = controlled
(a Tiingo failure pages, like a prices failure); a scraped article URL = uncontrolled (a 403 is an advisory,
surfaced-not-paged). So "Tiingo baseline + scrape on top" slots into the controlled/uncontrolled split with no
new taxonomy — nice validation that #114 was the right groundwork. **But** it also means the scrape gives you
bodies *opportunistically* — whatever doesn't 403 — so building it commits to an unreliable full-text layer.

Two consequences:

- **Don't build the scrape layer until the pilot proves snippet+tags fall short.** For the stated goal —
  detecting a theme *forming* across many niche sources — headline + snippet + tag co-occurrence is likely the
  signal; full bodies are deep-reading that theme-*detection* may not need. (Capture is write-only in v1
  regardless — nothing reads a body until v2, so a missing body costs nothing now.)
- **If bodies *do* prove necessary, the doc's own EODHD lead is the sharper move** — its in-payload `content`
  field *sidesteps the fragile scrape entirely* rather than tolerating it. "Baseline + scraping on top" may
  really want to be "baseline, and *maybe EODHD instead of* scraping." Bench EODHD before building a scrape.

### 4. This is a v1 capture-substrate change, not v2

Design's title says "V2 baseline," but building this is **v1's job — bank the substrate more richly** — and it
stays **write-only** (nothing reads it until v2; `test_never_read_wall`). Framing it as v2 risks the wall the
handoff note guards ("do not build the interpretation… a re-synthesis is exactly when an item like this drifts
into a plan"). Keeping the label straight — *a §6 capture-source change that improves what v2 will eventually
read* — is what keeps it on the safe side of the temptation the project named as its top risk. The wall
(`No LLM text as data`) holds cleanly: Tiingo's text is publisher-authored, its tags are structured third-party
metadata, none of it is model-generated prose.

## Recommendation (staging)

1. **Pilot — Stage 1 as written, but Option 1 (snippet-only, no scrape), ~$0.** Read-only daily incremental
   pull, `sortBy=crawlDate`, `tickers=` **resolved from the live lead identities**, into a throwaway store.
   Benchmark: for the *lowest-profile* names, does Tiingo surface ≥3–5 distinct correctly-tagged sources per
   emerging theme per week that the current search pipeline misses/finds late?
2. **Gate on licensing** (owner emails sales; the append-only framing above). Nothing merges to the real store
   until this is confirmed in writing.
3. **Defer the scrape layer.** Let the pilot decide whether bodies are even needed. If they are, bench **EODHD
   in-payload `content`** against Tiingo-plus-scrape before building the fragile layer.
4. **When it firms up it's a §6 change → decision record** (Design's to propose). The `is_controlled_host`
   seam and the forward-hash fan-out are the two pieces of existing machinery it reuses.

## What the build seat can ground next (on request)

- Sketch the **store shape** for ticker-indexed news over a lead-indexed capture tree (the fan-out, the `id`
  dedupe key, `crawlDate` high-water mark) against the real `StoreLayout`/registry.
- Wire a **throwaway pilot puller** (read-only, isolated store) so the Stage-1 benchmark runs on real lead
  universes without touching the fossil store.
- Run the **EODHD `content`-field side-by-side** on our specific lead tickers, if/when Stage 3 needs bodies.

*Net: adopt the direction, pilot cheap — but the two deciders aren't in the doc's control: the license answer,
and our own identity discipline on the ticker join.*
