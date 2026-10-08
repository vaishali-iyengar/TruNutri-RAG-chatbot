"""Citation validator and support check (implementation-plan.md, 6.4-6.5; §6.6).

Code, not the prompt, decides what reaches the user. A claim is dropped when it:

1. cites no chunk,
2. cites a chunk that wasn't retrieved,
3. cites a chunk from another document than its section's (this enforces "never
   blend sources"),
4. states a number that isn't in the matching part of its cited chunks ("5 days" vs
   "3-4 days"; in a table, the row for that food),
5. shares too few key words with its cited chunks.

Each check is a plain function, so it can be tested alone. Every dropped claim is kept
with its reason for tracing.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from guidance_rag.models import BlockType, Chunk, Claim, DocAnswer, Evidence
from guidance_rag.store import tokenize

# Share of a claim's key words that must appear in its cited chunks (5).
MIN_KEYWORD_OVERLAP = 0.5
# Numbers are checked against the best-matching lines and those within this many key
# words of them (see matching_lines).
ROW_SLACK = 1
_TABLE_RULE = re.compile(r"^\|[\s|:-]+\|$")  # the |---|---| line under a header row
# Words the generator adds when reporting guidance; they say nothing about support.
REPORTING_WORDS = frozenset(
    {
        "recommend", "recommended", "recommendation", "advise", "advised", "advice",
        "suggest", "suggested", "state", "stated", "say", "note", "noted", "guidance",
        "guideline", "document", "according", "should", "shall", "must", "also", "about",
        "per", "than", "not", "no", "more", "less", "least", "most", "only", "such",
        "include", "including", "use", "used", "way", "make", "made", "any", "all",
    }
)  # fmt: skip

_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "hundred": "100", "half": "0.5",
}  # fmt: skip
_NUMBER_WORD = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class DroppedClaim:
    doc_id: str
    text: str
    chunk_ids: tuple[str, ...]
    reason: str


@dataclass
class Validation:
    sections: list[DocAnswer]  # kept claims; sections left empty are dropped
    dropped: list[DroppedClaim] = field(default_factory=list)

    @property
    def claim_count(self) -> int:
        return sum(len(s.claims) for s in self.sections)


# --- Checks (6.4) ---------------------------------------------------------------------


def has_citation(claim: Claim) -> bool:
    return bool(claim.chunk_ids)


def cites_retrieved(claim: Claim, retrieved: Mapping[str, Chunk]) -> bool:
    return all(c in retrieved for c in claim.chunk_ids)


def cites_own_document(claim: Claim, doc_id: str, retrieved: Mapping[str, Chunk]) -> bool:
    return all(retrieved[c].doc_id == doc_id for c in claim.chunk_ids)


# --- Support check (6.5) -----------------------------------------------------------------


def numbers(text: str) -> set[str]:
    """Numbers in `text`: digits and number words, thousands separators removed
    ("1,800" -> "1800"), trailing ".0" dropped."""
    text = _NUMBER_WORD.sub(lambda m: _NUMBER_WORDS[m.group(1).lower()], text)
    text = _THOUSANDS.sub("", text)
    return {n[:-2] if n.endswith(".0") else n for n in _NUMBER.findall(text)}


def keywords(text: str) -> set[str]:
    """Content words, as BM25 tokenises them (lowercase, plurals folded, no stop words)."""
    return {t for t in tokenize(text) if not t[0].isdigit() and t not in REPORTING_WORDS}


def header_lines(lines: Sequence[str]) -> list[str]:
    """Lines that apply to every table row: the caption ("Table: …", "Columns: …") and
    everything above the |---| rule (the header row)."""
    rule = next((i for i, ln in enumerate(lines) if _TABLE_RULE.match(ln.strip())), None)
    head = list(lines[:rule]) if rule is not None else []
    return head + [ln for ln in lines if ln.startswith(("Table:", "Columns:"))]


def matching_lines(claim_words: set[str], source: str) -> list[str]:
    """The lines of a table chunk that support a claim's numbers: the best-matching rows
    (within `ROW_SLACK` key words of the best), plus the table caption and header.

    Each row is a line, so a storage time is checked against its own food's row, not
    any row: "5 days" for chicken must not pass because ham keeps "3 to 5 days"."""
    lines = [ln for ln in source.splitlines() if ln.strip()]
    if not claim_words:
        return lines
    overlap = [len(claim_words & keywords(ln)) for ln in lines]
    floor = max(1, max(overlap, default=0) - ROW_SLACK)
    best = [ln for ln, n in zip(lines, overlap, strict=True) if n >= floor]
    return header_lines(lines) + best


def support_problem(claim: Claim, cited: Sequence[Chunk]) -> str | None:
    """Why the cited chunks don't support the claim, or None if they do."""
    source = "\n".join(" > ".join(c.section_path) + "\n" + c.text for c in cited)
    words = keywords(claim.text)
    claimed = numbers(claim.text)
    if claimed:
        # Table chunks: only the matching rows (and the header) count. Prose and lists
        # are checked whole: one claim often combines two bullets of a passage.
        number_text = "\n".join(
            "\n".join(matching_lines(words, c.text)) if c.block_type is BlockType.TABLE
            else " > ".join(c.section_path) + "\n" + c.text
            for c in cited
        )  # fmt: skip
        missing = sorted(claimed - numbers(number_text))
        if missing:
            return f"numbers not in the cited text: {', '.join(missing)}"
    if len(words) >= 2:
        found = words & keywords(source)
        if len(found) / len(words) < MIN_KEYWORD_OVERLAP:
            return f"too few key words in the cited text ({len(found)}/{len(words)})"
    return None


# --- Validator ---------------------------------------------------------------------------


def validate(sections: Sequence[DocAnswer], evidence: Evidence, support: bool = True) -> Validation:
    """Keep only claims that pass every check; record the rest with a reason."""
    retrieved = {sc.chunk.chunk_id: sc.chunk for d in evidence.documents for sc in d.chunks}
    kept: list[DocAnswer] = []
    dropped: list[DroppedClaim] = []

    def drop(doc_id: str, claim: Claim, reason: str) -> None:
        dropped.append(DroppedClaim(doc_id, claim.text, tuple(claim.chunk_ids), reason))

    for section in sections:
        claims = []
        for claim in section.claims:
            if not has_citation(claim):
                drop(section.doc_id, claim, "no citation")
            elif not cites_retrieved(claim, retrieved):
                drop(section.doc_id, claim, "cites a chunk that wasn't retrieved")
            elif not cites_own_document(claim, section.doc_id, retrieved):
                drop(section.doc_id, claim, "cites another document's chunk")
            elif support and (
                problem := support_problem(claim, [retrieved[c] for c in claim.chunk_ids])
            ):
                drop(section.doc_id, claim, problem)
            else:
                claims.append(claim)
        if claims:
            kept.append(DocAnswer(doc_id=section.doc_id, claims=claims))
    return Validation(kept, dropped)
