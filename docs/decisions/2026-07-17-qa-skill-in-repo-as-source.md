# The QA skill lives in the repo as source (`tools/qa-skill/`); publishing to the platform catalog is the deploy

**Date:** 2026-07-17
**Status:** ratified (design thread) — recorded after the fact; executed by #93 (relocate + membrane
controls), #96 (obsolete mirror removed), #98 (the stamp), #99 (injectable transport + delivery guards).

## Decision

The QA branch-review skill (`prospector-branch-qa`: `SKILL.md` + `kernel.py`) lives **in the repo as its
source of truth**, at **`tools/qa-skill/`**. The platform catalog copy the session loads is a **publish
target — the deploy, not the source.** Changes to QA's procedure go through a `qa/*` PR into `main` (the
gate), exactly like every other change.

## Why

**A DRIFT signal against a mirror is cry-wolf — that is the decisive argument, not "so it can be reviewed."**
A mirror lags by design; drift is its *expected* state, so a drift check against one fires constantly and
means nothing — a brand-new alarm on this project's most-scarred failure mode. Against a **source**, DRIFT is
a finding. That is what makes the signal a signal. (An earlier "build it in the right place first" rework
argument was withdrawn in favour of this one.)

**Home = `tools/qa-skill/`, not `qa/`.** Every top-level directory in this repo names a **kind**, not an owner
— `prospector/` the package, `tests/` the suite, `docs/` the record, `ops/` operations, `config/` config.
`qa/` would be the only owner-named directory in the tree, encoding the wrong thing at exactly the moment you
are deciding the **repo** owns the artifact rather than QA. (`docs/` already holds `METHOD.md`, which governs
QA, and nobody calls it QA's.)

**The pattern it completes.** `CLAUDE.md` governs Code (in-repo, reviewed, gated); `METHOD.md` governs every
seat (in-repo, reviewed, gated); QA's skill governs QA — and didn't. It is the only seat-procedure that is
**executable**, which is exactly why it drifted out of the record: prose lands in `docs/` naturally, and code
that isn't the product had nowhere obvious to go, so it went nowhere. `tools/` is the missing home, and the
set closes.

## Honest tiers (do not overclaim on the way in)

- *Changes to QA's procedure are reviewed* → **mechanism.** `main` is gated; a `qa/*` PR is the only path
  into the source.
- *The published copy matches the source* → **discipline.** Self-reported: the platform loads the catalog
  copy at session start, so the match can only ever be self-reported — a genuine platform constraint QA
  verified, not a design shortcut.
- *A drifted publish is visible* → **the stamp** (#98, warn-loud). Per-file `SKILL.md` / `kernel.py` hashes,
  catalog-vs-repo, rendered in the findings-PR provenance block (where review already happens). It graduates
  to mechanism only when CI re-runs the membrane controls against the repo source. **Warn-not-block:** a
  refusal would mean a drifted skill blocks the QA run entirely — friction on the wrong side.

## Accepted cost (named)

Making the skill *source* slows QA's own iteration to **PR-speed** — METHOD.md's "overhead per change," now
aimed at QA's own tooling. It is the correct trade: the skill **is** the membrane, and it is the one artifact
that shipped **two PR-shaped defects with no PR available** — an optional-provenance guard (`reviewed_sha`
defaulting to un-enforced) and a test mock that failed **open into a live write token** (PR #74 / branch
`qa/x`, since cleaned). Warn-don't-block keeps the mid-run patch path open for when the platform copy is the
one that's wrong.

## Executed order

ratify source + home → **relocate** (#93) → lift the **network-free** membrane controls (`verify_red_green`'s
discriminators) into repo tests (#93) → the **stamp** (#98) → **injectable transport** + **delivery-path
guards** (#99). The obsolete skill *mirror* under `docs/qa-config/prospector-branch-qa/` — whose restore
snippet and drift-detector were anchored to a copy *expected* to lag — was deleted (#96): once the skill has
a durable in-repo home, git **is** the known-good copy.

## Provenance

Recorded after the fact — the decision preceded its record (the reasoning is the part that dies when a thread
ends; this preserves it). The anchors are the merged PRs above: #93 (`c50239f`), #96 (`45844a3`), #98
(`ced785a`), #99 (`43c556d`) — executed evidence, verifiable in git.
