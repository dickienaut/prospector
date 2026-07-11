# The Thesis Generator — Decisions Review

*Companion to the founding document. **Revision 2, 2026-07-01** — supersedes the 2026-06-29 version. This is a concept-freeze: it records every choice the brainstorm settled, the reasoning that load-bears each one, and the forks still open — so the choices can be reviewed cold and the open ones answered deliberately. Nothing here is built yet. Where the founding document is the why, this is the running log of what-we-decided-and-why-it-held.*

**Changes since the 2026-06-29 review (for re-familiarization):**
- **Fork A resolved (§15, was the main open question).** v1 runs the deterministic streams live *and* captures discourse without interpreting it; discourse interpretation is deferred to v2. The build-order argument from a parallel read is folded in and reconciled with the earlier capture/interpretation split.
- **"Same-pipeline-is-the-wall" added (§1).** A generated lead earns a position only by clearing the identical per-investment-thread discipline as any existing holding — converting a chunk of the generator's safety from habit back to structure.
- **§12 survivorship line corrected.** The caveat applies to *buying* launches; *watching* them as novelty events has no survivorship problem, which is what you are actually doing.
- **Type-minting gate upgraded (§7).** The multi-expert vote now produces *falsifiable artifacts* (reuse-prosecutors vs mint-justifiers), minting must state a boundary, and novelty escalates rather than resolving by tally.
- **Data sourcing and coordinate system decided (§9, §11).** Free data only for v1; GICS taxonomy is licensed, so membership is derived from free ETF holdings; etfdb categories seed the draft grid; sector-level resolution first, sub-industry deferred.
- Ledger (§13) and open questions (§14) updated to match.

---

## §0 — Naming the pair

The two tools are one primitive pointed two directions, so the names should make the symmetry legible.

- **Internal shorthand: yin (detector) / yang (generator).** Keep it. It already captures the polarity and you reach for it naturally.
- **Detector: the Smoke Detector.** Established; the files already carry the name. Defensive, inward, watches what you hold.
- **Generator: proposed — the Prospector.** It pans the frontier; most pans are gravel, a few carry ore, and a human assays what's promising before anything is mined. That maps exactly onto *novelty earns a look, reality earns a position* and onto the two-stage gate. Alternatives if it doesn't fit: **Scout** (lighter, recon-flavored) or **Forager** (closer to your animal-path instinct).
- **Umbrella for the pair, if you want one: Janus** — one system, two faces, one looking inward at what you hold and one outward at what's forming.

The rest of this document uses *detector* and *generator*.

---

## §1 — The spine that did not move

These came from the founding document and survived the brainstorm intact. Stated briefly because they are settled.

- **The governing asymmetry.** The detector is *structurally* safe — its vocabulary is GO-LOOK and silence, it has no verb for "acquire," and its prescriptive parts are closed-form rules written in calm. The generator is *open-form*: it produces new things to want, which is exactly what the over-trading defense most needs to contain. Its safety cannot be inherited; it must be a held habit.
- **The wall.** The generator's output is a reading list, never an order ticket. It proposes *up*; it never executes *down*. The human keeps the one thing never delegated — the commitment to act.
- **The consensus trap.** Well-argued ≠ mispriced. A machine that scores argument quality is a beautiful engine for discovering what everyone already knows, because the better-evidenced a thesis is, the more thoroughly it has already been priced.
- **The resolution.** Rank by substrate-reality (durable real shifts), not trade quality — consensus-but-true is fine to own for seventeen years. And target *novelty*, not quality: detect change, catch a shift as it forms, which is *before* consensus by construction. **Novelty ≠ interest** — interest is confirmation bias wearing a fun hat, and the generator must never become a machine for surfacing what already excites you.

**Making one part of the wall structural (new).** The wall above is held as a *habit*, and the detector earned its safety through *structure* — so the aim, everywhere possible, is to convert habit back into structure. One decisive conversion is available: a generated lead becomes a position only by clearing the *identical* per-investment-thread discipline as any existing holding — a written thesis, defined break-triggers, and sizing that survives a 50%+ drawdown — with no shortcut for being *interesting*. "The generator surfaced something exciting" and "I hold it" are separated by the same discipline that governs GRID and XBI. **The pipeline is the wall.** This is the structural complement to the held habit, and it is the thing §1 most wanted: a compelling generated lead can no longer lean on the disciplined portfolio process to shortcut itself, because it must pass *through* that process like everything else.

---

## §2 — The structural reframe: ETFs as a maintained ontology

The single largest move the brainstorm made. "Sector discourse" in the founding document was a placeholder for a corpus; the ETF universe replaced it with something far better.

**An ETF is a pre-packaged thesis.** Each basket hands you, for free: a holdings list (named entities — your nodes), a mandate (the explicit thesis), a rebalance schedule (the curator updating that thesis), and an issuer with skin in defining the boundary. It is the same instinct as keying look-through on CUSIP rather than ticker — the basket is the natural unit.

