"""Stage 2 tests. No API calls: the model's response is faked."""

import pytest

from ai_governance import DISCLAIMER, llm
from ai_governance.intake import (
    DimensionAnswer,
    Finding,
    Profile,
    ProfileField,
    RawExtraction,
    answer_follow_ups,
    build_system_prompt,
    normalize,
    quote_found,
    run_intake,
    verify,
)
from ai_governance.rubric import load_rubric

DESCRIPTION = (
    "Marketing wants a chatbot on our website that answers customer warranty questions. "
    "Customers type in their order number and the bot looks up their order history. "
    "Answers go straight to the customer in real time. Business owner is Dana Reyes."
)


@pytest.fixture(scope="module")
def rubric():
    return load_rubric()


def blank_profile(**overrides):
    fields = {name: ProfileField(value=None, quote=None) for name in Profile.model_fields}
    fields.update(overrides)
    return Profile(**fields)


def raw(*answers, profile=None):
    return RawExtraction(profile=profile or blank_profile(), dimensions=list(answers))


def answer(dimension_id, *findings, unclear=None):
    return DimensionAnswer(dimension_id=dimension_id, findings=list(findings), unclear_because=unclear)


def stated(level_id, quote):
    return Finding(level_id=level_id, quote=quote, basis="stated")


# --- quote matching ---------------------------------------------------------

def test_normalize_tolerates_whitespace_case_and_curly_quotes():
    assert normalize("  The  \u201cBot\u201d\nlooks ") == normalize('the "bot" looks')


def test_quote_must_actually_appear():
    assert quote_found("looks up their order history", DESCRIPTION)
    assert not quote_found("stores credit card numbers", DESCRIPTION)
    assert not quote_found("", DESCRIPTION)
    assert not quote_found(None, DESCRIPTION)


# --- verification -----------------------------------------------------------

def test_verified_finding_is_kept(rubric):
    result = verify(DESCRIPTION, raw(answer("audience", stated("external_direct", "go straight to the customer in real time"))), rubric)
    assert [f.level_id for f in result.answers["audience"]] == ["external_direct"]
    assert "audience" not in result.unknown_dimensions


def test_fabricated_quote_is_rejected_and_dimension_fails_closed(rubric):
    result = verify(DESCRIPTION, raw(answer("personal_data", stated("no_personal_data", "no personal data is used"))), rubric)
    assert "personal_data" not in result.answers
    assert "personal_data" in result.unknown_dimensions
    assert result.rejected[0].reason == "quote not found in description"
    assert any(fu.dimension_id == "personal_data" for fu in result.follow_ups)


def test_invented_level_is_rejected(rubric):
    result = verify(DESCRIPTION, raw(answer("audience", stated("the_whole_internet", "real time"))), rubric)
    assert result.rejected[0].reason == "level not in rubric"
    assert "audience" in result.unknown_dimensions


def test_invented_dimension_is_rejected(rubric):
    result = verify(DESCRIPTION, raw(answer("vibes", stated("good", "real time"))), rubric)
    assert result.rejected[0].reason == "dimension not in rubric"


def intake_dims(rubric):
    return [d.id for d in rubric.dimensions if d.source == "intake"]


def test_missing_dimensions_become_unknown_with_rubric_follow_ups(rubric):
    result = verify(DESCRIPTION, raw(answer("audience", stated("external_direct", "real time"))), rubric)
    assert len(result.unknown_dimensions) == len(intake_dims(rubric)) - 1
    follow_up = next(fu for fu in result.follow_ups if fu.dimension_id == "personal_data")
    assert [o.level_id for o in follow_up.options] == [lv.id for lv in rubric.dimension("personal_data").levels]


def test_register_dimension_is_never_unknown_or_asked(rubric):
    result = verify(DESCRIPTION, raw(), rubric)
    assert "vendor_handling" not in result.unknown_dimensions
    assert all(fu.dimension_id != "vendor_handling" for fu in result.follow_ups)


def test_description_cannot_set_register_dimension(rubric):
    result = verify(DESCRIPTION, raw(answer("vendor_handling", stated("enterprise_zdr", "Business owner is Dana Reyes"))), rubric)
    assert "vendor_handling" not in result.answers
    assert any("rated from the tool register" in note for note in result.needs_review)


