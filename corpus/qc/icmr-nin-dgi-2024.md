# Chunk QC: icmr-nin-dgi-2024

- Chunks: **313**, tokens: median 253, max 774, total 86805
- Empty chunks: 0
- From OCR: 0

## Chunks per block type

| Block type | Chunks |
|---|---:|
| list | 9 |
| prose | 183 |
| recommendation | 34 |
| table | 87 |

## Size histogram (tokens)

| Tokens | Chunks |
|---|---:|
| 0-50 | 10 |
| 50-100 | 30 |
| 100-200 | 79 |
| 200-400 | 126 |
| 400-600 | 64 |
| 600-800 | 4 |
| 800-1000 | 0 |
| 1000+ | 0 |

## 5 largest chunks

| Tokens | Chunk | Starts with |
|---:|---|---|
| 774 | `icmr-nin-dgi-2024:guideline-2-ensure-provision-of-extra-food-and-h:1` | RATIONALE Additional nutritious food and care are required during pregnancy and lactation … |
| 735 | `icmr-nin-dgi-2024:annexure-ii:3` | Table: ANNEXURE II Day / Mid-morning / Mid-morning / Mid-morning / Afternoo n / Afternoo n… |
| 614 | `icmr-nin-dgi-2024:indicative-glycemic-carbohydrates-content-mean-s:1` | Table: Indicative glycemic carbohydrates content (mean±SD) from commonly consumed cereals,… |
| 603 | `icmr-nin-dgi-2024:what-are-food-groups:7` | Table 1.2b. Nutrients from 'My Plate for the Day' (Non-vegetarian) Columns: Food groups (2… |
| 596 | `icmr-nin-dgi-2024:proteins:10` | Table 1.4. Average values of micronutrients (vitamins) in various food groups (Per 100gm r… |

## 5 smallest chunks

| Tokens | Chunk | Starts with |
|---:|---|---|
| 8 | `icmr-nin-dgi-2024:current-diet-and-nutrition-scenario:4` | (CNNS, 2019) |
| 8 | `icmr-nin-dgi-2024:annexure-ii:1` | Raw food item measures using household utensils |
| 8 | `icmr-nin-dgi-2024:diet-chart-for-1-3-years-old-children:1` | (for children weighing 13 kgs) |
| 14 | `icmr-nin-dgi-2024:what-are-protein-powders-or-protein-supplements:4` | - Protein from animal source are more easily digestible and better absorption. |
| 32 | `icmr-nin-dgi-2024:guideline-1-eat-a-variety-of-foods-to-ensure-a-b:1` | RATIONALE Nutritionally adequate diet or a balanced diet should be consumed through a wise… |

## Tables

- Split into row groups: `p24-t1` (2), `p24-t2` (2), `p26-t1` (8), `p28-t1` (8), `p61-t1` (3), `p62-t1` (3), `p114-t1` (3), `p115-t1` (4), `p131-t1` (2), `p132-t1` (5), `p133-t1` (4), `p134-t2` (4), `p135-t1` (5), `p143-t1` (2), `p146-t1` (8)
- Categories too large for one group (split by rows): p114-t1: Group A foods, p115-t1: Group B foods, p115-t1: Group C foods, p132-t1: SUNDAY, p132-t1: MONDAY, p132-t1: TUESDAY, p132-t1: WEDNESDAY, p133-t1: THURSDAY, p133-t1: FRIDAY, p133-t1: SATUR DAY, p134-t2: SUNDAY, p134-t2: MONDAY, p134-t2: TUESDAY, p135-t1: WEDNESDAY, p135-t1: THURSDAY, p135-t1: FRIDAY
- Without a header row (an override CSV can add one): `p15-t1`, `p22-t1`, `p25-t1`, `p35-t1`, `p46-t1`, `p51-t1`, `p59-t1`, `p61-t1`, `p62-t1`, `p87-t1`, `p113-t1`, `p130-t1`, `p130-t2`, `p131-t1`
- Flagged as broken: none

## Other splits

- List items longer than a chunk, split at sentences: 0
- Recommendations over the size guard, split at bullets: 0
