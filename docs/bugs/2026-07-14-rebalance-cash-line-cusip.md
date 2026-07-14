# rebalance-cash-line-cusip — a benign cash sweep fires a spurious "restructuring" rebalance

*Bug record, 2026-07-14. Status: **fixed** (reference patch drafted, pending land). Class: §1.1
green-on-synthetic/broken-on-real · §1.5 never-anchor-on-a-ticker (one grain deeper) · §1.8 fails-silently.
Branch `m6-discourse-capture` @ `4739b528bc`.*

- **Symptom.** The §4d rebalance sensor treats a **money-market / cash line's** day-over-day balance wiggle as
  a material holdings change and accretes a `rebalance` ("this basket is restructuring") onto every live lead
  whose baskets include the fund — including **shadow dispersion leads** in their 90-day burn-in, whose
  corroboration record is exactly what a human weighs when deciding to promote a lead to paging. A cash-wiggle
  alarm firing on benign daily cash flow is the §1.7 cry-wolf pattern one layer down, feeding a *silent* false
  corroboration (§1.8). Reproduced through the real `_run_rebalance` over a shadow lead: a pure +1% cash sweep
  (equities identical) → a spurious rebalance accreted. HIGH severity.

- **Root cause.** `_identified` (`prospector/sensors/rebalance.py`) builds the diff over rows it calls
  "identified securities", excluding only rows whose **`identifier` is empty**. The config comment
  (`config/prospector.yaml`) even states the intended contract: *"cash/derivative rows without a CUSIP are
  excluded."* But that premise is false on real data: a live SSGA daily file stamps its cash/money-market and
  currency lines with **populated CUSIP-like identifiers** — the recorded TEKX file carries
  `SSI US GOV MONEY MARKET CLASS` → `924QSGII3` @ 4.22% and `EURO CURRENCY` → `999EURZ94`. So the "no CUSIP"
  exclusion excludes **nothing** on live data; the cash lines enter the diff, and their daily balance moves
  cross the materiality threshold. This is class §1.5 recurring: not the ticker-as-identity error exactly, but
  its sibling — *the identifier field is being trusted to mean "this is a real security position," and it
  doesn't.*

- **Fix.** Add `_is_cash_or_derivative(row)` and exclude those rows in `_identified`, keyed on the **explicit
  `-` TICKER sentinel** SSGA stamps on cash/derivative/currency lines (+ `MONEY MARKET` in the name as
  defense-in-depth), mirroring the cash logic already in `holdings._is_priceable_us_equity`. **Crucially NOT**
  routed through `holdings.priceable_members` (the §9e price-universe gate): that gate also drops **foreign**
  (non-USD) equities — Siemens Energy, Schneider — whose genuine add/drop/reweight **is** a real rebalance
  signal, so using it would silence real foreign restructurings (the R2 caveat). The `-` sentinel excludes cash
  while keeping foreign constituents. Keys on an **explicit** `-` only: a missing/blank ticker column (the
  synthetic test frames omit `ticker` entirely) is treated as "unknown", **not** cash — so the existing
  `test_rebalance_sensor.py` frames are unaffected (all 9 still pass).

- **Regression test.** `tests/test_runner_rebalance_cash_and_prior.py::test_pure_cash_sweep_does_not_accrete_a_
  rebalance`. Freezes a prior/today pair where **only** the money-market line moves (+1%, past the 0.5%
  threshold; every equity constituent identical), the cash line carrying a real CUSIP-shaped identifier, and
  drives `_run_rebalance` over a shadow dispersion lead. Asserts BEHAVIOUR, not mechanism: a pure cash sweep
  accretes **no** rebalance on any lead (a fix by name-sentinel, ticker-sentinel, or any other cash test
  passes). RED on the branch (spurious rebalance); GREEN after the patch.

- **Why the suite missed it (class §1.1 / the convergent-prior root §1.2).** Every existing rebalance fixture
  builds cash-free equity baskets (identifiers `111/222/333`) or a cash line with an *empty* identifier — never
  a cash line with a CUSIP, which is the shape the real file has. Code and fixture shared the wrong prior
  ("cash lines have no CUSIP"), so no in-suite cross-check could catch it; only opening a real SSGA file
  (§1.6) breaks the prior. (Test authoring note: the first draft offset the cash sweep against NVDA, whose 1%
  move *itself* crossed the threshold — a test that would have passed for the wrong reason (§1.4); the final
  version moves only the cash line, letting the weight sum drift within the parser's `[0.5,1.5]` band.)

- **Rule born.** Extends the §1.1 **fixture-provenance discipline** with a concrete instance for the rebalance
  layer: *a holdings fixture that omits real cash/derivative/currency lines cannot exercise the identified-
  security filter.* Reinforces §1.6 (go to the primary source — the real TEKX file is what exposed the
  populated cash CUSIPs). No new CONTRACT; the value is the tag + the R2 caveat recorded so the "obvious" fix
  (`priceable_members`) is not adopted later.

- **References.** `notes/m6_deep_review_findings_qa.md` (R1 + the R2 caveat), `notes/dispersion_foreign_ticker_
  findings.md` (the 9e foreign/cash lesson this builds on), `notes/PROSPECTOR_M6_REVIEW_TESTS_README_QA.md`.
  Sibling bugs by class: H1, H4, P1, 9e-ENR, E1 (§1.1); I1, B1, 9e-ENR, 9e-membermap (§1.5).
