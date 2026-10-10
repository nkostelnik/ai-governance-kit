"""Stage 4 tests. No API calls: the model's evidence is faked."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_governance import llm
from ai_governance.clauses import parse_documents
from ai_governance.rubric import load_rubric
from ai_governance.vendor import (
    RequirementResult,
    decide,
    propose_level,
    render_documents,
    response_schema,
    review,
    summarize,
)

BRIGHTLOOM = Path(__file__).resolve().parent.parent / "samples" / "vendors" / "brightloom"


@pytest.fixture(scope="module")
def rubric():
    return load_rubric()


@pytest.fixture(scope="module")
def doc_set():
    return parse_documents([BRIGHTLOOM / "marketing.txt", BRIGHTLOOM / "terms.docx"])


@pytest.fixture(scope="module")
def schema(doc_set):
    return response_schema(doc_set)


def req(rubric, requirement_id):
    return next(r for r in rubric.vendor_requirements if r.id == requirement_id)


def answer(schema, *evidence, addressed=True):
    return schema(addressed=addressed, evidence=[
        {"clause_id": c, "quote": q, "stance": s, "reason": "r"} for c, q, s in evidence
    ])


MARKETING_PROMISE = ("marketing:para-2", "Brightloom never trains on your data.", "meets")
TERMS_RESERVATION = ("terms:sec-4.3", "including to train and refine Brightloom's models", "falls_short")


# --- schema ------------------------------------------------------------------

def test_schema_only_allows_real_clause_ids(schema):
    with pytest.raises(ValidationError):
        answer(schema, ("terms:sec-99", "x", "meets"))


# --- deciding ----------------------------------------------------------------

def test_verified_meets_only_is_met(rubric, doc_set, schema):
    result = decide(req(rubric, "no_training"), answer(schema, MARKETING_PROMISE), doc_set)
    assert result.outcome == "met" and result.gap_kind is None


def test_marketing_promise_vs_terms_reservation_is_a_gap_with_review(rubric, doc_set, schema):
    result = decide(req(rubric, "no_training"), answer(schema, MARKETING_PROMISE, TERMS_RESERVATION), doc_set)
    assert result.outcome == "gap" and result.gap_kind == "falls_short" and result.gap_type == "blocker"
    assert any("conflicting language" in n for n in result.needs_review)


def test_silence_is_a_gap(rubric, doc_set, schema):
    result = decide(req(rubric, "output_ip_indemnity"), answer(schema, addressed=False), doc_set)
    assert result.gap_kind == "not_addressed" and result.gap_type == "flag"   # preferred requirement


def test_quote_not_in_cited_clause_is_dropped_and_fails_closed(rubric, doc_set, schema):
    wrong_clause = ("terms:sec-5", "Brightloom will not train on Customer Content", "meets")
    result = decide(req(rubric, "no_training"), answer(schema, wrong_clause), doc_set)
    assert result.outcome == "gap" and result.gap_kind == "unresolved"
    assert result.rejected and not result.evidence


def test_unverified_falls_short_is_not_ignored(rubric, doc_set, schema):
    fake_short = ("terms:sec-5", "subprocessors may train", "falls_short")
    result = decide(req(rubric, "no_training"), answer(schema, MARKETING_PROMISE, fake_short), doc_set)
    assert result.outcome == "gap" and result.gap_kind == "unresolved"


def test_addressed_but_no_evidence_is_unresolved(rubric, doc_set, schema):
    result = decide(req(rubric, "confidentiality"), answer(schema, addressed=True), doc_set)
    assert result.gap_kind == "unresolved"


def test_failed_call_is_an_unresolved_gap(rubric, doc_set):
    result = decide(req(rubric, "security"), None, doc_set, why_empty="stop_reason=refusal")
    assert result.outcome == "gap" and result.gap_kind == "unresolved"
    assert "refusal" in result.needs_review[0]


# --- proposing the vendor level ------------------------------------------------

def outcomes(rubric, **gaps):
    """A RequirementResult per requirement: met unless named in gaps."""
    return [RequirementResult(id=r.id, name=r.name, standard=r.standard, severity=r.severity,
                              outcome="gap" if r.id in gaps else "met",
                              gap_kind="falls_short" if r.id in gaps else None,
                              gap_type=("blocker" if r.severity == "must_have" else "flag") if r.id in gaps else None,
                              evidence=[], rejected=[], needs_review=[])
            for r in rubric.vendor_requirements]


def test_training_gap_proposes_vendor_trains_even_with_zdr(rubric):
    assert propose_level(outcomes(rubric, no_training=1), rubric)[0] == "vendor_trains"


def test_zdr_met_proposes_enterprise_zdr(rubric):
    assert propose_level(outcomes(rubric), rubric)[0] == "enterprise_zdr"


def test_no_zdr_but_retention_met_proposes_limited_retention(rubric):
    assert propose_level(outcomes(rubric, zdr_available=1), rubric)[0] == "enterprise_limited_retention"


def test_neither_proposes_default_consumer_tool(rubric):
    assert propose_level(outcomes(rubric, zdr_available=1, retention=1), rubric)[0] == "consumer_tool"


# --- approvability -------------------------------------------------------------

def test_clean_vendor_with_only_preferred_gaps_is_approvable(rubric, doc_set):
    result = summarize(doc_set, outcomes(rubric, subprocessors=1, output_ip_indemnity=1), rubric)
    assert result.approvable and result.blockers == []
    assert result.flags == ["subprocessors", "output_ip_indemnity"]


def test_must_have_gap_blocks_approval_even_with_good_level(rubric, doc_set):
    result = summarize(doc_set, outcomes(rubric, output_ownership=1), rubric)
    assert result.proposed_vendor_level == "enterprise_zdr"
    assert not result.approvable and "output_ownership" in result.approval_note


# --- wiring --------------------------------------------------------------------

def test_review_calls_once_per_requirement_with_cached_documents(rubric, doc_set, schema):
    calls = []

    def fake_call(system, question, output_format, cached_context=None):
        calls.append((question, cached_context))
        return llm.LLMResult(parsed=answer(output_format, addressed=False), stop_reason="end_turn")

    result = review(doc_set, rubric, call=fake_call)
    assert len(calls) == len(rubric.vendor_requirements)
    assert all(ctx == render_documents(doc_set) for _, ctx in calls)
    assert [r.id for r in result.requirements] == [r.id for r in rubric.vendor_requirements]
    # Nothing addressed anywhere: every requirement is a gap. Silence on training
    # is a no_training gap, so rule 1 proposes vendor_trains (Prohibited).
    assert all(r.outcome == "gap" for r in result.requirements)
    assert result.proposed_vendor_level == "vendor_trains" and not result.approvable
    assert "Not legal advice" in result.disclaimer
