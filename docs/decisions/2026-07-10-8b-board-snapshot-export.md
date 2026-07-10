# §8b — the board-snapshot export + the per-panel-filename reframe

*Decision record, 2026-07-10. Implements the design doc `docs/2026-07-10-8b-dashboard-board-snapshot-export.md`
against spec §8b/§11 (read-only wall, no recompute/no-run-now). A small slice: the panel data already exists
as pure, tested `dashboard/views.py` view-models — this is serialization + download buttons, not new data
logic.*

## What landed

- **`prospector/dashboard/export.py`** — a **pure** serialization layer (no streamlit, unit-tested without a
  browser, same discipline as `views.py`). `board_snapshot_markdown(registry, states, runs, machine, cfg,
  now, store_path)` renders one self-describing markdown board-snapshot: a **manifest header** + the summary
  panels + the **tick-collapsed timeline of every ACTIVE lead (non-shadow AND shadow)**. Plus `rows_to_csv`
  and the filename helpers (`board_snapshot_filename`, `panel_csv_filename`).
- **`app.py`** — **one** `st.download_button` for the board-snapshot `.md` (top, the review artifact), and
  explicit CSV download buttons on the **sortable panels only** (active leads, run history, dormant pile).

## The reframe (Agent 1's finding — the doc's §2 corrected)

The design doc's §2 said "fix the per-panel filenames." Primary-source contact refuted the premise: **there
is no editable filename string.** The tables use Streamlit's built-in `st.dataframe` toolbar export, whose
filename the API does **not** expose — so a self-describing per-panel download means an explicit
`st.download_button`, not a tweak. That reframes the fork from build-vs-not to *how many buttons*, and the
board-snapshot answers it: once the `.md` is the review path, the per-panel download's only remaining job is
**sort/filter one panel in a spreadsheet**. So explicit CSV buttons go on the **genuinely-sortable panels
only** (active leads, run history, dormant pile) — not health/shadow/timelines (you read those, you don't
sort them). The built-in toolbar export stays on **every** `st.dataframe` for free, so no panel loses export;
the explicit buttons only add the self-describing `{panel}_{YYYYMMDDThhmmssZ}` filename where a spreadsheet
workflow actually exists. The design doc's §1 decision bullet is rewritten to match.

## Load-bearing choices

- **Tick-collapse authority = the fold vocabulary.** The ONLY silent-refresh events are `xcorr.tick` /
  `dispersion.tick` (they update `latest_z`, nothing in the {status,shadow,verdict} trio — `fold._apply`).
  A run of them collapses to one *"N ticks, first…last, latest z = X"* line (X = the **last tick's payload
  z**, so a mid-timeline block is honest, not the final fold `latest_z`); every other recognized event is
  state-relevant and rendered verbatim. This keeps timelines dense as histories lengthen.
- **Active = all-active INCLUDING shadow** (`[s for s in states if s["status"] == "active"]`, NOT
  `active_nonshadow`): burn-in timelines are review material. **Reverted leads never enter the file** — that
  is the bound that keeps the report reviewable for years (dead leads accrete in the record forever, not here;
  the active set is ≤ 55 xcorr pairs + ≤ 11 dispersion baskets = ≤ 66).
- **`config_changed` for the latest run** is derived as `runs[0].config_hash != runs[1].config_hash` (a
  config.changed fossil would have been emitted) — from the two most-recent `recent_runs` rows, **no run-log
  file read**; "n/a (first run)" when <2 runs.
- **Filenames reuse `store/layout.ts_compact`** (`YYYYMMDDThhmmssZ`) — the same second-resolution form the
  event/snapshot fossils use.

## CONTRACT invariants (enforced + tested)

- **Pure export of stored folds — NO recompute on export** (anti-slot-machine, extended): fetches nothing,
  runs no sensor; a `mode=ro` Registry suffices; re-running on an unchanged store yields a byte-identical
  document (proven).
- **Cannot drift from the screen** — serializes the *same* `views.*` view-models the panels render, never a
  re-query (proven: the report's sections match the view-model outputs).
- **Firewall** — `export.py` imports only `views` + `layout` + stdlib; reads only this store's own record;
  no streamlit, no portfolio / `portfolio.yaml` / trade path. The source-grep guard covers it.

## Deferred / named (not built)

`coverage_actual` (computed but not surfaced — joins the manifest/shadow section when the §9e observability
item lands) · dead/reverted-lead full history (the on-demand per-lead download) · the deep dispersion payload
(sub-cluster/centroids — v2 proto-cluster substrate, stays in the record) · xlsx / JSON export variants
(markdown is the review format for the .md-over-Taildrop loop).

## Verification

Full suite **520 passed / 1 xfailed** (+9 in `tests/test_dashboard_export.py`: pure-read/readonly-determinism,
no-drift, manifest + over-ceiling banner, all-active-incl-shadow-but-not-reverted, tick-collapse, filenames +
csv). Existing `test_dashboard_app.py` / `test_dashboard_readonly.py` still pass — the buttons add no write;
the read-only-substrate firewall is untouched. Independent of §9e and §10 — touches only the read-only
dashboard.

## Follow-up (review feedback): Launches panel legibility

The first board-snapshot review surfaced two issues in the **Launches (survey)** section — **all names
blank** and **one blank ticker**. Both traced to source (not export bugs — the export faithfully renders
`launch_panel`, so the same shows on the live dashboard): the mf-tickers feed carries no name (the launch
sensor records `name_raw=None` by design — a deferred enrichment), and a mf series with an empty `symbol` is
recorded as a `("", seriesId)` launch. Fixed as **pure view-model changes** (owner + design thread), fixing
the live dashboard and the export at once:

- **Dropped the `name` column** from `launch_panel` + the export — structurally empty at the survey stage; a
  column of "—" reads as missing-data where the truth is not-yet-enriched. It returns when the deferred
  name-enrichment slice is built (unchanged on the deferred list — building it now to fill a cosmetic gap
  would be scope-creep, so it was NOT built).
- **Filtered unlisted (empty-ticker) rows** from the survey table — a survey of LISTED launches shouldn't
  list a no-ticker series. **A view filter, NOT a launch-detection change** (the capture-broadly/filter-at-
  the-view discipline: the §4c sensor and the append-only record keep every detection). Crucially, the
  filtered row is **kept counted as a coverage fact** (`views.unlisted_launch_count` → an "N unlisted
  (no-ticker) detections kept in the record" line on the panel + export) — a no-ticker series is a real
  blind spot (a fund the universe can't yet resolve to a ticker); filtering it from the table must not make
  it silently vanish from the visible surface.

**Upstream nuance noted, NOT fixed here:** a series first seen with an empty symbol is *sticky* — `register_
launch` dedups on `series_id`, so a later real ticker for the same series isn't re-recorded (the blank-ticker
`launch.unverified` stands). A known launch-sensor consideration; out of scope for this view-model fix.
