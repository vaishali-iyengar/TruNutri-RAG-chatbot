"""Scoring in the full eval (implementation-plan.md, 9.1-9.2), on hand-built outcomes."""

import json
from typing import Any

from eval.golden import GoldenEntry, load_golden
from eval.judge import Judge, JudgedClaim, Verdict, judge_schema
from eval.run_eval import (
    ERROR,
    Outcome,
    failure_stage,
    metrics,
    missed_targets,
    outcome,
    percentile,
)
from guidance_rag.llm import LLMError
from guidance_rag.models import Answer, AnswerStatus, Claim, DocAnswer
from guidance_rag.render import render_answer
from tests.fakes import CHUNKS, DGI_OILS, WHO_FATS, FakeLLM

GOLDEN = {q.id: q for q in load_golden().questions}


def made(
    entry: GoldenEntry,
    status: str,
    cited: list[str] = (),  # type: ignore[assignment]
    refusal: str | None = None,
    claims: list[tuple[str, list[str]]] | None = None,
    trace: dict[str, Any] | None = None,
    latency: float = 1.0,
) -> Outcome:
    claims = claims if claims is not None else [(d, [d]) for d in cited]
    return Outcome(entry, status, refusal, list(cited), claims, trace or {}, latency, 0.0, 0, 1)


def test_an_answer_with_the_expected_documents_passes() -> None:
    sd = GOLDEN["sd-01"]
    assert made(sd, "answered", ["who-healthy-diet"]).passed
    assert made(sd, "partial", ["who-healthy-diet"]).passed  # partial is still an answer
    assert not made(sd, "answered", ["icmr-nin-dgi-2024"]).passed  # wrong document
    assert not made(sd, "not_in_corpus").passed


def test_a_filtered_question_may_only_cite_the_filter() -> None:
    df = GOLDEN["df-01"]
    assert made(df, "answered", ["icmr-nin-dgi-2024"]).passed
    assert not made(df, "answered", ["icmr-nin-dgi-2024", "who-healthy-diet"]).passed


def test_a_refusal_must_have_the_right_category() -> None:
    os1 = GOLDEN["os-01"]  # medical
    assert made(os1, "out_of_scope", refusal="medical").passed
    assert not made(os1, "out_of_scope", refusal="calorie_target").passed
    assert not made(os1, "answered", ["who-healthy-diet"]).passed


def test_metrics() -> None:
    outcomes = [
        made(GOLDEN["sd-01"], "answered", ["who-healthy-diet"], latency=2.0),
        made(GOLDEN["nm-01"], "not_in_corpus", latency=4.0),  # a false refusal
        made(GOLDEN["os-01"], "out_of_scope", refusal="medical"),
        made(GOLDEN["nc-01"], "not_in_corpus", refusal="not_in_corpus"),
        made(
            GOLDEN["cd-01"],
            "answered",
            ["icmr-nin-dgi-2024", "who-healthy-diet"],
            claims=[("icmr-nin-dgi-2024", ["who-healthy-diet"]), ("who-healthy-diet", [])],
        ),
    ]
    outcomes[0].judged = [
        JudgedClaim("who-healthy-diet", "a", ("c",), Verdict.SUPPORTED, ""),
        JudgedClaim("who-healthy-diet", "b", ("c",), Verdict.PARTIAL, ""),
    ]

    m = metrics(outcomes)

    assert m["false_refusal"] == 1 / 3  # nm-01 of the 3 answerable
    assert m["near_miss_false_refusal"] == 1.0
    assert m["oos_recall"] == 1.0 and m["nic_recall"] == 1.0
    assert m["blend_rate"] == 1 / 3  # one claim cites another document
    assert m["uncited_claims"] == 1
    assert m["citation_precision"] == 0.5
    assert m["p50_latency_s"] == 1.0  # every outcome here counts as live
    assert set(missed_targets(m)) == {
        "Retrieval Recall@10",  # no traced ranking here, so no gold chunk was found
        "False refusal on answerable questions",
        "Citation precision (judged)",
        "Blend rate",
        "Claims without citation in output",
    }


def test_unmeasured_targets_are_not_counted_as_missed() -> None:
    m = metrics([made(GOLDEN["os-01"], "out_of_scope", refusal="medical")])

    assert m["citation_precision"] is None and m["recall_at_10"] is None
    assert missed_targets(m) == []


def test_recall_reads_the_traced_ranking() -> None:
    sd = GOLDEN["sd-01"]
    gold = sd.gold_chunk_ids[0]
    ranked = [[f"x:{i}", 0.5] for i in range(10)]

    hit = made(sd, "answered", ["who-healthy-diet"], trace={"retrieval": {"ranked": [[gold, 0.9]]}})
    miss = made(
        sd,
        "answered",
        ["who-healthy-diet"],
        trace={"retrieval": {"ranked": [*ranked, [gold, 0.1]]}},
    )

    assert hit.recall_hit() is True
    assert miss.recall_hit() is False  # 11th


