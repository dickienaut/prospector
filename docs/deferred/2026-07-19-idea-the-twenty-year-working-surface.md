# The twenty-year working surface — where the human actually sits

**What this is:** a **living, additive** idea note — captured, not queued. It collects observations
about the surface the *owner* works on, as distinct from the record the machine writes. Started
2026-07-19 from a concrete trigger (below); **add to it freely.** Nothing here is a decision. Anything
that becomes one graduates to `docs/decisions/` via the design thread; anything that touches a CONTRACT
never changes here.

**The frame that started it:** *"I'm going to need a surface to work on for the next 20+ years."* The
horizon is not decoration. Prospector's whole premise is a 17+ year holding period and a fossil record
that is never edited. The **record** is built for that horizon. The **surface** — the thing a human
opens on a Sunday evening — was built for a system that was three weeks old, and it shows.

---

## 1. The trigger — what surfaced this

The 2026-07-19 tick produced 7 `strategy-section extraction unreliable` review-advisories, each ending
in the words **"— manual review."** The natural question was *"how do I review them?"* The honest
answer:

- The **weekly heartbeat email** has a purpose-built section (`Manual review — advisories`,
  `runner/email_render.py`) — but its source is `views.fault_log(registry, limit=20)`, the **20 most
  recent fault events**. During the ~30–60/day stretch it was showing a fraction, silently.
- The **dashboard** shows them as undifferentiated rows in one flat `Health · fault log` table
  (`dashboard/app.py`), with no filter, no sort, and no CSV download (the leads panels have one). Its
  caption still reads *"A fault always paged (§10)"* — **stale since the taxonomy split**; advisories
  do not page unless `on_live_lead`.
- The **CLI** has nothing. `pros lead show _system` dumps advisories interleaved with every other
  system event, payload truncated to 100 chars.
- There is **no way to mark one reviewed.** No ack, no dismiss, no resolve — anywhere.
- `capture_budget` has **no human read surface at all**, though `ingest/capture.py`'s docstring says it
  is "visible to the dashboard."

None of this is a bug. Every piece was a correct decision for a young system. The point is that the
decisions were made against a *weeks* horizon and are now being asked to serve a *decades* one.

## 2. The structural insight — two artifacts, two lifetimes

The thing worth not losing from this session:

> **The fossil record and the working surface are different artifacts with different laws, and the
> project currently has only the first.**

The record is append-only, permanent, machine-written, and complete. Those properties are exactly right
and non-negotiable. But they make it a **poor working surface**, because a working surface needs the one
thing the record forbids: **mutable, personal, disposable state** — *I have looked at this. I have not
looked at that. Remind me in a month. This one is noise, stop showing me.*

Today those two are conflated, so "review the queue" means "read the log," and there is nothing to read
*against*. The absence of an ack surface is not an oversight — it is what happens when the only
substrate available is one that forbids mutation.

**Two candidate resolutions, deliberately both left open** (this is a design-thread question, not a
build-seat one):

- **(a) Review state as events.** `advisory.reviewed` / `advisory.muted` as new event types. Fits the
  constitution perfectly — *a changed mind is a new event that supersedes, never an edit* — and the
  fold materializes "currently open" from the record, exactly like verdicts already work. Costs: it
  puts human bookkeeping into the same stream as machine observation, which may be exactly what you
  do **not** want cluttering the fossil record.
- **(b) A separate working index.** A store outside `events/`, rebuildable and discardable, holding only
  attention state. Keeps the record pure. Costs: a second source of truth, and the honest question of
  what happens when it is lost (answer: nothing important — it is attention, not evidence, and can be
  rebuilt by re-triaging).

The existing `resolution_queue` (`identity/resolution.py`) is a **precedent for (b)**: it is the only
queue with a terminal state (`status='resolved'`), and it is explicitly a working index, not the record.
It has worked well. That is real evidence, not speculation.

## 3. What actually changes over twenty years

Worth being specific, because these are the forces the surface has to survive:

1. **Volume compounds; attention does not.** At ~7–60 advisories/day the fossil record grows without
   bound while the reader's weekly budget stays roughly one coffee. Any surface whose default view is
   *"most recent N"* silently drops the tail forever. The email's `limit=20` is this failure already
   happening.
2. **You will forget your own reasoning.** The 2046 reader is not the 2026 author. This project is
   unusually well defended here — decision records, the bug register, spec-citing docstrings — and that
   defence covers *the code*. It does not yet cover *the operating history*: "why did I mark this
   dormant in 2031?" has no home.
3. **Silence must stay meaningful.** The §8a dead-man works because silence is unambiguous. Every
   surface addition is a chance to make silence ambiguous. This is the one property most worth
   protecting and the easiest to erode by accident.
