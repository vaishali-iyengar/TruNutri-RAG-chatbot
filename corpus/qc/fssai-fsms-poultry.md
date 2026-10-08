# Chunk QC: fssai-fsms-poultry

- Chunks: **132**, tokens: median 214, max 604, total 32647
- Empty chunks: 0
- From OCR: 0

## Chunks per block type

| Block type | Chunks |
|---|---:|
| list | 45 |
| prose | 52 |
| table | 35 |

## Size histogram (tokens)

| Tokens | Chunks |
|---|---:|
| 0-50 | 14 |
| 50-100 | 16 |
| 100-200 | 33 |
| 200-400 | 50 |
| 400-600 | 16 |
| 600-800 | 3 |
| 800-1000 | 0 |
| 1000+ | 0 |

## 5 largest chunks

| Tokens | Chunk | Starts with |
|---:|---|---|
| 604 | `fssai-fsms-poultry:inspection-checklist-poultry-slaughter-house:1` | Table: INSPECTION CHECKLIST – POULTRY SLAUGHTER HOUSE Columns: S.No. / S.No. / S.No. / Aud… |
| 603 | `fssai-fsms-poultry:2-hazard-analysis-in-poultry-meat:17` | Table: 2. Hazard Analysis in Poultry Meat Columns: Process Step / Hazard Type / Potential … |
| 600 | `fssai-fsms-poultry:2-hazard-analysis-in-poultry-meat:14` | Table: 2. Hazard Analysis in Poultry Meat Columns: Process Step / Hazard Type / Potential … |
| 594 | `fssai-fsms-poultry:2-hazard-analysis-in-poultry-meat:8` | Table: 2. Hazard Analysis in Poultry Meat Columns: Process Step / Hazard Type / Potential … |
| 593 | `fssai-fsms-poultry:inspection-checklist-processed-poultry-products:4` | Table: INSPECTION CHECKLIST – PROCESSED POULTRY PRODUCTS maintained at 0°C to 4°C. / maint… |

## 5 smallest chunks

| Tokens | Chunk | Starts with |
|---:|---|---|
| 15 | `fssai-fsms-poultry:2-hazard-analysis-in-poultry-meat:1` | Possible Hazard Type: P: Physical; C: Chemical; B: Biological |
| 22 | `fssai-fsms-poultry:2-storage-of-raw-and-packaging-materials:1` | All packaging materials used to pack the processed meat at final stage should be located a… |
| 25 | `fssai-fsms-poultry:4-8-lighting:3` | - Light bulbs and fixtures suspended over plant in any stage of production should be prote… |
| 25 | `fssai-fsms-poultry:4-8-lighting:4` | Table: 4.8 Lighting / Figure 9 : Protected Tubelight / Figure 9 : Protected Tubelight / |
| 25 | `fssai-fsms-poultry:3-8-carcass-chilling:1` | All dressed birds shall be chilled below 4 °C by appropriate method within 4 hours from sl… |

## Tables

- Split into row groups: `p63-t1` (3), `p64-t1` (2), `p65-t1` (13), `p70-t1` (3), `p89-t1` (3), `p90-t1` (3), `p92-t1` (3), `p93-t1` (2)
- Categories too large for one group (split by rows): none
- Without a header row (an override CSV can add one): `p33-t1`, `p64-t1`, `p90-t1`, `p93-t1`
- Flagged as broken: none

## Other splits

- List items longer than a chunk, split at sentences: 0
- Recommendations over the size guard, split at bullets: 0
