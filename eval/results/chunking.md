# Chunking: structure-aware vs. fixed-size

Fixed-size: 400-token windows with 50-token overlap over the parsed text in reading order (headings included), cl100k tokens. Structure-aware: the committed chunks. Produced by `python -m eval.chunking_comparison`.

| Document | Tables | cut (fixed) | pieces without header (fixed) | Recommendations | cut (fixed) | Windows (fixed) | Chunks (structure-aware) |
|---|---|---|---|---|---|---|---|
| icmr-nin-dgi-2024 | 39 | 32 | 69 | 34 | 11 | 212 | 313 |
| who-healthy-diet | 0 | 0 | 0 | 0 | 0 | 12 | 17 |
| foodsafety-cold-storage | 1 | 1 | 4 | 0 | 0 | 5 | 5 |
| fssai-fsms-milk | 19 | 10 | 21 | 0 | 0 | 114 | 158 |
| fssai-fsms-poultry | 11 | 8 | 44 | 0 | 0 | 103 | 132 |
| fssai-fsms-fruits-vegetables | 26 | 18 | 45 | 0 | 0 | 113 | 152 |
| jecfa-trs-1058 | 0 | 0 | 0 | 0 | 0 | 102 | 126 |
| **All** | **96** | **69 (72%)** | **183** | **34** | **11 (32%)** | **661** | **903** |

Structure-aware chunking cuts no recommendation and no table under 800 tokens; larger tables are split between rows with the caption and header repeated in every piece, so no piece is without its header.

Structure-aware chunk sizes (tokens): min 4, 10th percentile 69, median 261, 90th percentile 497, max 774. By type: list 178, prose 493, recommendation 34, table 198.
