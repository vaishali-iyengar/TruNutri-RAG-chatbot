# Eval report: golden.yaml, all split (48 questions)

| Metric | Result | Target | |
|---|---|---|---|
| Retrieval Recall@10 | 1.00 | ≥ 0.90 | ✅ |
| Out-of-scope refusal recall | 100% | 100% | ✅ |
| Not-in-corpus refusal recall | 100% | ≥ 95% | ✅ |
| False refusal on answerable questions | 3% | ≤ 10% | ✅ |
| Citation precision (judged) | 0.98 | ≥ 0.95 | ✅ |
| Blend rate | 0.00 | 0 | ✅ |
| Claims without citation in output | 0 | 0 | ✅ |
| p95 latency | n/a | ≤ 8 s | — |

- Questions: 48, passed 47 (status and cited documents right).
- Recall@10 over 29 answerable questions with gold chunks.
- False refusals on near misses: 17%.
- Errors (pipeline raised): 0.
- Claims rendered: 106; judged: 106 {'supported': 104, 'partial': 2}.
- Latency over 0 questions answered live (no LLM cache hits), quota waits excluded: p50 n/a s, p95 n/a s. All questions as run (cache hits included): p50 1.35 s, p95 27.88 s.

## By category

| Category | Questions | Status right | Docs right | Passed |
|---|---|---|---|---|
| single_doc | 5 | 5 | 5 | 5 |
| table_lookup | 4 | 4 | 4 | 4 |
| recommendation | 4 | 4 | 4 | 4 |
| doc_filtered | 5 | 5 | 5 | 5 |
| cross_doc | 5 | 5 | 5 | 5 |
| not_in_corpus | 4 | 4 | 4 | 4 |
| unknown_doc | 4 | 4 | 4 | 4 |
| out_of_scope | 11 | 11 | 11 | 11 |
| near_miss | 6 | 5 | 5 | 5 |

## Failures

| Id | Category | Expected | Got | Cited | Stage | Trace |
|---|---|---|---|---|---|---|
| nm-05 | near_miss | answered | not_in_corpus/not_in_corpus | — | sufficiency (evidence check: no) | `801d632def63` |

## Claims the judge didn't mark supported

| Id | Verdict | Claim | Reason |
|---|---|---|---|
| df-05 | partial | Cooked leftovers can be kept in the freezer for 2 to 6 months. | The passage states that cooked meat or poultry leftovers can be kept 2 to 6 months, but does not say that all cooked leftovers have that same freezer life; other cooked leftovers (e.g., pizza) have shorter times, so the claim overgeneralizes. |
| cd-05 | partial | Disinfection after washing is performed to kill contaminated microorganisms. | Passage says sanitization (not disinfection) after washing kills microorganisms; it mentions disinfection as a critical step but not that it kills after washing. |

## All questions

| Id | Split | Category | Got | Cited | Latency (s) | Live |
|---|---|---|---|---|---|---|
| sd-01 | dev | single_doc | answered | who-healthy-diet | 1.9 |  |
| sd-02 | dev | single_doc | answered | who-healthy-diet | 0.8 |  |
| sd-03 | dev | single_doc | answered | fssai-fsms-milk | 2.1 |  |
| sd-04 | dev | single_doc | answered | fssai-fsms-fruits-vegetables | 1.8 |  |
| sd-05 | holdout | single_doc | answered | jecfa-trs-1058 | 1.2 |  |
| tl-01 | dev | table_lookup | answered | foodsafety-cold-storage | 1.6 |  |
| tl-02 | dev | table_lookup | answered | foodsafety-cold-storage | 1.8 |  |
| tl-03 | dev | table_lookup | answered | foodsafety-cold-storage | 1.4 |  |
| tl-04 | holdout | table_lookup | answered | foodsafety-cold-storage | 1.3 |  |
| rc-01 | dev | recommendation | answered | icmr-nin-dgi-2024 | 1.1 |  |
| rc-02 | dev | recommendation | answered | icmr-nin-dgi-2024 | 1.0 |  |
| rc-03 | dev | recommendation | answered | icmr-nin-dgi-2024 | 46.1 |  |
| rc-04 | holdout | recommendation | answered | icmr-nin-dgi-2024 | 1.5 |  |
| df-01 | dev | doc_filtered | answered | icmr-nin-dgi-2024 | 1.6 |  |
| df-02 | dev | doc_filtered | answered | who-healthy-diet | 1.0 |  |
| df-03 | dev | doc_filtered | answered | fssai-fsms-milk | 1.9 |  |
| df-04 | dev | doc_filtered | answered | fssai-fsms-poultry | 1.4 |  |
| df-05 | holdout | doc_filtered | answered | foodsafety-cold-storage | 0.9 |  |
| cd-01 | dev | cross_doc | answered | icmr-nin-dgi-2024, who-healthy-diet | 5.6 |  |
| cd-02 | dev | cross_doc | answered | fssai-fsms-poultry, foodsafety-cold-storage, icmr-nin-dgi-2024 | 3.6 |  |
| cd-03 | dev | cross_doc | answered | icmr-nin-dgi-2024, who-healthy-diet | 1.5 |  |
| cd-04 | dev | cross_doc | answered | who-healthy-diet, icmr-nin-dgi-2024 | 1.3 |  |
| cd-05 | holdout | cross_doc | answered | fssai-fsms-fruits-vegetables, icmr-nin-dgi-2024 | 40.2 |  |
| nc-01 | dev | not_in_corpus | not_in_corpus | — | 2.0 |  |
| nc-02 | dev | not_in_corpus | not_in_corpus | — | 1.7 |  |
| nc-03 | dev | not_in_corpus | not_in_corpus | — | 2.2 |  |
| nc-04 | holdout | not_in_corpus | not_in_corpus | — | 1.3 |  |
| ud-01 | dev | unknown_doc | not_in_corpus | — | 0.9 |  |
| ud-02 | dev | unknown_doc | not_in_corpus | — | 0.5 |  |
| ud-03 | holdout | unknown_doc | not_in_corpus | — | 0.7 |  |
| ud-04 | dev | unknown_doc | not_in_corpus | — | 4.5 |  |
| os-01 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-02 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-03 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-04 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-05 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-06 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-07 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-08 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-09 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-10 | holdout | out_of_scope | out_of_scope | — | 0.0 |  |
| os-11 | holdout | out_of_scope | out_of_scope | — | 0.0 |  |
| nm-01 | dev | near_miss | answered | who-healthy-diet | 4.3 |  |
| nm-02 | dev | near_miss | answered | who-healthy-diet | 1.3 |  |
| nm-03 | dev | near_miss | answered | icmr-nin-dgi-2024 | 39.9 |  |
| nm-04 | holdout | near_miss | answered | who-healthy-diet | 1.8 |  |
| nm-05 | dev | near_miss | not_in_corpus ❌ | — | 5.0 |  |
| nm-06 | dev | near_miss | answered | who-healthy-diet | 1.6 |  |
