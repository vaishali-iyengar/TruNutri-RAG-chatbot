"""Chunker rules (implementation-plan.md, 3.1-3.8) on hand-built trees.

Small limits keep the test texts short; each test names the rule it checks.
"""

import pytest

from guidance_rag.config import ChunkingConfig
from guidance_rag.ingest.chunker import (
    Chunker,
    ChunkReport,
    count_tokens,
    dedupe_row,
    deep_link,
    slugify,
    table_problems,
)
from guidance_rag.ingest.tree import Block, Document, Section, Table
from guidance_rag.models import BlockType, Chunk, SourceDocument
from guidance_rag.registry import load_registry

REGISTRY = load_registry()
PDF_DOC = REGISTRY.get("icmr-nin-dgi-2024")  # source_url is the PDF itself
HTML_DOC = REGISTRY.get("who-healthy-diet")
LANDING_PAGE_DOC = REGISTRY.get("jecfa-trs-1058")  # source_url is a web page about the PDF

SMALL = ChunkingConfig(
    prose_max=60,
    table_whole_max=80,
    table_group_max=60,
    small_section_max=25,
    recommendation_max=60,
    overlap_max=20,
)


def para(text: str, page: int | None = 1) -> Block:
    return Block(type=BlockType.PROSE, text=text, page=page)


def words(n: int, word: str = "salt") -> str:
    """A sentence of about n tokens."""
    return " ".join([word] * (n - 1)) + "."


def chunk(
    sections: list[Section], doc: SourceDocument = PDF_DOC, config: ChunkingConfig = SMALL
) -> tuple[list[Chunk], ChunkReport]:
    return Chunker(config).chunk(Document(doc_id=doc.doc_id, sections=sections), doc)


# --- 3.1 skeleton -------------------------------------------------------------------


def test_count_tokens_is_stable() -> None:
    assert count_tokens("Restrict salt intake") == 4
    assert count_tokens("") == 0


def test_one_chunk_per_section_for_small_blocks() -> None:
    chunks, _ = chunk(
        [
            Section(heading="Salt", level=1, blocks=[para("Limit salt to 5 g a day.")]),
            Section(heading="Sugar", level=1, blocks=[para("Limit free sugars.")]),
        ],
        config=ChunkingConfig(),
    )
    assert [(c.section_heading, c.text) for c in chunks] == [
        ("Salt", "Limit salt to 5 g a day."),
        ("Sugar", "Limit free sugars."),
    ]


# --- 3.2 packing paragraphs and lists -----------------------------------------------


def test_paragraphs_pack_up_to_the_limit_and_never_cut_inside_one() -> None:
    blocks = [para(f"Point {i}: " + words(18)) for i in range(6)]
    chunks, _ = chunk([Section(heading="Salt", level=1, blocks=blocks)])
    assert len(chunks) > 1
    assert all(c.token_count <= SMALL.prose_max for c in chunks)
    for c in chunks:  # every paragraph appears whole
        for part in c.text.split("\n\n"):
            assert part in [b.text for b in blocks]


def test_next_chunk_starts_with_the_previous_paragraph_as_overlap() -> None:
    short, long_a, long_b = para("Short note."), para(words(45, "oil")), para(words(45, "fat"))
    chunks, _ = chunk([Section(heading="Fats", level=1, blocks=[long_a, short, long_b])])
    assert [c.text for c in chunks] == [
        f"{long_a.text}\n\nShort note.",
        f"Short note.\n\n{long_b.text}",
    ]


def test_large_overlap_paragraphs_are_not_repeated() -> None:
    a, b = para(words(45, "oil")), para(words(45, "fat"))  # 45 tokens > overlap_max
    chunks, _ = chunk([Section(heading="Fats", level=1, blocks=[a, b])])
    assert [c.text for c in chunks] == [a.text, b.text]


