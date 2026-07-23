# Project Prospector — repo constitution

This repo is **Project Prospector**, the offensive twin of the thesis smoke detector. It watches
the ETF universe for structural novelty and proposes **reading, never orders**.

The canonical spec is `docs/spec.md`; **read its header for the current rev**, earlier revs in
`docs/history/`. Read it before changing anything load-bearing. (The spec names its own rev; this file names
no rev number, so the pointer cannot drift — the CONTRACTs the old rev-narrative summarized all live in the
spec: the §9-runner mandate-prior-from-the-frozen-blob invariant, forward-hash routing, `sectors_unresolved`,
the registrant-level `prospectus_accession` residual, the frozen GICS industry→sector rollup.)

**How to read this file.** *Operative rules live here · the **why** is in `METHOD.md` · the full **contract**
is the spec (`docs/spec.md`) · past **scars** are `docs/bugs/` · **on any disagreement, this file wins** (and
the disagreeing doc is the bug).* Sections: **Firewall · CONTRACT vs DEFAULT · Enforcement tiers · The record ·
Vendored store provenance · No LLM text as data · No run-now surfaces · Fund identity · Config honesty · Alert
posture · Standing review items · The seats · Verification · Development · Fixture provenance · Documentation.**
(No index-of-every-NEVER by design — it would either restate the imperatives, a second home, or rot into a
maintenance-cost pointer list.)

## Firewall
- Never add code that reads the detector's bucket or `portfolio.yaml`.
- Never add a code path that places, sizes, or recommends a trade.
- The only connection to the portfolio system is human and one-way (a lead graduates by hand).

## CONTRACT vs DEFAULT
Items marked CONTRACT in `docs/` specs change only via the design thread (chat with the owner), never
unilaterally in implementation. DEFAULTs are config in `config/prospector.yaml` — change freely. **The full
CONTRACT text is the spec**; this section **indexes the design-thread-ratified amendments** under
`docs/decisions/` — the operative constraint + its record, the narrative left in the record:
- **Stress gate** — frozen at absolute **0.85** (crisis-only); fix its aging by human recalibration, **never**
  a rolling percentile (the baseline-relative failure it diagnosed) — `2026-07-02-stress-gate-recalibration.md`.
- **Verdict vocabulary (§5/§8c)** — four values, three live meanings (`yes` · `watch` · `off-thesis-real` ·
  `noise`); **never** file a live tech lead as macro (`off-thesis-real` ≠ `watch`). `VERDICT_VOCAB` in
  `fold/fold.py` is the single source — `2026-07-02-crash-flags-guidance-rev2.md`.
- **Dispersion payload (§4b)** — `dispersion.tick` carries **full membership + each name's sub-cluster +
  correlation structure** (you cannot backfill a payload you did not capture). The v2 proto-cluster wall (not
  built): **price-only** · the canary is a **cluster, never a single name** · **observation-only — the canary
  is never the trade** — `2026-07-03-dispersion-payload-generous.md`.
- **Rebalance routing (§4d)** — an **accretion** sensor (no Schmitt, no lead of its own). Forward-hash
  memberships via `xcorr_lead_id`/`dispersion_lead_id`; **never** add series_ids to a lead payload (the lead-id
  encodes them — duplication invites drift). Read active leads from the **registry-materialized fold**, never a
  separate cache — `2026-07-03-rebalance-accretion-and-routing.md`.
- **Mandate-diff (§4d)** — diff the **principal-investment-strategy section only**, **never** the whole filing
  (a full-text diff is a false-positive machine — the diff-trap); `mandate.changed` is a silent corroboration;
  extraction-unreliable → `fault`, **never** a false change. Boundary: **bs4 owns structure, our code owns
  meaning, the human owns significance** (`beautifulsoup4==4.15.0`, pinned) —
  `2026-07-03-mandate-diff-targeted-section.md`.
- **Launch corroboration (§4c)** — a launch's sectors derive from its **first holdings**; a both-sides overlap
  **accretes**, **never spawns** a ceiling lead. The v1 live lag is an **existence proof, not a rate**
  (holdings-unavailable → dormant — flag the blind spot, never guess). **Anti-fitting:** a dormant real outcome
  **NEVER** lowers `corroboration.sector_min_weight` — `2026-07-03-launch-corroboration-existence-proof.md`,
  `2026-07-04-real-holdings-xlsx-and-blank-sectors.md`.
