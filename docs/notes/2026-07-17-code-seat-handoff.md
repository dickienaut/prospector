# Code-seat handoff — where the Code seat left off (2026-07-17)

*A cold-start capture for the next Code seat (every session is new). **As-of: `main @ c50239f`.** Git is the
source of truth — before trusting any status line below, `git fetch origin` and read `origin/main`; this note
**describes, it does not ratify**. Filed to `notes/` (freely authored). QA and Design are dropping their own.*

---

## Where it stands (verified against main this session)

- **v1 is build-complete and deployed.** Recent work has been **doc consolidation**, not code.
- **Merged today (2026-07-17):** #88 (M6 capture-built correction) · #89 (QA rule-3 consolidation findings +
  the `.diff`) · #90 (QA config snapshot) · #91 (**rolling-docs rename**) · #92 (three design/QA notes tracked).
- **The rename is live:** the build spec is now **`docs/spec.md`** and the state doc **`docs/state.md`** —
  stable names, **rev in the header**, amended in place. The dated `-revN` filenames are retired; `history/`
  holds the pre-2026-07-17 fossils; INDEX carries the redirect. Ratified:
  `docs/decisions/2026-07-17-rolling-docs-stable-named.md`.
- **No PRs open.**

## The queue (ordered; sequencing constraints noted)

1. **Apply QA's rule-3 `.diff` to `METHOD.md`.** #89 landed the *findings + the patch file*
   (`docs/notes/METHOD_rule3_consolidation.diff`) but did **not** touch `METHOD.md`. This Code PR applies it:
   the `reviewed_sha` scar → one home + cited anchor. **Re-run `git apply --check` against current main first**
   (its base moved when #89 merged; #89 didn't touch `METHOD.md`, so it should still be clean — but verify, don't
   assume). **Precedes item 2** (adjacent bullets in the same rule-3 list; whichever lands second rebases).
2. **`METHOD.md` Code-ledger rule-3 scar.** The Code seat's rule-3 slice now has **three** instances:
   fixture-provenance (the labeled-synthetic SPDR holdings fixture), the M6 "front-loaded to v2" miss, and the
   **#88 stale-status miss** (reported main's state from a stale local checkout, never fetched — QA caught it
   against git). Add them to the per-seat ledger. Do **not** promote rule 3's tier — it is QA-enforced only and
   stays *aspired* (QA's call, ratified; "enforced" = a gate a stochastic seat cannot cross, true for QA alone).
   After item 1.
3. **Bug-register anchors.** `docs/bugs/INDEX.md` carries **10 bare `file.py:line`** citations; line numbers rot,
   `file.py:line @ <sha>` doesn't (a bug record is a fossil — the SHA *completes* the anchor it already implies).
   Cheap, recoverable-class → **opportunistic**: fold into the next register edit, not a standalone PR.
4. **Prune merged branches** (Code's standing job; only MERGED ones): `docs/fix-m6-capture-built`,
   `qa/method-rule3-consolidation`, `qa/config-snapshot`, `docs/stable-name-rolling-docs`, `docs/track-design-qa-notes`,
   and this handoff's branch once merged. (Owner may prefer to prune from the phone.)

## Working disciplines the Code seat carries (the scars)

- **Identity = the bot.** Commit/PR as `claudeatalphalabsengineering`; `git push` auto-auths via
  `.git/bot-cred.sh`; **`gh` needs `GH_TOKEN=$GITHUB_PAT_CODE`** or it acts as the human.
- **Code opens the PR and STOPS.** The owner reviews + merges (from the phone; the Mini holds no owner
  credential). The merge gate enforces it — the bot is not a code owner and cannot self-approve.
- **Fetch + read `origin/main` before ANY claim about repo / PR / branch state.** The local checkout lags the
  owner's out-of-band phone-merges; reporting a stale working tree as "main" was the #88 miss. When relaying
  state to Design, cite the `origin/main` HEAD SHA so its as-of is checkable.
- **Branch off freshly-fetched `origin/main`**, never a sibling feature branch; diff against `origin/main`
  before opening the PR.
- **Canonical docs: amend-never-regenerate** (surgical diff + a changelog line tracing to a decision record).
  **Decision records are append-only** — you don't amend a record; you write a *new* record superseding it and
  surgically amend the operative rule in `CLAUDE.md`. **New docs are born-dated;** stable-named docs
  (`CLAUDE.md`, `INDEX.md`, `ARCHITECTURE.md`, the READMEs, `METHOD.md`, and now `spec.md` / `state.md`) are
  amended in place.

## Design-thread outcomes worth not re-litigating

- **Status-truth is one home, not a linter.** A `status.yaml` + CI-check was proposed and **rejected** — it's the
  `provenance_stamp`-before-`reviewed_sha` anti-pattern (a green token proves a doc-token == a yaml-token, not
  that the claim is *true*); "built" is a judgment with no repo fact to bind; and it adds homes, not fewer.
  Landing point: **one home + the cited-path/SHA-resolution gate** (the honest machine-limit), in the CLAUDE.md
  consolidation. `ARCHITECTURE.md` is still the most-stale status home (M7 not marked built; "499 tests").
- **Before proposing any mechanism, run the pain test** (process only under *real recurring pain* — doc drift is
  caught 3-for-3 by the cross-seat read, zero damage → no mechanism) **and name the seat-bias rather than gating
  on it** (Code reaches for tools by default; the checking is the reviewer's half). Where failure is
  *irreversible*, mechanize *before* the pain instead — the pain test scopes to recoverable failures.
- **QA's D1/D2** (rev8 test count `634` vs real `~640–642`, environment-dependent → read from
  `pytest --collect-only`, don't type it; `INDEX.md` lagged `METHOD.md` + the identity-split decision) — folds
  into the CLAUDE.md consolidation.

## Read first (cold start)

`CLAUDE.md` (constitution) → `METHOD.md` (the four-seat method) → `docs/state.md` (where it stands) →
`docs/spec.md` (the CONTRACTs) → `docs/INDEX.md` (the map) → `docs/decisions/` for any slice you touch. The
companion captures: `docs/notes/2026-07-15-design-thread-state-and-open-decisions.md` (Design's decided/open/
queued index) and the QA/Design handoffs landing alongside this one.
