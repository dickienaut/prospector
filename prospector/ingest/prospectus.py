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

from prospector.ingest.edgar import EdgarError
from prospector.primitives.atomic import write_atomic

_FROZEN_NAME = "index.html"  # the raw prospectus HTML, frozen per accession (blob-per-accession, §7)
_FROZEN_HEADER_NAME = "header.txt"  # the raw SGML submission header, frozen per accession (series-coverage)


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

    def series_sharing(self, accession: str) -> list[str]:
        """Every series that holds THIS accession frozen, sorted. More than one means several series
        point at a single filing — so at most one of them legitimately owns it.

        WHY IT MATTERS: a fund's prospectus resolves at REGISTRANT (trust) level, not series level
        (bug B1), so a trust's combined filing is frozen under each of its series. `extract_mandate`
        then takes the first strategy section it can bound, and every one of those series diffs the
        SAME (first) fund's strategy. Observed live: a Goldman Sachs ETF Trust 485APOS carrying TWO
        strategy sections is claimed by two series, which on 2026-07-19 emitted two BYTE-IDENTICAL
        `mandate.changed` events — exactly one of which can be right.

        Read from the BLOB STORE, never the registry's `prospectus_accession` — same §9c invariant
        the mandate prior obeys: the sensor's state is its frozen blobs, and an identity pass earlier
        in the same run may have moved the registry field. See
        `docs/notes/2026-07-19-mandate-pair-blindness-and-multifund-sections.md`."""
        # .../ingest/prospectus/{series_id}/{accession}/index.html -> parents[2] is the prospectus root.
        # Derived from the layout rather than rebuilt by hand, so a path change can't silently orphan this.
        base = self._layout.prospectus_path("_", accession, _FROZEN_NAME).parents[2]
        return sorted(p.parent.parent.name for p in base.glob(f"*/{accession}/{_FROZEN_NAME}"))

    # --- SGML SERIES/CLASS header: which series a filing ACTUALLY covers (B1 series-scoped confirmation) ---
    # Frozen ACCESSION-keyed (series-independent bytes: the same header covers every series of the filing),
    # not per-series like the body — so a filing over-attributed to a wrong series doesn't get a wrong-fund
    # header copied under it, and the coverage-aware prior walk reuses one frozen copy across the trust.

    def has_frozen_header(self, accession: str) -> bool:
        return self._layout.prospectus_header_path(accession, _FROZEN_HEADER_NAME).exists()

    def pull_header(self, cik: int, accession: str) -> bytes:
        """Fetch the filing's SGML submission header and freeze it (accession-keyed) before returning."""
        body = self._edgar.filing_header(cik, accession)
        write_atomic(self._layout.prospectus_header_path(accession, _FROZEN_HEADER_NAME), body)
        return body

    def load_frozen_header(self, accession: str) -> bytes:
        return self._layout.prospectus_header_path(accession, _FROZEN_HEADER_NAME).read_bytes()

    def series_classes(self, cik: int, accession: str) -> dict:
        """The filing's SERIES/CLASS coverage (freeze-once, then re-read): the parsed
        `<SERIES-AND-CLASSES-CONTRACTS-DATA>` header. Returns `parse_series_classes`'s three-signal dict.
        A header we cannot FETCH (EDGAR error) degrades to `complete: False` — "coverage unknown" — so the
        caller FAULTS (flag, don't guess) exactly as it does for a truncated header; it never silently
        reads "not covered" from a fetch that failed. Other errors propagate (a real bug, not a not-yet)."""
        try:
            if not self.has_frozen_header(accession):
                self.pull_header(cik, accession)
            body = self.load_frozen_header(accession)
        except EdgarError as e:
            return {"series": {}, "complete": False, "has_series_block": False,
                    "reason": f"series/class header fetch failed: {e}"}
        return parse_series_classes(body)


# --- STRUCTURE: SGML SERIES/CLASS header (which series the filing declares — never significance) ---