- **SOI sector concentration (§4c resolver)** — the EDGAR SOI carries the GICS grouping; roll industry→sector
  through a **frozen table** (re-freeze only on a GICS structure revision, **never** a knob); no ticker
  classifier, no third-party feed (the primary-source wall). Extraction-unreliable → `fault`, **never** a wrong
  sector set; multi-fund NPORT-EX requires fund-block isolation — `2026-07-04-soi-derived-sector-concentration.md`.

## Enforcement tiers
The firewall and its neighbours are stated with their **true tier**, so no clause reads as stronger than it is
(the honest-ledger discipline, `METHOD.md` rule 3):

| clause | enforcement (verified) | tier |
|---|---|---|
| never read `portfolio.yaml` | AST **package-wide sweep** over `prospector/**` (`test_firewall.py`) | **mechanism** |
| never read the detector's bucket | **S3-client-confinement proxy** — only `store/s3_sync.py` may construct an S3 client (import-root sweep over `boto3`/`botocore`/`s3transfer`, `test_firewall.py`) | **mechanism (proxy, named gaps)** |
| never place / size a trade | capability absence — no broker credentials, no reachable portfolio | **mechanism-adjacent** |
| never **recommend** a trade | nothing — you cannot test the absence of a recommendation | **prose — the clause closest to the real risk** |

The detector-bucket check is a **proxy with named gaps**, not a capability wall: an import-root sweep cannot
catch a bare bucket-name string with no import, nor a client reached through a not-yet-enumerated dependency.
The **bucket name is deliberately absent from this repo**, so there is nothing to grep — the real wall is
**IAM, outside CI**; this gate is the cheap in-repo tripwire under it. Also **mechanism**: offline-tests /
network-guard, append-only (write-path validators), ticker-rejection-at-write, tag-only deploy. **Prose by
design** (the human is the only mover): no-run-now, no-auto-tune. **Assumed, unguarded:** `config.changed`
strict ordering has no ordering test — do not state it as mechanism until one exists.

## The record
The append-only discipline, in three forms — nothing (data, docs, or history) silently rewrites the past.

### Append-only (the fossil store)
- Nothing under `events/` is ever edited or deleted. Corrections are new events.
- A changed mind is a new `verdict` event that supersedes via `superseded_by`, never an edit.
- Backtests write **only** under `backtest/` (separate store root + registry per run).

### Canonical documents — amended, never regenerated
The doc-process form of Append-only: never let the present silently rewrite the past. **Canonical
contract/reference documents are amended, never regenerated.** The build spec, this file (the constitution),
the package READMEs, and the founding document change by **surgical diff — altering only the clauses a
recorded decision changed — plus a changelog note of the delta and its decision-record.** All other text is
preserved verbatim. A **wholesale rewrite is forbidden**: regenerating such a document silently drifts
contract text no one decided to change, and the drift is invisible precisely because there is no diff to
check. A clause is **superseded in place with the change recorded** (changelog + decision trail + git), never
silently dropped — the document states the *current* contract, but *every* change is traceable.
- **Two document kinds, two rules.** The **state-of-project doc** is the partial exception: its stable
  conceptual body (**Parts I–IV**) follows the amend rule (carried forward, not rewritten), but its
  current-status rollup (**Part V**) is **re-synthesized each rev** — it is a snapshot of *now*, not a
  contract. (Rev 7 carried I–IV verbatim and rewrote Part V; the spec took amendments — correctly.)
