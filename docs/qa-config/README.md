# QA config snapshot — PROSPECTOR_QA profile

This directory is the durable snapshot of the **`PROSPECTOR_QA` agent profile**, which
originates on the Claude Science platform and has no other home in the repo. If the profile
drifts or is edited by mistake, this is the known-good copy to restore from — the same "anchor
the record outside itself" discipline METHOD.md applies to the code.

> **The QA skill is NOT here.** `prospector-branch-qa` (`SKILL.md` + `kernel.py`) is git-tracked
> at **`tools/qa-skill/`**, where it is reviewed and CI-tested. Git is its durable copy — every
> version, with history, cryptographically. A second copy in this directory would be a duplicate,
> not a backup: it would lag by design, and a restore from it would restore stale bytes. It was
> removed for exactly that reason (see `tools/qa-skill/README.md`). Restore the skill from
> `tools/qa-skill/` (below); its live catalog-vs-repo drift check is the runtime provenance stamp.

**Snapshot taken:** see `MANIFEST.json` (`snapshot_utc`). **Captured from:** the live platform via
`host.agents`.

## What is here

| File | What it is |
|---|---|
| `PROSPECTOR_QA.profile.json` | The user-owned agent profile — machine-restorable (the fields `host.agents.create`/`update` take). `unrestricted: true`. |
| `PROSPECTOR_QA.system_prompt.md` | The profile's identity/system prompt, human-readable + diffable. |
| `MANIFEST.json` | sha256 + byte count of the two profile files above — the drift detector for the profile (which has no git-tracked source). |

**Not here:** the QA **skill** (git-tracked at `tools/qa-skill/`, above) and the 30 `anthropic`-origin
skills (alphafold2, figure-style, customize, …), which are platform-managed and restore themselves.
The profile's connector list is recorded in the profile JSON as `_connectors_at_snapshot` for
reference only: an `unrestricted` profile automatically gets the full live connector set on restore,
so the list is informational, not a thing to replay.

## Detect drift (run any time)

All snippets run in a **`repl`** cell (the control-plane kernel), from the **repo root**, as a seat
with `host.skills`/`host.agents` available.

**Profile** — diff the live `systemPrompt` against the snapshot:

```python
# host.agents.list(), take the PROSPECTOR_QA record, diff its systemPrompt
# against PROSPECTOR_QA.system_prompt.md (below the `---`).
```

**Skill (interim, until the runtime stamp lands)** — the reference is the git source, not a cached
sha. Re-export the live catalog copy and compare to `tools/qa-skill/`:

```python
import hashlib
for f in ("SKILL.md", "kernel.py"):
    live = host.skills.read("prospector-branch-qa", f)["content"]
    repo = open(f"tools/qa-skill/{f}").read()
    same = hashlib.sha256(live.encode()).hexdigest() == hashlib.sha256(repo.encode()).hexdigest()
    print(f, "MATCH" if same else "DRIFT — live catalog diverged from tools/qa-skill/")
```

(Once step 4 lands, this becomes the per-file hash carried in every findings-PR provenance stamp.)

## Restore

All calls run in a **`repl`** cell, from the **repo root**, as a seat with the `customize` skill loaded.

**Restore the skill** from its git-tracked source (`tools/qa-skill/`):

```python
name = "prospector-branch-qa"
host.skills.edit(name, "SKILL.md",  open("tools/qa-skill/SKILL.md").read(),
                 old_string=host.skills.read(name, "SKILL.md")["content"])   # full replace
host.skills.edit(name, "kernel.py", open("tools/qa-skill/kernel.py").read(),
                 old_string=host.skills.read(name, "kernel.py")["content"])
host.skills.publish(name, overwrite=True)   # push to the live catalog
```

(If the skill was deleted entirely, `host.skills.edit(name, "SKILL.md", <content>)` with
`old_string=None` creates it fresh, then add `kernel.py` the same way, then publish. Prefer a
specific tag/commit of `tools/qa-skill/` if you need a known-good older state.)

**Restore the profile** from this snapshot:

```python
import json
p = json.load(open("docs/qa-config/PROSPECTOR_QA.profile.json"))
patch = {k: p[k] for k in ("display_name","description","system_prompt","icon_key","color_key","unrestricted")}
host.agents.update("PROSPECTOR_QA", patch)          # if it still exists
# or, if it was deleted:
# host.agents.create(p["name"], p["display_name"], p["description"], system_prompt=p["system_prompt"])
# then: host.agents.update(p["name"], {"unrestricted": True, "icon_key": p["icon_key"], "color_key": p["color_key"]})
```

## Refresh this snapshot after an intentional profile change

When you deliberately edit the profile, re-run the export so the snapshot tracks the new known-good
state (otherwise the drift check flags your own intended change). Keep the manifest's shas in sync
with the live copies. The **skill** needs no snapshot refresh — it is git-tracked; edit it via a PR
into `tools/qa-skill/` and history is the record.

---

*Scope note: this is a point-in-time copy of the profile. It does not capture platform-managed
skills, connector authorizations, or credentials (those are account/session state, not repo
artifacts). The QA skill lives in `tools/qa-skill/`.*
