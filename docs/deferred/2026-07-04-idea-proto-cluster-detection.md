# Idea — detecting the theme before it packages (proto-cluster, the commercial turn)

**What this is:** an idea document to sit with — not a spec, not a decision, nothing to build yet. It pulls the §1.9 proto-cluster / pseudo-ETF direction out of the roadmap and points it at two questions that only surfaced once the *commercial* framing did: (1) can the pre-packaging co-movement be detected blind — not just confirmed in hindsight — and (2) is "surface the theme before it's packaged" a sellable feature for users whose rules aren't the owner's. Connects to §1.4, §1.5, §1.9, §2.4, §2.9, §3.2.

## 1. The core idea, and the turn that makes it new

§1.9 already states it: a thesis no one has packaged and no one is loudly discussing is still visible in the substrate, as a cluster of names co-moving across the existing sector boundaries — a pseudo-ETF you construct yourself, the earliest possible T0 for the cross-stream lag. The roadmap files this under v2 and observation-only, because for a 17-year owner the disciplined move is to detect at T0 and act late, through the wall, when a clean instrument exists — the horizon (§1.3) makes that timing gap costless, so there is no reason to hold a hand-built single-name basket.

The turn: a commercial version of this app would serve users who are not 17-year owners. For a shorter-horizon user who explicitly wants early single-name exposure, "here is the theme forming, months before anyone packages it" is a genuine value proposition, not a discipline violation. So the owner's rule (own industries via rules-based ETFs, never pick winners) gets bracketed for the product context — it stays true for the owner personally, but it is a user preference, not a law of the tool. Once bracketed, the question stops being "should I act early" (settled) and becomes "is the signal real, early, and detectable — enough to sell honestly."

## 2. Why it should be there (the structural claim, not a hope)

This is not wishful. §1.5's whole premise requires it: launches are near-consensus by construction, so the underlying names syncing up must predate the packaging almost by definition. If the co-movement did not lead the launch, the cross-stream-lag thesis the entire tool rests on would be false. NUKZ (2023 nuclear+AI, before the fund existed) is therefore the worked proof of a structural claim, not a lucky anecdote. So the honest question is not "is it possible" — the thesis says it is — but characterize it: how much lead time, how much the lead varies across themes, and the load-bearing one — is the cluster detectable blind (no membership handed to you), or only obvious once you already know who ended up in the basket. Those are different questions, and only the second one is a product.

## 3. From lookup to program — the instrument already exists

The tool to characterize it is one that is already built and validated: the β-strip (§3.2, proven to remove the common market factor) plus the dispersion Q (§2.4), pointed at a constructed basket and run backward in time. The launch date is the timestamp; the onset of the basket's excess residual-correlation departure is T0; the gap between them is the lead. Run it over a set of themes and you get a distribution of leads, which is the thing a product claim would rest on. It is a program, not a lookup, because of three traps — and the traps are what separate an honest feature from an overfit demo.

## 4. The three traps (the intellectual crux — get these wrong and you fool yourself)

1. **Survivorship / look-ahead — the big one, and §1.9/§2.9 already flag it.** Taking an ETF's launch holdings and correlating them backward uses knowledge of who ended up in the basket. The names that co-moved and then got acquired or delisted before launch are not in your list, and hand-picking a coherent set inflates the correlation you measure. So a retrospective probe answers "was the co-movement there?" (cheap, hindsight-assisted — a fine first look) but not "could you have found it blind?" (the product claim — unsupervised clustering on a survivorship-clean universe, with no membership given). Only the second question validates anything sellable.
2. **Market-factor leakage.** Any basket co-moves in a rally. Measure excess co-movement (β stripped), never raw — this is exactly what §3.2 established for the pair sensor, applied one level down.
3. **Base rate / control.** A hindsight-picked coherent basket almost always shows rising correlation. You need a control — random same-sector baskets of the same size — to show the theme basket's excess co-movement beats chance. Without it you will see clusters everywhere, which is the false-discovery problem (§1.6's over-firing) surfacing in the substrate.

## 5. The commercial angle raises the bar rather than lowering it

Marketing "we'd have caught nuclear+AI in 2022" on a hindsight backtest is precisely the overfit-marketing trap this whole project was built to avoid — and sophisticated users, or a regulator, will see through a survivorship-inflated claim fast. An honest product claim needs the blind, survivorship-clean version, which is the same v2-hard problem §1.9 names. The feature is real and sellable; the credible version of it is the harder one. Worth stating plainly because it inverts the usual intuition: the commercial motive does not let you cut the corner, it is the reason you can't.

## 6. Candidate themes to study (varied lead times and legibility)