def test_no_chunk_crosses_into_another_section() -> None:
    chunks, _ = chunk(
        [
            Section(
                heading="Parent",
                level=1,
                blocks=[para("Parent text.")],
                children=[Section(heading="Child", level=2, blocks=[para(words(50))])],
            )
        ]
    )
    assert [(c.section_path, c.text[:6]) for c in chunks] == [
        (["Parent"], "Parent"),
        (["Parent", "Child"], "salt s"),
    ]


def test_short_list_packs_with_its_paragraphs_and_keeps_its_markers() -> None:
    blocks = [
        para("Storage facilities shall:"),
        Block.from_items(["i. Be dry.", "ii. Be clean."], page=2),
        Block.from_items(["Keep it cold", "Keep it covered"], page=2),
    ]
    (c,), _ = chunk([Section(heading="Storage", level=1, blocks=blocks)])
    assert c.text == (
        "Storage facilities shall:\n\n"
        "i. Be dry.\nii. Be clean.\n\n"
        "- Keep it cold\n- Keep it covered"
    )
    assert c.block_type is BlockType.PROSE
    assert (c.page_start, c.page_end) == (1, 2)


def test_chunk_of_only_a_list_has_list_type() -> None:
    (c,), _ = chunk([Section(heading="L", level=1, blocks=[Block.from_items(["a", "b"])])])
    assert c.block_type is BlockType.LIST


# --- 3.3 small sibling sections -------------------------------------------------------


def test_small_sibling_sections_merge_under_their_parent() -> None:
    steps = [
        Section(heading=name, level=3, page=16, blocks=[para(f"{name} is done with care.", 16)])
        for name in ["Stunning", "Slaughtering", "Evisceration"]
    ]
    big = Section(heading="Chilling", level=3, page=18, blocks=[para(words(40), 18)])
    parent = Section(heading="Process details", level=2, children=[*steps, big])
    chunks, _ = chunk([Section(heading="Poultry", level=1, children=[parent])])

    merged, alone = chunks
    assert merged.section_path == ["Poultry", "Process details"]
    assert merged.subsections == ["Stunning", "Slaughtering", "Evisceration"]
    assert merged.text.startswith("Stunning\nStunning is done with care.\n\nSlaughtering\n")
    assert merged.page_start == 16
    assert alone.section_path == ["Poultry", "Process details", "Chilling"]
    assert alone.subsections == []


def test_a_single_small_section_is_not_merged() -> None:
    lone = Section(heading="Stunning", level=2, blocks=[para("Done with care.")])
    chunks, _ = chunk([Section(heading="Poultry", level=1, children=[lone])])
    assert chunks[0].section_path == ["Poultry", "Stunning"]
    assert chunks[0].subsections == []


def test_sections_with_tables_or_recommendations_are_never_merged() -> None:
    rec = Section(
        heading="A", level=2, blocks=[Block(type=BlockType.RECOMMENDATION, text="RATIONALE x")]
    )
    other = Section(heading="B", level=2, blocks=[para("tiny")])
    chunks, _ = chunk([Section(heading="G", level=1, children=[rec, other])])
    assert [c.section_heading for c in chunks] == ["A", "B"]


# --- 3.4 recommendations ------------------------------------------------------------


def test_recommendation_is_one_chunk() -> None:
    text = "POINTS TO REGISTER\n- Use iodized salt.\n- Restrict added salt to 5g per day."
    blocks = [para("Intro."), Block(type=BlockType.RECOMMENDATION, text=text), para("Outro.")]
    chunks, _ = chunk(
        [Section(heading="GUIDELINE 11 Restrict salt intake", level=1, blocks=blocks)]
    )
    assert [(c.block_type, c.text) for c in chunks] == [
        (BlockType.PROSE, "Intro."),
        (BlockType.RECOMMENDATION, text),
        (BlockType.PROSE, "Outro."),
    ]


