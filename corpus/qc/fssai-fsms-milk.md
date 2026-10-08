# Chunk QC: fssai-fsms-milk

- Chunks: **158**, tokens: median 231, max 748, total 37316
- Empty chunks: 0
- From OCR: 4

## Chunks per block type

| Block type | Chunks |
|---|---:|
| list | 75 |
| prose | 59 |
| table | 24 |

## Size histogram (tokens)

| Tokens | Chunks |
|---|---:|
| 0-50 | 17 |
| 50-100 | 15 |
| 100-200 | 38 |
| 200-400 | 78 |
| 400-600 | 7 |
| 600-800 | 3 |
| 800-1000 | 0 |
| 1000+ | 0 |

## 5 largest chunks

| Tokens | Chunk | Starts with |
|---:|---|---|
| 748 | `fssai-fsms-milk:2-maintenance:2` | Table: 2. Maintenance Columns: Corrective/ Break-down maintenance / Preventive maintenance… |
| 680 | `fssai-fsms-milk:annexure-3-floors-for-dairy-manufacturing-facili:1` | Table: ANNEXURE 3: Floors for dairy manufacturing facilities Floor finish / Features / Con… |
| 653 | `fssai-fsms-milk:annexure-4-general-guide-to-packaging-material:1` | Table: ANNEXURE 4: General guide to packaging material / Food Products / Thermoplastics th… |
| 595 | `fssai-fsms-milk:2-1-skimmed-milk-powder:7` | Table: 2.1 Skimmed Milk Powder Columns: S. No. / List of Manufacturing/ / Process Steps / … |
| 594 | `fssai-fsms-milk:2-1-skimmed-milk-powder:3` | Table: 2.1 Skimmed Milk Powder Spray dryer operation / Microbiological Contamination / Pre… |

## 5 smallest chunks

| Tokens | Chunk | Starts with |
|---:|---|---|
| 4 | `fssai-fsms-milk:4-13-air-quality-and-ventilation:3` | Air Filter Class: |
| 7 | `fssai-fsms-milk:i-introduction-to-haccp:3` | Frequent Extreme Extreme Very High |
| 7 | `fssai-fsms-milk:2-1-skimmed-milk-powder:9` | 7. Inoculation & Mixing |
| 9 | `fssai-fsms-milk:1-cleaning-and-sanitation:3` | Sample Sanitation and Housekeeping Program for warehouses |
| 12 | `fssai-fsms-milk:2-1-skimmed-milk-powder:13` | 10. Blast cooling 11. Storage 12. Dispatch |

## Tables

- Split into row groups: `p63-t1` (4), `p68-t1` (3)
- Categories too large for one group (split by rows): none
- Without a header row (an override CSV can add one): `p39-t1`, `p62-t1`, `p63-t1`, `p71-t1`, `p72-t1`, `p92-t1`, `p93-t1`, `p95-t1`
- Flagged as broken: none

## Other splits

- List items longer than a chunk, split at sentences: 0
- Recommendations over the size guard, split at bullets: 0