It also dissolved a fork I had flagged as a hard problem. New *edges* between known entities live inside tracked baskets — home turf for a co-occurrence graph. New *entities* show up as new ETF launches — curated, named, and rare, so the "new node floods every edge" problem evaporates. The architecture separates two detection problems that no single statistic could separate.

---

## §3 — Three novelty streams, and the thing they measure together

Once the ETF universe is the structure, there is not one novelty signal but three, sitting at different points on the consensus curve.

| Stream | Position on the curve | Character | Maintained by | Writer |
|---|---|---|---|---|
| **Discourse edges** | earliest | noisy, high-recall, speculative | nobody (you build it) | LLM scouts (v2) |
| **Rebalancing (N-PORT)** | middle | curated, lagged, high-precision | every issuer, for free | deterministic |
| **ETF launches** | near-consensus | the timestamp of package-ability | issuers + market | deterministic |

**The payload is the lag between streams** — velocity toward consensus, the exact quantity §2 swore no web-scanner could measure. The sweet spot is an edge you watched form *just* getting its first basket: real enough to package, young enough that you are not late.

**The barbell dodge.** ETFs lag, so a universe of only existing baskets risks being structurally late. The fix is to watch a few *broad* baskets as the wide early-coverage sensor array (datacenter × utility co-occurrence shows up between broad-tech and broad-utility holdings long before any "AI power" thematic exists) and watch *thematic launches* as the consensus clock. The breadth keeps you early. Note the pleasing fact: this watch-structure is your portfolio barbell pointed outward — broad core where you detect, thematic satellites where detection graduates.

**Fleet reconciliation, offense edition.** Streams agreeing or disagreeing gives CORROBORATED / CONTESTED / THIN — the detector's Bank C enum, opposite polarity. CONTESTED (an edge forming while curators pull holdings *out*) is the most information-rich state the system can sit in: either you are early or it is a head-fake.

---

## §4 — The throughput problem and the policy network

You chose **auto-expand**: the watched universe grows along holdings-graph edges into the firewalled skunkworks, rather than staying hand-curated. The reasoning was decisive — *you don't know novelty until it's knocking on your door*, so a curated universe is blind to the genuinely new by construction. Let it search, pin the weird, watch it. The AlphaGo Move-37 standard: alien but not reckless.

The AlphaGo lesson cuts the other way too, and it relocated the real risk. **Alien is cheap; alien-and-correct is expensive, and correctness cannot be gotten by searching harder.** The scarce resource is not the search — it is the oracle, and the oracle is you, and you are slow. So the over-trading chamber is not the universe expanding; it is the **throughput mismatch**: generation is free and unbounded, adjudication is slow, costly, low-volume, and human. The defense is AlphaGo's other half — a cheap pre-filter (the policy network) that ranks the firehose by a proxy for realness, so the scarce human evaluation lands on the most-robust-weird first.

**Dispersion is that pre-filter.** Rising intra-basket dispersion is the empirical signature of a taxonomy under strain: when a basket's members fly apart, some new force is differentiating them that does not respect the old boundary. It is cheap (variance across constituents, no NLP, on data you already hold) and it is the *inside-out shadow* of those constituents forming new edges to *other* baskets. Cheap dispersion finds the defection; expensive graph search finds the destination. Dispersion aims the graph. Two refinements: the signal is really *bimodality* (a clean split into sub-clusters), not plain variance (one runaway outlier is usually idiosyncratic noise); and dispersion is cause- and direction-blind, which is fine, because pointing is its whole job.

---

## §5 — The fossil record: LTEE, append-only, and the limit

You pointed at the Lenski Ledger, and the analogy turned out to be load-bearing rather than decorative.

| LTEE | Generator |
|---|---|
| 12 founding lines | the watched universe (sectors, industries, their ETFs) |
| daily transfer, identical medium | the fixed-cadence scan — the unbiased backbone |
| frozen samples every 500 generations | the freezer: archived snapshots, never overwritten |
| fossil record locates *when* a trait arose | thaw-backward through cadence frames |
| Cit+ at ~33,000 generations | the rare lead that becomes an ownable substrate |
| potentiation: silent prior mutations | sub-threshold precursor edges, invisible at the time |

The deepest finding: **potentiation is only visible in replay, and replay needs the frozen record.** A novelty-only archive catches the event and loses its causes. So the boring cadence backbone *is* the scientific instrument; the exciting capture is nearly useless without it.

**Where the analogy snaps, and it matters.** Lenski's replay is *causal* — he regrows a frozen ancestor and re-runs evolution forward. Your fossil record is read-only forever; you can thaw backward and *observe* the precursors, but you can never re-run discourse to prove a linkage was inevitable. So the honest label for what the generator produces is **reconstructed path, never demonstrated cause.** A read-only record is perfectly designed to let hindsight draw an elegant inevitable line backward from any outcome and feel like potentiation. Name the limit explicitly, or thaw-backward becomes a confirmation-bias engine in a lab coat — which fails condition three of your own graduation gate. (Your own framing: *knowing we're on a path is information* — the animal-track point — is exactly what an immutable event stream can honestly deliver. The track is real; the destination is not yet written.)