# The SEC full-submission SGML header is line-oriented tag/value (`<TAG>value`, no closing tag on leaf
# lines), so it is parsed by walking lines, not with bs4 (that owns the HTML BODY). The block we want:
#   <SERIES-AND-CLASSES-CONTRACTS-DATA> … <SERIES> <SERIES-ID>S00…</> <SERIES-NAME>…</>
#     <CLASS-CONTRACT-ID>C00…</> <CLASS-CONTRACT-TICKER-SYMBOL>GCPB</> … </SERIES-AND-CLASSES-CONTRACTS-DATA>
_SGML_TAG = re.compile(r"^<([A-Za-z0-9-]+)>(.*)$")


def parse_series_classes(header_bytes: bytes) -> dict:
    """Parse a filing's SGML submission header into its SERIES/CLASS coverage. Returns
    `{"series": {series_id: {"name": str, "tickers": [str]}}, "complete": bool, "has_series_block": bool}`.

    This is B1's deferred series-scoped confirmation source (`edgar.py` `confirm_prospectus` docstring;
    decision `2026-07-06-identity-integrity.md`): the submissions JSON has no series dimension, so
    `latest_prospectus` returns the trust's newest filing for EVERY series of a CIK — but this header says
    which series the filing actually covers. STRUCTURE only (which series the filing declares), never which
    change matters.

    THREE distinct signals, never collapsed (the fail-silent trap this repo keeps getting bitten by):
      - `series` populated (+ `has_series_block` True) — AUTHORITATIVE coverage. A `series_id` absent from
        it is genuinely not covered (registrant-level over-attribution, B1).
      - `complete` True, `has_series_block` False — the filing declares NO series block (an older / non-fund
        form). Benign "no series data", NOT "not covered" — the caller must not read absence as exclusion.
      - `complete` False — the header is TRUNCATED (`</SEC-HEADER>` never seen) or unfetched. Coverage is
        UNKNOWN; the caller FAULTS (flag, don't guess), never reads "not covered" from partial bytes."""
    text = header_bytes.decode("latin-1", errors="replace")
    complete = "</SEC-HEADER>" in text.upper()
    series: dict[str, dict] = {}
    in_block = False
    cur_id: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("<"):
            continue
        up = line.upper()
        if up.startswith("<SERIES-AND-CLASSES-CONTRACTS-DATA>"):
            in_block, cur_id = True, None
            continue
        if up.startswith("</SERIES-AND-CLASSES-CONTRACTS-DATA>"):
            in_block, cur_id = False, None
            continue
        if not in_block:
            continue
        m = _SGML_TAG.match(line)
        if not m:
            continue
        tag, val = m.group(1).upper(), m.group(2).strip()
        if tag == "SERIES-ID":
            cur_id = val
            series.setdefault(cur_id, {"name": "", "tickers": []})
        elif tag == "SERIES-NAME" and cur_id:
            series[cur_id]["name"] = val
        elif tag == "CLASS-CONTRACT-TICKER-SYMBOL" and cur_id and val and not val.startswith("["):
            series[cur_id]["tickers"].append(val)  # a placeholder "[ ]" (preliminary filing) is not a ticker
    # "has a usable series map" — a present-but-empty block (or one truncated before any SERIES-ID) is
    # NOT authoritative coverage, so it must fall to the benign / truncated dispositions above.
    return {"series": series, "complete": complete, "has_series_block": bool(series)}


# --- STRUCTURE (bs4's job ends here) ------------------------------------------------------------

# Tags that END a line. Everything else — b, i, span, font, a, sup, ix:nonNumeric … — is INLINE and
# must NOT break the text. This list is the whole of `html_to_text`'s structural judgment.
_BLOCK_TAGS = frozenset((
    "p", "div", "br", "hr", "table", "tr", "td", "th", "caption",
    "ul", "ol", "li", "dl", "dt", "dd",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "aside", "nav", "main",
    "blockquote", "pre", "address", "center", "figure", "figcaption",
    "form", "fieldset", "tbody", "thead", "tfoot",
))

