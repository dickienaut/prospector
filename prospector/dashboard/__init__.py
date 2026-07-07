"""The §11 read-only dashboard. `views` holds the pure view-models (folds of the fossil record,
no streamlit / no writes / no recompute — fully tested); `app` is the thin Streamlit render shell
(imported only when the `dashboard` extra is installed). CONTRACT: read-only, no run-now, no
autorefresh — the discipline variable is computation cadence, not display richness (spec §11)."""
