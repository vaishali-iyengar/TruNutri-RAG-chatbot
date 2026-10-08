# Eval report: golden.yaml, holdout split (10 questions)

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

- Questions: 10, passed 9 (status and cited documents right).
- Recall@10 over 6 answerable questions with gold chunks.
- False refusals on near misses: 0%.
- Errors (pipeline raised): 1.
- Claims rendered: 22; judged: 0 .
- Latency over 0 questions answered live (no LLM cache hits), quota waits excluded: p50 n/a s, p95 n/a s. All questions as run (cache hits included): p50 2.28 s, p95 3.68 s.

## By category

| Category | Questions | Status right | Docs right | Passed |
|---|---|---|---|---|
| single_doc | 1 | 1 | 1 | 1 |
| table_lookup | 1 | 1 | 1 | 1 |
| recommendation | 1 | 1 | 1 | 1 |
| doc_filtered | 1 | 0 | 0 | 0 |
| cross_doc | 1 | 1 | 1 | 1 |
| not_in_corpus | 1 | 1 | 1 | 1 |
| unknown_doc | 1 | 1 | 1 | 1 |
| out_of_scope | 2 | 2 | 2 | 2 |
| near_miss | 1 | 1 | 1 | 1 |

## Failures

| Id | Category | Expected | Got | Cited | Stage | Trace |
|---|---|---|---|---|---|---|
| df-05 | doc_filtered | answered | error | — | llm unavailable | `413481e07ecf` |

## All questions

| Id | Split | Category | Got | Cited | Latency (s) | Live |
|---|---|---|---|---|---|---|
| sd-05 | holdout | single_doc | answered | jecfa-trs-1058 | 4.2 |  |
| tl-04 | holdout | table_lookup | answered | foodsafety-cold-storage | 2.2 |  |
| rc-04 | holdout | recommendation | answered | icmr-nin-dgi-2024 | 2.8 |  |
| df-05 | holdout | doc_filtered | error ❌ | — | 1.7 |  |
| cd-05 | holdout | cross_doc | answered | fssai-fsms-fruits-vegetables, icmr-nin-dgi-2024 | 3.1 |  |
| nc-04 | holdout | not_in_corpus | not_in_corpus | — | 2.9 |  |
| ud-03 | holdout | unknown_doc | not_in_corpus | — | 1.1 |  |
| os-10 | holdout | out_of_scope | out_of_scope | — | 0.0 |  |
| os-11 | holdout | out_of_scope | out_of_scope | — | 0.0 |  |
| nm-04 | holdout | near_miss | answered | who-healthy-diet | 2.4 |  |