- **The escape valve (so patchwork can't trap you).** A cleanup **rewrite is allowed only as an explicit
  consolidation rev**, and only with a **clause-by-clause diff proving no contract changed except the ones
  intended**, recorded in that rev's decision record. The forbidden thing was never *rewrite*; it is *rewrite
  unchecked* — make the check mandatory and the drift can't hide.
- **Scope.** Bound: the enumerated canonical set above (+ the state-of-project Parts I–IV). NOT bound (freely
  authored): working notes, build notes, QA findings, session logs — and the **decision records themselves**,
  which are append-only (a changed decision is a *new* record superseding, never an edit — the immutable trail
  this rule points to).
- **The check (build seat).** Before writing a canonical doc: diff against the prior version and confirm every
  changed clause traces to a decision record. Ratified with the design thread:
  `docs/decisions/2026-07-11-canonical-docs-amended-not-regenerated.md`. (This rule was itself added by
  surgical amendment — fittingly.)

### Doc naming — provenance in the filename
Every doc is **born with a leading ISO date** (`YYYY-MM-DD-…`) so versions are tellable apart at a glance — the
date orders it and never changes. This mostly formalizes existing practice (decision records are dated; the spec
and state doc carry date + rev). The rule is deliberately narrow in three ways:
- **Rev only where it versions.** A `-revN` suffix is added **only** where the doc is one of a versioned series
  (a decision revisited as rev 2+; and the superseded spec/state revs already fossilized in `history/`). A
  rev-bump of such a fossil series is a **new dated file, the prior moved to `history/`** — never a
  rename-in-place. Date is universal; a `-rev1` on a one-shot fossil (a QA finding that will only ever be rev 1)
  is just noise. **The *live* build spec and state-of-project doc are not in this class** — they are amended in
  place under stable names (next bullet); filing them as a dated series was a misclassification, corrected
  2026-07-17.
- **Stable-named exceptions — because they are amended in place.** `CLAUDE.md`, `INDEX.md`, `ARCHITECTURE.md`,
  the **build spec (`docs/spec.md`)**, the **state-of-project doc (`docs/state.md`)**, the package `README`s, and
  `LICENSE` keep fixed names: they are the always-current single instance, amended in place per
  amend-never-regenerate, their history in git + changelog — not re-fossilized as a dated series; the rev they
  carry lives in the **header** (a content claim, one home), never the filename. The distinction is principled,
  the same one that governs how each kind changes: **stable-named = amended-in-place single instance; dated =
  point-in-time or versioned.** The spec and state doc belong here *by their own rule*: amend-never-regenerate
  already governs them (surgical diff, everything else verbatim) — which **is** the amended-in-place contract, so
  filing them as a dated series was the misclassification corrected 2026-07-17
  (`docs/decisions/2026-07-17-rolling-docs-stable-named.md`).
- **Forward-only — the load-bearing clause.** This governs **new** files (born dated); **existing filenames are
  never bulk-renamed.** The reorg's insight was *relocate, never rename* — references point at filenames, so
  byte-identical names keep ~99% of them resolvable by search; a bulk rename would break exactly those and
  *multiply* the un-fixable fossil drift the reorg recorded as its one cost (a decision record is immutable — it
  cannot be edited to point at a renamed file). The escape valve mirrors amend-never-regenerate's: a **specific**
  legacy misnamed doc may be normalized as a deliberate, **reference-checked one-off** (grep its references, fix
  the fixable, document any fossil drift — the same shape as the reorg), **never a bulk rename.**
- Ratified with the design thread: `docs/decisions/2026-07-11-doc-naming-convention.md`; the live-spec/state
  reclassification (stable-named, amended in place — `docs/spec.md`, `docs/state.md`) added 2026-07-17,
  `docs/decisions/2026-07-17-rolling-docs-stable-named.md`.

## Vendored store provenance
The store/registry primitives in `prospector/primitives/` are ported from
`prophit_skunkworks/ltee_archive/` (snapshot dated 2026-03-29, vendored 2026-07-02) with the
trading ontology stripped and the schema inverted to envelope + JSON-payload.
- Keep the provenance headers.
- Do not re-introduce wide typed-metric columns to the events table.
- Do not import anything from the sibling repo's `models/` (capacity and opacity — forbidden).

## No LLM text as data (v1)
No model-generated prose is ever persisted as record content. Capture (milestone 6) stores raw
search-result blocks and fetched page text only.

## No run-now surfaces
No commands, buttons, or endpoints that trigger recompute or capture on demand. Record on cadence;
push on state change. No dashboard autorefresh. (`pros store reindex` rebuilds the index from the
fossil record — it computes nothing new, so it is repair, not run-now.)

## Fund identity
Every fund keys on its SEC series ID (S######). A bare ticker is rejected at the write path.
Failed resolutions go to the retry-then-manual queue, never silently dropped. Tickers are
display-only attributes. (The **machine-account** identity — the bot seats vs the human — is the
`## The seats` + `## Development` merge-gate, not this fund-key rule.)

## Config honesty
On every run the config is hashed; a change emits `config.changed` with the diff **before** any
sensor runs.

## Alert posture
Hard cadence floor (weekly heartbeat), state-change-only push, read-only surfaces, no execution.
Silence beyond 7 days unambiguously means broken. No auto-tune of thresholds, ever — the
active-lead ceiling is a tripwire for human recalibration.

## Standing review items (human-ratified, never auto-tuned)
Some thresholds are reviewed on a cadence and moved only by deliberate human recalibration that
leaves a `config.changed` fossil — never by a self-updating rule:
- **Active-lead ceiling** (§8a) — a tripwire for human recalibration of sensor sensitivity.
- **Stress-gate aging monitor** (§4a) — the backtest reports the recent-window **calm-regime** p95
  (non-crisis days) and its headroom to the frozen absolute gate. If the margin compresses,
  re-freeze the level higher by hand. **Never** a rolling percentile / self-updating window — that
  reintroduces the baseline-relative failure the recalibration diagnosed.
- **Macro catalog** (`off-thesis-real` verdicts) — a read-only reference layer of real-but-off-thesis
  (macro/sector) classifications, consulted by the human when adjudicating elsewhere. **Read-only
  context, NEVER a trade/tilt trigger, never piped anywhere as actionable, and never a macro-regime
  alert stream / "regime forming" push / monitoring surface** (same class of rule as the reading-list
  wall). The cap-weighted core already absorbs sector regimes; the correct action on a detected macro
  regime is none. The sensor also never strips the macro regime out (no multi-factor β — it is
  entangled with real tech theses; stripping it would delete real signal). See
  `docs/decisions/2026-07-02-crash-flags-guidance-rev2.md` §8.

## The seats
Four seats coordinate only through git + committed artifacts (the full model + the identity boundary are in
`METHOD.md`). The operative subset:
- **Design** rules on CONTRACT/disposition; **Build/Code** implements and opens PRs; **QA** cold-reads the real
  substrate and proposes findings; **the Human** decides and merges.
- **QA findings arrive as `qa/*` PRs, Option-2 composition:** QA proposes a **RED test + a reference patch**;
  Code applies it with an **independent read** (never blind `git apply`); the handoff ships as
  `@pytest.mark.xfail(strict=True)` so today's gate is green and the marker flips loud the moment the fix lands.
- **Machine-account boundary:** Code acts under the bot `claudeatalphalabsengineering` (not a code owner);
  QA/the human seats are distinct. No seat merges its own PR (see `## Development`).

## Verification
The fix discipline — what "done" means:
- **Every fix ships the violation test that would have caught it** — and **prove the gate bites** (a gate that
  has never rejected is observationally identical to no gate; plant the violation, watch it go RED, revert).
- **Verify against the unit the system *acts* on, not the unit you changed** — a fixture must reproduce the
  pre-fix failure, and **the deploy is not the proof, the tick is** (record the null result, name the retest).
- **A fix isn't done until its `docs/bugs/INDEX.md` row is current** (the register is the searchable memory).
- Parser/extraction changes are **corpus-checked**: the frozen substrate (§7) makes a whole-corpus replay
  nearly free, so re-run `tools/corpus-check/` over every frozen blob — a fix verified only on its target
  documents is verified on a biased sample.

## Development
- **Always work on a new branch.** Never commit directly to `main`. At the start of any change,
  branch off `main` (`git switch -c <descriptive-name>`) and do the work there; graduate it to `main`
  by pull request. If a session begins on `main` with work to do, create the branch first.
- **Code never merges to `main`** — it opens the PR and stops. Code's job ends at pushed branch → green CI →
  open PR; the owner reviews, approves, and merges from the phone (the Mini holds no owner credential). This
  is now mechanism, not posture: Code acts under the machine account `claudeatalphalabsengineering`, which is
  not a code owner and cannot approve its own PR, and the `main` ruleset requires one code-owner approval
  covering the most recent push, no bypass — so no sequence of agent actions alone lands code on `main`. The
  residual posture is narrow and still binding: once the owner has approved, Code could click merge — it must
  not. CI-green is not correctness: green-on-synthetic, a test that passes for the wrong reason, a
  merge-introduced regression all clear CI — and the human review is where that class is caught. Ratified:
  `docs/decisions/2026-07-16-agent-identity-split-and-merge-gate.md` (supersedes
  `docs/decisions/2026-07-12-code-does-not-merge-human-reviews.md`, which recorded the posture-era rule).
- **Merge commits, never squash** — the repo enforces it (`allow_squash_merge: false`, verified via the GitHub
  API), so the append-only history is a mechanism, not a habit; the merge-commit trail stays traceable.
- **Branch off a freshly-fetched `origin/main`, never off a sibling feature branch** —
  `git fetch origin && git switch -c <descriptive-name> origin/main`. When PRs merge quickly, a branch cut from
  a **stale local `main`** (or from another feature branch) carries a stale base, and a PR from it can
  **silently revert an already-merged change** — the diff shows the sibling's merged work as *deletions*.
  **Diff against `origin/main` before opening the PR**; that catch is the last guard. (Born from exactly that
  near-miss — see `docs/decisions/2026-07-11-branch-off-fresh-main.md`.)
- **Verify git/PR state before acting on it — `main` moves, and that is its default.** Code opens PRs; the
  **owner** merges them asynchronously (often from a phone), so *"is this PR open / is this branch merged /
  where is `origin/main`"* is never something Code knows — only something it last observed. Before amending or
  force-pushing a branch, check `gh pr view <n> --json state,mergedAt`: **never amend a merged branch** — the
  change is orphaned and **silently does not land**; put it on a fresh branch off `origin/main` instead. Before
  reporting a change as landed, verify against the remote (`git merge-base --is-ancestor <sha> origin/main`),
  never against local state or memory. The hazard is not the force-push (harmless) — it is **believing a fix
  landed when it did not**, the fail-silent class wearing a git hat. (Born from exactly that:
  `docs/notes/2026-07-19-verify-git-state-before-assuming.md`.)
- **Production deploys from a tag, by mechanism** — `ops/deploy.sh <tag>` refuses any non-tag ref and takes the
  single-writer `run.lock`, so production can never be pinned to a moving ref or swapped under an in-flight tick
  (`docs/decisions/2026-07-14-single-writer-lock-and-deploy-coordination.md`).
- `uv sync` to set up; `uv run pytest` to test; `uv run pros --help` for the CLI.
- Tests are offline: a network guard fails any test that opens a real socket. Recorded fixtures
  live in `tests/fixtures/`.
- All record times are UTC.

## Fixture provenance
Every test fixture is either **recorded-real** — carrying a source-URL + retrieval-date header (a
sidecar for binary files like xlsx) — or **declared synthetic** in-band (a trailer or comment that says
so). No fixture silently stands in for a real filing. Fixtures were the one input class exempt from the
freeze-the-substrate discipline (§7 frozen ingest); the launch-corroboration slice is why they no longer
are — a labeled-synthetic SPDR-format holdings fixture carried a green the real filing had not yet
earned. Reading the real file broke two shared (convergent) priors the cross-thread review could not:
the real SSGA daily file is **xlsx, not CSV**, and for an **active fund carries no `Sector` column at
all** ("-"), so the derivation was proven against *imagined* messiness, not *filed* messiness (the split
assertion held, so nothing was wrong — the gap was invisible until someone read the real file). When a
fixture is synthetic, say so where a reader will see it; when it is real, say where it came from and
when. Primary-source verification is the specific antidote to convergent priors.

## Documentation (standing practice — document as we build)
- `ARCHITECTURE.md` (repo root) is the top-level map of what's built and why. **Keep it current**:
  when a milestone lands or a module's shape changes, update the module map (§2) and the built/deferred
  status (§9) in the same change. It is written for someone catching up — orient, don't just enumerate.
- Every load-bearing decision or CONTRACT amendment leaves a written trace in `docs/decisions/`
  (pointed to from this file), next to its `config.changed` fossil / commit.
- Code carries **spec-citing docstrings** (which `§` a module implements) and **inline comments on the
  subtle bits** — especially anything that encodes a CONTRACT, a deliberate non-obvious choice, or a
  "do not do X because Y." Comment the *why*, not the *what*. This density is the norm; match it.

---
*Consolidation rev, 2026-07-23 — the reconciled edit-list (`docs/notes/2026-07-21-claude-md-consolidation-reconciled.md`)
executed: the CONTRACT-vs-DEFAULT narrative compressed to an amendment index, the three doc-rule sections grouped
under `## The record`, `## Identity` → `## Fund identity`, the header map + section list added, the honest
enforcement tiers stated, and the missing operative rules (the seats, verification, the record-as-mechanism,
deploy-by-tag) folded in. Clause-by-clause diff proof + the §4 protected-list table:
`docs/decisions/2026-07-23-claude-md-consolidation-rev.md`. C-1 (the version-free spec pointer) landed earlier in
`docs/decisions/2026-07-23-claude-md-minimal-drift-kill.md`.*
