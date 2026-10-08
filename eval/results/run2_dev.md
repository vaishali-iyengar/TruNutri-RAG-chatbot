# Eval report: golden.yaml, dev split (35 questions)

| Metric | Result | Target | |
|---|---|---|---|
| Retrieval Recall@10 | 1.00 | ≥ 0.90 | ✅ |
| Out-of-scope refusal recall | 100% | 100% | ✅ |
| Not-in-corpus refusal recall | 100% | ≥ 95% | ✅ |
| False refusal on answerable questions | 0% | ≤ 10% | ✅ |
| Citation precision (judged) | 1.00 | ≥ 0.95 | ✅ |
| Blend rate | 0.00 | 0 | ✅ |
| Claims without citation in output | 0 | 0 | ✅ |
| p95 latency | 18.12 | ≤ 8 s | ❌ |

- Questions: 35, passed 35 (status and cited documents right).
- Recall@10 over 21 answerable questions with gold chunks.
- False refusals on near misses: 0%.
- Errors (pipeline raised): 0.
- Claims rendered: 82; judged: 82 {'supported': 82}.
- Latency over 2 questions answered live (no LLM cache hits), quota waits excluded: p50 11.67 s, p95 18.12 s. All questions as run (cache hits included): p50 2.26 s, p95 23.80 s.

## By category

| Category | Questions | Status right | Docs right | Passed |
|---|---|---|---|---|
| single_doc | 4 | 4 | 4 | 4 |
| table_lookup | 3 | 3 | 3 | 3 |
| recommendation | 3 | 3 | 3 | 3 |
| doc_filtered | 4 | 4 | 4 | 4 |
| cross_doc | 4 | 4 | 4 | 4 |
| not_in_corpus | 3 | 3 | 3 | 3 |
| unknown_doc | 2 | 2 | 2 | 2 |
| out_of_scope | 9 | 9 | 9 | 9 |
| near_miss | 3 | 3 | 3 | 3 |

## Failures

None.

## All questions

| Id | Split | Category | Got | Cited | Latency (s) | Live |
|---|---|---|---|---|---|---|
| sd-01 | dev | single_doc | answered | who-healthy-diet | 2.5 |  |
| sd-02 | dev | single_doc | answered | who-healthy-diet | 1.9 |  |
| sd-03 | dev | single_doc | answered | fssai-fsms-milk | 3.3 |  |
| sd-04 | dev | single_doc | answered | fssai-fsms-fruits-vegetables | 3.5 |  |
| tl-01 | dev | table_lookup | answered | foodsafety-cold-storage | 3.3 |  |
| tl-02 | dev | table_lookup | answered | foodsafety-cold-storage | 55.9 | yes |
| tl-03 | dev | table_lookup | answered | foodsafety-cold-storage | 2.4 |  |
| rc-01 | dev | recommendation | answered | icmr-nin-dgi-2024 | 2.0 |  |
| rc-02 | dev | recommendation | answered | icmr-nin-dgi-2024 | 2.2 |  |
| rc-03 | dev | recommendation | answered | icmr-nin-dgi-2024 | 1.7 |  |
| df-01 | dev | doc_filtered | answered | icmr-nin-dgi-2024 | 4.7 |  |
| df-02 | dev | doc_filtered | answered | who-healthy-diet | 4.8 |  |
| df-03 | dev | doc_filtered | answered | fssai-fsms-milk | 3.4 |  |
| df-04 | dev | doc_filtered | answered | fssai-fsms-poultry | 3.3 |  |
| cd-01 | dev | cross_doc | answered | icmr-nin-dgi-2024, who-healthy-diet | 10.0 |  |
| cd-02 | dev | cross_doc | answered | fssai-fsms-poultry, foodsafety-cold-storage, icmr-nin-dgi-2024 | 58.6 | yes |
| cd-03 | dev | cross_doc | answered | icmr-nin-dgi-2024, who-healthy-diet | 4.1 |  |
| cd-04 | dev | cross_doc | answered | who-healthy-diet, icmr-nin-dgi-2024 | 4.6 |  |
| nc-01 | dev | not_in_corpus | not_in_corpus | — | 3.7 |  |
| nc-02 | dev | not_in_corpus | not_in_corpus | — | 3.6 |  |
| nc-03 | dev | not_in_corpus | not_in_corpus | — | 4.9 |  |
| ud-01 | dev | unknown_doc | not_in_corpus | — | 0.5 |  |
| ud-02 | dev | unknown_doc | not_in_corpus | — | 0.6 |  |
| os-01 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-02 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-03 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-04 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-05 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-06 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-07 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-08 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-09 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| nm-01 | dev | near_miss | answered | who-healthy-diet | 1.8 |  |
| nm-02 | dev | near_miss | answered | who-healthy-diet | 2.3 |  |
| nm-03 | dev | near_miss | answered | icmr-nin-dgi-2024 | 1.7 |  |
