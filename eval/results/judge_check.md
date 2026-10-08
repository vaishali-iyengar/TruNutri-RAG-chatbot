# Citation judge: hand check (implementation-plan.md, 9.2)

**Date:** 2026-10-07. **Judge:** `eval/judge.py`, `openai/gpt-oss-120b`, temperature 0,
reasoning effort medium; one call per answer judging every claim against the full text of
the passages it cites.

**Sample:** 20 of the 82 claims judged on the dev split (`eval/results/judged_dev.jsonl`),
drawn with `random.seed(92)`. Each claim was read against the full text of every cited
chunk. The check was done by Claude (the coding assistant), not by a person; a person
should spot-check a few of these before the numbers are quoted outside the project.

**Result: the hand check agrees with 19 of 20 verdicts** (target: at least 18).

| # | Question | Claim (shortened) | Judge | Hand check |
|---|---|---|---|---|
| 1 | df-04 | QC programme: periodic microbiological examination of air, water, hand swabs and food-contact surfaces, records kept, **testing at least once every six months** | supported | **partial**: the passage's "at least once in six months" is for testing food products for contaminants; air, water and swab checks are only "periodic". The claim merges two requirements. |
| 2 | cd-03 | Salt intake should be limited to less than 5 g per day | supported | supported, borderline: the passage says "in adults"; children's limit is lower. The claim drops the qualifier. |
| 3 | cd-04 | Sugar may be consumed but restricted to 25–30 g per day | supported | supported |
| 4 | cd-04 | Free sugars include mono- and disaccharides added to foods, and sugars in honey, syrups and juices | supported | supported |
| 5 | cd-04 | Reduce free sugars without using non-sugar sweeteners | supported | supported |
| 6 | nm-02 | Free sugars below 10% of total energy intake | supported | supported |
| 7 | rc-03 | Boil water when its safety is in doubt | supported | supported |
| 8 | sd-04 | Washing with potable, ozonated or chlorinated water | supported | supported |
| 9 | nm-03 | Regular physical activity and yoga are crucial to maintain good health and weight | supported | supported |
| 10 | nm-03 | Regular UPF/HFSS consumption increases the risk of diabetes | supported | supported |
| 11 | cd-02 | Chilled meat, including chicken, stored at or below 4 °C until dispatch | supported | supported |
| 12 | rc-01 | Restrict processed and preserved foods (snacks, sauces, ketchup, …) | supported | supported |
| 13 | sd-03 | Work wear: fit for purpose, no buttons or pockets above the waist, laundered, hair restrained; PPE used and kept hygienic | supported | supported (two chunks: grooming rules and the inspection checklist) |
| 14 | df-02 | Industrial and ruminant trans fat, and where each is found | supported | supported |
| 15 | sd-03 | Report jaundice, diarrhoea, vomiting, fever …; cover cuts with waterproof dressings | supported | supported |
| 16 | sd-03 | Handlers inoculated against enteric diseases, records kept | supported | supported |
| 17 | sd-02 | Children 6–9: at least 350 g of fruit and vegetables a day | supported | supported |
| 18 | rc-01 | Salt intake exceeds the requirement; no more than 5 g a day | supported | supported |
| 19 | nm-03 | To maintain weight and waist: vegetables every meal, whole grains, pulses; avoid sugar, processed foods, juices, HFSS | supported | supported |
| 20 | df-01 | Millets up to 30–40% of total recommended cereals (raw weight) | supported | supported |

## What this says about the judge

- It catches nothing on this sample that the validator missed, but it is **lenient where a
  claim merges two requirements or drops a qualifier** (#1, #2). The judge marked all 82
  dev claims supported, so judged precision (1.00) is an upper bound; the hand sample
  suggests the true figure is around 0.95–1.00.
- Both lenient cases are about scope, not invented facts: every number and food in the
  sample is in the cited text. That is what the validator's number and key-word checks
  (6.5) enforce.
- Possible tightening, not done: tell the judge that a claim must keep the passage's
  population ("in adults") and must not attach a condition from one sentence to another.