# A sentinel marking a line break WE derived from block structure, so it survives the whitespace
# collapse below that erases every break the SOURCE bytes happened to contain. NUL cannot occur in
# the extracted text, so it can never be confused with document content.
_BREAK = "\x00"


def html_to_text(body: bytes) -> str:
    """SEC prospectus HTML -> plain text. Uses bs4's stdlib `html.parser` backend (no lxml). Block
    structure becomes newlines so section HEADINGS stay on their own lines and remain findable; runs
    of whitespace (incl. non-breaking spaces) collapse; entities are unescaped. Deliberately dumb: it
    turns markup into navigable text and stops — it never decides what any text MEANS.

    LINE BREAKS COME FROM STRUCTURE, NEVER FROM SOURCE WHITESPACE. A newline inside HTML *text* is
    insignificant whitespace — it renders as a space, not a break — so only a block-level tag (or
    `<br>`) ends a line. Getting this backwards was the mandate sensor's largest fault source: the
    prior version split on every tag boundary AND kept the source's own newlines, which
      - **split headings**, because filers hard-wrap them mid-phrase
        (`<b>Principal\\nInvestment Strategies of the Fund</b>` -> two lines, so the phrase was never
        visible on one line and the section was reported "heading not found"); and
      - **split PROSE into heading-shaped fragments** — the more dangerous half, because a chopped
        risk sentence yielded the short line `principal investment strategy to do so`, which passed
        the `strict=True` guard (its tail "to do so" opens with a connective) and returned a RELIABLE
        extraction of risk text as the strategy — a spurious-`mandate.changed` risk of exactly the
        MANDATE-PROSE-HEADING class (docs/bugs/INDEX.md). Reflowing prose back onto one line puts it
        over the 80-char heading bar, so the guard sees prose as prose.
    See docs/decisions/2026-07-19-mandate-extraction-structural-lines.md."""
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(list(_BLOCK_TAGS)):
        tag.insert_before(_BREAK)
        tag.insert_after(_BREAK)
    # separator=" " so inline tags JOIN with a space rather than run words together
    # ("Principal" + "Investment" must not become "PrincipalInvestment").
    text = soup.get_text(separator=" ")
    # Collapse ALL whitespace (incl. source newlines and the non-breaking spaces from &nbsp;, which
    # \s matches) to one space; the surviving breaks are exactly the structural ones.
    text = re.sub(r"\s+", " ", text)
    return "\n".join(ln for ln in (p.strip() for p in text.split(_BREAK)) if ln)


# A section heading's optional tail is a short QUALIFIER phrase introduced by a closed-class connective
# ("Principal Investment Strategies OF THE Fund", "Fees AND Expenses of the Fund", "Investment Objective
# AND Principal Investment Strategies"). A body-prose sentence that merely OPENS with the same phrase
# runs on instead into a verb/content word ("investment objectives MAY change…", "investment objective
# INFORMATION for each fund…"). That is the whole discriminator for `strict` heading matching below, and
# it is STRUCTURE only (a fixed function-word set), never a judgment about what the heading MEANS.
_HEADING_TAIL_CONNECTIVES = frozenset(
    ("of", "and", "for", "in", "to", "the", "on", "at", "by", "with", "or", "a", "an"))


_HEADING_MAX_CHARS = 80       # a heading is a SHORT line; longer is prose
_DECLARATION_MAX_CHARS = 240  # a self-declaration is one line but a long one — see `max_chars` below