4. **The rare event is the whole point.** A tool that fires meaningfully a handful of times per decade
   must be **legible after long gaps**. The surface's hardest job is not the daily tick — it is being
   openable after eight quiet months without a re-orientation cost that makes you skip it.
5. **The instrument itself will drift.** Extractors, feeds, and filing formats change (this session
   alone: xlsx-not-CSV, blank sector columns, hard-wrapped headings). A twenty-year surface needs a
   view of **"how well is the machine currently seeing?"** — coverage and blind spots — not just what it
   found. Today `holdings-unavailable → dormant` and `sectors_unresolved` are first-class *dispositions*
   in the record with no first-class *display*.

## 4. Standing constraints — anything proposed here must clear these

Not negotiable, and listed so ideas below are born compliant:

- **No run-now surfaces.** No buttons, commands, or endpoints that trigger recompute or capture. Record
  on cadence; push on state change. No dashboard autorefresh.
- **Read-only at the substrate.** The dashboard opens the registry `readonly=True` / `mode=ro`.
- **The reading-list wall.** No surface places, sizes, or recommends a trade. The macro catalog stays
  read-only context — never an alert stream, never piped anywhere actionable.
- **No LLM text as data (v1).** No model-generated prose persisted as record content. A surface may
  *display* a summary; it must not *store* one as a record.
- **Append-only.** Corrections are new events. Any review-state design must respect this or live
  outside `events/` deliberately (§2).
- **No auto-tuning.** A surface may *show* that a threshold is aging; it must never move one.

## 5. The backlog — append freely

Status: 💡 idea · 🔎 worth investigating · 📐 wants a design thread · ❄️ parked. Nothing here is queued.

| # | Idea | Why | Status |
|---|------|-----|--------|
| 1 | **Review state for advisories** — pick (a) events or (b) working index, per §2 | The "manual review" instruction currently has no mechanism at all | 📐 |
| 2 | **Uncap / paginate the email advisory section**, or replace the raw list with counts + a "what's new since you last looked" delta | `limit=20` silently truncated during the noisy stretch — the failure mode is invisible by construction | 💡 |
| 3 | **Advisory panel on the dashboard** — filter by `category`, `subsystem`, `on_live_lead`; CSV download like the leads panels | Today they're undifferentiated rows in the fault log | 💡 |
| 4 | **Fix the stale fault-log caption** (*"A fault always paged (§10)"*) | Factually wrong since the taxonomy split; a doc-drift row waiting to happen | 💡 (small, do anytime) |
| 5 | **A "how well am I seeing?" coverage panel** — holdings coverage, `sectors_unresolved`, dormant-for-blind-spot vs dormant-for-real | The blind spot is recorded but not displayed; §5 above | 🔎 |
| 6 | **`capture_budget` read surface** | Table exists, docstring claims it's visible, nothing reads it | 💡 |
| 7 | **An operating journal** — the owner's own dated notes against a lead, alongside the machine's events | Defends against §3.2 (forgetting your reasoning) where decision records don't reach | 📐 |
| 8 | **"Since you last looked" as the primary frame** rather than "most recent N" | Directly addresses §3.1; makes long gaps safe, which is the rare-event requirement | 🔎 |
| 9 | **A yearly/decade retrospective view** — what fired, what graduated, what the lag distribution looks like over time | The cross-stream lag is currently an existence proof; over 20 years it could become a measured rate | 🔎 |
| 10 | **Advisory triage by shape, not by document** — today 7 advisories were 4 documents and *1 root cause* | The unit of human attention should be the cause, not the row; would have collapsed a 30/day stream to one item | 🔎 |
| 11 | **A physical/ambient surface** — e-ink, a single status pane, something that is *already open* rather than something you must decide to open | Twenty years of "remember to check the dashboard" loses to twenty years of glancing | ❄️ |

*(Add rows. Ideas are cheap here by design; the wall is at `docs/decisions/`.)*

## 6. The one thing I'd argue for first

If only one item is ever built: **#10, triage by shape.** Today's 7 advisories were **4 documents and
exactly 1 root cause**. The surface presented them as 7 rows, and the volume (30–60/day earlier in the
week) read as "the machine is noisy" when it actually meant "one parser assumption is wrong." A surface
that had grouped by *cause* rather than by *occurrence* would have said that out loud, days earlier, in
one line.

That is the generalizable point, and it is the same lesson the fix itself produced: **the row is not the
unit of attention — the cause is.** Over twenty years, the difference between a surface that shows
occurrences and one that shows causes is the difference between one you keep opening and one you stop
opening.