def test_failure_stages() -> None:
    cd = GOLDEN["cd-02"]
    gold = {g.split(":")[0]: g for g in cd.gold_chunk_ids}
    missing_row = made(
        cd,
        "partial",
        ["fssai-fsms-poultry"],
        trace={"retrieval": {"evidence": [["foodsafety-cold-storage:x:1", 0.8]], "ranked": []}},
    )
    assert failure_stage(missing_row) == (
        "retrieval (gold chunk of foodsafety-cold-storage not in evidence)"
    )
    dropped = made(
        cd,
        "answered",
        ["fssai-fsms-poultry"],
        trace={
            "retrieval": {"evidence": [[gold["foodsafety-cold-storage"], 0.8]], "ranked": []},
            "dropped": [{"doc_id": "foodsafety-cold-storage"}],
        },
    )
    assert failure_stage(dropped) == "validator (claims from foodsafety-cold-storage dropped)"
    assert failure_stage(made(GOLDEN["os-01"], "answered", ["x"])) == "scope guard (missed)"
    assert failure_stage(made(GOLDEN["nc-01"], "answered", ["x"])).startswith("sufficiency")
    assert failure_stage(made(cd, ERROR)) == "llm unavailable"
    refused_by_score = made(
        GOLDEN["sd-01"],
        "not_in_corpus",
        trace={
            "retrieval": {
                "evidence": [["who-healthy-diet:a:1", 0.2]],
                "ranked": [[GOLDEN["sd-01"].gold_chunk_ids[0], 0.2]],
            },
            "sufficiency": {"sufficient": False, "reason": "score below tau_answer"},
        },
    )
    assert failure_stage(refused_by_score) == "sufficiency (score below tau_answer)"


def test_outcome_reads_cited_documents_from_the_rendered_answer() -> None:
    sections = [
        DocAnswer(doc_id="icmr-nin-dgi-2024", claims=[Claim(text="t", chunk_ids=[DGI_OILS])]),
        DocAnswer(doc_id="who-healthy-diet", claims=[Claim(text="u", chunk_ids=[WHO_FATS])]),
    ]
    answer = render_answer(sections, CHUNKS, "t")

    o = outcome(GOLDEN["cd-01"], answer, {}, 1.0, 0.0)

    assert o.cited_docs == ["icmr-nin-dgi-2024", "who-healthy-diet"]
    assert o.claims == [
        ("icmr-nin-dgi-2024", ["icmr-nin-dgi-2024"]),
        ("who-healthy-diet", ["who-healthy-diet"]),
    ]
    assert outcome(GOLDEN["cd-01"], None, {}, 1.0, 0.0).status == ERROR


def test_percentile() -> None:
    assert percentile([], 95) is None
    assert percentile([3.0], 95) == 3.0
    assert percentile([float(i) for i in range(1, 101)], 95) == 95.05


# --- Judge (9.2) --------------------------------------------------------------------------


def answer_with_two_claims() -> Answer:
    sections = [
        DocAnswer(
            doc_id="icmr-nin-dgi-2024",
            claims=[Claim(text="Reheating oil is harmful.", chunk_ids=[DGI_OILS])],
        ),
        DocAnswer(
            doc_id="who-healthy-diet", claims=[Claim(text="Use canola oil.", chunk_ids=[WHO_FATS])]
        ),
    ]
    return render_answer(sections, CHUNKS, "t")


def test_the_judge_gives_each_claim_its_verdict() -> None:
    reply = {
        "verdicts": [
            {"claim": 2, "verdict": "partial", "reason": "canola is one option among several"},
            {"claim": 1, "verdict": "supported", "reason": "stated"},
        ]
    }
    llm = FakeLLM(json.dumps(reply))

    judged = Judge(llm, CHUNKS).judge("Which oils?", answer_with_two_claims())

    assert [j.verdict for j in judged] == [Verdict.SUPPORTED, Verdict.PARTIAL]
    request = llm.requests[0]
    assert CHUNKS[DGI_OILS].text in request.user  # the judge sees the cited text
    assert "Use canola oil." in request.user


def test_a_failed_judge_leaves_claims_unjudged() -> None:
    llm = FakeLLM(LLMError("down"), LLMError("down"))

    judged = Judge(llm, CHUNKS).judge("Which oils?", answer_with_two_claims())

    assert [j.verdict for j in judged] == [None, None]
    assert metrics([made(GOLDEN["cd-01"], "answered", ["x"])])["judged"] == 0


def test_the_judge_schema_limits_claim_numbers() -> None:
    schema = judge_schema(3)
    item = schema["properties"]["verdicts"]["items"]
    assert item["properties"]["claim"]["enum"] == [1, 2, 3]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])


def test_no_claims_means_no_judge_call() -> None:
    llm = FakeLLM()
    answer = Answer(status=AnswerStatus.NOT_IN_CORPUS, trace_id="t")

    assert Judge(llm, CHUNKS).judge("q", answer) == []
    assert llm.requests == []
