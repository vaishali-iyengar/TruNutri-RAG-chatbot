# Eval report: golden.yaml, dev split (6 questions)

| Metric | Result | Target | |
|---|---|---|---|
| Retrieval Recall@10 | 1.00 | ≥ 0.90 | ✅ |
| Out-of-scope refusal recall | n/a | 100% | — |
| Not-in-corpus refusal recall | n/a | ≥ 95% | — |
| False refusal on answerable questions | 0% | ≤ 10% | ✅ |
| Citation precision (judged) | n/a | ≥ 0.95 | — |
| Blend rate | 0.00 | 0 | ✅ |
| Claims without citation in output | 0 | 0 | ✅ |
| p95 latency | 8.43 | ≤ 8 s | ❌ |

- Questions: 6, passed 6 (status and cited documents right).
- Recall@10 over 6 answerable questions with gold chunks.
- False refusals on near misses: 0%.
- Errors (pipeline raised): 0.
- Claims rendered: 23; judged: 0 .
- Latency over 6 questions answered live (no LLM cache hits), quota waits excluded: p50 4.31 s, p95 8.43 s. All questions as run (cache hits included): p50 58.74 s, p95 61.55 s.

## By category

| Category | Questions | Status right | Docs right | Passed |
|---|---|---|---|---|
| single_doc | 1 | 1 | 1 | 1 |
| table_lookup | 1 | 1 | 1 | 1 |
| recommendation | 1 | 1 | 1 | 1 |
| doc_filtered | 1 | 1 | 1 | 1 |
| cross_doc | 1 | 1 | 1 | 1 |
| near_miss | 1 | 1 | 1 | 1 |

## Failures

None.

## All questions

| Id | Split | Category | Got | Cited | Latency (s) | Live |
|---|---|---|---|---|---|---|
| sd-01 | dev | single_doc | answered | who-healthy-diet | 3.9 | yes |
| tl-01 | dev | table_lookup | answered | foodsafety-cold-storage | 3.2 | yes |
| rc-01 | dev | recommendation | answered | icmr-nin-dgi-2024 | 61.6 | yes |
| df-01 | dev | doc_filtered | answered | icmr-nin-dgi-2024 | 60.0 | yes |
| cd-01 | dev | cross_doc | answered | icmr-nin-dgi-2024, who-healthy-diet | 61.5 | yes |
| nm-01 | dev | near_miss | answered | who-healthy-diet | 57.4 | yes |
