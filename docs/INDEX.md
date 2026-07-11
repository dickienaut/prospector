# Prospector — documentation index

*The front door to the project's knowledge base. **Start here.** This is a map, not a document: it says what
each doc is, what it's for, and which revision is current. It is a **living file** — updated as docs land and
as canonical revs advance (the one doc that is continuously maintained rather than fossilized).*

---

## How this knowledge base works (read once)

**Three kinds of document, three lifetimes — do not confuse them:**

- **Contract / reference** — the standing law: the build spec, `CLAUDE.md`, the package READMEs, the founding
  document. **Amended, never regenerated** (CLAUDE.md rule): a rev applies surgical diffs + appends a
  changelog entry; unchanged text is preserved verbatim, so the contract never silently mutates. States the
  *current* contract; the change history lives in the changelog + the decision trail + git.
- **Decision records** (`docs/decisions/`) — dated, point-in-time **fossils, never rewritten.** The trail of
  *what was decided and why.* Chronological; the newest is not "the truth," the whole sequence is.
- **The state-of-project doc** — the **current rollup:** where the whole thing stands, in registers
  (built / queued / deferred / aspirational). Re-synthesized each rev; its stable conceptual body is carried
  forward, only its status rollup is rewritten.

The four seats (design / implementation / QA / git) coordinate **only** through git and these documents — a
cold-mounting seat re-derives from the artifact, never from another seat's reasoning. That is why the
knowledge base lives in the repo, not in a separate wiki: the docs must be where the seats read them.

---

## Cold-start reading order

1. **`CLAUDE.md`** — the constitution. Firewall, CONTRACT-vs-DEFAULT, append-only, no-run-now, identity, the
   standing human-ratified review items, and the amend-never-regenerate rule. Read first; it governs all.
2. **The state-of-project doc (current rev)** — where it stands *now*, and the roadmap. Orientation.
3. **The build spec (current rev)** — the CONTRACTs and defaults, section by section. Authoritative
   build instructions.
4. **`ARCHITECTURE.md`** — the module map, the spine, built-vs-deferred, the CLI table.
5. **The relevant decision record(s)** — for any slice you're touching, the dated doc that decided it.

---

## The catalog

### Law
- **`CLAUDE.md`** — repo constitution: the firewall (never read the detector's bucket / `portfolio.yaml`,
  never place/size/recommend a trade); CONTRACT-vs-DEFAULT; append-only events; no-run-now surfaces;
  series-ID identity; the verdict vocabulary; the standing human-ratified review items (the active-lead
  ceiling, the stress-gate aging monitor); the **amend-never-regenerate** doc rule. *Contract — amended only.*

### Where it stands
- **State-of-project — CURRENT: `project-prospector-state-of-project-rev7-2026-07-11.md`**
  (supersedes rev 6, rev 5). Status, registers, marching orders. *Rollup — re-synthesized each rev.*

### The build spec
- **CURRENT: `prospector-v1-spec-rev14-2026-07-08.md`** — *rev 15 pending* (the §9e / §8b / §10 CONTRACT
  fold). Section-numbered CONTRACTs + defaults; the IN / OUT scope; the milestones; **Appendix A** (LTEE
  archive port map) + **Appendix B** (proto-clusters, the v2 constituent-substrate design note).
  *Contract — amended only.*

### Origins & founding-era archive
*The pre-code thinking — the **"Thesis Generator" era** (Prospector's earlier name; the offensive twin of the
thesis smoke detector). Docs were spottier here, before the document discipline set in; kept for provenance.*
- **The founding document — `thesis-generator-founding-document.md`** — the founding brief: the premise, the
  consensus trap, novelty-not-quality, the reasoning the whole design rests on; the first experiment named at
  §11. *Contract-adjacent.*
- **The decisions review — `thesis-generator-decisions-review-2026-06-29.md`** — the concept-freeze companion:
  every choice the brainstorm settled + the reasoning that load-bears it + the open forks. The
  *what-we-decided-and-why-it-held* log to the founding doc's *why*.
- **The founding thread — `Prospector.pdf`** — the raw conversation transcript of the first ~2–3 days
  (primary-source archive / provenance; a **fossil capture**, not machine-parsed here — the repo carries no
  PDF toolchain by design).