def test_oversized_recommendation_splits_at_bullets_with_its_title_repeated() -> None:
    points = [f"- {words(30, w)}" for w in ["salt", "sugar", "oil"]]  # two don't fit in one
    text = "\n".join(["POINTS TO REGISTER", *points])
    chunks, report = chunk(
        [Section(heading="G", level=1, blocks=[Block(type=BlockType.RECOMMENDATION, text=text)])]
    )
    assert len(chunks) == 3
    assert all(c.text.startswith("POINTS TO REGISTER\n- ") for c in chunks)
    assert [c.text.splitlines()[1] for c in chunks] == points
    assert report.split_recommendations == 1


# --- 3.5 table serialisation and checks ---------------------------------------------

STORAGE = Table(
    table_id="t1",
    caption="Table 2: Storage temperatures",
    header_rows=[["Product", "Fridge", "Freezer"]],
    rows=[["Milk", "4 °C", "-18 °C"], ["Butter", "4 °C", "4 °C"]],
)


def test_narrow_table_is_markdown_with_caption_and_header() -> None:
    (c,), _ = chunk([Section(heading="S", level=1, blocks=[Block.from_table(STORAGE)])])
    assert c.block_type is BlockType.TABLE
    assert c.table_id == "t1"
    assert c.text.splitlines() == [
        "Table 2: Storage temperatures",
        "| Product | Fridge | Freezer |",
        "|---|---|---|",
        "| Milk | 4 °C | -18 °C |",
        "| Butter | 4 °C | 4 °C |",  # equal short values are real, not a merged cell
    ]


def test_wide_table_writes_column_value_pairs() -> None:
    header = ["Step", "Hazard", "Limit", "Monitoring", "Action", "Verification", "Records"]
    table = Table(
        header_rows=[header], rows=[["Chilling", "B", "<4 °C", "Probe", "Re-chill", "QA", "Log"]]
    )
    (c,), _ = chunk([Section(heading="HACCP Plan", level=1, blocks=[Block.from_table(table)])])
    assert c.text.splitlines() == [
        "Table: HACCP Plan",  # no caption: the section heading names the table
        "Columns: " + " | ".join(header),
        "Step: Chilling; Hazard: B; Limit: <4 °C; Monitoring: Probe; Action: Re-chill; "
        "Verification: QA; Records: Log",
    ]


def test_merged_cells_are_printed_once() -> None:
    long = "Exclusive breastfeeding for the first six months"
    assert dedupe_row(["Infants", long, long, "5.8"]) == ["Infants", long, "", "5.8"]
    assert dedupe_row(["Men", "Men", "Women"], header=True) == ["Men", "", "Women"]
    assert dedupe_row(["2", "2", "2"]) == ["2", "2", "2"]


@pytest.mark.parametrize(
    ("table", "problem"),
    [
        (Table(rows=[["Sun", words(320)], ["Mon", "x"]]), "a cell has"),
        (Table(rows=[["Figure 7", "", "", ""], ["", "", "", ""]]), "mostly empty"),
    ],
)
def test_broken_tables_are_flagged(table: Table, problem: str) -> None:
    assert any(problem in p for p in table_problems(table, ChunkingConfig()))


def test_a_long_checklist_with_blank_score_cells_is_not_flagged() -> None:
    rows = [[str(i), f"Question {i}", "", "", ""] for i in range(20)]
    assert table_problems(Table(header_rows=[["No", "Q", "", "", ""]], rows=rows), SMALL) == []


# --- 3.6 table splitting ------------------------------------------------------------