This is the direct reason Fork A (§15) resolves the way it does: capturing discourse on cadence *now*, even uninterpreted, is the frozen backbone; declining to capture it until v2's interpreter exists would be the Lenski mistake of failing to freeze the boring history before you knew it would matter.

---

## §6 — The schema

A chain of decisions that now form a coherent whole.

**Output medium: text only.** This moved the system's center of gravity off the briefing and onto the archive (append-only is an archive-first decision). Text lets the briefing *show its work inline* — a folded narrative carried next to the literal dated events it folds from. You cannot footnote a podcast; you can footnote a file. So the answer to "narrative is more persuasive than a table" is not to suppress the narrative but to **bind it to its receipts** — cite-or-fault, reappearing on the generator side as fold-shows-its-events.

**Storage: append-only.** The unit is an immutable dated observation; a *lead* is the **fold** over its event stream, never a mutated row. Three properties carry it:
1. *Corrections are appends, never edits* (an `edge.faded` event, the original left standing). This is what makes the generator scoreable — you cannot grade a forecaster who edits their old forecasts.
2. *Late-arriving meaning is free* — a fold re-run against the full stream finds significance that was invisible at write time, because it includes everything that arrived after. The thaw-backward feature is only expressible over an append-only store.
3. *The fold is hindsight-resistant by construction* — immutable, dated events cannot be rewritten to make an outcome look inevitable, so the narrative is constrained to the actual observation order. Reconstructed-path honesty becomes a property of the schema, not a disclaimer you must remember.
   - **Cost:** the store only grows and folds slow down. Mitigation is periodic snapshots (a materialized state-as-of-date you fold forward from). Snapshot cadence is a real parameter, not a detail (see open questions).

**Event taxonomy: closed envelope, open type, graceful fallback.** The thing that must be frozen is the fold's ability to *read* old events, not the vocabulary. So: a closed five-field envelope (`ts, lead, type, payload, schema`) that never changes; an open `type` string; a payload whose shape varies by type. The fold interprets the types it knows and *renders the unknown ones visibly rather than dropping or guessing them* — cite-or-fault again (known = interpreted, unknown = visible fault). The elevation: **an unrecognized event type is the generator's highest-value output** — novelty in its own detection categories, Bank D pointed at the toolmaker. A rising rate of "the fold saw something it couldn't name" is itself a front-page metric. Cost: the open vocabulary tends toward entropy (five hundred near-duplicate types), so minting is disciplined in two stages. At *write* time a new type must survive the falsifiable-artifact gate (§7) before it earns the label; over *time*, a mandatory periodic **vocabulary review** — the offensive twin of the detector's roulette-chamber review — ratifies which minted types graduate from raw-rendered to interpreted, using the append-only log's recurrence evidence (a type that mints once and never recurs is retired with evidence, not vibes).

**The DNA frame that governs all of it.** Fixed bases = the envelope. Codon→amino-acid mapping = the fold's tag→interpretation table. New genes from the same bases = new tags from the same envelope. A written genome doesn't rewrite itself = events are immutable. Evolution edits the population = vocabulary review edits the recognized set. A mutation is a new sequence, not an edited old one = a correction is a new event. This resolves the apparent paradox "immutable but can grow": the *event* is immutable, the *vocabulary* grows — different objects. **Tags can always be added as theses shift; an event already written never mutates.**

---

## §7 — The human in the loop

**Verdicts: yes / no / watch, as append-only events.** You don't flip a status field; you append a dated verdict, so your *own adjudication history* lives in the fossil record beside the machine's observations. Given your memory, this is a prosthesis: when a culled lead resurfaces months later, the fold returns *"you marked this no on this date — here is the event stream you saw at the time."* It also makes *you* scoreable — a `no` that later sprouts a `launch` is an auditable miss. *Watch* is the patient middle, which is most of the collection.

**Tag disagreement, and the minting gate.** Two cases, handled differently. The *routine* case — which existing tag fits an observation — the multi-expert scouts resolve by convergence: they agree, you tally it, done. But minting a *new* type must never resolve by tally, for two symmetric reasons. Majority-to-reuse smothers a real lone mint — the one scout who saw the genuinely new thing, outvoted by three who pattern-matched it into a comfortable existing box. Majority-to-mint launders a shared hallucination into a permanent type. And a plain vote on "is this novel?" is a vote on an *unfalsifiable* question — models hallucinate *agreement* as easily as any one hallucinates an answer, so a tally rubber-stamps false consensus in either direction.

