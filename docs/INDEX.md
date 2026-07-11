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
- **Decision records** (`decisions/`) — dated, point-in-time **fossils, never rewritten.** The trail of
  *what was decided and why.* Chronological; the newest is not "the truth," the whole sequence is.
- **The state-of-project doc** — the **current rollup:** where the whole thing stands, in registers
  (built / queued / deferred / aspirational). Re-synthesized each rev; its stable conceptual body is carried
  forward, only its status rollup is rewritten.
- **Working notes** (`notes/`) — QA findings, reviews, build-notes, and slice-specs that later fold into a
  spec rev. **Freely authored, not bound** — the shop floor, not the contract.

The four seats (design / implementation / QA / git) coordinate **only** through git and these documents — a
cold-mounting seat re-derives from the artifact, never from another seat's reasoning. That is why the
knowledge base lives in the repo, not in a separate wiki: the docs must be where the seats read them.

---

## The folder map (the shape of `docs/`)

The **live docs sit at the `docs/` root**; everything else is grouped by kind. Nothing was renamed in the
reorg — only relocated (`docs/decisions/2026-07-11-docs-reorganization.md`).

```
docs/
  INDEX.md                                       ← you are here
  prospector-v1-spec-rev14-2026-07-08.md         ← CURRENT build spec
  project-prospector-state-of-project-rev7-2026-07-11.md   ← CURRENT status rollup
  decisions/   dated fossils — every load-bearing decision, chronological, never rewritten
  history/     superseded revs of the build spec + the state-of-project doc
  notes/       QA findings, reviews, build-notes, slice-specs, guidance, handoffs (freely authored)
  origins/     founding-era + sibling-project archive (provenance), incl. the PDFs
  deferred/    parked v2 designs — captured, not queued (walled off from v1)
```

**Advancing a canonical rev** is a fixed ritual: drop the new rev at the `docs/` root, `git mv` the superseded
one into `history/`, and update this index + the pointers in `CLAUDE.md` / `ARCHITECTURE.md`.

---

## Cold-start reading order

1. **`CLAUDE.md`** (repo root) — the constitution. Firewall, CONTRACT-vs-DEFAULT, append-only, no-run-now,
   identity, the standing human-ratified review items, and the amend-never-regenerate rule. Read first; it
   governs all.
2. **The state-of-project doc** (current rev, at the `docs/` root) — where it stands *now*, and the roadmap.
   Orientation.
3. **The build spec** (current rev, at the `docs/` root) — the CONTRACTs and defaults, section by section.
   Authoritative build instructions.
4. **`ARCHITECTURE.md`** (repo root) — the module map, the spine, built-vs-deferred, the CLI table.
5. **The relevant decision record(s)** in `decisions/` — for any slice you're touching, the dated doc that
   decided it.

---

## The catalog

### Law
- **`CLAUDE.md`** (repo root) — repo constitution: the firewall (never read the detector's bucket /
  `portfolio.yaml`, never place/size/recommend a trade); CONTRACT-vs-DEFAULT; append-only events; no-run-now
  surfaces; series-ID identity; the verdict vocabulary; the standing human-ratified review items (the
  active-lead ceiling, the stress-gate aging monitor); the **amend-never-regenerate** doc rule.
  *Contract — amended only.*

### The live docs (at the `docs/` root)
- **Build spec — CURRENT: `prospector-v1-spec-rev14-2026-07-08.md`** — *rev 15 pending* (the §9e / §8b / §10
  CONTRACT fold). Section-numbered CONTRACTs + defaults; the IN / OUT scope; the milestones; **Appendix A**
  (LTEE archive port map) + **Appendix B** (proto-clusters, the v2 constituent-substrate design note).
  *Contract — amended only.*
- **State-of-project — CURRENT: `project-prospector-state-of-project-rev7-2026-07-11.md`**
  (supersedes rev 6, rev 5). Status, registers, marching orders. *Rollup — re-synthesized each rev.*