def _is_heading(line: str, patterns: list[str], *, strict: bool = False,
                max_chars: int = _HEADING_MAX_CHARS) -> bool:
    """True when `line` matches one of `patterns` (case-insensitive, on its own short line — a long line
    is prose, never a heading). Two match modes, because two callers ask different things of the same test:

      - **declaration** (`strict=False`, default) — the line OPENS with the phrase. Used by
        `is_prospectus_supplement`: a sticker self-declares "Supplement dated <date>" / "Supplement to
        <prospectus>" and an SAI titles itself — here the tail is MEANT to be free text (a date, a name).
      - **heading** (`strict=True`) — the phrase IS the heading: it spans the line bar at most a bounded
        connective qualifier tail ("… of the Fund", "… and Principal …"), completing the pattern's final
        (possibly stem-truncated) word first ("principal investment strateg" → "…strategies"). Used by
        `extract_mandate`, so a body line that merely opens with "Investment objective…" is NOT taken as
        the strategy heading. That prose guard is load-bearing: plain `startswith` accepted a line like
        "Investment objectives may change without shareholder approval" as the heading and returned a
        RELIABLE extraction on garbage — a spurious `mandate.changed` risk (docs/bugs/INDEX.md
        MANDATE-PROSE-HEADING). Structure only; never what the heading means.

    `max_chars` is the short-line bar, and the two modes need DIFFERENT bars now that `html_to_text`
    reflows a paragraph onto one structural line. A heading stays short (80). A sticker's
    self-declaration is a single long line — "Supplement dated July 15, 2026 to the Pictet AI &
    Automation ETF's and Pictet Cleaner Planet ETF's currently effective Prospectus…" is 98 chars, and
    the old splitter only kept it under 80 by chopping it mid-phrase. Holding declarations to the
    heading bar silently reclassified 11 real 497 stickers as full prospectuses, which would have
    re-created the very advisory noise the 2026-07-18 supplement cut removed. The looser bar is safe
    precisely because declaration mode is ANCHORED at the start of the line: a full prospectus that
    merely *mentions* a supplement mid-sentence still cannot match."""
    # Terminal heading punctuation includes "?" — a Q&A-format summary prospectus titles its sections as
    # QUESTIONS ("What are the Fund's main investment strategies?"), so the "?" is punctuation, not a prose
    # tail. And filings render apostrophes as smart quotes (’ from &rsquo;), so normalize them to a plain '
    # so a config pattern can carry a plain apostrophe. Both are terminal-form only and do not loosen the
    # prose guard: a prose sentence still runs on into a content word after the pattern (verified).
    ln = line.lower().strip().replace("’", "'").replace("‘", "'").rstrip(":.?")
    if not ln or len(ln) > max_chars:
        return False
    for p in patterns:
        if not ln.startswith(p):
            continue
        if not strict:
            return True                                   # declaration mode: the opening match is enough
        # Heading mode: the pattern must BE the line, bar a bounded connective qualifier tail. Complete
        # the pattern's final word first (the strategy stem is a mid-word prefix of "…strategies").
        rest = ln[len(p):]
        j = 0
        while j < len(rest) and rest[j].isalpha():
            j += 1
        tail = rest[j:].strip()
        if not tail or tail.split(None, 1)[0] in _HEADING_TAIL_CONNECTIVES:
            return True
        # else: the tail runs on into prose ("… may change …") — not a heading; keep scanning patterns.
    return False


def _find_heading(lines: list[str], patterns: list[str], start: int = 0, *,
                  strict: bool = False, max_chars: int = _HEADING_MAX_CHARS) -> int | None:
    for i in range(start, len(lines)):
        if _is_heading(lines[i], patterns, strict=strict, max_chars=max_chars):
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
    if _find_heading(lines[:_DECLARE_HEAD_LINES], list(_SAI_HEADINGS),
                     max_chars=_DECLARATION_MAX_CHARS) is not None:
        return True
    # A sticker announces "Supplement dated…/Supplement to…" — phrases specific to a supplement's own
    # heading (they do not appear as a heading in a full prospectus), so the whole (small) doc is scanned.
    # The declaration bar (not the 80-char heading bar) applies: a real sticker names every fund it
    # amends on that one line, which routinely runs past 80 characters.
    return _find_heading(lines, list(_SUPPLEMENT_HEADINGS),
                         max_chars=_DECLARATION_MAX_CHARS) is not None


