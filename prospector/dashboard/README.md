# `prospector/dashboard/` — the read-only Streamlit surface

The forensic window onto the fossil record: ranked active leads, the dispersion shadow panel,
the manual-resolution queue, the coverage/dormant pile, the macro catalog, the fault log, and
the weekly dead-man. It renders **folds of the record the runner already wrote** — it never
triggers a sensor, a fetch, or a computation. Implements spec §11. **Built.**

## Modules

- **`views.py`** — the **pure** view-models. Each function shapes stored events/snapshots into
  what a panel renders: `rank_active_leads` (where the wired §4a xcorr firings surface,
  `off-thesis-real` filtered out at the boundary), `shadow_panel` (honestly-empty until §4b is
  wired), `dormant_pile` (the §10 blindness map), `heartbeat` (the weekly dead-man), `manual_
  queue`, `macro_catalog`, `fault_log`, `registry_health`, `lead_timeline`. **No `streamlit`
  import, no writes, no recompute** — so the whole layer is testable offline without a browser.
- **`app.py`** — the thin `st.*` render shell (`main()`). Reads config + store paths from
  `PROSPECTOR_CONFIG` / `PROSPECTOR_STORE`, folds the record via `views`, and renders it: the
  dead-man + ceiling up top, then evidence / blindness / health, with the rest a click deeper
  in collapsed expanders.

## Important to know

- **Read-only (CONTRACT §11), enforced at the substrate.** `app.py` opens the registry with
  `readonly=True` (`mode=ro`) — merely viewing issues no WAL PRAGMA / DDL / commit and cannot
  mutate the store the runner owns. There is deliberately **no autorefresh and no run-now**: the
  discipline variable is computation cadence, not display richness (a surface that only renders
  stored runs cannot reward compulsive checking).
- The split is deliberate: keeping all shaping in `views` (pure, tested) makes `app.py` a thin,
  swappable skin. Match this when adding a panel — logic in `views`, `st.*` only in `app`.
- `streamlit` is an **optional extra** (`uv sync --extra dashboard`); `views` stays
  streamlit-free so importing it (tests, the firewall grep) never requires the extra.
- The **macro catalog** is read-only context for human adjudication — never a trade/tilt
  trigger, never a "regime forming" alert stream (same rule class as the reading-list wall).

## See also

- Spec §11 in `docs/prospector-v1-spec-rev15-2026-07-16.md`; `ARCHITECTURE.md` §2 (module map)
  and §9 (built vs deferred, incl. the deferred §4b dispersion vertical).
- `docs/decisions/2026-07-02-crash-flags-guidance-rev2.md` §8 (the macro-catalog posture).
