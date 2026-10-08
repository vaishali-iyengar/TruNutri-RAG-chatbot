from pathlib import Path

from guidance_rag.ingest.parse_html import parse_html, text_fragment
from guidance_rag.ingest.tree import Document, iter_sections, outline, walk
from guidance_rag.models import BlockType, ParserConfig

FIXTURES = Path(__file__).parent / "fixtures"


def parse_fixture(name: str, config: ParserConfig | None = None) -> Document:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return parse_html(html, doc_id="doc", title="Fallback title", config=config)


def who() -> Document:
    return parse_fixture(
        "who_healthy_diet.html", ParserConfig(content_selector="article.sf-detail-body-wrapper")
    )


def foodsafety() -> Document:
    return parse_fixture(
        "foodsafety_cold_storage.html",
        ParserConfig(
            content_selector="article.node--type-article",
            drop_selectors=[".field--name-field-date-last-reviewed"],
        ),
    )


def test_who_outline_nests_h1_to_h3() -> None:
    assert outline(who()).splitlines() == [
        "Healthy diet",
        "  Key facts",
        "  WHO guidance on healthy diets",
        "    Sugars",
        "    Salt/sodium and potassium",
        "  How to promote healthy diets",
        "  WHO response",
    ]


def test_who_blocks_are_typed_and_in_order() -> None:
    blocks = [(path[-1], b.type) for path, _, b in walk(who())]
    assert blocks == [
        ("Key facts", BlockType.LIST),
        ("Sugars", BlockType.LIST),
        ("Salt/sodium and potassium", BlockType.PROSE),
        ("Salt/sodium and potassium", BlockType.LIST),
        ("How to promote healthy diets", BlockType.LIST),
        ("WHO response", BlockType.PROSE),
    ]


def test_nested_list_items_fold_into_their_parent_item() -> None:
    lists = [b for path, _, b in walk(who()) if path[-1] == "How to promote healthy diets"]
    assert lists[0].items == [
        "encouraging consumer demand for healthy foods and meals through:\n"
        "  - promoting consumer awareness of a healthy diet;\n"
        "  - encouraging culinary skills, including in children through schools;"
    ]


def test_inline_markup_stays_in_its_paragraph() -> None:
    texts = [b.text for path, _, b in walk(who()) if path[-1] == "WHO response"]
    assert texts == [
        "1. Building the evidence: guidelines, standards and tools To fulfil these mandates, "
        "WHO turns nutrition science into practical, evidence\u2011based guidance."
    ]


def test_navigation_cookie_banner_share_and_comments_are_removed() -> None:
    text = " ".join(b.text for _, _, b in walk(who()))
    for noise in ["Home", "cookies", "Share on", "Malnutrition", "© 2026", "editor's comment"]:
        assert noise not in text


def test_headings_without_id_get_a_text_fragment_anchor() -> None:
    anchors = {s.heading: s.anchor for _, s in iter_sections(who())}
    assert anchors["Sugars"] == ":~:text=Sugars"
    assert anchors["Salt/sodium and potassium"] == text_fragment("Salt/sodium and potassium")
    assert "/" not in text_fragment("Salt/sodium")


def test_foodsafety_chart_keeps_its_header_row() -> None:
    tables = [b.table for _, _, b in walk(foodsafety()) if b.table]
    assert len(tables) == 1
    assert tables[0].header_rows == [
        ["Food", "Type", "Refrigerator [40°F (4°C) or below]", "Freezer [0°F (-18°C) or below]"]
    ]
    assert tables[0].table_id == "foo-bar-baz"


def test_foodsafety_rowspans_are_expanded_so_each_row_has_its_food() -> None:
    (table,) = [b.table for _, _, b in walk(foodsafety()) if b.table]
    assert table.rows[1:3] == [
        ["Hot dogs", "Opened package", "1 week", "1 to 2 months"],
        ["Hot dogs", "Unopened package", "2 weeks", "1 to 2 months"],
    ]
    # A cell spanning two rows in the middle of the row is carried down too.
    assert table.rows[-1] == [
        "Fin Fish",
        "Lean Fish (cod, flounder, haddock, halibut, sole, etc.)",
        "1 - 3 Days",
        "6 - 8 Months",
    ]
    assert all(len(row) == 4 for row in table.rows)


def test_multi_paragraph_cell_and_linked_cell_are_flattened() -> None:
    (table,) = [b.table for _, _, b in walk(foodsafety()) if b.table]
    assert table.rows[3][:2] == [
        "Ham",
        "Canned, shelf-stable, opened Note: An unopened, shelf-stable, canned ham can be "
        "stored at room temperature for 2 years.",
    ]


def test_foodsafety_title_outside_the_article_becomes_the_section() -> None:
    tree = foodsafety()
    assert [s.heading for s in tree.sections] == ["Cold Food Storage Chart"]
    texts = [b.text for _, _, b in walk(tree) if b.type is BlockType.PROSE]
    assert len(texts) == 1 and texts[0].startswith("Follow the guidelines below")


def test_buttons_and_dropped_selectors_are_removed() -> None:
    text = " ".join(b.text for _, _, b in walk(foodsafety()))
    assert "Download Cold Food Storage Chart" not in text
    assert "Date Last Reviewed" not in text


def test_without_a_content_selector_main_is_used() -> None:
    tree = parse_fixture("who_healthy_diet.html")
    assert "Related" not in outline(tree)  # <aside> is noise even inside <main>
    assert tree.sections[0].heading == "Healthy diet"


def test_page_without_headings_uses_the_title() -> None:
    tree = parse_html("<p>Just text.</p>", doc_id="d", title="Doc title")
    assert [(p, b.text) for p, _, b in walk(tree)] == [(["Doc title"], "Just text.")]
