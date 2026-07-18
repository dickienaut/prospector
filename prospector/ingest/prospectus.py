"""Prospectus ingest + mandate extraction (spec §4d mandate-diff, milestone 4).

A fund quietly rewriting what it's *about* is how a position bought for one thesis becomes something
else underneath a long-term holder — so when a watched fund files a new prospectus, the mandate-diff
extracts its **principal-investment-strategy / investment-objective section** and diffs that against
the prior filing. The sensor driver (`sensors/mandate.py`) turns a real change into `mandate.changed`
— a SILENT corroboration the human adjudicates, never a pager.

**Targeted section, NOT full-text (the spine).** A whole-filing diff is a false-positive machine —
fee tables, dates, and legal boilerplate re-file constantly (the diff-trap; the HECO lesson: diffing
a churning source surfaces data-quality churn, not thesis change). Only the strategy section is
compared.

**Three jobs, three owners — a line this module must not blur:**
  - **BeautifulSoup owns STRUCTURE.** `html_to_text` turns messy filing markup into navigable text;
    `extract_mandate` locates the section. That's it. bs4 is boring, understood, correctness-critical
    infrastructure (like numpy / SQLite / boto3) — imported so we don't hand-roll an HTML tokenizer,
    not because parsing is where the judgment lives. It is PINNED (pyproject) because it parses
    external, occasionally-malformed input.
  - **This module owns MEANING** — *which* section is the strategy, and (in `diff_mandate`) whether
    its text changed. Nothing here decides whether a change is *meaningful*.
  - **The human owns SIGNIFICANCE** — cosmetic-vs-substantive is the verdict, downstream (§4d/§5).

**Extraction-unreliable fallback.** Section extraction is fragile across issuers' formats. When it is
unreliable (heading not found, section too short, or a runaway with no boundary), we return
`reliable: False` and the caller FLAGS it (a `fault` for manual review) — a false `mandate.changed`
is worse than a missed one, so we never diff what we couldn't reliably extract.
"""

from __future__ import annotations

import difflib
import re

from bs4 import BeautifulSoup

from prospector.primitives.atomic import write_atomic

_FROZEN_NAME = "index.html"  # the raw prospectus HTML, frozen per accession (blob-per-accession, §7)


class ProspectusIngest:
    """Fetch a fund's prospectus HTML via the (rate-limited, SEC-polite) EdgarClient and FREEZE it
    per accession under ingest/prospectus/{series_id}/{accession}/ BEFORE any parsing (§3). The
    accession keys each filing as its own immutable blob, so the mandate-diff can compare versions."""

    def __init__(self, layout, edgar_client):
        self._layout = layout
        self._edgar = edgar_client

    def pull(self, series_id: str, cik: int, accession: str, primary_doc: str) -> bytes:
        """Fetch the filing's primary document and freeze it before returning. A same-accession
        re-pull overwrites (ingest/ is dated substrate, not the append-only events/ record)."""
        body = self._edgar.filing_text(cik, accession, primary_doc)
        write_atomic(self._layout.prospectus_path(series_id, accession, _FROZEN_NAME), body)
        return body

    def has_frozen(self, series_id: str, accession: str) -> bool:
        return self._layout.prospectus_path(series_id, accession, _FROZEN_NAME).exists()

    def load_frozen(self, series_id: str, accession: str) -> bytes:
        """Re-read a frozen prospectus (pure function of the frozen bytes — extraction is offline
        and re-derivable, so a later, better extractor re-reads old filings with no stored staleness)."""
        return self._layout.prospectus_path(series_id, accession, _FROZEN_NAME).read_bytes()


# --- STRUCTURE (bs4's job ends here) ------------------------------------------------------------

