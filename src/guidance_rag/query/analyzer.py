"""Query analyzer: which documents to search (implementation-plan.md, 4.7; ARCHITECTURE.md §6.2).

- An explicit `doc_filter` is checked against the registry and used as given.
- Otherwise the question is matched against the registry `aliases`: exactly (acronyms
  such as "WHO" case-sensitively, so "people who handle milk" doesn't match), then
  fuzzily for multi-word aliases ("Dietary Guideline for Indian"). Matches set the filter.
- A question naming an authority that is not in the corpus (NHS, FDA, MyPlate, ...)
  gets `UNKNOWN_DOC`, so it is refused before retrieval.

Aliases are matched longest first and each match is blanked out, so "Joint FAO/WHO
Expert Committee" finds JECFA and not also WHO.

The retriever gets `query`: the question with the document names that set the filter
replaced by "the guidance".
The filter already does their job, and the reranker scores a passage lower when the
question names a document the passage doesn't mention (rc-02, "What does the Dietary
Guidelines for Indians recommend about physical activity?": gold score 0.11 with the
name, 0.98 without).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from rapidfuzz import fuzz

from guidance_rag.registry import Registry, load_registry
from guidance_rag.store import tokenize

FUZZY_MIN_SCORE = 90  # rapidfuzz partial_ratio, 0-100
FUZZY_MIN_CHARS = 10  # shorter aliases must match exactly

# Authorities and documents people ask about that are not in the corpus. Acronyms are
# case-sensitive; names are not.
UNKNOWN_SOURCES: dict[str, str] = {
    "NHS": r"\bNHS\b",
    "Eatwell Guide": r"(?i:\beat ?well (guide|plate)\b)",
    "USDA MyPlate": r"(?i:\bmy ?plate\b)",
    "Dietary Guidelines for Americans": r"(?i:\bdietary guidelines for americans\b)",
    "FDA": r"\bFDA\b",
    "CDC": r"\bCDC\b",
    "NIH": r"\bNIH\b",
    "EFSA": r"\bEFSA\b",
    "Health Canada": r"(?i:\bhealth canada\b|\bcanada'?s food guide\b)",
    "Food Standards Agency": r"(?i:\bfood standards agency\b)",
    "FSANZ": r"\bFSANZ\b|(?i:\bfood standards australia\b)",
    "American Heart Association": r"(?i:\bamerican heart association\b)",
    "American Diabetes Association": r"(?i:\bamerican diabetes association\b)",
    "Harvard Healthy Eating Plate": r"(?i:\bharvard\b)",
    "Mayo Clinic": r"(?i:\bmayo clinic\b)",
}


class AnalysisStatus(StrEnum):
    OK = "ok"
    UNKNOWN_DOC = "unknown_doc"


class UnknownDocumentError(ValueError):
    """An explicit doc_filter names a document that is not in the corpus."""


@dataclass(frozen=True)
class QueryAnalysis:
    question: str
    status: AnalysisStatus
    doc_ids: list[str] | None  # None = search every document
    matched: list[tuple[str, str]] = field(default_factory=list)  # (alias, doc_id)
    unknown_sources: list[str] = field(default_factory=list)
    query: str = ""  # what to search for; the question without matched document names
    # The two halves of a two-part question ("…, and how …?"), searched and scored on
    # their own as well, so each half can find its document (4.9). Empty otherwise.
    sub_queries: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.query:
            object.__setattr__(self, "query", self.question)


def _is_acronym(alias: str) -> bool:
    return not any(ch.islower() for ch in alias)


def _exact_pattern(alias: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(word) for word in alias.split())
    flags = 0 if _is_acronym(alias) else re.IGNORECASE
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", flags)


_MASK = "\x00"  # marks a matched alias; not a word character, so aliases can't span it


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + _MASK * (end - start) + text[end:]


def _search_query(masked: str, question: str) -> str:
    """Replace each masked document name (and a "the" before it) with "the guidance".
    Falls back to the question if no search term would be left."""
    text = re.sub(rf"(?i)(\bthe\s+)?{_MASK}+", " the guidance ", masked)
    # "the ICMR guidance" -> "the guidance guidance" -> "the guidance"
    text = re.sub(r"(?i)\bguidance\s+(?=(guidance|guidelines?|recommendations?)\b)", "", text)
    text = re.sub(r"\s+([,?.!;:'])", r"\1", re.sub(r"\s+", " ", text)).strip()
    return text if set(tokenize(text)) - {"guidance"} else question


def _word_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Snap a fuzzy match to whole words: a word cut after 1-2 characters is left out,
    a word cut later is taken whole ("guideline" for the alias "guidelines")."""
    word_start = start
    while word_start > 0 and text[word_start - 1].isalnum():
        word_start -= 1
    if word_start < start:
        start = (
            word_start if start - word_start > 2 else start + len(text[start:].split(None, 1)[0])
        )
    word_end = end
    while word_end < len(text) and text[word_end].isalnum():
        word_end += 1
    if word_end > end:
        word_begin = end
        while word_begin > 0 and text[word_begin - 1].isalnum():
            word_begin -= 1
        end = word_end if end - word_begin > 2 else word_begin
    return start, max(start, end)


# --- Two-part questions ---------------------------------------------------------------