def test_large_table_splits_between_categories_with_title_and_header_repeated() -> None:
    rows = [
        [food, f"{kind} package", "1 week"]
        for food in ["Hot dogs", "Bacon", "Ham", "Eggs"]
        for kind in ["Opened", "Unopened"]
    ]
    table = Table(
        table_id="chart", caption="Cold Food Storage Chart",
        header_rows=[["Food", "Type", "Fridge"]], rows=rows,
    )  # fmt: skip
    chunks, report = chunk([Section(heading="S", level=1, blocks=[Block.from_table(table)])])

    assert len(chunks) > 1 and report.split_tables == {"chart": len(chunks)}
    seen = []
    for c in chunks:
        lines = c.text.splitlines()
        assert lines[:3] == ["Cold Food Storage Chart", "| Food | Type | Fridge |", "|---|---|---|"]
        assert c.token_count <= SMALL.table_group_max
        foods = [line.split(" | ")[0].strip("| ") for line in lines[3:]]
        seen += foods
        assert foods == sorted(foods, key=foods.index)  # categories stay contiguous
    for food in {"Hot dogs", "Bacon", "Ham", "Eggs"}:  # each food sits in exactly one chunk
        assert sum(food in {line.split(" | ")[0].strip("| ") for line in c.text.splitlines()}
                   for c in chunks) == 1  # fmt: skip
    assert len(seen) == len(rows)


def test_headerless_table_repeats_its_title_and_is_reported() -> None:
    rows = [[f"Step {i}", words(12)] for i in range(8)]
    table = Table(table_id="hz", rows=rows)
    chunks, report = chunk([Section(heading="Hazards", level=1, blocks=[Block.from_table(table)])])
    assert len(chunks) > 1
    assert all(c.text.startswith("Table: Hazards\n| Step") for c in chunks)
    assert report.headerless_tables == ["hz"]


# --- 3.7 long lists -----------------------------------------------------------------


def test_long_list_splits_between_items_with_its_lead_in_repeated() -> None:
    items = [f"{n}. {words(15, w)}" for n, w in enumerate(["dry", "clean", "cool", "dark"], 1)]
    blocks = [para("Storage areas shall be:"), Block.from_items(items)]
    chunks, _ = chunk([Section(heading="Storage", level=1, blocks=blocks)])
    assert len(chunks) > 1
    for c in chunks:
        lead, *rest = c.text.splitlines()
        assert lead == "Storage areas shall be:"
        assert all(line in items for line in rest)  # items are whole
        assert c.block_type is BlockType.LIST
    assert [line for c in chunks for line in c.text.splitlines()[1:]] == items


def test_an_item_longer_than_a_chunk_is_split_at_sentences() -> None:
    item = " ".join(f"Sentence {i} {words(12)}" for i in range(6))
    chunks, report = chunk([Section(heading="L", level=1, blocks=[Block.from_items([item, item])])])
    assert report.split_items == 2
    assert all(c.token_count <= SMALL.prose_max for c in chunks)
    assert all(c.text.rstrip().endswith(".") for c in chunks)


# --- 3.8 metadata, contextual header and IDs ------------------------------------------


def sample_sections() -> list[Section]:
    """Two guidelines, each with one "Sources" subsection (a heading used twice)."""
    return [
        Section(
            heading=f"GUIDELINE {n} {title}",
            level=1,
            page=page,
            blocks=[Block(type=BlockType.RECOMMENDATION, text="RATIONALE Salt.", page=page)],
            children=[
                Section(heading="Sources", level=2, page=page + 1, blocks=[para(text, page + 1)]),
            ],
        )
        for n, title, page, text in [
            (11, "Restrict salt intake", 90, "Processed foods."),
            (12, "Consume safe and clean foods", 94, "Clean water."),
        ]
    ]


def test_every_chunk_carries_document_metadata() -> None:
    chunks, _ = chunk(sample_sections())
    for c in chunks:
        assert c.doc_title == PDF_DOC.title and c.publisher == PDF_DOC.publisher
        assert c.year == 2024 and c.domain is PDF_DOC.domain
        assert c.retrieval_date == PDF_DOC.retrieval_date
        assert c.section_heading == c.section_path[-1]
        assert c.token_count == count_tokens(c.text)


