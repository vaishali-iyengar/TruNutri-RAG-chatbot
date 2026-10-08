"""Ask the chatbot a question and print its cited answer (or refusal).

.venv/bin/python scripts/ask.py "How long can I keep leftover pizza in the fridge?"
.venv/bin/python scripts/ask.py --doc who-healthy-diet "What about trans fats?"
.venv/bin/python scripts/ask.py            # a random question from a small built-in list
.venv/bin/python scripts/ask.py --evidence "…"   # show the retrieved passages instead

Answers need GROQ_API_KEY in .env (the safety classifier and answer generator run on Groq).
"""

import argparse
import random
import time

from guidance_rag.query.analyzer import AnalysisStatus, QueryAnalyzer
from guidance_rag.query.retriever import load_retriever
from guidance_rag.store import STOPWORDS, tokenize

EXAMPLES = [
    "How long can I keep leftover pizza in the fridge?",
    "Is it safe to reuse cooking oil?",
    "How much sugar should I eat per day?",
    "Should milk be boiled before drinking?",
    "Which millets do the Indian guidelines recommend?",
    "Can I refreeze thawed chicken?",
    "Is coconut oil healthy?",  # partly covered
    "Is kombucha good for gut health?",  # not in the corpus
    "What does the NHS say about fibre?",  # a source outside the corpus
]


def preview(text: str, query: str, width: int = 300) -> list[str]:
    """Up to 4 lines that share a word with the query (e.g. the matching table rows),
    else the start of the text."""
    terms = set(tokenize(query)) - STOPWORDS - {"long", "keep", "much", "many", "day"}
    hits = [ln.strip() for ln in text.split("\n") if terms & set(tokenize(ln))]
    if hits:
        return [h[:width] for h in hits[:4]]
    flat = " ".join(text.split())
    return [flat[:width] + ("…" if len(flat) > width else "")]


def answer(question: str, docs: list[str] | None) -> None:
    from guidance_rag.pipeline import load_pipeline

    start = time.perf_counter()
    pipeline = load_pipeline()
    print(f"(models loaded in {time.perf_counter() - start:.1f} s)\n")
    try:
        start = time.perf_counter()
        result = pipeline.run(question, docs)
    finally:
        pipeline.close()
    print(f"[{result.status.value}] in {time.perf_counter() - start:.1f} s\n")
    print(result.markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="?", help="omit for a random example")
    parser.add_argument("--doc", action="append", help="search only this doc_id (repeatable)")
    parser.add_argument("--evidence", action="store_true", help="show retrieved passages only")
    args = parser.parse_args()
    question = args.question or random.choice(EXAMPLES)

    print(f"Question: {question}\n")
    if not args.evidence:
        answer(question, args.doc)
        return
    analysis = QueryAnalyzer().analyze(question, args.doc)
    if analysis.status is AnalysisStatus.UNKNOWN_DOC:
        print(f"UNKNOWN_DOC: not in my documents: {', '.join(analysis.unknown_sources)}")
        return
    if analysis.doc_ids:
        print(f"Searching only: {', '.join(analysis.doc_ids)}")
    if analysis.query != question:
        print(f"Search query: {analysis.query}")
    for sub in analysis.sub_queries:
        print(f"  part: {sub}")

    start = time.perf_counter()
    retriever = load_retriever()
    print(f"(models loaded in {time.perf_counter() - start:.1f} s)\n")
    try:
        ev = retriever.retrieve(analysis.query, analysis.doc_ids, analysis.sub_queries)
    finally:
        retriever.close()

    seconds = sum(ev.timings_ms.values()) / 1000
    print(f"Retrieved in {seconds:.2f} s, best score {ev.best_score:.3f}")
    if not ev.documents:
        print("\nNOT_IN_CORPUS: no passage scored high enough. Documents searched:")
        for doc_id in ev.docs_searched:
            print(f"  - {doc_id}")
        return
    for doc in ev.documents:
        first = doc.chunks[0].chunk
        print(f"\n=== {first.doc_title} ({first.publisher}, {first.year})")
        for sc in doc.chunks:
            c = sc.chunk
            page = f", p. {c.page_start}" if c.page_start else ""
            print(f"\n  [{sc.score:.2f}] {' > '.join(c.section_path)}{page}")
            for line in preview(c.text, question):
                print(f"    {line}")
            print(f"  {c.deep_link}")


if __name__ == "__main__":
    main()
