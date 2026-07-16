# QA verification record — METHOD.md mechanism claims

**Verified:** 2026-07-16T21:23:07Z · **against `main` @ `44d81c630cdf6f78fcf3c52554e94a106b3cf5bf`**
**Seat:** QA (cold read, repo of record) · **Method:** live GitHub API reads + two write-probes, no merge, no lasting writes.
**Build addendum:** 2026-07-16 · rule-6 acceptance half (below) · against `main` @ `eeb1c389d19251ef0657f90f2525c6fb00b42d10`, Build seat.

This record anchors the enforced-tier mechanism claims in `METHOD.md` (formerly
`2026-07-16-how-we-work.md`) to evidence outside the narrative — the live `main`
ruleset, `CODEOWNERS`, the workflow set, and a rule-6 rejection probe generated
in the same pass. Per the doc's own discipline: a mechanism claim is tied to a
commit SHA, a config value, or a watched rejection — never to another summary.
Re-runnable from the QA seat; re-verify when `main` moves.

## Rule 1 — nothing merges unless the suite passes · CONFIRMED
Ruleset **"main protection"** (id 18823846), enforcement **active**:
- `required_status_checks` = `['test']`, `strict_required_status_checks_policy` = `true`
- `bypass_actors` = `None` → no bypass for anyone, including the owner.

## Rule 2 — agents propose; the human disposes · CONFIRMED
- `required_approving_review_count` = `1`
- `require_code_owner_review` = `true`
- `require_last_push_approval` = `true`
- `dismiss_stale_reviews_on_push` = `false` — the doc correctly does **not** claim this setting; the approve-then-swap hole is closed by `require_last_push_approval`, not by stale-dismissal.
- `.github/CODEOWNERS` = `* @dickienaut` (sole owner, every path).
- Behaviour proven earlier (PR #79, 2026-07-16): bot-opened PR → blocked; human code-owner approves → mergeable; bot pushes after approval → re-blocked, and stays blocked even after CI `test` goes green (isolates `require_last_push_approval` from the status check). Bot self-approval is refused (422).

## Rule 3 (QA sub-clause) — go to the primary source · CONFIRMED (QA seat)
`deliver_qa_findings_pr` in the `prospector-branch-qa` skill requires `reviewed_sha`:
delivery **raises before any push** if it is omitted, non-40-hex, or ≠ the resolved
base head. Proven RED/GREEN with meta-controls (`proof_reviewed_sha.py`, exit 0).
Scope is honest: this binds QA's fetch-and-deliver path only. Code/Design/Human
remain discipline, as the per-seat ledger states.

## Rule 6 — least privilege: "QA cannot modify CI config" · CONFIRMED by rejection
CI is a workflow: `.github/workflows` = `['ci.yml']`.
On a throwaway branch off `main` @ `44d81c630cdf6f78fcf3c52554e94a106b3cf5bf`, the QA-seat account
(`claudeatalphalabsengineering`, token scope `repo`) attempted two writes:

| write target | status | reading |
|---|---|---|
| `.github/workflows/_probe.yml` | **404** (Not Found) | CI-config write **refused** |
| `docs/notes/_probe.md` (control) | **201** | non-workflow write **succeeds** |

Same token, same branch, same method — the refusal is specific to the
workflow path. "QA cannot modify CI config" is therefore proven by a **watched
rejection**, not inferred from a scope string. Probe branch deleted
(`204`); nothing left on the remote.

## Rule 6, the other half — "Build can modify CI config" · CONFIRMED (Build seat, 2026-07-16)
Build closed QA's open ask from its own seat. Build's token is the **same** machine
account (`claudeatalphalabsengineering`) but carries scope `read:org, repo, workflow` —
the `workflow` scope QA's token lacks. On a throwaway branch off `main` @
`eeb1c389d19251ef0657f90f2525c6fb00b42d10`, the Build seat ran the same two writes QA did:

| write target | status | reading |
|---|---|---|
| `.github/workflows/_build_probe.yml` | **201** (created, commit `e08ca19`) | CI-config write **succeeds** |
| `docs/notes/_build_probe.md` (control) | **201** (commit `78df7b0`) | non-workflow write succeeds |

Same account, same method as the QA probe; only the token scope differs. The
workflow-path write QA's `repo`-only token got **404** on, Build's `+workflow` token
gets **201** on. The enforced-tier differential is now a **watched result from both
sides** — QA cannot (404), Build can (201) — so rule 6's "Build can / QA cannot" is
evidence-backed both directions, asserted on neither. Probe branch deleted; nothing
left on the remote. The interim hedge QA proposed ("pending Build-side confirmation")
is no longer needed; METHOD.md's rule 6 stands affirmatively.

---
*Anchored record. Every value above is a live read or a watched probe result as
of the header timestamp and `main` head. If `main` has moved, re-run the probes
before trusting this page.*