def test_embed_text_puts_the_contextual_header_before_the_body() -> None:
    chunks, _ = chunk(sample_sections())
    assert chunks[1].embed_text == (
        "[ICMR-NIN DGI 2024]\n"
        "[Section: GUIDELINE 11 Restrict salt intake > Sources]\n"
        "Processed foods."
    )
    assert chunks[1].text == "Processed foods."


def test_chunk_ids_are_unique_and_stable() -> None:
    first, _ = chunk(sample_sections())
    second, _ = chunk(sample_sections())
    ids = [c.chunk_id for c in first]
    assert ids == [c.chunk_id for c in second]
    assert ids == [
        "icmr-nin-dgi-2024:guideline-11-restrict-salt-intake:1",
        "icmr-nin-dgi-2024:sources:1",
        "icmr-nin-dgi-2024:guideline-12-consume-safe-and-clean-foods:1",
        "icmr-nin-dgi-2024:sources:2",  # a repeated heading gets the next number
    ]


def test_deep_links_point_at_the_page_or_the_heading() -> None:
    pdf_chunks, _ = chunk(sample_sections())
    assert pdf_chunks[1].deep_link == f"{PDF_DOC.source_url}#page=91"

    html = [Section(heading="Sugars", level=2, anchor=":~:text=Sugars", blocks=[para("x", None)])]
    (h,), _ = chunk(html, doc=HTML_DOC)
    assert h.deep_link == f"{HTML_DOC.source_url}#:~:text=Sugars"
    assert h.page_start is None

    (j,), _ = chunk([Section(heading="Adipates", level=2, blocks=[para("x", 17)])],
                    doc=LANDING_PAGE_DOC)  # fmt: skip
    assert j.deep_link == str(LANDING_PAGE_DOC.source_url)  # a web page: no #page fragment
    assert j.page_start == 17
    assert deep_link(PDF_DOC, None, None) == str(PDF_DOC.source_url)


def test_ocr_flag_carries_over() -> None:
    blocks = [Block(type=BlockType.PROSE, text="Chill to 4°C.", page=74, ocr=True)]
    (c,), _ = chunk([Section(heading="Checklist", level=1, blocks=blocks)])
    assert c.ocr


def test_slugify() -> None:
    assert slugify("GUIDELINE 11 Restrict salt intake") == "guideline-11-restrict-salt-intake"
    assert slugify("4.3 Storage of Hazardous Substances & Chemicals (Detailed) Requirements") == (
        "4-3-storage-of-hazardous-substances-chemicals-de"
    )
    assert slugify("—") == "section"


# --- QC report (3.9) ------------------------------------------------------------------


def test_qc_report_lists_sizes_types_and_table_findings() -> None:
    from guidance_rag.ingest.qc import qc_report

    broken = Table(table_id="p9-t1", rows=[["Figure 7", "", "", ""], ["", "", "", ""]])
    sections = [
        *sample_sections(),
        Section(heading="T", level=1, blocks=[Block.from_table(broken)]),
    ]
    chunks, report = chunk(sections)
    text = qc_report(chunks, report)
    assert text.startswith(f"# Chunk QC: {PDF_DOC.doc_id}\n")
    assert f"- Chunks: **{len(chunks)}**" in text
    assert "| recommendation | 2 |" in text
    assert "- `p9-t1`: small and mostly empty" in text
    assert "Without a header row (an override CSV can add one): `p9-t1`" in text


def test_search_header_uses_the_short_name_and_adds_the_year_once() -> None:
    from guidance_rag.ingest.chunker import search_header

    assert search_header(PDF_DOC) == "[ICMR-NIN DGI 2024]"
    assert search_header(HTML_DOC) == "[WHO Healthy diet · 2026]"


def test_search_text_normalises_degrees_and_strips_symbol_font_bullets() -> None:
    from guidance_rag.ingest.chunker import search_text

    assert search_text("Store at 4ºC\n\uf0fc  Keep   covered") == "Store at 4°C\nKeep covered"
