import pytest
from pydantic import ValidationError

from guidance_rag.ingest.tree import (
    Block,
    Document,
    Section,
    Table,
    TreeBuilder,
    iter_sections,
    outline,
    strip_enumerator,
    walk,
)
from guidance_rag.models import BlockType


def prose(text: str, page: int | None = None) -> Block:
    return Block(type=BlockType.PROSE, text=text, page=page)


def sample_tree() -> Document:
    table = Table(header_rows=[["Food", "Fridge"]], rows=[["Eggs", "3 to 5 weeks"]])
    return Document(
        doc_id="doc",
        sections=[
            Section(
                heading="GUIDELINE 11 Restrict salt intake",
                level=1,
                page=90,
                blocks=[Block(type=BlockType.RECOMMENDATION, text="RATIONALE ...", page=90)],
                children=[
                    Section(
                        heading="How to avoid excess salt intake?",
                        level=2,
                        page=91,
                        blocks=[prose("Processed foods ...", 91), Block.from_table(table, page=92)],
                    ),
                ],
            ),
            Section(heading="GUIDELINE 12", level=1, blocks=[prose("Consume safe food.")]),
        ],
    )


def test_walk_yields_blocks_with_section_paths_in_reading_order() -> None:
    got = [(path, block.type) for path, _, block in walk(sample_tree())]
    assert got == [
        (["GUIDELINE 11 Restrict salt intake"], BlockType.RECOMMENDATION),
        (
            ["GUIDELINE 11 Restrict salt intake", "How to avoid excess salt intake?"],
            BlockType.PROSE,
        ),
        (
            ["GUIDELINE 11 Restrict salt intake", "How to avoid excess salt intake?"],
            BlockType.TABLE,
        ),
        (["GUIDELINE 12"], BlockType.PROSE),
    ]


def test_walk_returns_the_section_that_holds_each_block() -> None:
    for _, section, block in walk(sample_tree()):
        assert block in section.blocks


def test_iter_sections_is_depth_first() -> None:
    paths = [path for path, _ in iter_sections(sample_tree())]
    assert paths == [
        ["GUIDELINE 11 Restrict salt intake"],
        ["GUIDELINE 11 Restrict salt intake", "How to avoid excess salt intake?"],
        ["GUIDELINE 12"],
    ]


def test_outline_indents_children_and_counts_blocks() -> None:
    assert outline(sample_tree(), counts=True).splitlines() == [
        "GUIDELINE 11 Restrict salt intake  (p. 90)  [recommendation 1]",
        "  How to avoid excess salt intake?  (p. 91)  [prose 1, table 1]",
        "GUIDELINE 12  [prose 1]",
    ]


def test_table_block_text_keeps_header_first() -> None:
    table = Table(caption="Table 1", header_rows=[["Food", "Fridge"]], rows=[["Eggs", "3 weeks"]])
    block = Block.from_table(table)
    assert block.text.splitlines() == ["Table 1", "Food | Fridge", "Eggs | 3 weeks"]
    assert table.n_cols == 2


def test_list_block_text_is_one_line_per_item() -> None:
    block = Block.from_items(["i. Keep clean.", "ii. Keep cold."])
    assert block.text == "i. Keep clean.\nii. Keep cold."


def test_block_type_must_match_its_payload() -> None:
    with pytest.raises(ValidationError):
        Block(type=BlockType.TABLE, text="no table")
    with pytest.raises(ValidationError):
        Block(type=BlockType.PROSE, text="x", table=Table(rows=[["a"]]))
    with pytest.raises(ValidationError):
        Block(type=BlockType.PROSE, text="x", items=["a"])


def test_tree_round_trips_through_json() -> None:
    tree = sample_tree()
    assert Document.model_validate_json(tree.model_dump_json()) == tree


# --- TreeBuilder --------------------------------------------------------------------


def test_builder_nests_by_level_and_closes_deeper_sections() -> None:
    b = TreeBuilder("doc")
    b.heading("A. Overview", 1)
    b.block(prose("intro"))
    b.heading("1. Location", 3)  # levels may skip; nesting follows the stack
    b.block(prose("site"))
    b.heading("2.1 Layout", 4)
    b.block(prose("layout"))
    b.heading("B. Programmes", 1)
    b.block(prose("prp"))
    tree = b.build("Title")
    assert [p for p, _ in iter_sections(tree)] == [
        ["A. Overview"],
        ["A. Overview", "1. Location"],
        ["A. Overview", "1. Location", "2.1 Layout"],
        ["B. Programmes"],
    ]


def test_builder_merges_a_repeated_title_into_the_empty_section() -> None:
    b = TreeBuilder("doc")
    b.heading("A. OVERVIEW OF POULTRY MEAT INDUSTRY IN INDIA", 1)  # divider page
    assert b.heading("Overview of poultry meat industry in India:", 1) is None
    b.block(prose("Poultry ..."))
    tree = b.build("Title")
    assert [s.heading for s in tree.sections] == ["A. OVERVIEW OF POULTRY MEAT INDUSTRY IN INDIA"]
    assert tree.sections[0].blocks[0].text == "Poultry ..."


def test_builder_drops_reference_and_contents_sections_with_their_children() -> None:
    b = TreeBuilder("doc", drop_sections=[r"^annex 1\b"])
    b.heading("1. Introduction", 1)
    b.block(prose("kept"))
    b.heading("References", 2)
    b.block(prose("1. Smith J. ..."))
    b.heading("1. Some reference title", 3)
    b.block(prose("dropped too"))
    b.heading("2. Results", 1)
    b.block(prose("kept again"))
    b.heading("Annex 1. Previous meetings", 1)
    b.block(prose("dropped by config"))
    tree = b.build("Title")
    texts = [blk.text for _, _, blk in walk(tree)]
    assert texts == ["kept", "kept again"]
    assert [s.heading for s in tree.sections] == ["1. Introduction", "2. Results"]


def test_builder_puts_text_before_the_first_heading_under_the_title() -> None:
    b = TreeBuilder("doc")
    b.block(prose("preamble"))
    b.heading("Key facts", 2)
    b.block(prose("fact"))
    tree = b.build("Healthy diet")
    assert [p for p, _, _ in walk(tree)] == [["Healthy diet"], ["Key facts"]]


def test_builder_prunes_sections_without_content() -> None:
    b = TreeBuilder("doc")
    b.heading("Empty", 1)
    b.heading("Also empty", 2)
    b.heading("Full", 1)
    b.block(prose("x"))
    assert [s.heading for s in b.build("T").sections] == ["Full"]


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("A. OVERVIEW", "OVERVIEW"),
        ("II. CONTROL OF OPERATIONS", "CONTROL OF OPERATIONS"),
        ("3.1.4 Carob bean gum", "Carob bean gum"),
        ("References", "References"),
        ("2) Scope", "Scope"),
    ],
)
def test_strip_enumerator(heading: str, expected: str) -> None:
    assert strip_enumerator(heading) == expected