# --- MULTI-FUND BLOCK ISOLATION (which fund's block — mirrors soi._fund_blocks selection) --------
# A combined prospectus (a trust filing SEVERAL funds in one document) carries one strategy section PER
# FUND. Scanning for the FIRST strategy section makes every covered series diff the FIRST fund's strategy
# (bug MANDATE-MULTIFUND-SECTION: on 2026-07-19 two Goldman series emitted byte-identical `mandate.changed`
# from one 485APOS). When the SGML SERIES/CLASS header (see `series_classes`) says a filing covers >1
# series, the sensor hands `extract_mandate` the target fund's NAME (`fund_anchor`) + all covered names
# (`fund_names`); we isolate the target's block by its name — the SAME exact/unique-substring/else-FAULT
# discipline the SOI reader uses (ingest/soi.py `extract_soi_sectors`) — then run the ordinary strategy
# finder INSIDE that block. bs4 owns structure, this owns which block, the human owns significance.

def _norm_name(s: str) -> str:
    """Normalize a fund name for matching (mirrors `soi._norm`): uppercase, `&`→`AND`, every run of
    non-alphanumerics collapsed to one space. So the header's SERIES-NAME matches the body's summary
    heading across the em-dash/affix punctuation — "Goldman Sachs Income ETF" ⊂ the heading
    "Goldman Sachs Income ETF—Summary" once both normalize."""
    return re.sub(r"[^A-Z0-9]+", " ", s.upper().replace("&", " AND ")).strip()


_FUND_SUMMARY_TOKEN = "SUMMARY"  # a fund's summary block opens with a "{Name} … Summary"/"Fund Summary" heading


def _fund_summary_blocks(lines: list[str], fund_names: list[str]) -> list[tuple[list[str], int]]:
    """Every candidate fund-SUMMARY block-start, as `(matched_norm_names, line_index)`. A candidate is a
    heading-shaped line (short enough to be a heading, not prose) whose normalized text carries a SUMMARY
    token AND contains at least one covered fund name (normalized substring). The fund NAME is the block
    delimiter — the strategy heading is NOT (it recurs 2-3× per fund: summary, statutory, SAI, which is
    exactly the "take the first" bug). Table-of-contents and cover-page copies of a name are candidates
    too (they also read "{Name} … Summary"); they are filtered downstream by "does this block bound a real
    strategy section?" (a TOC entry's region is just a page number)."""
    norm_names = [_norm_name(n) for n in fund_names if n]
    out: list[tuple[list[str], int]] = []
    for i, line in enumerate(lines):
        if len(line) > _DECLARATION_MAX_CHARS:      # a heading is short; longer is prose (as _is_heading)
            continue
        nl = _norm_name(line)
        if _FUND_SUMMARY_TOKEN not in nl:
            continue
        hits = [nn for nn in norm_names if nn and nn in nl]
        if hits:
            out.append((hits, i))
    return out


# --- MEANING (which section — never significance) -----------------------------------------------

