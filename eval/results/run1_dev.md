# Eval report: golden.yaml, dev split (35 questions)

| Metric | Result | Target | |
|---|---|---|---|
| Retrieval Recall@10 | 1.00 | ≥ 0.90 | ✅ |
| Out-of-scope refusal recall | 100% | 100% | ✅ |
| Not-in-corpus refusal recall | 100% | ≥ 95% | ✅ |
| False refusal on answerable questions | 0% | ≤ 10% | ✅ |
| Citation precision (judged) | n/a | ≥ 0.95 | — |
| Blend rate | 0.00 | 0 | ✅ |
| Claims without citation in output | 0 | 0 | ✅ |
| p95 latency | n/a | ≤ 8 s | — |

- Questions: 35, passed 34 (status and cited documents right).
- Recall@10 over 21 answerable questions with gold chunks.
- False refusals on near misses: 0%.
- Errors (pipeline raised): 0.
- Claims rendered: 79; judged: 0 .
- Latency over 0 questions answered live (no LLM cache hits), quota waits excluded: p50 n/a s, p95 n/a s. All questions as run (cache hits included): p50 1.82 s, p95 12.95 s.

## By category

| Category | Questions | Status right | Docs right | Passed |
|---|---|---|---|---|
| single_doc | 4 | 4 | 4 | 4 |
| table_lookup | 3 | 3 | 3 | 3 |
| recommendation | 3 | 3 | 3 | 3 |
| doc_filtered | 4 | 4 | 4 | 4 |
| cross_doc | 4 | 4 | 3 | 3 |
| not_in_corpus | 3 | 3 | 3 | 3 |
| unknown_doc | 2 | 2 | 2 | 2 |
| out_of_scope | 9 | 9 | 9 | 9 |
| near_miss | 3 | 3 | 3 | 3 |

## Failures

| Id | Category | Expected | Got | Cited | Stage | Trace |
|---|---|---|---|---|---|---|
| cd-02 | cross_doc | answered | partial | fssai-fsms-poultry, icmr-nin-dgi-2024 | retrieval (gold chunk of foodsafety-cold-storage not in evidence) | `949b35289e78` |

## All questions

| Id | Split | Category | Got | Cited | Latency (s) | Live |
|---|---|---|---|---|---|---|
| sd-01 | dev | single_doc | answered | who-healthy-diet | 2.0 |  |
| sd-02 | dev | single_doc | answered | who-healthy-diet | 0.9 |  |
| sd-03 | dev | single_doc | answered | fssai-fsms-milk | 2.5 |  |
| sd-04 | dev | single_doc | answered | fssai-fsms-fruits-vegetables | 2.7 |  |
| tl-01 | dev | table_lookup | answered | foodsafety-cold-storage | 2.5 |  |
| tl-02 | dev | table_lookup | answered | foodsafety-cold-storage | 2.3 |  |
| tl-03 | dev | table_lookup | answered | foodsafety-cold-storage | 1.8 |  |
| rc-01 | dev | recommendation | answered | icmr-nin-dgi-2024 | 1.4 |  |
| rc-02 | dev | recommendation | answered | icmr-nin-dgi-2024 | 1.2 |  |
| rc-03 | dev | recommendation | answered | icmr-nin-dgi-2024 | 1.4 |  |
| df-01 | dev | doc_filtered | answered | icmr-nin-dgi-2024 | 2.2 |  |
| df-02 | dev | doc_filtered | answered | who-healthy-diet | 0.9 |  |
| df-03 | dev | doc_filtered | answered | fssai-fsms-milk | 41.7 |  |
| df-04 | dev | doc_filtered | answered | fssai-fsms-poultry | 2.9 |  |
| cd-01 | dev | cross_doc | answered | icmr-nin-dgi-2024, who-healthy-diet | 8.1 |  |
| cd-02 | dev | cross_doc | partial ❌ | fssai-fsms-poultry, icmr-nin-dgi-2024 | 10.4 |  |
| cd-03 | dev | cross_doc | answered | icmr-nin-dgi-2024, who-healthy-diet | 2.3 |  |
| cd-04 | dev | cross_doc | answered | who-healthy-diet, icmr-nin-dgi-2024 | 4.1 |  |
| nc-01 | dev | not_in_corpus | not_in_corpus | — | 2.9 |  |
| nc-02 | dev | not_in_corpus | not_in_corpus | — | 3.5 |  |
| nc-03 | dev | not_in_corpus | not_in_corpus | — | 2.7 |  |
| ud-01 | dev | unknown_doc | not_in_corpus | — | 0.5 |  |
| ud-02 | dev | unknown_doc | not_in_corpus | — | 0.7 |  |
| os-01 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-02 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-03 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-04 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-05 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-06 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-07 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-08 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| os-09 | dev | out_of_scope | out_of_scope | — | 0.0 |  |
| nm-01 | dev | near_miss | answered | who-healthy-diet | 1.1 |  |
| nm-02 | dev | near_miss | answered | who-healthy-diet | 18.9 |  |
| nm-03 | dev | near_miss | answered | icmr-nin-dgi-2024 | 3.8 |  |
