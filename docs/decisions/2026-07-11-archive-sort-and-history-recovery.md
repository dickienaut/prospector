# Design-thread archive sorted; missing history recovered; rho-G restored

*Decision record, 2026-07-11. The owner dropped a 66-file `docs/Archived/` dump — the accumulated outputs of
every design-thread conversation, spanning several projects — and asked to sort the Prospector-relevant files
into the taxonomy, duplicates aside, flagging anything uncertain. This records what was filed, what was
deliberately **not** filed (the firewall call), and the rho-G restoration.*

## Method

Exact duplicates were found by **content hash** (SHA-256) against the current repo docs — deterministic, not
name-guessing (same-named files can differ; different-named files can be identical). Everything else was
classified by reading its header. Guiding rule from the owner: **flag anything uncertain and leave it** — so
only high-confidence Prospector-own docs were filed; the rest stay in `Archived/` (untracked) with a manifest
(`docs/Archived/FLAGGED.md`).

## What was filed into the repo

- **`history/` (5) — recovered missing spec revs.** `prospector-v1-spec-rev2, rev4, rev7, rev10` fill the exact
  gaps the reorg (`2026-07-11-docs-reorganization.md`) flagged, and **rev 1** was recovered as
  `generator-v1-spec-2026-07-01.md` — the owner designated it the series' first doc (written before the
  "Prospector" rename), so it was renamed `prospector-v1-spec-rev1-2026-07-01.md` (its content keeps the
  original *"Generator v1"* title, faithful to the era). The series is now contiguous **rev1–rev14**.
- **`notes/` (4).** `2026-07-04-rev13-rev4-fold-for-claude-code`, `2026-07-04-soi-slice-design-review`, and the
  two active CI-gating notes (`note-github-test-gating` + `2026-07-11-ci-branch-protection-setup`) — CI-gating
  (tests must pass to merge) is the current next step.
- **`origins/` (11, incl. restored rho-G).** Founding-era Prospector (the decisions-review rev 2;
  `thesis-generator-outside-read`; `prospector-v1-spec-punchlist`; `concept-freeze-2026-06-28`;
  `two-instruments-for-a-long-horizon`; `yin-yang-monitoring-system-overview`;
  `systems-failure-and-portfolio-resilience-synthesis` — the resilience **base-case** the design answers to),
  and sibling-project provenance (`thesis-smoke-detector-{decisions-review-2026-06-29, one-pager,
  technical-overview}`, alongside the design-brief already present). *(The founding build spec `generator-v1-spec`
  went to `history/` as rev 1 — see above.)*

## rho-G restored — to the canonical version

The reorg deleted `rho-G-hawkes-criticality-subsystem-design-theory.md` as unbuilt sibling cruft; the design
thread reversed that (**never delete — git tracks it, it costs nothing, and it is the sibling's foundational
theory**). The owner had re-placed a **24 KB** copy in `origins/`, but the authoritative version — the one that
was reviewed and lived in the repo, matching git history *and* the archive — is **36 KB**. The **36 KB canonical
was restored**; the 24 KB variant is preserved at `Archived/rho-G-USER-PLACED-24kb-variant.md` in case the
difference was intentional.

## What was deliberately NOT filed — the firewall call

The archive spans projects. Two classes were kept **out** of Prospector and left flagged, on the firewall
(*"the only connection to the portfolio system is human and one-way"*):

1. **The "Portfolio Research Dashboard" project (all of `files3/` + several others).** A *different* Claude Code
   project — the owner's personal Roth/IRA thematic-investing work: its own `CLAUDE.md`, the master investment
   thesis, target-allocation reviews, per-investment-thread templates, the holdings look-through notebook. This
   is the **walled-off portfolio side**; importing it into Prospector would breach the firewall. It belongs in
   that project's own repo.
2. **The Thesis Smoke Detector's internal build specs** (`bank-c-fleet-reconciliation`, `indicator-hud` — the
   latter references `portfolio.yaml`). The sibling's *conceptual* docs are legitimate Prospector provenance
   (and were filed to `origins/`), but its *implementation* specs against its own codebase are that project's
   internal docs, not ours.

Also left flagged: same-name/different-content pairs where the repo already holds a version (the owner picks
the winner — notably `bench-note-crowding-detection`, where the **archive copy is larger** than `origins/` and
may be the fuller one), and a generic cross-project `skunkworks-ledger` template.

## Staging convention

`docs/Archived/` is the owner's **untracked** staging area — **not committed**. Duplicates were moved to
`Archived/duplicates/` (source structure preserved) for a glance-then-delete; the flagged remainder stays in
`Archived/files*/`. Only the high-confidence Prospector docs above were added to the tracked tree. A follow-up
is pending: a `CLAUDE.md` amendment on dated-filename discipline (a date + rev/slug on point-in-time docs;
living contract docs versioned by git) — the archive's undated/same-named collisions are the motivating case.