def _scan_strategy(lines: list[str], cfg: dict) -> dict:
    """Scan `lines` for the principal-investment-strategy / investment-objective section, returning
    `{section, reliable, heading, reason}` (the shared core of `extract_mandate`, run over the whole
    document or over a single isolated fund block).

    `strategy_headings` is a PRIORITY list: prefer the detailed "Principal Investment Strategies" section,
    fall back to "Investment Objective" only when the richer one is absent. First pattern that yields a
    section wins.

    CONTINUE-SCAN PAST A NON-SECTION MATCH. Taking the FIRST heading-shaped line and failing on it let a
    **table of contents** shadow the real section: a TOC lists "PRINCIPAL INVESTMENT STRATEGY" (a perfectly
    heading-shaped line), then the page number, then the next TOC entry — which is a stop heading. So the
    "section" was the string "2" and the filing was reported unreliable while its real strategy section sat
    140 lines below. A candidate is the heading only if it yields a section-shaped extraction; otherwise
    keep scanning. STRUCTURE, not meaning — it asks "did this heading bound a section?", never "is this the
    important one." (This TOC-skip is also what filters a name-block's own table-of-contents copy during
    multi-fund isolation.) The unreliable REASON reported is the FIRST candidate's."""
    stops = [h.lower() for h in cfg["stop_headings"]]
    min_chars = int(cfg.get("min_section_chars", 80))
    max_lines = int(cfg.get("max_section_lines", 400))
    first_reason, first_heading = None, None
    for pattern in [h.lower() for h in cfg["strategy_headings"]]:
        at = 0
        while True:
            start = _find_heading(lines, [pattern], at, strict=True)  # a heading, not a prose line
            if start is None:
                break
            at = start + 1
            end = _find_heading(lines, stops, start + 1, strict=True)
            bounded = end is not None
            if end is None:
                end = min(len(lines), start + 1 + max_lines)
            section = "\n".join(lines[start + 1:end]).strip()

            if len(section) < min_chars:
                reason = "section too short to be the strategy"
            elif not bounded:
                reason = "no section boundary before cap (runaway extraction)"
            else:
                return {"section": section, "reliable": True, "heading": lines[start], "reason": "ok"}
            if first_reason is None:
                first_reason, first_heading = reason, lines[start]

    if first_reason is None:
        return {"section": None, "reliable": False, "heading": None,
                "reason": "strategy heading not found"}
    return {"section": None, "reliable": False, "heading": first_heading, "reason": first_reason}


def _extract_isolated(lines: list[str], fund_anchor: str, fund_names: list[str], cfg: dict) -> dict:
    """Isolate the target fund's block in a multi-fund filing, then scan only that block. Mirrors
    `soi.extract_soi_sectors`'s selection: the anchor picks its block-start(s) by unique substring, and
    ANY unresolvable case FAULTS (`reliable: False`) rather than guessing which fund owns the section —
    §4d: a false `mandate.changed` is worse than a missed one."""
    def fault(reason: str) -> dict:
        return {"section": None, "reliable": False, "heading": None, "reason": reason}

    anchor = _norm_name(fund_anchor)
    if not anchor:
        return fault("no fund anchor given")
    # The anchor must not be a substring of ANOTHER covered fund's name — the tie would be unresolvable
    # (the SOI anti-ambiguity rule, applied to the name set rather than the block titles).
    others = [n for n in (_norm_name(x) for x in fund_names) if n and n != anchor]
    if any(anchor in o for o in others):
        return fault(f"fund anchor {fund_anchor!r} is ambiguous — a substring of another covered fund name")

    blocks = _fund_summary_blocks(lines, fund_names)
    starts = sorted(i for _, i in blocks)
    anchor_starts = [i for hits, i in blocks if anchor in hits]
    if not anchor_starts:
        return fault(f"target fund block not found for anchor {fund_anchor!r}")
    # For each anchor block-start (document order), bound it by the NEXT block-start of ANY fund and try to
    # scan a strategy section inside. The FIRST that yields a reliable section wins; a TOC/cover copy of the
    # name yields none (its region is a page number) and is skipped to the real block.
    for s in anchor_starts:
        after = [i for i in starts if i > s]
        window = lines[s:(after[0] if after else len(lines))]
        result = _scan_strategy(window, cfg)
        if result["reliable"]:
            return result
    return fault(f"no bounded strategy section in the {fund_anchor!r} block")