- **Also archived (provenance, uncurated — exact lineage uncertain, kept in case we need it):**
  `project-prospector-overview-2026-07-02.md` (the research-note overview) ·
  `prospector-milestone3-gate-and-recalibration-brief.md` (the M3 acceptance + the authorized stress-gate
  recalibration, from the design thread — the brief behind `decisions/2026-07-02-stress-gate-recalibration.md`)
  · `generator-review-recommendations.md` (an external read of the decisions review) ·
  `bench-note-crowding-detection.md` (a **Protector-side** sensor-bank brief that vendors Prospector
  primitives — sibling-project, not v1) · `thesis-smoke-detector-design-brief.md` (the sibling brief Prospector
  twins) · the `Project Prospector … (rev 3).pdf` state-of-project snapshot.

### The decision trail — `docs/decisions/`
*Dated fossils, chronological, never rewritten. The full trail is the directory; the recent / load-bearing:*
- `2026-07-06-m5-runner-skeleton.md` — the §9 cadence runner.
- `2026-07-09-dispersion-vertical-9e.md` — dispersion wired live in shadow.
- `2026-07-10-9e-constituent-symbol-resolution.md` (+ `-build`) — the ENR foreign-ticker / CUSIP-key /
  membership-exclusion / honest-coverage fix.
- `2026-07-10-8b-board-snapshot-export.md` — the pure-read markdown board-snapshot + launch-panel legibility.
- `2026-07-10-10-email-sender.md` — §10, the volatile-message suppression fix, and the §8a advisory-posture
  CONTRACT (operational faults + live-lead advisories page; other advisories counted/surfaced, not paged).
- `2026-07-11-canonical-docs-amended-not-regenerated.md` — the constitution amendment this index embodies:
  canonical docs are **amended, never regenerated** (surgical diff + changelog + decision trail).
- *(earlier: crash-flags guidance, mandate-diff, launch-corroboration existence-proof, SOI-derived
  concentration, identity-integrity, remote-doc-consolidation + reindex.)*

### QA findings & build notes — in `docs/` (NOT `docs/decisions/`)
*A freely-authored working kind (per the CLAUDE.md amend-rule scope — not bound, not fossilized). The
load-bearing ones:*
- `email_nuisance_suppression_findings.md` + `PROSPECTOR_FAULT_SUPPRESSION_README.md` — the QA finding + the
  RED-first fix package for the volatile-message suppression bug.
- Build notes (`docs/2026-07-*-*-build-note.md`), `dispersion_foreign_ticker_findings.md`, the
  `PROSPECTOR_REGRESSION_TESTS*_README.md` set, and the Claude-Science reviews.

### Deferred / v2 — `docs/deferred/`
*Parked designs — captured, not queued (the aspirational register; walled off from v1 per the firewall).*
- `2026-07-04-idea-prospector-as-product.md` — Prospector-as-product: the v2 **proto-cluster / pseudo-ETF**
  direction (§1.9 / spec Appendix B), captured for when v1's dispersion substrate has accrued. Observation-
  only, price-only, cluster-never-single-name — same firewall class as the reading-list wall.
- `2026-07-04-idea-proto-cluster-detection.md` — detecting the theme *before* it packages: can pre-packaging
  co-movement be found **blind** (not just confirmed in hindsight), and is that a sellable feature? (The
  commercial turn on §1.9.)
- `idea-note-tunable-pattern-finder-2026-07-03.md` — the tunable pattern-finder: Prospector-as-a-product, the
  reframe underneath it, and the one thing that would make it real rather than dangerous. A what-if for later.

### Code-level docs — in the tree, next to what they describe
- **`ARCHITECTURE.md`** — module map, the three-part spine, built-vs-deferred, the CLI table, the conventions.
  *Contract-adjacent.*
- **Per-package READMEs** — `prospector/store/README.md`, `prospector/cli/README.md`, and the others under
  `prospector/*/README.md`: the local law for each package (store = append-only, five-field envelope, WAL
  index; cli = the four writers, no run-now; etc.). *Contract-adjacent — amended only.*

---

*Maintenance: update this index when a doc is added or a canonical rev advances. It is the map — and a map
that lags the territory is the exact failure mode the whole project fights.*