def html_to_text(body: bytes) -> str:
    """SEC prospectus HTML -> plain text. Uses bs4's stdlib `html.parser` backend (no lxml). Block
    structure becomes newlines so section HEADINGS stay on their own lines and remain findable; runs
    of whitespace (incl. non-breaking spaces) collapse; entities are unescaped. Deliberately dumb: it
    turns markup into navigable text and stops — it never decides what any text MEANS."""
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse horizontal whitespace (incl. non-breaking spaces from &nbsp;, which \s matches) to
    # one space per line; keep line breaks so headings stay findable; drop blank lines.
    lines = [re.sub(r"[^\S\n]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _is_heading(line: str, patterns: list[str]) -> bool:
    """A line reads as one of `patterns` when it IS the heading (a short line that starts with the
    pattern, allowing a trailing 's'/':'/'.'), not a passing mention buried in body prose. SEC
    headings sit on their own short line; a long line is prose, never a heading."""
    ln = line.lower().strip().rstrip(":.")
    if not ln or len(ln) > 80:
        return False
    return any(ln == p or ln.startswith(p) for p in patterns)


def _find_heading(lines: list[str], patterns: list[str], start: int = 0) -> int | None:
    for i in range(start, len(lines)):
        if _is_heading(lines[i], patterns):
            return i
    return None


# A 497 filing is not always a full prospectus: the SAME form covers one-page SUPPLEMENT "stickers" and
# the STATEMENT OF ADDITIONAL INFORMATION, neither of which carries a principal-investment-strategy
# section. Diffing one faults spuriously (the extraction-unreliable review-advisory noise), and freezing
# one as a fund's "prior prospectus" contaminates the next real diff. These filings DECLARE themselves —
# a sticker announces "Supplement dated…/Supplement to…", an SAI titles itself — so a structure-only,
# ANCHORED check separates them from a full prospectus (verified against every failing filing in the
# 2026-07-18 diagnosis). See docs/decisions/2026-07-18-mandate-supplement-not-a-prospectus.md.
_SAI_HEADINGS = ("statement of additional information",)
_SUPPLEMENT_HEADINGS = ("supplement dated", "supplement to")
_DECLARE_HEAD_LINES = 45  # the opening window where a filing titles/declares its nature


def is_prospectus_supplement(body: bytes) -> bool:
    """True when the filing is a 497 SUPPLEMENT (sticker) or a STATEMENT OF ADDITIONAL INFORMATION, not
    a full prospectus — the mandate-diff must SKIP it (it carries no strategy section by construction, so
    extracting one faults spuriously; and it must never be diffed against, as a supplement frozen as a
    "prior" contaminates the next real filing's diff). Same three-owner boundary as `extract_mandate`:
    STRUCTURE only, anchored to a heading the filing declares itself with (a short heading-shaped line),
    NEVER a substring buried in body prose — so a full prospectus that merely mentions "supplement" or
    references its SAI is not tripped. A full prospectus (titles itself "Prospectus"/"485…", carries a
    strategy section) → False, and is diffed normally."""
    lines = html_to_text(body).split("\n")
    # SAI titles itself near the top; a full prospectus only *references* the SAI mid-body, so anchor to
    # the opening window.
    if _find_heading(lines[:_DECLARE_HEAD_LINES], list(_SAI_HEADINGS)) is not None:
        return True
    # A sticker announces "Supplement dated…/Supplement to…" — phrases specific to a supplement's own
    # heading (they do not appear as a heading in a full prospectus), so the whole (small) doc is scanned.
    return _find_heading(lines, list(_SUPPLEMENT_HEADINGS)) is not None


# --- MEANING (which section — never significance) -----------------------------------------------

def extract_mandate(body: bytes, cfg: dict) -> dict:
    """Locate and return the principal-investment-strategy / investment-objective section text.
    Returns `{section, reliable, heading, reason}`. `reliable` is False (and `section` None) when the
    strategy heading isn't found, the section is trivially short, or no stop-heading boundary is hit
    before a hard cap (a runaway to EOF) — the caller flags an unreliable extraction rather than
    diffing it. Decides ONLY which text is the section; never whether a change to it is meaningful."""
    lines = html_to_text(body).split("\n")
    stops = [h.lower() for h in cfg["stop_headings"]]

    # `strategy_headings` is a PRIORITY list: prefer the detailed "Principal Investment Strategies"
    # section, fall back to "Investment Objective" only when the richer one is absent (some filings
    # carry only the objective). First pattern that matches any heading line wins.
    start = None
    for pattern in [h.lower() for h in cfg["strategy_headings"]]:
        start = _find_heading(lines, [pattern])
        if start is not None:
            break
    if start is None:
        return {"section": None, "reliable": False, "heading": None,
                "reason": "strategy heading not found"}
    end = _find_heading(lines, stops, start + 1)
    bounded = end is not None
    if end is None:
        end = min(len(lines), start + 1 + int(cfg.get("max_section_lines", 400)))
    section = "\n".join(lines[start + 1:end]).strip()

    if len(section) < int(cfg.get("min_section_chars", 80)):
        return {"section": None, "reliable": False, "heading": lines[start],
                "reason": "section too short to be the strategy"}
    if not bounded:
        return {"section": None, "reliable": False, "heading": lines[start],
                "reason": "no section boundary before cap (runaway extraction)"}
    return {"section": section, "reliable": True, "heading": lines[start], "reason": "ok"}


def _normalize(section: str) -> str:
    """Collapse ALL whitespace to single spaces for the change decision, so a pure formatting/date
    re-flow does not read as a change. Case is preserved (a real wording edit shows; the human, not
    this code, judges whether it matters)."""
    return re.sub(r"\s+", " ", section).strip()


def _summarize(prior_section: str, current_section: str, max_chars: int = 800) -> str:
    """A compact, human-readable unified line-diff of the strategy section — the go-look content for
    the human's cosmetic-vs-substantive verdict. Bounded so the event payload stays small."""
    diff = "\n".join(difflib.unified_diff(
        prior_section.splitlines(), current_section.splitlines(),
        fromfile="prior", tofile="current", lineterm=""))
    return diff[:max_chars] + ("…" if len(diff) > max_chars else "")


def diff_mandate(prior_body: bytes, current_body: bytes, cfg: dict) -> dict:
    """Diff the strategy section across two prospectus filings. PURE, and deliberately narrow:
    returns `{changed, reliable, summary, reason}` — whether the section TEXT differs, never whether
    the difference is meaningful. If either extraction is unreliable, the whole diff is
    `reliable: False` (the caller flags it, emits no change). Otherwise the whitespace-normalized
    sections are compared: a formatting/date/fee re-file normalizes identical -> `changed: False`; a
    wording change -> `changed: True` with a bounded unified-diff `summary`. Cosmetic-vs-substantive
    is NOT decided here — that is the human's verdict (mandate.changed is a silent corroboration)."""
    prior = extract_mandate(prior_body, cfg)
    current = extract_mandate(current_body, cfg)
    if not (prior["reliable"] and current["reliable"]):
        reason = prior["reason"] if not prior["reliable"] else current["reason"]
        return {"changed": False, "reliable": False, "summary": None, "reason": reason}
    changed = _normalize(prior["section"]) != _normalize(current["section"])
    summary = _summarize(prior["section"], current["section"]) if changed else None
    return {"changed": changed, "reliable": True, "summary": summary, "reason": "ok"}