A spread chosen so the distribution of leads is visible, not a single point:

- **Uranium miners** — the 2021 Sprott physical-trust squeeze; synced hard well before the junior-uranium / nuclear funds packaged it.
- **Generative-AI infrastructure** — post-ChatGPT, synced through 2023 ahead of the gen-AI ETF wave; a short, sharp lead.
- **GLP-1 / obesity** — Lilly and Novo running together from mid-2023, roughly a year before the obesity ETFs.
- **Bitcoin miners** — RIOT / CLSK / CORE / CIFR co-moving through 2023–24 before the digital-asset funds; already sitting in your own holdings data, so the cheapest to probe.
- **Quantum** — a recent, violent sync-up run, recent enough to be a near-live test. (Confirm the specifics — that one is at the edge of what is safe to assert from memory.)

Each is a different lead-time regime, which is the point — a feature you can sell needs the lead to be reliably present, not present in one flattering case.

## 7. Where it sits relative to the current build

Still v2, downstream of a calibrated dispersion sensor and survivorship-clean data (the gating dependency — §2.9; and note it is worse for exactly this layer, since the acquired winners vanish from the survivor set precisely when their thesis was real). But it is not a from-scratch build: it is the existing β-strip and dispersion Q run backward over constructed baskets, plus a random-basket control. And the generous dispersion payload (§2.4) is already banking the substrate a live version would consume — the current build's only job toward this was to capture richly, and it is doing it.

## 8. Prior art — what exists, and where the white space is

The lay of the land is four layers, three of which are mature. It matters because it tells you exactly which parts are settled (stand on them) and where the genuine open ground is.

**Layer 1 — finding price-correlation clusters that cross sector lines.** Foundational and decades deep, from Mantegna's correlation-based trees through a large network-science literature. The recurring empirical result *is* your §1.9 premise: price-derived groupings differ from the standard sector classification, and a stock can be influenced by sectors outside its own primary classification. The standard method is community detection with a modularity quality index Q — literally your dispersion Q — and its statistical significance is established by comparing the observed Q against a null-model expectation via permutation testing. That is the base-rate control from trap 3; here it is not a gap you invent but standard practice. Your §2.4 sensor already lives inside this layer.

**Layer 2 — detecting a cluster forming or reconfiguring over time.** Also active, and where the directly useful tools live. There is dynamic/temporal community detection that tracks how clusters change month to month and flags regime shifts, and a deep change-point-detection literature on correlation matrices — online methods tracking correlation on a Riemannian manifold with CUSUM, offline libraries, and, most relevant to you, a very recent entropy-based indicator built specifically because the plain Frobenius norm of correlation-matrix differences is insensitive to reconfigurations of cluster membership (groups reorganizing without much change in overall correlation strength). A new theme coalescing is exactly a membership reconfiguration, so that is nearly the detector you would want, off the shelf. The cleanest existence-proof that emergence-forecasting works at all is from biomedical text, not markets: a temporal-network + community-detection + link-prediction pipeline flagged an emerging COVID theme months early, with link prediction validated at AUC 0.87. Same machine, different substrate.

**Layer 3 — the productized version, and the tell.** Emerging-theme detection is very much a commercial product — but the big shops build it from text, not price co-movement. BlackRock/iShares runs an AI thematic-rotation fund (THRO); their described process seeds a basket from existing sell-side baskets and thematic funds, tracking stocks brokers and PMs have already identified, then uses NLP on news and earnings calls to quantify a theme's attention and lifespan. Bloomberg sells correlation-based regime detection (MAC3). The academic thematic-NLP area is hot — THEME, SETN, SimStock, and NLP-on-10-K AI indices that reportedly outperform existing AI-themed ETFs. But notice where all of it operates: downstream of packaging and discourse. BlackRock literally seeds from sell-side baskets and existing thematic funds — it reads what has already been identified, which is §1.2's adversely-selected territory. That the best-resourced quant shops went text-first is a real signal: for identifying a theme, text is the richer, earlier channel (a broker publishes a basket before prices fully sync), so price co-movement is more confirmation than discovery.

**The gap.** The specific §1.9 framing — price-only, unsupervised, cluster-emergence measured as a survivorship-clean lead over the eventual packaging — is where there is no clean product or paper. The components are all mature; the assembly and the lead-as-measured-object are the open part, which is exactly what §1.8 already claims. Two honest reads: the encouraging one is that nearly everything you need exists and is battle-tested, including established survivorship handling (rolling out-of-sample validation and Adjusted Rand Index for cluster stability), so the traps have known methodology rather than just warnings. The sobering one is that the price-only route being later and noisier than text for theme identification is probably why it is unclaimed — it may be the deterministic floor rather than the edge, which is precisely how §1.9 frames it. The price substrate's real advantages: cheap, deterministic, no NLP, and it can catch a covey syncing before anyone writes about it — the genuine pre-discourse T0 — at the cost of more false clusters to filter.

