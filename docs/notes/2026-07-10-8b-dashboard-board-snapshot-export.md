# §8b — the one-button board-snapshot export: design spec

*Design spec, 2026-07-10. For the build seat (VSCode). Adds a single "download the whole board" export to
the read-only §8b dashboard, producing one self-describing **markdown** report — the review artifact for the
.md-over-Taildrop loop (the human eyeballs it; the design/review seat parses it, in one pass). Governing
docs: spec §8b (dashboard), `ARCHITECTURE.md` §7 (the read-only wall + four writers), the dashboard decision
record (`2026-07-07-dashboard-11.md`), `CLAUDE.md` (read-only / no-run-now CONTRACT). Small slice: the panel
data already exists as tested view-models — this is serialization, not new data logic.*

---

## 1. The problem, and the decision

The dashboard renders every panel, but review requires downloading each section separately, and the
per-panel files (a) don't say what they are — the filename is just the current time — and (b) collide when
two are downloaded in the same minute. Real friction, every session.

Decision:
- **Per-panel downloads — reframed after primary-source contact (build seat, 2026-07-10).** There is no
  editable filename string to "fix": the tables use Streamlit's built-in `st.dataframe` toolbar export, whose
  filename the API does **not** expose. A self-describing per-panel download therefore means an explicit
  `st.download_button`. And once the board-snapshot below exists, a per-panel download's only remaining job is
  *sort/filter one panel in a spreadsheet* — so explicit CSV buttons go on the **sortable panels only (active
  leads, run history, dormant pile)**, named `{panel}_{YYYYMMDDThhmmssZ}` (self-describing, second-resolution,
  collision-free across panels). The built-in toolbar export **remains on every `st.dataframe`** (Streamlit
  gives it free), so no panel loses export. (Original framing "fix the per-panel filenames" superseded; see
  `docs/decisions/2026-07-10-8b-board-snapshot-export.md`.)
- **Add one button → one markdown file:** a board-snapshot of the whole live board, self-describing at the
  top, that the human reads and the review seat parses in one pass. **Add it; do NOT replace the per-panel
  downloads** — the per-panel CSVs stay, for sorting a single panel in a spreadsheet.

**Why markdown (the format is load-bearing).** The export has two readers with different needs: the human
eyeballs it, the review seat parses it. Every panel actually reviewed is flat tabular data → clean markdown
tables render for the human **and** parse straight for the model. JSON is lossless-for-the-model but
unreadable-for-the-human; xlsx is sortable-for-the-human but off the Taildrop-.md loop and heavier for the
model. Markdown is native to the loop that already exists and costs neither reader anything (xlsx/JSON
variants filed deferred, §7).

## 2. Scope — what to build

- **A pure serialization layer** (a new `dashboard/export.py`, or functions in `views.py`) that consumes the
  **existing** view-models and renders one markdown document. No streamlit import, fully unit-tested without
  a browser — the same discipline as `views.py`. `app.py` adds exactly **one** `st.download_button` wired to
  it.
- **The report =** a self-describing manifest header (§3) + the summary panels (§4) + the complete,
  tick-collapsed event timeline of every **active** lead (§4).
- **"Active" here = all-active, INCLUDING shadow** dispersion leads — *not* the `active_nonshadow` paging
  filter. Burn-in timelines are core review material (not paging material, but review material). The
  report's active set = every lead with `status == "active"`, shadow or not.
- **Out of the board-snapshot (targeted drill-downs, not this file):** a *dead/reverted* lead's full history
  (rare forensic case → the per-lead per-panel download on demand); the **deep dispersion payload**
  (sub-cluster membership, centroids, the pairwise matrix — v2 proto-cluster substrate, not review surface;
  it stays in the record, never in this report).

## 3. The manifest (self-describing header — the bigger half of the "what is this file" fix)

The file must announce what it is when opened *anywhere*, independent of its name. Lead with a manifest
block:

- store path; export timestamp (UTC, second-resolution);
- latest run: run-id + date, and that run's `config_changed` / `pushed` / `faults`;
- **active N / ceiling** (the live non-shadow count vs `oracle.active_lead_ceiling`) — plus the ceiling
  banner text **if over**;
- **shadow M** (active shadow-dispersion count);
- heartbeat: OK / BROKEN (+ reason) + last-run date.

The filename fix (§2) solves "what is this file" at the name level; the manifest solves it at the contents
level — the bigger of the two.

## 4. The report body

Summary panels, each a markdown section with a table, in the dashboard's own lead-with-the-live order:

1. **Active leads** (`rank_active_leads`) — live non-shadow, ranked recency × |z|.
2. **Dispersion shadow / burn-in** (`shadow_panel`) — active shadow leads, days-elapsed / target,
   burn-in-complete.
