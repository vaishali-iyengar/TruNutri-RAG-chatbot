"""Hand-corrected tables (sub-task 2.7).

When the parser gets a table wrong, save the right version as
`corpus/overrides/{doc_id}/{table_id}.csv` and it replaces the parsed table.
The first CSV row is the header row. `table_id` is shown by
`python -m guidance_rag.ingest parse --dump --doc DOC_ID` (e.g. "p28-t1").
"""

import csv
from pathlib import Path

from guidance_rag.config import PROJECT_ROOT
from guidance_rag.ingest.text import clean_text
from guidance_rag.ingest.tree import Document, Table, walk

DEFAULT_OVERRIDES_DIR = PROJECT_ROOT / "corpus" / "overrides"


def load_override(path: Path, base: Table) -> Table:
    with path.open(encoding="utf-8", newline="") as f:
        rows = [
            [clean_text(c) for c in row] for row in csv.reader(f) if any(c.strip() for c in row)
        ]
    if len(rows) < 2:
        raise ValueError(f"{path}: an override needs a header row and at least one data row")
    return base.model_copy(update={"header_rows": rows[:1], "rows": rows[1:]})


def apply_overrides(doc: Document, overrides_dir: Path = DEFAULT_OVERRIDES_DIR) -> list[str]:
    """Replace parsed tables that have an override CSV. Returns the table_ids replaced."""
    folder = overrides_dir / doc.doc_id
    if not folder.is_dir():
        return []
    available = {p.stem: p for p in folder.glob("*.csv")}
    used = []
    for _, _, block in walk(doc):
        table_id = block.table.table_id if block.table else None
        if block.table and table_id in available:
            block.table = load_override(available[table_id], block.table)
            block.text = block.table.to_text()
            used.append(table_id)
    unused = sorted(set(available) - set(used))
    if unused:
        raise ValueError(f"{folder}: override(s) match no parsed table: {', '.join(unused)}")
    return used