Underneath all of it, the thematic-critique literature keeps confirming the thing that makes early detection worth more than early action: thematic portfolios show high concentration, elevated turnover, and returns strongly correlated with investor flows rather than structural growth (the Ben-David finding, restated across multiple papers). The value is in seeing it early and vetting it cold, not in owning the packaged product late.

**Key references (to chase down):**
- Mantegna (1999); Onnela, Bonanno, Tumminello et al. — correlation-based networks and hierarchical clustering of equity returns; the finding that price clusters cross sector lines.
- Community detection with modularity Q and null-model permutation significance (e.g. the 88-year multilayer-network study, *Applied Network Science*, 2019) — the base-rate control made rigorous.
- Dynamic community detection: DynMSA (dynamic modularity-spectral) with Adjusted Rand Index for cluster stability over time.
- Change-point detection on correlation matrices: the `ruptures` library (offline); RIO-CPD (online, Riemannian geometry + CUSUM); a 2026 entropy-based indicator targeting cluster-membership reconfiguration specifically.
- Kritzman & Li, "Financial Turbulence" / absorption ratio — already in the stress-gate lineage (§2.5).
- Emergence-forecasting proof-of-concept (biomedical): temporal word-embedding network + community detection + link prediction on COVID literature; link-prediction AUC 0.87.
- Commercial: iShares THRO (AI thematic rotation); BlackRock systematic thematic NLP; Bloomberg MAC3 (correlation-based regime detection).
- Academic thematic-NLP: THEME (CIKM 2025), SETN, SimStock; NLP-on-10-K AI stock indices.
- Ben-David, Franzoni, Kim & Moussawi (2023), "Competition for Attention in the ETF Space" — already cited in §1.8; plus the broader finding that thematic-ETF returns track investor flows.
- López de Prado — Hierarchical Risk Parity and *Machine Learning for Asset Managers* — the practitioner bridge for the clustering-to-portfolio step (from general knowledge, not the search).

## 9. Open questions — the part to sit with

- **What is the minimum viable honest claim?** "Co-movement was present before packaging" (retrospective, hindsight-assisted) versus "detectable without being told the membership" (blind). The first is easy and nearly true by §1.5; the second is the real product and the hard one. Is there a middle — blind detection with a generous false-positive rate, sold as a watchlist rather than a signal?
- **What lead-time distribution makes it sellable?** A lead reliably beyond some months across themes is a product; a lead that is huge for nuclear and negative for the next theme is a demo. The distribution is the feature.
- **The curation problem (what the wrapper was really for).** A proto-basket's membership churns as the thesis forms. A commercial proto-ETF product has to either re-decide membership on a live, mostly-false-positive signal (operationally heavy, the noisy-desk problem) or freeze a T0 snapshot (a worse-curated guess than the eventual fund, since early co-movers are rarely the eventual winners). Fractional shares solve diversification but not maintenance — so how the product keeps the basket honest over time is the genuinely unsolved design question, and it is the thing §1.4's "professional curator continuously updating the thesis" was actually providing.
- **Who is the user, exactly?** Horizon and rules determine whether early single-name exposure is a feature or a footgun. A different user profile might want the watchlist (names to research) rather than a basket (names to hold) — which sidesteps the curation problem entirely and might be the better product.
- **The false-discovery rate is the product's precision.** How many spurious clusters per real one? That number, not the nuclear success, is what a serious buyer would ask for — and it is unmeasurable without the survivorship-clean base-rate work.
- **Regulatory / marketing surface.** What can you claim without a survivorship-clean backtest behind it — and does the honest claim ("a research watchlist of forming themes," not "a signal that beats the market") change the product you would build?

## 10. Two ways to start looking (whenever, not now)

- **A proto-cluster backtest harness** — construct a basket, strip β, roll the within-basket residual correlation and dispersion Q, mark the launch date, read the lead, with the random-basket control built in. Runs on real price data on your Mac (a sandbox can't reach market-data feeds). This answers the retrospective question cleanly and is the honest first step before the blind version.
- **A quick qualitative first-look** — a search pass over one or two themes to eyeball whether the lead is visibly there before bothering to quantify it.

Neither is urgent, and neither commits anything. The first is the real instrument; the second is a five-minute gut-check. The blind, survivorship-clean version — the one that would actually back a product claim — is a larger piece of work and is genuinely the hard problem §1.9 has been pointing at all along.
