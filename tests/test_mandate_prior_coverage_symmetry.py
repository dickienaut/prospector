"""F5 (post-#99 sweep) — a diff must extract BOTH sides with the same discipline, or it is a false diff.

`mandate.scan` vets the CURRENT filing's SGML coverage via `_coverage_verdict`, which refuses to diff
(a review-advisory) when the header is `complete: False` — unfetchable or truncated. The PRIOR side had
no equivalent gate: it passed `series_classes(cik, prior_accession)` straight to `_isolation_args`, which
branches ONLY on `len(series) <= 1`. So a prior whose header FETCH FAILED (transient EdgarError ->
`{series: {}, complete: False}`) is silently treated as a single-fund prior -> `(None, None)` ->
whole-document extraction, while the current side isolates its fund's block. For a NON-FIRST fund in a
multi-fund filing, whole-doc returns the FIRST fund's strategy and the isolated current returns THIS
fund's — a `reliable=True, changed=True` diff from the asymmetry alone. That accretes a spurious
`mandate.changed` onto every live lead touching the fund and writes a permanent event into the
append-only store.

Reproduced on the real Goldman multi-fund body (S000106341 = Goldman Sachs Income ETF, the 2nd covered
series) with identical bytes on both sides. NOT a cross-era bug: headers are fetched on-demand,
accession-keyed, so a "legacy" prior gets its header fetched fresh — the trigger is a transient
prior-header fetch failure, which is exactly what this test models (a registered EdgarError).

Fix (Design-ruled): vet the prior's coverage completeness with the same gate as the current side —
refuse to diff (review-advisory) on `complete: False`, never fall back to whole-doc. Asserts BEHAVIOUR
(no spurious mandate.changed when the prior header is unverifiable), not the disposition wording.

House rule: no test imports a sibling test module — the small harness below is duplicated, not imported.
Authored RED against main 6eccdabf; GREEN against the reference fix (docs/notes/post99_sweep_fixes.diff).
"""
from pathlib import Path

from prospector.ingest.edgar import EdgarError
from prospector.ingest.prospectus import ProspectusIngest
from prospector.sensors import mandate

FIXTURES = Path(__file__).parent / "fixtures" / "prospectus"
GS_BODY = (FIXTURES / "goldman_multifund_body_300911.html").read_bytes()  # real 2-fund rendered body
GS_A, GS_B = "S000106340", "S000106341"          # Core Plus Bond (1st), Income ETF (2nd) — real series
GS_NAMES = ["Goldman Sachs Core Plus Bond ETF", "Goldman Sachs Income ETF"]
CIK = 300911
A = "0001193125-25-280452"   # prior accession
B = "0001193125-26-291833"   # current accession
NOW = "2026-07-03T22:30:00Z"
CFG = {"strategy_headings": ["principal investment strateg",
                             "what are the fund's main investment strateg", "investment objective"],
       "stop_headings": ["principal risk", "principal investment risk", "performance",
                         "fees and expenses", "portfolio management", "purchase and sale",
                         "tax information"],
       "min_section_chars": 80, "max_section_lines": 400}


def _hdr_named(*pairs, complete=True):
    body = "<SEC-HEADER>\n<SERIES-AND-CLASSES-CONTRACTS-DATA>\n"
    for sid, name in pairs:
        body += f"<SERIES>\n<SERIES-ID>{sid}\n<SERIES-NAME>{name}\n"
    body += "</SERIES-AND-CLASSES-CONTRACTS-DATA>\n"
    if complete:
        body += "</SEC-HEADER>\n"
    return body.encode()


GS_HDR = _hdr_named((GS_A, GS_NAMES[0]), (GS_B, GS_NAMES[1]))


class _FakeEdgar:
    """filing_text serves fixture bytes per accession; filing_header serves the SGML header, or RAISES a
    registered EdgarError to model a header-fetch failure (the transient F5 trigger)."""
    def __init__(self, by_accession, headers_by_accession):
        self.by_accession = by_accession
        self.headers_by_accession = headers_by_accession

    def filing_text(self, cik, accession, primary_doc):
        return self.by_accession[accession]

    def filing_header(self, cik, accession):
        v = self.headers_by_accession[accession]
        if isinstance(v, Exception):
            raise v
        return v


def test_prior_header_fetch_failure_does_not_fabricate_a_mandate_change(layout):
    # CURRENT header OK (multi-fund, both funds); PRIOR header fetch FAILS (transient EdgarError).
    # Scan the NON-FIRST fund (Income, GS_B). Both bodies are the SAME bytes — a real diff is impossible;
    # any `mandate.changed` here is purely the isolate-vs-whole-doc asymmetry.
    edgar = _FakeEdgar({A: GS_BODY, B: GS_BODY},
                       {A: EdgarError("edgar down", status=503), B: GS_HDR})
    prospectus = ProspectusIngest(layout, edgar)
    prospectus.pull(GS_B, CIK, A, "prior.htm")   # seed the prior blob (a prior run's baseline)

    events = []
    def report_advisory(subsystem, message, series_id, extra=None):
        events.append({"type": "fault", "payload": {"subsystem": subsystem, "message": message,
                                                     "series_id": series_id,
                                                     "category": "review-advisory", **(extra or {})}})

    result = mandate.scan(GS_B, "GINC", CIK, B, "cur.htm", A,
                          [GS_A, GS_B], set(), prospectus, CFG, NOW, events.append, report_advisory)

    # The bug: a reliable, spurious mandate.changed on identical bytes. The fix: NO mandate.changed —
    # the unverifiable prior coverage is flagged for review instead (asymmetric diff refused).
    assert not any(e.get("type") == "mandate.changed" for e in events), \
        "spurious mandate.changed emitted from prior/current extraction asymmetry"
    assert result["action"] != "mandate_changed"