The fix is to make what the voters *produce* falsifiable, by splitting the burden. Some scouts prosecute for *reuse*: map the observation onto the nearest existing tags, and the mint survives only if that mapping genuinely fails. Others justify the *mint* and must state its *boundary* — what would and would *not* belong to the new type. A type that cannot say what would fail to belong to it is not a category, it is a mood, and that vagueness is the tell for a hallucinated one. The vote then ranks over *checkable artifacts* — does existing tag X actually cover this; does the proposed type have a real boundary — instead of over vibes. This is the adversarial function you asked for, living *inside* the voting structure as opposing assignments rather than as a separate network you would have to trust symmetrically anyway.

The purpose of all this is to make minting *expensive*, because right now it is the cheapest thing a confused writer can do — a fresh label is unfalsifiable at the moment of writing, so inventing one costs nothing. That is exactly backwards: minting is *permanent* (it enters the vocabulary), it is the *highest-value* signal (novelty in the system's own categories), and it triggers your review — so it must be the *most* expensive action, earned only by surviving the strongest case *for reuse*.

**Escalate on novelty (the safety valve).** Agreement auto-resolves; novelty escalates. On a genuine mint the vote's job is not to *decide* but to *detect that novelty is present* and route it to you — dual-written, both the majority tag and the novel tag with the novel one flagged, exactly like the dual-write settled earlier (blocking loses data; unwritten, given your queue, means never-written — the observation evaporates). The append-only log then adjudicates over time whether the mint earned its keep.

**Symmetric distrust.** The reuse-prosecutors are themselves LLMs and can hallucinate a *fit* as easily as scouts hallucinate *novelty* — waving away a real mint by inventing a bad match, suppressing genuine signal. Independence is the protection (they fail differently), but the resolution when they disagree is not "the prosecutor wins" any more than it was "the majority wins" — a mint/reject split is *itself* the high-information state, and it routes to you, dual-written. The adversary never gets to *kill* novelty; it gets to make novelty expensive and falsifiable, and to escalate the fights it cannot cleanly win. Disagreement is surfaced, never averaged; you are the referee of last resort — now with the guarantee that by the time a mint reaches your desk it has already had to survive the strongest case *against* its own novelty.

---

## §8 — Who writes the events

Settled split, and it follows the loose-coupling instinct.

- **Deterministic writers** own dispersion, rebalance, and launch. These are countable facts (a threshold crossed, a holding in an N-PORT delta, a basket existing); they cannot lie and they emit only pre-defined tags. Correct for these streams precisely because numerical facts cannot surprise you in *kind*, only in *degree*.
- **LLM writers** own only the discourse-edge stream, where novelty is genuinely pre-categorical. They run under the *upgraded* multi-expert protocol (§7): not a plain vote on novelty, but split-burden voting over falsifiable artifacts (reuse-prosecutors vs mint-justifiers), with minting required to state a boundary and novelty escalating rather than resolving by tally. The fabrication risk specific to LLM writers is contained by independence *plus* that falsifiability — concordance alone is not enough, because scouts can share a hallucination; the falsifiable artifact is the thing a shared hallucination cannot fake.

**v1 scope (Fork A, §15): the LLM writers do not run yet.** In v1 the discourse stream is *captured, not interpreted* — raw discourse is frozen on cadence with no LLM scouting, no tag minting, no interpretation. The only *interpreting* writers in v1 are the deterministic ones. The multi-expert protocol above describes v2, when the interpretation layer turns on; it is specified now so the schema and the append-only log are built to receive it, but it is dark until the deterministic core has proven the oracle can keep up.

A clarification that emerged late and matters: **a single agent scanning a deterministic feed and a fleet of agents searching the open web are two roles, not competitors.** The single feed-scanner is pattern-spotting on ground truth (low fabrication risk — the prices and flows are already real); the multi-agent web search is a fabrication filter built from independence (high risk — any one agent can hallucinate a linkage). They map onto AlphaGo: the feed-scanner is the *policy network* (cheap, wide, always-on, prunes), the multi-agent discourse search is the *rollout* (expensive, narrow, fired only on what the policy net flags). The scanner does not replace the scouts; it decides *when to spend them*.

---

## §9 — The corpus, and the HECO finding

**The discourse scout is anchored on frozen thesis docs, not raw headlines.** Raw headline co-occurrence has brutal signal-to-noise (two tickers in one news cycle is mostly same-day-earnings noise). A fund's stated mandate is an *explicit, curated baseline*, so the scout's job sharpens to "find discourse linking this basket to something *outside* its stated mandate" — novelty by construction relative to the fund's own self-definition. It composes with the rest: dispersion says which basket is straining, the thesis doc says what it claims to be, the scout finds what it is straining *toward*. (This is a v2 concern — the scout does not run in v1 — but the anchor is decided now.)

**Which document is the baseline — the HECO natural experiment.** You proposed etfdatabase blurbs as the cheap corpus; the fund you grabbed at random handed us the cautionary tale before the resource earned any trust. etfdatabase's HECO blurb describes an *eco/ESG fund*. The live HECO is the *State Street Galaxy Hedged Digital Asset Ecosystem ETF* — crypto, launched 9 Sep 2024, explicitly not ESG. The blurb is categorically wrong and currently serving. Had you frozen HECO's baseline as "ESG fund" and pointed a scout at its actual crypto holdings, the system would have fired its loudest-possible false-positive departure — measuring etfdatabase's error, not the world. That is §7-of-the-founding-doc made concrete: the metric firing on an artifact of the measurement apparatus.

**The resolutions this forced:**
- *Division of labor.* The blurb is a fine **skim** layer (look-or-don't); the prospectus is the frozen **baseline** (the truth you measure departure against). A baseline that is categorically wrong manufactures departure. Don't let the skim layer do the anchor's job.
- *Identity is the CUSIP problem one level up.* The skim source is ticker-keyed; the authoritative anchor is keyed on the permanent SEC series ID; the ticker "HECO" silently bridged a crypto fund onto a defunct ESG fund's record. Funds must be pinned to something that cannot be reused — series ID or CIK — or the whole append-only record sits on a foundation that can quietly become a different fund.
- *The seed/verify/audit loop, and etfdb as the draft coordinate system (your design).* etfdb's own sector/industry categories seed the first-draft grid: scraping the category tree gives a serviceable draft taxonomy *and* a rough membership map (the funds in each category) in one pull, touching no classification license — you are reading etfdb's editorial grouping, theirs to show, not reproducing GICS. etfdb *steers*; primary sources set *truth*: the draft points at a bucket, you pull the constituent ETFs' prospectuses and holdings from EDGAR, and those overwrite the draft. A draft that decays into truth as you verify — the same shape as the whole system, where nothing cheap is trusted, only used to aim an expensive check. Resolve tickers to permanent series IDs at the verify step; that is where identity gets pinned. New categories arrive for free as the site posts them, so the frontier search is reserved for linkages no category has captured.
- *Audit = detection.* Make the audit event-driven, not calendar-driven: a fund filing a new prospectus or N-PORT is itself the trigger to re-verify, and when the new filing disagrees with what you recorded, that diff *is* a `mandate-changed` event — the exact thesis-drift signal the generator exists to catch. The staleness audit and the drift detector are one mechanism reading one diff.
- *The diff trap, and why it generalizes.* etfdatabase-as-change-detector (diffing periodic scans) is the right reframe, but HECO reappears in it: the day etfdb fixes that record, the scan-diff shows "a fund moved from ESG to crypto," which is the *source correcting itself*, not the world changing. And the trap is not confined to blurbs — etfdb's *category assignments* are wrong too. A fund mis-described is a fund mis-filed: the stale ESG-HECO would have sat in an *ESG bucket* while actually holding bitcoin miners. So when you diff category-tree scans over time, a fund hopping categories carries the same two meanings as any diff — real thesis-drift, or etfdb correcting a mis-file. The verify step is therefore not only for first-time ID population; it disambiguates *every* category change etfdb ever shows you. Same diff, same two possible meanings, same referee: the primary source.

---

## §10 — Infrastructure and cost

- **Target:** cheap AWS, S3 buckets as the append-only store (object writes are natural appends; versioning backstops immutability; lifecycle rules age old events into cheap storage without deletion — the fossil record gets cheaper, never pressured to prune). SSH control from the Mac, but **infra-as-code as a file in the repo**, not a hand-configured server, so future-you's knowledge is not load-bearing.
- **Briefing:** a morning text email — the fold, rendered and pushed, receipts inline. Email is text-only by nature, which enforces the discipline for free.
- **Dashboard:** a read-only Streamlit companion for the deep-dive surfaces — the unrecognized-type panel, the thaw-backward views, ranking and connection exploration.
- **Dead-man's-switch (real, easy to forget):** an unwatched server drifts until the email silently stops, and *no email looks identical to a quiet day* — the turkey problem in the infra layer. The briefing must fire even on a quiet day ("scanned, nothing promoted") so that *no email* unambiguously means *broken*, never *calm*.
- **API:** Messages API `web_search` server tool (metered per search) plus `web_fetch` (which can only fetch URLs from prior search results or you — it cannot construct URLs, an anti-exfiltration property that suits us). Multi-scout is 3+ agents with differently-aimed searches, reconciled — a v2 concern.
- **Batch + prompt caching** is the right cost lever and async is fine — but hold the cost model lightly until two product numbers are confirmed (don't architect around memory): the batch discount, the cache lifetime, and crucially *whether they stack* — cache TTL is short, a batch can take much longer to return, so if the scheduler spreads requests out the cache may expire between the ones that would have hit it. If they don't compose, you pick one.
- **v1 running cost (Fork A):** the deterministic streams are near-free (EDGAR filings, ETF price history), but v1 *also* pays a small standing bill for cadence discourse *capture* — metered single-pass searches plus storage — even though nothing is interpreted yet. This buys the frozen backbone (§5, §15) and adds *zero* oracle load. It is the one recurring cost that exists purely to protect future retrospective analysis; budget it as such.

---

## §11 — Cheap signals, the divergence reframe, velocity, and data sourcing

**The reframe under your skim signals (AUM, holdings, price): the information lives in divergence from peers, not in the level.** A fund's AUM growing tells you mostly that its sector is in favor (laggy, and the most promotion-contaminated number on the page); growing *faster than its siblings* tells you something specific. Price-level is the laggiest, most-priced-in signal you can pick — the consensus trap in one number — but price *divergence* among funds that normally co-move is a real pointer. Holdings change is the exception that proves it: already a delta, already the curated middle stream. **Rank the skim by divergence, not level.**

**The sector layer (your SIX-index screenshot).** Those are the eleven GICS sectors; you don't need the index values, because the tracking sector ETFs (the XL-series) carry decades of free daily history, so rolling correlations are trivial — your data worry is unfounded. The trap: raw correlation is dominated by the market factor (everything correlates in a selloff), so a Tech–Utility correlation spike may just mean "the market moved together." The signal you want is *excess* co-movement — correlation of the residuals after stripping the common factor. Same instinct as your ρ(G) branching-ratio work (endogenous vs exogenous), and the founding doc's "density in previously-empty regions, not global drift" in another costume. Total co-movement is the global drift; excess co-movement is the new edge.

**Data sourcing and the licensing wall (decided: free-only for v1).** The *numbers* in the sector/industry tables are free; the *classification* underneath them is not, and the gap is where the architecture already has the answer. Returns come from tracking-ETF price history — the Select Sector SPDRs for the eleven sectors, industry funds where they exist — free from Yahoo or Stooq; membership comes from SEC EDGAR N-PORT holdings, free and authoritative. What is licensed is GICS itself: the taxonomy is the exclusive property of S&P Global and MSCI, may not be redistributed, and company-level codes are sold through GICS Direct. So you do not license GICS — you *derive* membership from free ETF holdings, exactly the prospectus-over-blurb instinct: the sector SPDRs hand you GICS sector membership free and legal because you read the fund's *mandatory holdings disclosure*, its free output, not the licensed database behind it.

**Granularity fork (decided: sector-level first).** Sector-level resolution is free, clean, legally unambiguous, and already carries the inter-sector dispersion that catches things like AI-power (Tech × Utilities). Sub-industry resolution is where the *finest* dispersion lives — where "Interactive Media defected from Communication Services" is visible (that sector's five-year sub-industry returns span roughly −61% to +137%, a live intra-sector dispersion example) — but it is precisely the level that costs money or fidelity. So v1 runs the free sector grid, and sub-industry resolution is a later upgrade paid for only once the coarse grid proves it earns the spend. Honest limitation: below the sector level, free reproduction works only where an industry ETF happens to exist (semis, banks, biotech); the rest waits for that upgrade or a lower-fidelity free taxonomy.

**Velocity — there are three, and they are not equally worth measuring.**

| Velocity | What it is | Worth |
|---|---|---|
| Rate-of-change of price level | momentum | weak — the priced-in signal as a derivative |
| Rate-of-change of divergence | how fast a linkage is forming or breaking among peers | useful |
| Cross-stream lag | discourse-edge → rebalance → launch timing | the deep one — velocity *toward consensus* |

A *compressing* cross-stream lag is a thesis accelerating toward consensus; no price-velocity can see it. One signal-processing caution on all of them: differentiation amplifies noise, so a fast gauge is mostly noise and a slow gauge is mostly signal-but-late — which means velocity wants the same multi-timescale, agreement-is-the-signal treatment as the distances. Multi-scout reconciliation, on the time axis.

---

## §12 — The TEKX lesson, in the wild

The prospectus you grabbed at random is a three-fund document, and the third fund — TEKX, "Transformative Tech Accelerators" — is the datacenter × energy × AI × semis linkage *packaged into a single fund*, concentration industries listed as electrical equipment / oil & gas / semis / software. Your canonical known-shift test case, found by accident. Two lessons, both true:

1. **The launch stream is real and legible.** A consensus-formation event you can detect deterministically.
2. **The launch stream alone makes you late, and the chart proves the path matters more than the endpoint.** TEKX launched near $26, ran to ~$36 (the late-2024 peak), *fell into the low $20s by mid-2025* — below its launch price, a ~40% drawdown — then ran to $70. The +95% from that peak was capturable *only* by an investor whose sizing let them sit through a drawdown that took the position underwater — your "sized so a 50% drawdown can't force a sale" discipline, demonstrated on a fund you grabbed by accident.

**Correction to the earlier draft — the survivorship point applies to *buying*, not *watching*.** A prior version of this section called "+95% from the peak" survivorship, "not a property of buying launches" — and the caveat is right, but it aimed at a claim you never made. You are not *buying* launches; you are *watching* them as novelty events. Watching has no survivorship problem at all: you are not claiming the launched fund will win, you are reading the launch as information that *a thesis has become packageable* — true regardless of whether that particular fund goes on to 3x or quietly delist. The graveyard funds are as informative as the winners for this purpose: a launch that later dies still told you, at its moment, that someone with skin in the game believed the thesis had cohered. **The launch stream's value is the event, not the fund.** (The survivorship caveat still stands for the *separate*, downstream question of whether *owning* a launched fund pays — that is where sizing across a basket of maybe-winners matters, so the one that 3x's covers the graveyard. But that is the portfolio question, distinct from the generator's watching.)

This is where the two tools close the loop: the generator surfaces the thesis, you size it so the path cannot force you out, and the **detector's break-trigger** — not the price — tells you whether a drawdown is "buy the next tranche" (thesis intact, timing wrong) or "flatten, keep on the watchlist" (thesis broken). Same drawdown, opposite action. The generator's output becomes the detector's input at exactly this handoff.

---

## §13 — Decisions ledger (for fast review)

| # | Decision | Choice | Why it held |
|---|---|---|---|
| 1 | Corpus structure | ETF universe as a maintained ontology of theses | gives nodes, mandate, curator, boundary for free; separates new-edge from new-node detection |
| 2 | Universe growth | Auto-expand along holdings-graph edges, walled in skunkworks | curated universe is blind to the genuinely new by construction |
| 3 | Pre-filter | Intra-basket dispersion (bimodality) aims the expensive graph | cheap, no NLP; the inside-out shadow of edges forming to other baskets |
| 4 | Storage | Append-only event log; a lead is the fold | makes the system scoreable; late meaning is free; hindsight-resistant by construction |
| 5 | Event taxonomy | Closed envelope, open `type`, graceful fallback | freezes readability not vocabulary; unknown types are the highest-value signal |
| 6 | Human verdict | yes / no / watch, as append-only events | adjudication history in the record; memory prosthesis; makes you scoreable |
| 7 | Tag disagreement | Dual-write majority + novel, flag novel to bubble | blocking loses data; disagreement is the core signal; defers judgment to best-informed |
| 8 | Writers | Deterministic for numbers; LLM only for discourse | numbers can't surprise in kind; independence + falsifiability is the fabrication filter |
| 9 | Discourse anchor | Frozen thesis docs, not raw headlines | explicit curated baseline; novelty = linkage outside stated mandate |
| 10 | Baseline source | Prospectus (authoritative, freezable); blurb is skim only | HECO: a wrong baseline manufactures departure |
| 11 | Fund identity | Permanent SEC series ID / CIK, not ticker | HECO: tickers get reused and silently mis-bridge |
| 12 | Audit | Event-driven (on new filing), and audit = drift detection | one mechanism reads one diff; staleness check and `mandate-changed` are the same |
| 13 | Output | Text-only briefing, receipts inline; archive is the center | text can footnote itself; bind narrative to evidence |
| 14 | Skim ranking | By divergence-from-peers, not level | level is consensus-already-priced; divergence is where novelty is |
| 15 | Velocity | Cross-stream lag is the real gauge; price-ROC is weak | lag is velocity-toward-consensus, the system's novel output |
| 16 | v1 scope (Fork A) | Deterministic streams live + discourse captured, **not** interpreted; interpretation in v2 | build order mirrors the detector (deterministic A/A′ before agentic B); defer the fabrication-prone oracle-flooder, keep the cheap cadence backbone |
| 17 | Generator safety | Same-pipeline-is-the-wall: a lead earns a position only via the full per-thread discipline | converts habit back to structure; no shortcut for being interesting |
| 18 | Type minting | Falsifiable-artifact vote (reuse-prosecutors vs mint-justifiers); minting states a boundary; novelty escalates | a plain novelty vote is unfalsifiable and rubber-stamps shared hallucination; minting must be made expensive |
| 19 | Data sourcing | Free-only v1: returns via ETF-proxy prices, membership via EDGAR; GICS not licensed | derive membership from free holdings, not the licensed taxonomy |
| 20 | Coordinate system | etfdb categories as draft grid + rough membership; primary sources overwrite; sector-level first | draft decays into truth via verify; sub-industry deferred until it earns the spend |

---

## §14 — Open questions, for your review

**A. [RESOLVED] The cadence-vs-reactive fork for discourse.** v1 captures discourse on cadence without interpreting it; interpretation is deferred to v2. See §15 for the decision and its rationale.

**B. [largely resolved] Identity resolution placement.** The etfdb-draft → resolve-ticker-to-series-ID → verify-against-prospectus flow (§9) pins identity at the verify step, before the baseline is frozen. Residual is implementation: making the verify step *unskippable*, so nothing downstream is ever anchored to a bare ticker.

**C. Snapshot cadence** for the append-only fold (the performance mitigation). A real parameter; unset.

**D. Vocabulary-review cadence** — the *mechanism* is now settled (write-time falsifiable gate in §7; over-time recurrence review in §6), but *how often* the review runs is unset.

**E. Velocity timescales and residual-correlation method** — which windows, and how cleanly to strip the common market factor.

**F. Batch + caching economics** — confirm current numbers and whether they stack, before architecting around both.

**G. Name** — confirm or replace the §0 proposal.

**H. [new] Granularity upgrade trigger.** Sector-level is the v1 grid (§11). What concrete evidence would justify paying for sub-industry resolution? Name the bar now, so the upgrade is a decision rather than a drift.

---

## §15 — Fork A resolved: v1 scope and its rationale

Fork A — how the discourse stream relates to the deterministic ones — is resolved. **v1 runs the deterministic streams (N-PORT rebalancing + launch) fully live and adjudicated, *and* captures discourse cheaply on cadence, frozen and uninterpreted. v2 turns on discourse interpretation (the multi-agent scouting) once the oracle throughput is proven.**

Two independent arguments converged on this, and the fact that they *converged* rather than conflicted is the tell that it is right.

**The build-order argument (from a parallel read).** The detector was built deterministic-first: Banks A/A′ (regime gauges, look-through — no LLM) before the agentic scouts (B) before reconciliation (C) before OOD (D). The generator has the identical layering — rebalancing + launch are the A/A′ equivalent (curated, high-precision, deterministic, low-fabrication), and discourse interpretation is the Bank-B equivalent (agentic, LLM, high-fabrication). The discourse interpretation layer is simultaneously the noisiest, the most expensive, and the most fabrication-prone stream, which makes it the one that most floods the resource §4 names as the true bottleneck — the slow human oracle. For a v1 whose primary failure mode is overwhelming that oracle, starting with the deterministic core is not a compromise; it respects the throughput constraint the design itself identifies as the core risk. It also starts on a substrate the build already has: the SPDR family (TEKX, HECO, and the rest) is known, frozen-prospectus, series-ID-anchored, N-PORT-filing.

**The capture/interpretation split (the earlier insight).** The hard, deferrable part of the discourse stream is the *interpretation* — the expensive, fabrication-prone, oracle-flooding multi-agent scouting. Discourse *capture* is the opposite kind of thing entirely: cheap single-pass archiving of raw discourse on cadence, frozen and uninterpreted, touching the oracle *not at all* (nothing captured is surfaced until the interpreter exists in v2), with value that is *purely retrospective*.

**Why they reconcile instead of conflict — and why the naive reading is wrong.** A loose reading of "deterministic-only v1" would defer discourse *entirely*, capture included. That is the Lenski mistake (§5): with no v1 discourse archive, v2's interpreter can only run *forward*, and the whole v1 window becomes a permanent blind spot in the system's *earliest* signal, with nothing to thaw backward through. The backbone's entire point is that it was already running before you knew what mattered; a backbone you switch on only once you have a reason is not a backbone. Splitting capture from interpretation dissolves the apparent conflict: defer the expensive *interpreting* (build-order discipline satisfied) while running the cheap *capture* (cadence backbone preserved). The two recommendations were never actually in tension — the loose reading just bundled capture with interpretation, and once you unbundle them, both are satisfiable at once.

**Honest cost.** Capture is not free — the cadence searches are metered and storage accrues — so v1 carries a small standing capture bill (§10). But it adds *zero* oracle load, which is the one thing v1 must protect, so it does not endanger the v1 goal. It is a little money spent purely to keep the backbone running, which is the trade the whole project's ethos already endorses.

**The meta-pattern, which is the through-line of nearly every decision in this document:** *model normal and flag departure; let a cheap signal aim the expensive one; freeze the substrate and defer the interpretation; let the human ratify.* Prove-it-cheap, append-only, dispersion-aims-the-graph, envelope-and-open-type, capture-now-interpret-later, and now Fork A — all the same shape. The generator is that pattern applied outward, and v1 is its most disciplined possible first cut: the cheap, deterministic, low-fabrication core running live, the expensive interpreting layer dark but wired to receive, and the frozen backbone already accumulating the history v2 will read.

---

*Throughline: the generator is the detector's primitive pointed outward — same drift measure, same freezer, same reconciliation logic, opposite polarity, with a habit where the detector had a wall (now with one decisive part of that wall made structural). The brainstorm's work was mostly to find, fork by fork, that the right answer was almost always to split cheap-always-on from expensive-triggered and to refuse to let the present rewrite the past. v1 is that discipline made concrete: deterministic core live, interpretation deferred, backbone already freezing. It proposes; it never commits. It earns you a look, never a position.*
