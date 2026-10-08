# Threshold calibration (7.5)

Golden set v2: 27 answerable and 4 not-in-corpus questions. Scores are rerank scores (`cross-encoder/ms-marco-MiniLM-L-12-v2`), best over the question and its halves.

## Best score per question

- Answerable: lowest **0.446** (df-01), median 0.989
- Not in corpus: highest **0.102** (nc-04); nc-01 0.001, nc-02 0.004, nc-03 0.000, nc-04 0.102
- Gap between the groups: 0.102–0.446

## Score gate over the grid

Cells: answerable passed / 27 · not-in-corpus passed (false answers) / 4. A question passes when evidence is selected at `tau_doc` and its best score reaches `tau_answer`.

| tau_doc \ tau_answer | 0.1 | 0.15 | 0.2 | 0.25 | 0.3 | 0.35 | 0.4 | 0.45 | 0.5 | 0.6 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.05 | 27 · 1 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 26 · 0 | 26 · 0 | 26 · 0 |
| 0.1 | 27 · 1 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 26 · 0 | 26 · 0 | 26 · 0 |
| 0.15 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 26 · 0 | 26 · 0 | 26 · 0 |
| 0.2 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 26 · 0 | 26 · 0 | 26 · 0 |
| 0.25 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 26 · 0 | 26 · 0 | 26 · 0 |
| 0.3 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 26 · 0 | 26 · 0 | 26 · 0 |
| 0.4 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 27 · 0 | 26 · 0 | 26 · 0 | 26 · 0 |

## Pick

`tau_doc` = **0.2**, `tau_answer` = **0.27**: 27/27 answerable pass the score gate, 0/4 false answers.

## End to end at the pick (score check + LLM evidence check + generator)

| Category: status | Count |
|---|---:|
| cross_doc: answered | 4 |
| cross_doc: partial | 1 |
| doc_filtered: answered | 5 |
| near_miss: answered | 4 |
| not_in_corpus: not_in_corpus | 4 |
| recommendation: answered | 4 |
| single_doc: answered | 5 |
| table_lookup: answered | 4 |

- Not-in-corpus questions answered `not_in_corpus` with the documents listed: all
- Answerable questions wrongly refused: 0/27 (0%; target ≤ 10%) 

## The evidence check on hard cases (live, 2026-10-07)

All 4 not-in-corpus golden questions stop at the score check, so the LLM evidence check
was also probed with questions retrieval finds related passages for. Gate = score check
(`tau_answer` 0.27) then the evidence check (`openai/gpt-oss-20b`).

| Question | Best score | Gate | Verdict | Correct? |
|---|---:|---|---|---|
| Is it safe to microwave food in plastic containers? | 0.772 | refused | no | Yes: the passage is about microwave cooking preserving nutrients, nothing on plastic. **The score check alone would have answered it.** |
| Can I reuse frying oil, and what is the smoke point of mustard oil? | 0.964 | answered | partial ("smoke point of mustard oil") | Yes |
| How long can raw eggs in the shell be kept in the refrigerator? | 0.961 | answered | yes | Yes |
| How long can cooked tofu be kept in the fridge? | 0.174 | refused | — (no evidence) | Yes: the chart has no tofu row |
| How long can opened ketchup be kept in the fridge? | 0.141 | refused | — | Yes |
| At what temperature should a home freezer be set to keep ice cream soft? | 0.070 | refused | — | Yes |
| Can cooked rice be reheated more than once? | 0.042 | refused | — | Yes |
| Does WHO recommend drinking red wine for heart health? | 0.001 | refused | — | Yes |

## Limits

- Only 4 not-in-corpus golden questions back "zero false answers"; the gap (0.102 vs
  0.446) is wide but rests on few negatives. Phase 9 grows the set (9.4) and holds out
  questions for final scoring (9.1).
- If the evidence check can't run (Groq error or quota), the gate lets the question
  through and logs it; grounding then rests on the generator ("none") and the validator.
