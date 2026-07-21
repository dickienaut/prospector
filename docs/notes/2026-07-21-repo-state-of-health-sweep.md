# Repo state-of-health sweep — build seat, 2026-07-21 (for QA)

*A build-seat survey of the whole repo at `main @ eef1d7c` (v1.0.6), taken because we've shipped a lot
since QA last looked. **Base: PR #99** (`43c556d`, merged 2026-07-17 — QA's last repo read); everything
below is the delta since — **32 merged PRs (#100–#131), 69 files, +7209/−146**, top areas docs (31),
tests (20), `prospector/` (8), tools/ops/config.*

**What this is:** the build seat's read, to hand to QA as a base for an independent deep check. QA should
do the same from #99 and **find what this missed** — the divergences are the value. Method: four parallel
audits (mandate/ingest · firewall+test-integrity · docs/register/consolidation · ops/config/deploy/capture),
each grounded in file:line / command output, each told to be a skeptic. **This is a survey, not an
exhaustive audit** — the `NEEDS-QA-DEEP-CHECK` list (§4) is where the deeper adversarial passes belong.

---

## 0. Verdict

**Healthy.** The heaviest change area — the mandate B1 stack (guard → isolation → Q&A heading) — is
coherent, well-tested, and its residuals are honestly flagged. The firewall discrepancy QA demonstrated at
`a8010d61` (the 6/54 allowlist) is **resolved** by #127 and now **provably bites**. The bug register is
accurate on the rows sampled. **The owed work is overwhelmingly documentation** — a ratified-but-unexecuted
CLAUDE.md consolidation and two stale headline docs — plus a handful of small register/test-citation fixes
and the standing set of unproven-in-prod gates.

## 1. Resolved since QA's last look (so QA doesn't re-flag)

- **FIREWALL-ALLOWLIST (QA's #1 finding at `a8010d61`) — FIXED by #127, proven RED.** `tests/test_firewall.py`
  now sweeps the **whole package** (54 modules, AST-not-grep so docstrings don't false-positive) for
  `portfolio.yaml`, the sibling-`models/` import ban, and an S3-client-confinement proxy for the detector
  bucket. Both old 6/54 allowlist tests are retired. A planted `config/portfolio.yaml` read in `sensors/xcorr.py`
  (one of the 48 modules the allowlist never covered) → **RED**. The INDEX row is accurate.
- **Test hermeticity (#112) — RESOLVED, differential-proven.** Full suite is byte-identical with the machine
  overlay present vs moved aside (704 passed / 4 skipped / 2 xfailed both ways).
- **v1.0.6 cut + deployed + deploy record.** (Three audits flagged "no v1.0.6 record"; that was true at
  audit-start — it's now closed by PR #132, this session.) Prod is at v1.0.6, 0 behind origin/main.

## 2. Discrepancies found (organized by area · severity)

### A. Documentation / consolidation drift — the main bucket

- **A1 · The CLAUDE.md consolidation is RATIFIED but NOT EXECUTED.** The reconciled edit-list
  (`docs/notes/2026-07-21-claude-md-consolidation-reconciled.md`) prescribes C-1…C-6 + 5 Category-E
  additions; **none have landed** in `CLAUDE.md`. This is the single largest owed item.
- **A2 · Rev-narrative drift (C-1).** `CLAUDE.md:6` says "rev 15"; `docs/spec.md:1` is **rev 16**. The opener
  still narrates rev12→rev5. (QA flagged this at `a8010d61`; still stale one rev later.)
- **A3 · `mandate.changed` called "deferred" when it's BUILT.** `CLAUDE.md:21,75` — and `docs/state.md:70-71,143`
  list "combined-prospectus multi-fund extraction" under DEFERRED. Both are now false: the mandate diff is
  wired and multi-fund block isolation shipped (#130, register ✅).
- **A4 · `docs/state.md` (rev 8) stale** — spec rev (says 15 → is 16), test count (says 634 → ~707), the whole
  mandate arc + v1.0.6 absent. Part V owed a re-synthesis.
- **A5 · `ARCHITECTURE.md` headline stale (register C.2, confirmed open)** — "499 tests", "spec rev14 canonical",
  "last updated after the M5 arc". The module map (§2) is fairly current but omits the Q&A heading (#131).
- **A6 · The merge-gate rule is UNWRITTEN (not stale-wrong).** You disabled rebase+squash (merge-commits only).
  No *current* canonical doc claims "rebase deliberately enabled"; CLAUDE.md simply carries no merge-method
  rule — it's a pending Category-E addition (M-5). **But** the design-thread note
  `docs/notes/2026-07-15-design-thread-state-and-open-decisions.md:41` still says "Use 'Update with rebase'",
  which is now impossible (rebase-merge off) — a stale instruction (precondition P-3, owner UI call).
- **A7 · `.github/CODEOWNERS` cites the superseded merge record** (`2026-07-12-…` instead of
  `2026-07-16-agent-identity-split-and-merge-gate.md`). Mutable file → a clean one-line fix (precondition B-2).
- **A8 · DRIFT-1 / DRIFT-2 / C.2 ("doc pass owed") — genuinely still open** (`INDEX.md:56,73,237`). This sweep
  independently confirms them (A4, A5).

### B. Bug-register / test-citation accuracy — small, mine to fix

- **B1 · `MANDATE-PROSE-HEADING` (✅, `INDEX.md:168`) cites two tests that no longer exist** —
  `test_extract_faults_on_a_prose_investment_objective_line_no_false_section` and
  `test_prose_heading_cannot_produce_a_spurious_mandate_change`. **PR #131 renamed/replaced them** (the Q&A
  heading inverted the JPM_QA fixture's expected outcome from fault→reliable). The *guard itself* is still
  tested (`test_is_heading_strict_rejects_prose_but_keeps_real_heading_variants`), so ✅ is substantively
  correct — but the citation is stale, exactly the drift the register exists to prevent. **Introduced by this
  session's PR3.**
- **B2 · ~8 INDEX rows still read "✅ (this PR)" / "(stacked, PR pending QA)"** for since-merged work
  (MANDATE-PROSE-HEADING, MANDATE-SOURCE-NEWLINES, MANDATE-TOC-SHADOW, MANDATE-DECL-BAR, the CAP-* rows…).
  Mild present-tense staleness across the file.

### C. Test gaps — small

- **C1 · No direct test for the `series_classes` fetch-failure branch** (`prospectus.py:115-117`): an
  `EdgarError` on the header `.txt` fetch is caught → `complete:False` → `review-advisory`. Unit/runner tests
  always supply a header, so only the *parse-level* truncation path is pinned, not the *fetch-level* catch.
  The behaviours differ (caught → review-advisory that pages only on a live lead; if the catch narrowed, the
  error would propagate as an operational fault that pages). **Introduced by this session's PR1.** A test
  should force the header fetch to raise and assert `review`.
- **C2 · Test `CFG` carries a spurious `"mandate": None` key** (`test_mandate_sensor.py:42`) with no
  counterpart in the config's mandate block — harmless (code reads flat keys) but not a faithful mirror.

### D. Ops / activation — pending gates (not defects)

- **D1 · Dead-man human loop — NEVER exercised** (activation item 4). The single most load-bearing unproven
  gate; needs a deliberately *withheld* due heartbeat caught by the calendar backstop — a multi-day test.
- **D2 · Heartbeat cadence *recurrence*** — catch-up proven, a second scheduled send not; next due **2026-07-24
  22:30 UTC**.
- **D3 · #114 capture-403 host-split — unproven in prod**; retest at the first tick on/after **~2026-07-25**
  (weekly per-lead gate). Untestable in CI (no armed API).
- **D4 · v1.0.6 first-tick evidence owed** — tonight's 18:30 EDT tick; the deploy record (PR #132) has the
  checklist stub awaiting it.
- **D5 · Activation 781 is version-stale** (records v1.0.3; later gate proofs are scattered across the
  v1.0.4/v1.0.5 deploy notes, no fresh 781). Fossil is scattered, safety unaffected.
- **D6 · Mandate review-advisory backlog** (faults 9→27 across recent runs, all `review-advisory` / not on a
  live lead — the §4d "flag, never false-change" contract firing as designed). Not a defect; an accreting
  manual-triage backlog the v1.0.5/v1.0.6 mandate work is *expected* to reduce — unconfirmed in prod.
- **D7 · DEPLOY-OVERLAY-DRIFT (🟡) + CAP-DRIFT (🟡)** — ratified-residuals; mitigations holding (dual
  `lock-path` identical today; armed byte-compare passed 2026-07-18).

## 3. Firewall residuals (honest coverage boundaries, for QA's eyes)

- The detector-bucket has **no name-based check** — enforcement is the boto3-client-confinement proxy (only
  `store/s3_sync.py` may construct an S3 client). A bare bucket-name string with no boto3 import → **not
  caught** (the name is deliberately absent from the repo). The proxy also matches only the root `boto3`; a
  `from botocore…` / aliased / transitive import would evade it.
- **IAM** (the spec's stronger "credentials *unable* to read the bucket") is out-of-repo and out-of-CI —
  documented, genuinely uncovered by nature.

## 4. NEEDS-QA-DEEP-CHECK (the handoff — where QA's independent pass is most valuable)

1. **Mandate pair-level verification on the deployed v1.0.6 build + first live tick** (the CORPUS-CHECK-PAIRBLIND
   class — per-document greens hid 3 false fires before). Run `backfill_headers.py` (done today) then
   `extraction_corpus_check.py` section 6 against the real store, and read tonight's tick: confirm reduced
   advisories AND **zero newly-firing `mandate.changed` on any live lead**.
2. **The cross-era header transition (Q2).** The live store predates the header freeze. If a *legacy prior*'s
   header fetch fails live, its isolation degrades to whole-doc (first fund) while a multi-fund *current*
   isolates — a theoretically reachable cross-fund diff for legacy priors. Self-heals as headers freeze;
   worth a probe against the real store.
3. **The `series_classes` EdgarError→review branch (C1)** — unpinned; assert it pages only on a live lead,
   never as an operational fault.
4. **Firewall residuals (§3)** — the detector-bucket/IAM boundary is the highest-value external-QA target.
5. **#114 capture-403 host-split, live (~07-25)** and **the dead-man human loop (D1)** — the two unproven-in-prod
   gates.

## 5. Roadmap of next steps (prioritized)

**Tier 0 — small, mechanical, unblock the consolidation:**
- B-2 · repoint `.github/CODEOWNERS` to the 2026-07-16 merge record (one line).
- P-2 · land the spec §3b survivor-bias amendment (`spec.md:67`) + rev bump, so the CLAUDE.md NPORT-P line
  deletes cleanly during consolidation.
- Register fixes: correct the `MANDATE-PROSE-HEADING` citation (B1); sweep the "✅ (this PR)" present-tense (B2).
- Test fixes: add the `series_classes` EdgarError→review test (C1); drop the spurious CFG key (C2).
- P-3 · **owner UI check** — the "Update with rebase" button on a behind-branch PR; decide knowingly whether to
  re-enable repo-level `allow_rebase_merge`, and reconcile the stale `2026-07-15` note (A6). *Owner-only.*

**Tier 1 — the CLAUDE.md consolidation rev (highest reader value):** execute the reconciled edit-list against
fresh main — C-1 version-free pointer (kills A2 *and* A3's rev-narrative in one deletion), C-2 compression,
the 32 Category-B deletions-with-pointers, C-3/C-5/C-6 structure, the firewall tiering table (P-1 now makes
"mechanism" true), and the 5 Category-E additions **including the merge-commits-only rule (M-5, A6)**.
Diff-protocol + §4 protected-list check + a QA cold post-check.

**Tier 2 — "record matches territory" doc pass (closes DRIFT-1/2/C.2):** re-synthesize `docs/state.md` Part V
(rev 9: spec rev 16, ~707 tests, mandate arc built, v1.0.6); refresh the `ARCHITECTURE.md` headline (§9 intro,
test count, spec rev, the Q&A-heading module line).

**Ongoing — prod evidence (proves, unblocks nothing):** append tonight's v1.0.6 tick to the deploy record;
the corpus-check pair verification (§4.1); #114 retest (~07-25); the heartbeat-cadence recurrence (07-24); the
dead-man-loop exercise.

## 6. Method / limits

Four parallel audits, ~490s each, all left the tree clean (verified). Coverage is broad, not exhaustive:
the register was **sampled** (8 ✅ rows, all tests verified present), not fully walked; the firewall bite-test
covered `portfolio.yaml` + the S3 proxy, not every conceivable evasion; prod behaviour was read from docs +
static state, not exercised (no tick run). The `NEEDS-QA-DEEP-CHECK` list is the honest boundary of this
survey — QA's independent read from #99 is expected to extend it, and the divergences are the point.