_QUESTION_WORDS = r"how|what|which|when|where|why|is|are|can|could|should|does|do|will|would"
_SPLIT = re.compile(rf"(?i),?\s+and\s+(?=({_QUESTION_WORDS})\b)")
_AUX = {"can", "could", "should", "does", "do", "did", "is", "are", "was", "will", "would", "must"}
_LEADS = [("how", "long"), ("how", "much"), ("how", "many"), ("how", "often"), ("how",)]
_LEADS += [(w,) for w in ("what", "which", "when", "where", "why")]
# Words that end the subject of the first half ("How long can raw chicken | stay …").
_SUBJECT_END = _AUX | {
    "i", "we", "you", "be", "been", "stay", "last", "keep", "kept", "remain", "store",
    "stored", "go", "get", "eat", "eaten", "use", "used", "cook", "cooked", "need", "have",
    "has", "contain", "cause", "make", "take", "say", "says", "recommend", "in", "on", "at",
    "for", "to", "of", "with", "after", "before", "during", "per", "a", "an",
}  # fmt: skip
# "is it OK to …", "it is …": a dummy "it", not a reference to the first half's subject.
_DUMMY_IT = re.compile(r"(?i)\b(is|was) it\b|\bit (is|was)\b")
_PRONOUN = re.compile(r"(?i)\b(it|they|them)\b")


def _subject(clause: str) -> str | None:
    """The noun phrase a question is about, from its word order: after "Which"/"What"
    ("Which cooking oils should …"), or after the question word and auxiliary ("How
    long can raw chicken stay …"). None when unclear."""
    words = clause.rstrip("?.! ").split()
    lower = [w.lower().strip(",") for w in words]
    for lead in _LEADS:
        if tuple(lower[: len(lead)]) == lead:
            i = len(lead)
            break
    else:
        return None
    if i < len(lower) and lower[i] in _AUX:
        i += 1
    start = i
    while i < len(lower) and lower[i] not in _SUBJECT_END and i - start < 4:
        i += 1
    if i == start or i == len(lower):
        return None
    return " ".join(words[start:i]).strip(",")


_SENTENCE_BREAK = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"'(])")


def question_sentences(query: str) -> list[str]:
    """The question sentences of a multi-sentence question; [] for one sentence.

    The reranker scores a passage against the whole text, so a preamble ("I'm cooking
    for my family.") or a half in another language ("WHO salt ke baare mein kya kehta
    hai? How much salt …?") can push the passage that answers below one that matches
    the noise (9.3, red team rt-29 and rt-30). Searching each question sentence on its
    own as well lets that passage score on the part that asks."""
    sentences = [s.strip() for s in _SENTENCE_BREAK.split(query.strip())]
    if len(sentences) < 2:
        return []
    return [s for s in sentences if s.endswith("?") and len(tokenize(s)) >= 2]


def split_question(query: str) -> list[str]:
    """Split "A, and how/is/what … B?" into two questions; [] when it isn't one.

    A "they"/"it" in the second half that refers back is replaced by the first half's
    subject: "How long can raw chicken stay in the fridge, and how should it be handled
    …?" gives "How should raw chicken be handled …?"."""
    parts = _SPLIT.split(query, maxsplit=1)
    if len(parts) != 3:
        return []
    first, _, second = parts
    first = first.strip().rstrip(",?") + "?"
    second = second.strip()
    second = second[0].upper() + second[1:]
    subject = _subject(first)
    if subject and _PRONOUN.search(second) and not _DUMMY_IT.search(second):
        second = _PRONOUN.sub(subject, second, count=1)
    if len(tokenize(first)) < 2 or len(tokenize(second)) < 2:
        return []
    return [first, second]


def sub_queries(query: str) -> list[str]:
    """Extra searches for `query`: the halves of a two-part question and the question
    sentences of a multi-sentence one."""
    return list(dict.fromkeys([*split_question(query), *question_sentences(query)]))


class QueryAnalyzer:
    def __init__(self, registry: Registry | None = None) -> None:
        registry = registry or load_registry()
        self.doc_ids = [d.doc_id for d in registry.included]
        aliases = [(a, d.doc_id) for d in registry.included for a in d.aliases]
        self._aliases = sorted(aliases, key=lambda pair: -len(pair[0]))
        self._exact = {a: _exact_pattern(a) for a, _ in self._aliases}
        self._unknown = {name: re.compile(rx) for name, rx in UNKNOWN_SOURCES.items()}

    def analyze(self, question: str, doc_filter: Sequence[str] | None = None) -> QueryAnalysis:
        if doc_filter:
            unknown = sorted(set(doc_filter) - set(self.doc_ids))
            if unknown:
                raise UnknownDocumentError(f"not in the corpus: {unknown}")
            return QueryAnalysis(
                question,
                AnalysisStatus.OK,
                list(dict.fromkeys(doc_filter)),
                sub_queries=sub_queries(question),
            )

        text, matched = question, []
        for alias, doc_id in self._aliases:
            span = self._find(alias, text)
            if span:
                matched.append((alias, doc_id))
                text = _blank(text, *span)

        unknown_sources = [name for name, rx in self._unknown.items() if rx.search(text)]
        status = AnalysisStatus.UNKNOWN_DOC if unknown_sources else AnalysisStatus.OK
        query = _search_query(text, question) if matched else question
        return QueryAnalysis(
            question,
            status,
            list(dict.fromkeys(doc_id for _, doc_id in matched)) or None,
            matched,
            unknown_sources,
            query,
            sub_queries(query),
        )

    def _find(self, alias: str, text: str) -> tuple[int, int] | None:
        m = self._exact[alias].search(text)
        if m:
            return m.span()
        if _is_acronym(alias) or len(alias) < FUZZY_MIN_CHARS or " " not in alias:
            return None
        found = fuzz.partial_ratio_alignment(
            alias.lower(), text.lower(), score_cutoff=FUZZY_MIN_SCORE
        )
        return _word_span(text, found.dest_start, found.dest_end) if found else None