### Superseded revs — `history/`
*The prior revs of the two rolling docs, carried for provenance. The current rev always lives at the root; the
whole series is the change-history.*
- Build spec: `prospector-v1-spec-rev1` through `rev13` (rev 14 is current, at the root). Revs 1 / 2 / 4 / 7 / 10
  were recovered 2026-07-11 from the design-thread archive.
  - **rev 1 — one doc, two names (by design).** The file is `history/prospector-v1-spec-rev1-2026-07-01.md`
    (its **series** name; content keeps the *"Generator v1"* title, as it predates the "Prospector" rename). It
    is **also known as `generator-v1-spec-2026-07-01.md`** — its **born** name, under which the pre-rename docs
    reference it: the `origins/` spec-punchlist, the rev 2 spec, and the archive-sort decision record. Those
    references were **not** rewritten (never change the past), so if you're chasing `generator-v1-spec`, this is
    the file — series identity in the filename, founding identity in the references.
- State-of-project: `project-prospector-state-of-project-{2026-07-02,rev2,rev3,rev4,rev5,rev6}-*.md`
  (rev 7 is current, at the root; note rev 1's filename carries no "rev").

### The decision trail — `decisions/`
*Dated fossils, chronological, never rewritten. The full trail is the directory; the recent / load-bearing:*
- `2026-07-11-docs-reorganization.md` — **this reorg**: the folder taxonomy + the certified content-preserving
  moves + the pointer amendments.
- `2026-07-11-canonical-docs-amended-not-regenerated.md` — canonical docs are **amended, never regenerated**
  (surgical diff + changelog + decision trail).
- `2026-07-10-10-email-sender.md` — §10, the volatile-message suppression fix, and the §8a advisory-posture
  CONTRACT (operational faults + live-lead advisories page; other advisories counted/surfaced, not paged).
- `2026-07-10-8b-board-snapshot-export.md` — the pure-read markdown board-snapshot + launch-panel legibility.
- `2026-07-10-9e-constituent-symbol-resolution.md` (+ `-build`) — the ENR foreign-ticker / CUSIP-key /
  membership-exclusion / honest-coverage fix.
- `2026-07-09-dispersion-vertical-9e.md` — dispersion wired live in shadow.
- `2026-07-06-m5-runner-skeleton.md` — the §9 cadence runner.
- *(earlier: crash-flags guidance, mandate-diff, launch-corroboration existence-proof, SOI-derived
  concentration, identity-integrity, remote-doc-consolidation + reindex.)*

### Working notes — `notes/`
*A freely-authored kind (per the CLAUDE.md amend-rule scope — not bound, not fossilized). The load-bearing:*
- **QA findings & reviews** — `prospector_full_review_claude_science.md` (fresh-eyes package review),
  `prospector_followup_review_2026-07-07.md` (live-cadence pass), `2026-07-07-live-cadence-qa-fixes.md`
  (the ordered fix plan), `2026-07-04-soi-slice-design-review.md` (design-thread review of the SOI slice),
  `email_nuisance_suppression_findings.md` + `PROSPECTOR_FAULT_SUPPRESSION_README.md`
  (the volatile-message suppression bug + RED-first fix), `dispersion_foreign_ticker_findings.md` (the §9e
  ticker-anchor finding), the `PROSPECTOR_REGRESSION_TESTS*_README.md` set (N1–N10 regression tests).
- **Slice-specs & build-notes** (interim, fold into a future spec rev) —
  `2026-07-04-soi-derived-sector-concentration.md` (SOI resolver design; the *design half* of the
  same-named `decisions/` pair — kept distinct, not a duplicate), `prospector-m5-runner-spec-2026-07-05.md`,
  `2026-07-10-8b-dashboard-board-snapshot-export.md`, `2026-07-04-rev13-rev4-fold-for-claude-code.md` (the
  doc-fold instruction for the SOI slice), and the `2026-07-*-*-build-note.md` set (§9e dispersion ×2,
  §10 email-sender).
- **Dev / CI** — `note-github-test-gating.md` + `2026-07-11-ci-branch-protection-setup.md` (gate `main` on a
  green test suite — make the discipline structural).
- **Guidance & handoff** — `prospector-crash-flags-guidance-rev2-2026-07-02.md` (+ the superseded
  `...-diagnostic-guidance-2026-07-02.md`) — the March-2020 crash-flag diagnostic + its resolved Box-B
  outcome; `prospector-thread-handoff-2026-07-08.md` — a point-in-time cold-start snapshot (now stale).

### Origins & sibling-project archive — `origins/`
*The pre-code thinking — the **"Thesis Generator" era** (Prospector's earlier name) — plus sibling-project
briefs and the foundational reading. Docs were spottier here, before the document discipline set in; kept for
provenance. Several were recovered 2026-07-11 from the design-thread archive.*
- **Founding & concept** — `thesis-generator-founding-document.md` (the founding brief: premise, consensus
  trap, novelty-not-quality — the reasoning the whole design rests on, first experiment at §11);
  `concept-freeze-2026-06-28.md` (the earliest skunkworks concept snapshot); `two-instruments-for-a-long-horizon.md`
  + `yin-yang-monitoring-system-overview.md` (the offensive/defensive twin philosophy);
  `systems-failure-and-portfolio-resilience-synthesis.md` (the resilience **base-case** — the foundational
  reading the design answers to); `skunkworks-ledger.md` (the founding "experiment freezer" ledger — one
  door out to production); **`2026-07-11-recursive-spine.md`** (retrospective synthesis — the project's one
  axiom, *preserve the primary record*, applied self-similarly at every layer; why the whole is fractal, and
  bounded by the human-in-the-loop). *Contract-adjacent.*
- **Founding-era decisions & reviews** — `thesis-generator-decisions-review-2026-06-29.md` + its rev 2
  `...-2026-07-01.md` (the concept-freeze log); the outside reviews — `thesis-generator-outside-read.md`,
  `prospector-v1-spec-punchlist.md`, `generator-review-recommendations.md`. *(The founding build spec itself is
  now `history/prospector-v1-spec-rev1-2026-07-01.md` — rev 1, the pre-rename "Generator v1" spec.)*
- **Provenance (uncurated)** — `project-prospector-overview-2026-07-02.md` (research-note overview),
  `prospector-milestone3-gate-and-recalibration-brief.md` (the M3 acceptance + the authorized stress-gate
  recalibration).
- **Sibling-project (the Thesis Smoke Detector — the defensive twin)** — `thesis-smoke-detector-design-brief.md`,
  `...-decisions-review-2026-06-29.md`, `...-one-pager.md`, `...-technical-overview.md`;
  `bench-note-crowding-detection.md` (a Protector-side sensor-bank brief that vendors Prospector primitives);
  `rho-G-hawkes-criticality-subsystem-design-theory.md` (the sibling's unbuilt criticality-subsystem theory —
  restored 2026-07-11).
- **The PDFs** — `Prospector.pdf` (the founding-thread transcript) and `Project Prospector … (rev 3).pdf`
  (an early state-of-project snapshot) — fossil captures, not machine-parsed. Plus `Systemic Fragility in
  Global Supply Chains.pdf` — **foundational reading** (the supply-chain fragility research that seeded the
  project's thinking; the worked-examples companion to `systems-failure-and-portfolio-resilience-synthesis.md`).

### Deferred / v2 — `deferred/`
*Parked designs — captured, not queued (the aspirational register; walled off from v1 per the firewall).*
- `2026-07-04-idea-prospector-as-product.md` — the v2 **proto-cluster / pseudo-ETF** direction (§1.9 / spec
  Appendix B). Observation-only, price-only, cluster-never-single-name — same firewall class as the
  reading-list wall.
- `2026-07-04-idea-proto-cluster-detection.md` — detecting the theme *before* it packages: can pre-packaging
  co-movement be found **blind**, and is that a sellable feature?
- `idea-note-tunable-pattern-finder-2026-07-03.md` — the tunable pattern-finder: Prospector-as-a-product, and
  the one thing that would make it real rather than dangerous.

### Code-level docs — in the tree, next to what they describe
- **`ARCHITECTURE.md`** (repo root) — module map, the three-part spine, built-vs-deferred, the CLI table, the
  conventions. *Contract-adjacent.*
- **Per-package READMEs** — `prospector/store/README.md`, `prospector/cli/README.md`, and the others under
  `prospector/*/README.md`: the local law for each package. *Contract-adjacent — amended only.*

---

*Maintenance: update this index when a doc is added, moved, or a canonical rev advances. It is the map — and a
map that lags the territory is the exact failure mode the whole project fights.*