def test_model_cannot_claim_a_requester_answer(rubric):
    fake = Finding(level_id="external_direct", quote="real time", basis="answered")
    result = verify(DESCRIPTION, raw(answer("audience", fake)), rubric)
    assert "audience" not in result.answers
    assert "requester answer" in result.rejected[0].reason


def test_follow_up_answers_close_questions_and_only_add(rubric):
    intake = verify(DESCRIPTION, raw(answer("audience", stated("external_direct", "real time"))), rubric)
    answered = answer_follow_ups(intake, {"personal_data": ["customer_basic"], "audience": ["personal_use"]}, rubric)
    assert "personal_data" not in answered.unknown_dimensions
    assert all(fu.dimension_id != "personal_data" for fu in answered.follow_ups)
    assert answered.answers["personal_data"][0].basis == "answered"
    assert {f.level_id for f in answered.answers["audience"]} == {"external_direct", "personal_use"}


def test_follow_up_answers_are_validated(rubric):
    intake = verify(DESCRIPTION, raw(), rubric)
    with pytest.raises(KeyError):
        answer_follow_ups(intake, {"personal_data": ["no_such_level"]}, rubric)
    with pytest.raises(ValueError, match="register"):
        answer_follow_ups(intake, {"vendor_handling": ["enterprise_zdr"]}, rubric)


def test_all_supported_levels_are_kept_not_just_the_worst(rubric):
    result = verify(DESCRIPTION, raw(answer(
        "personal_data",
        stated("customer_basic", "their order history"),
        stated("customer_basic", "order number"),          # duplicate level: kept once
    )), rubric)
    assert [f.level_id for f in result.answers["personal_data"]] == ["customer_basic"]


def test_inferred_finding_counts_but_needs_review(rubric):
    finding = Finding(level_id="customer_basic", quote="order history", basis="inferred")
    result = verify(DESCRIPTION, raw(answer("personal_data", finding)), rubric)
    assert "personal_data" in result.answers
    assert any("inferred" in note for note in result.needs_review)


def test_unclear_note_on_answered_dimension_needs_review(rubric):
    result = verify(DESCRIPTION, raw(answer("audience", stated("external_direct", "real time"), unclear="audience size not stated")), rubric)
    assert any("audience size not stated" in note for note in result.needs_review)


def test_profile_value_with_bad_quote_is_dropped(rubric):
    profile = blank_profile(
        business_owner=ProfileField(value="Dana Reyes", quote="Business owner is Dana Reyes"),
        department=ProfileField(value="Legal", quote="the legal department"),
    )
    result = verify(DESCRIPTION, raw(profile=profile), rubric)
    assert result.profile.business_owner.value == "Dana Reyes"
    assert result.profile.department.value is None


def test_no_usable_response_means_everything_unknown(rubric):
    result = verify(DESCRIPTION, None, rubric, why_empty="stop_reason=refusal")
    assert result.answers == {}
    assert len(result.unknown_dimensions) == len(intake_dims(rubric))
    assert "refusal" in result.needs_review[0]


def test_every_result_carries_the_disclaimer(rubric):
    assert verify(DESCRIPTION, None, rubric).disclaimer == DISCLAIMER


# --- prompt and wiring ------------------------------------------------------

def test_system_prompt_lists_every_rubric_level(rubric):
    prompt = build_system_prompt(rubric)
    for dim in rubric.dimensions:
        for level in dim.levels:
            assert f"- {level.id}:" in prompt


def test_run_intake_uses_the_injected_call(rubric):
    seen = {}

    def fake_call(system, user, output_format):
        seen["user"] = user
        parsed = raw(answer("audience", stated("external_direct", "real time")))
        return llm.LLMResult(parsed=parsed, stop_reason="end_turn")

    result = run_intake(DESCRIPTION, rubric, call=fake_call)
    assert "<description>" in seen["user"]
    assert "audience" in result.answers


def test_run_intake_refusal_fails_closed(rubric):
    def refusing_call(system, user, output_format):
        return llm.LLMResult(parsed=None, stop_reason="refusal")

    result = run_intake(DESCRIPTION, rubric, call=refusing_call)
    assert len(result.unknown_dimensions) == len(intake_dims(rubric))
