# QA config snapshot — PROSPECTOR_QA profile + prospector-branch-qa skill

> **Source-of-truth update (2026-07-17).** The **skill** (`prospector-branch-qa`:
> `SKILL.md` + `kernel.py`) is now sourced from **`tools/qa-skill/`**, where it is
> reviewed and CI-tested — the repo is the source, publishing to the platform is the
> deploy. Treat `tools/qa-skill/` as authoritative for the skill; the skill copy in
> this directory is a convenience mirror only and may lag. This directory remains the
> **home for the `PROSPECTOR_QA` profile** (`*.profile.json` / `*.system_prompt.md`),
> which has no other repo home, and a one-stop restore bundle. See
> `tools/qa-skill/README.md` for the source/deploy discipline.

The QA seat's **agent profile** and **skill** originate on the Claude Science platform.
If they drift or are edited by mistake, there is no undo unless a known-good copy exists
somewhere durable. This directory is that copy — the same "anchor the record outside itself"
discipline METHOD.md applies to the code, pointed at the QA infrastructure. (As of the update
above, the skill's authoritative copy is `tools/qa-skill/`, not this snapshot.)

**Snapshot taken:** see `MANIFEST.json` (`snapshot_utc`). **Captured from:** the live platform via
`host.agents` / `host.skills`.

## What is here (and what is deliberately NOT)

| File | What it is |
|---|---|
| `PROSPECTOR_QA.profile.json` | The user-owned agent profile — machine-restorable (the fields `host.agents.create`/`update` take). `unrestricted: true`. |
| `PROSPECTOR_QA.system_prompt.md` | The profile's identity/system prompt, human-readable + diffable. |
| `prospector-branch-qa/SKILL.md` | The personal skill's instructions, verbatim. |
| `prospector-branch-qa/kernel.py` | The skill's kernel sidecar (the QA helper functions: `fetch_prospector_branch`, `deliver_qa_findings_pr`, `verify_red_green`, `check_diff_hygiene`, `provenance_stamp`, `qa_git_env`), verbatim. |
| `MANIFEST.json` | sha256 + byte count of each file above — the drift detector. |

**Not exported:** the 30 `anthropic`-origin skills (alphafold2, figure-style, customize, …) are
platform-managed and restore themselves — they are not "our config." The profile's connector list
is recorded in the profile JSON as `_connectors_at_snapshot` for reference only: an `unrestricted`
profile automatically gets the full live connector set on restore, so the list is informational,
not a thing to replay.

## Detect drift (run any time)

Re-export the live artifacts and compare against `MANIFEST.json`. A changed sha256 = the live copy
diverged from this snapshot. From a Claude Science session as the QA seat (or any seat with
`host.skills`/`host.agents`), in a `repl` cell:

```python
import hashlib
live = {
  "prospector-branch-qa/SKILL.md":  host.skills.read("prospector-branch-qa","SKILL.md")["content"],
  "prospector-branch-qa/kernel.py": host.skills.read("prospector-branch-qa","kernel.py")["content"],
}
for k,v in live.items():
    print(k, hashlib.sha256(v.encode()).hexdigest())
# compare each against MANIFEST.json["files"][k]["sha256"]
```

(For the profile: `host.agents.list()`, take the `PROSPECTOR_QA` record, and diff its
`systemPrompt` against `PROSPECTOR_QA.system_prompt.md` below the `---`.)

## Restore (if the live copy is wrong and this snapshot is right)

All calls run in a **`repl`** cell (the control-plane kernel), as a seat that has the `customize`
skill loaded.

**Restore the skill** (SKILL.md + kernel.py):

```python
name = "prospector-branch-qa"
host.skills.edit(name, "SKILL.md",  open("qa-config/prospector-branch-qa/SKILL.md").read(),
                 old_string=host.skills.read(name,"SKILL.md")["content"])   # full replace
host.skills.edit(name, "kernel.py", open("qa-config/prospector-branch-qa/kernel.py").read(),
                 old_string=host.skills.read(name,"kernel.py")["content"])
host.skills.publish(name, overwrite=True)   # push to the live catalog
```

(If the skill was deleted entirely, `host.skills.edit(name, "SKILL.md", <content>)` with
`old_string=None` creates it fresh, then add `kernel.py` the same way, then publish.)

**Restore the profile:**

```python
import json
p = json.load(open("qa-config/PROSPECTOR_QA.profile.json"))
patch = {k: p[k] for k in ("display_name","description","system_prompt","icon_key","color_key","unrestricted")}
host.agents.update("PROSPECTOR_QA", patch)          # if it still exists
# or, if it was deleted:
# host.agents.create(p["name"], p["display_name"], p["description"], system_prompt=p["system_prompt"])
# then: host.agents.update(p["name"], {"unrestricted": True, "icon_key": p["icon_key"], "color_key": p["color_key"]})
```

## Refresh this snapshot after an intentional change

When you deliberately edit the profile or skill, re-run the export so the snapshot tracks the new
known-good state (otherwise the drift check will flag your own intended change). The export
procedure is the one that produced this directory; keep the manifest's shas in sync with the live
copies.

---

*Scope note: this is a point-in-time copy. It restores the profile identity and the skill's files;
it does not capture platform-managed skills, connector authorizations, or credentials (those are
account/session state, not repo artifacts).*