3. **Health** — heartbeat (`heartbeat`) + fault log (`fault_log`).
4. **Run history** (`recent_runs`) — date, run-id, pushed, faults, config-hash.
5. **Dormant pile / launches** (`dormant_pile`, `launch_panel`) — survey-only, unpushed.
6. **Manual-resolution queue** (`manual_queue`) — if non-empty.
7. **Registry health** — as the dashboard renders it.

Then:

8. **Active-lead timelines** — for **every active lead** (non-shadow *and* shadow), the full event history
   via `events_for_lead`, in (ts, event_id) order.
   - **Tick-collapse (keeps timelines dense as histories lengthen).** List the **state-relevant** events
     verbatim — spawn, departure/entry, corroboration/accretion (launch-corroboration, rebalance,
     `mandate.changed`), reversion, verdict, promotion. Collapse a run of consecutive **silent per-cadence
     refresh ticks** (`*.tick` that changed nothing but `latest_z`) into a single line: *"N ticks,
     &lt;first&gt;…&lt;last&gt;, latest z = X."* The fold's trigger vocabulary is the authority on which
     events are state-relevant vs silent-refresh.

## 5. CONTRACT invariants

- **Pure export of stored folds — NO recompute on export (the anti-slot-machine rule, extended).** The
  export reads the **same view-models the runner already wrote** and serializes them; it fetches nothing,
  recomputes nothing, runs no sensor. Click it a hundred times → the same stored snapshot, byte-identical but
  for the export timestamp. The discipline variable is computation cadence, not export convenience — a
  download-all has nothing new to reward re-clicking, and the build must keep it that way (no
  recompute-on-export, ever).
- **Cannot drift from the dashboard.** Because it serializes the *same* tested `views.py` view-models the
  on-screen panels render, the report and the screen can't disagree. This is *why* it stays a read of the
  view-models, not a re-query.
- **Firewall (unchanged).** Reads only this store's own record — never a portfolio, never `portfolio.yaml`,
  never a trade path. The read-only-media / source-grep guard covers it exactly as it covers the dashboard.
- **Bounded by the sensor universe (so it stays reviewable for years).** The active set is bounded by the
  universe: **≤ 55 xcorr pairs + ≤ 11 dispersion baskets = ≤ 66 active leads**, each with a tick-collapsed
  timeline — and in practice far fewer. *(Correction to a claim made in design discussion: the **ceiling does
  NOT cap this** — it banners at N but never suppresses a spawn, so `active_nonshadow` can exceed the
  ceiling; the real bound is the universe size, not the ceiling.)* **Dead/reverted leads accrete in the
  record forever but never in this file** — that is what keeps the report bounded as the system runs.

## 6. Acceptance — tests are the gate (offline, no browser)

Against a seeded store, pure unit tests on the serialization layer:

- **no-recompute / pure-read:** the export issues no fetch and no sensor call; a read-only registry
  suffices; re-running on an unchanged store yields an identical document (modulo the export timestamp).
- **serializes the view-models (no drift):** the report's active-leads / shadow / health / runs sections
  match the corresponding `views.py` view-model outputs exactly (assert against the same outputs the
  dashboard renders).
- **manifest present and correct:** the header carries store, run-id + date, active/ceiling, shadow,
  heartbeat, faults — and the over-ceiling banner when `active_nonshadow` exceeds the ceiling.
- **active = all-active incl shadow:** an active shadow-dispersion lead's timeline appears; a reverted
  lead's does **not**.
- **tick-collapse:** a lead with many silent ticks renders the state-changes verbatim and the ticks as a
  single count-plus-latest-z line (assert the ticks are not listed individually and the count is right).
- **filename:** the per-panel and report filenames are `{panel}_{second-resolution-UTC}`, collision-free
  within a minute.

## 7. Deferred / named

- **`coverage_actual` is not in the report yet** — computed but **not surfaced** (the §5 observability item
  Code deferred in the §9e symbol-resolution fix). It joins the manifest/shadow section **when that lands** —
  do not promise a panel the dashboard doesn't render.
- **Dead-lead full history** — an on-demand per-lead drill-down (the existing per-panel download), not the
  board-snapshot.
- **Deep dispersion payload** (sub-cluster membership / centroids) — v2 proto-cluster substrate; stays in
  the record, out of the review report.
- **xlsx / JSON export variants** — markdown is the review format; a tabbed-xlsx (human sorting) or
  compact-JSON (machine) variant is filed as an idea, not built.

## 8. Sequence

Independent of the §9e merge and §10 — it touches only the read-only dashboard. Small slice: the view-models
exist and are tested; this is serialization + one button. Land it whenever; it does not gate, and is not
gated by, the fix-merge or the sender.