def extract_mandate(body: bytes, cfg: dict, *,
                    fund_anchor: str | None = None, fund_names: list[str] | None = None) -> dict:
    """Locate and return the principal-investment-strategy / investment-objective section text.
    Returns `{section, reliable, heading, reason}`. `reliable` is False (and `section` None) when the
    strategy heading isn't found, the section is trivially short, or no stop-heading boundary is hit
    before a hard cap (a runaway to EOF) — the caller flags an unreliable extraction rather than
    diffing it. Decides ONLY which text is the section; never whether a change to it is meaningful.

    MULTI-FUND ISOLATION (MANDATE-MULTIFUND-SECTION). When the filing covers MORE THAN ONE fund and the
    caller supplies the target fund's `fund_anchor` (its SGML SERIES-NAME) + all covered `fund_names`, the
    target's block is isolated FIRST (else the first fund's strategy is returned for every covered series).
    A single-fund filing (`fund_names` ≤ 1) or no anchor → the whole document, byte-identical to before —
    so the single-fund majority path is unchanged."""
    lines = html_to_text(body).split("\n")
    if fund_anchor and fund_names and len(fund_names) > 1:
        return _extract_isolated(lines, fund_anchor, fund_names, cfg)
    return _scan_strategy(lines, cfg)


def _normalize(section: str) -> str:
    """Collapse ALL whitespace to single spaces for the change decision, so a pure formatting/date
    re-flow does not read as a change. Case is preserved (a real wording edit shows; the human, not
    this code, judges whether it matters)."""
    return re.sub(r"\s+", " ", section).strip()


# Sentence-ish boundaries. The diff unit must NOT be the source's own line wrapping: once
# `html_to_text` reflows a paragraph onto one structural line (as it must — see its docstring), a
# line-diff reports the WHOLE paragraph as changed and the 800-char bound then truncates away the
# very words that moved. Splitting on sentence ends restores a granular diff and, unlike line
# wrapping, is stable across re-files. Structure only — it never weighs which sentence matters.
_SENTENCE_END = re.compile(r"(?<=[.;:])\s+")


def _summarize(prior_section: str, current_section: str, max_chars: int = 800) -> str:
    """A compact, human-readable unified diff of the strategy section, sentence by sentence — the
    go-look content for the human's cosmetic-vs-substantive verdict. Bounded so the event payload
    stays small. Diffs the NORMALIZED text, matching the change decision in `diff_mandate`, so the
    summary can never disagree with the `changed` flag it accompanies."""
    prior = _SENTENCE_END.split(_normalize(prior_section))
    current = _SENTENCE_END.split(_normalize(current_section))
    diff = "\n".join(difflib.unified_diff(
        prior, current, fromfile="prior", tofile="current", lineterm=""))
    return diff[:max_chars] + ("…" if len(diff) > max_chars else "")


def diff_mandate(prior_body: bytes, current_body: bytes, cfg: dict, *,
                 prior_anchor: str | None = None, prior_names: list[str] | None = None,
                 current_anchor: str | None = None, current_names: list[str] | None = None) -> dict:
    """Diff the strategy section across two prospectus filings. PURE, and deliberately narrow:
    returns `{changed, reliable, summary, reason}` — whether the section TEXT differs, never whether
    the difference is meaningful. If either extraction is unreliable, the whole diff is
    `reliable: False` (the caller flags it, emits no change). Otherwise the whitespace-normalized
    sections are compared: a formatting/date/fee re-file normalizes identical -> `changed: False`; a
    wording change -> `changed: True` with a bounded unified-diff `summary`. Cosmetic-vs-substantive
    is NOT decided here — that is the human's verdict (mandate.changed is a silent corroboration).

    MULTI-FUND: each side is isolated with ITS OWN filing's anchor + covered names (keyed on the stable
    series_id, so a fund NAME never crosses from one filing into the other — name drift is un-weaponizable).
    All-None → whole-document extraction, unchanged (single-fund path)."""
    prior = extract_mandate(prior_body, cfg, fund_anchor=prior_anchor, fund_names=prior_names)
    current = extract_mandate(current_body, cfg, fund_anchor=current_anchor, fund_names=current_names)
    if not (prior["reliable"] and current["reliable"]):
        reason = prior["reason"] if not prior["reliable"] else current["reason"]
        return {"changed": False, "reliable": False, "summary": None, "reason": reason}
    changed = _normalize(prior["section"]) != _normalize(current["section"])
    summary = _summarize(prior["section"], current["section"]) if changed else None
    return {"changed": changed, "reliable": True, "summary": summary, "reason": "ok"}
