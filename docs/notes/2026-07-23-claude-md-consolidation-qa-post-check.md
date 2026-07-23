# §7.4 QA cold post-check — CLAUDE.md consolidation (merged)

**Reviewed commit:** `438952e623baf7b257704d2d46f841a8eeb4a3a9` (main, post-merge)
**Spec at review:** `docs/spec.md` **rev 18** (2026-07-22)
**CLAUDE.md:** 23,637 B (the reconciled consolidation rev, changelog dated 2026-07-23)
**Procedure of record:** `docs/notes/2026-07-21-claude-md-consolidation-reconciled.md` §7.4 —
"one cold pass over the merged result: the protected-list sweep and a re-plant of the §1 violation
(which must now fail)."
**Seat:** QA (Claude Science). Cold read of the primary source; proposes, does not merge.

## Verdict: PASS — no scar was smoothed away. One documentation-accuracy nit (below), not a scar loss.

---

## Part 1 — Firewall re-plant (the mechanized backstop)

The §1 violation is: a new module reads `portfolio.yaml` and CI stays green (the pre-P-1 defect — the
old 6/54-module allowlists didn't cover it). P-1 replaced the allowlists with a package-wide AST sweep
(`test_firewall.py::test_no_module_reads_the_portfolio_file`, `PACKAGE.rglob("*.py")`).

**Cold re-plant, executed:**
1. Baseline `tests/test_firewall.py` clean → **9 passed**.
2. Planted a real `open("portfolio.yaml")` read (a function body, not a docstring/comment) into
   `prospector/sensors/soi.py` — the exact un-allowlisted module class from the §1 violation.
3. Ran the sweep → **RED**, naming the offender exactly:
   `AssertionError: firewall: these modules reference portfolio.yaml in code: ['sensors/soi.py']`.
4. Restored `soi.py` (md5 back to pristine `08b4f06b…`), re-ran → **9 passed** (re-plant left no trace).

**The scar holds.** The forbidden read that passed CI pre-P-1 now fails, and it fails from the single
package-wide home, not a hand-maintained list. AST-based (separates code that reads from prose that
names — `dashboard/export.py`'s docstring naming `portfolio.yaml` is correctly NOT an offender).

**F3 (my post-#99 finding) confirmed landed in the same test:** `S3_CLIENT_ROOTS =
("boto3","botocore","s3transfer")`; the botocore-evasion negative control is present. The S3 clause is
tiered honestly in CLAUDE.md `## Enforcement tiers` as "mechanism (proxy, named gaps)."

## Part 2 — Protected-list sweep (14 scars, independently verified)

Rule (§4): every clause on Design's §4 scar-tissue list
(`docs/notes/2026-07-16-claude-md-consolidation-design-seat-findings.md`) present in exactly one
canonical home — spec (CLAUDE.md points) or CLAUDE.md (constitutional) — with the **Firewall the one
deliberate both-homes exception**. Verified by grepping the actual merged bytes, NOT by trusting Build's
§4 table (`docs/decisions/2026-07-23-claude-md-consolidation-rev.md`).

**13 of 14 verified present exactly as the table claims.** The 14th (scar 13, the fixture pair) is
present but homed differently than the table's annotation says — see the nit.

| scar | claimed home | QA verified |
|---|---|---|
| 1 Firewall (3 bullets, whole) | CLAUDE.md + spec (exception) | `## Firewall`: portfolio.yaml + detector's bucket + sibling — PRESENT; test green |
| 2a No LLM text as data | CLAUDE.md | `## No LLM text as data (v1)` — PRESENT |
| 2b No run-now surfaces | CLAUDE.md | `## No run-now surfaces` — PRESENT |
| 3 Never rolling percentile / self-updating window | CLAUDE.md | `## Standing review items` — PRESENT |
| 4 NPORT-P never survivor-biased | spec §3b | spec: survivor-bias + NPORT — PRESENT; CLAUDE.md count 0 (correctly deleted) |
| 5 No import sibling models/ | CLAUDE.md | `## Vendored store provenance`: models/ + "capacity and opacity" — PRESENT |
| 6 No wide typed-metric columns | CLAUDE.md | "typed-metric columns" — PRESENT |
| 7 anti-fitting: dormant never lowers sector_min_weight | spec §4c | spec: sector_min_weight — PRESENT |
| 8 never add series_ids to lead payload | spec §4d | spec: series_ids — PRESENT |
| 9 diff strategy-section only (diff-trap) | spec §4d | spec: principal-investment-strategy + full-text diff — PRESENT |
| 10 bs4 structure / code meaning / human significance | spec §4d | spec: structure + significance — PRESENT |
| 11 proto-cluster wall (price-only · cluster · never-the-trade) | spec §4b/App B | spec: cluster + price-only + never the trade — PRESENT |
| 12 macro both directions | CLAUDE.md | `## Standing review items`: trade/tilt trigger + strips-the-macro — PRESENT (both directions) |
| 13a fixtures never refreshed by fetch | (table says CLAUDE.md verbatim) | **spec.md:75 + :392 verbatim** ("fixtures are never refreshed by fetch"); mechanized in fixture sidecars + `test_edgar_client.py:630`. NOT in CLAUDE.md. |
| 13b no fixture stands in for a real filing | CLAUDE.md | `## Fixture provenance`: "No fixture silently stands in for a real filing" — PRESENT |
| 14 bare ticker rejected at write path | CLAUDE.md | `## Fund identity`: bare ticker + display-only — PRESENT |

### The one nit (LOW · documentation accuracy, not a scar loss)

Build's §4 table (consolidation-rev, row 13) says both fixture clauses live in CLAUDE.md
`## Fixture provenance` "verbatim." **That annotation is inaccurate.** Reading the merged bytes:
- **13b** ("No fixture silently stands in for a real filing") IS in CLAUDE.md `## Fixture provenance`, verbatim. ✓
- **13a** ("fixtures are never refreshed by fetch") is **NOT** in CLAUDE.md. It lives in **`docs/spec.md`
  (rev 18) at :75 and :392**, verbatim, and is additionally mechanized (fixture `.source.txt` sidecars
  carry "NEVER refreshed by fetch code"; `test_edgar_client.py:630` enforces it for the frozen `.htm`).

**Why this PASSES §4 anyway:** §4 requires each scar present in *exactly one* canonical home. 13a is in
the spec — a canonical home — so the scar is safe; the consolidation did not smooth it away. The defect
is only that the *proof table* mislabels 13a's home as CLAUDE.md. A reader auditing the table against
CLAUDE.md alone would not find 13a there and might wrongly conclude it was dropped. The scar is intact;
the table's "verified present" cell for row 13a points at the wrong file.

**Suggested correction (Build/Design seat, not QA's to make):** in the consolidation-rev §4 table,
split row 13 — 13a home = **spec (+ mechanized in fixtures/tests)**, 13b home = **CLAUDE.md**. One-line
edit to the decision doc; no code or CLAUDE.md change needed.

## Suite health at merged main

Full offline suite: **726 passed, 2 xfailed, 1 failed**. The 1 failure is `test_run_lock` — the known
environment artifact (its subprocess can't import `prospector` without an editable install; green on CI,
which installs the package). Confirmed identical on the pristine tarball; never a repo defect. Firewall
suite specifically: **9 passed** clean.

## Bottom line

The merged consolidation preserves every protected scar. The firewall's mechanized backstop bites on a
cold re-plant. The only issue is a mislabeled home in the proof table's fixture row — a doc-accuracy fix,
not a scar restoration. §7.4 post-check: **PASS**.
