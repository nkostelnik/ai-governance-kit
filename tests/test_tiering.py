"""Stage 3 tests. Pure Python: no API, no network."""

import copy
import json
from pathlib import Path

import pytest
import yaml

from ai_governance.intake import Finding, IntakeResult, Profile, ProfileField
from ai_governance.rubric import DEFAULT_RUBRIC, Rubric, Tier, load_rubric
from ai_governance.tiering import ToolRecord, assess, is_approved_tool

FIXTURES = Path(__file__).parent / "fixtures" / "intakes"

ZDR_TOOL = ToolRecord(name="Approved Assistant", vendor_handling_level="enterprise_zdr", listed_as_approved=True)


@pytest.fixture(scope="module")
def rubric():
    return load_rubric()


def intake(answers: dict[str, list[str]], unknown: list[str] | None = None) -> IntakeResult:
    """An intake with the given levels found; every other intake dimension unknown unless `unknown` says otherwise."""
    profile = Profile(**{f: ProfileField(value=None, quote=None) for f in Profile.model_fields})
    found = {d: [Finding(level_id=lv, quote="q", basis="stated") for lv in lvs] for d, lvs in answers.items()}
    if unknown is None:
        unknown = [d.id for d in load_rubric().dimensions if d.source == "intake" and d.id not in answers]
    return IntakeResult(description="d", profile=profile, answers=found, unknown_dimensions=unknown,
                        needs_review=[], rejected=[], follow_ups=[])


ALL_LOW = {
    "data_sensitivity": ["public"],
    "personal_data": ["no_personal_data"],
    "decision_impact": ["draft_reviewed"],
    "regulated_domain": ["no_regulated_domain"],
    "audience": ["personal_use"],
    "accuracy_criticality": ["errors_harmless"],
}


def with_(**changes):
    return {**ALL_LOW, **changes}


def rubric_with(tiers: dict[str, str] | None = None, count_unknowns: bool | None = None) -> Rubric:
    """A copy of the real rubric with some level tiers changed, to test rules the
    current rubric cannot reach (after the Stage 6 recalibration, stacking cannot
    fire on real facts)."""
    raw = copy.deepcopy(yaml.safe_load(DEFAULT_RUBRIC.read_text(encoding="utf-8")))
    for dim in raw["dimensions"]:
        for level in dim["levels"]:
            if level["id"] in (tiers or {}):
                level["tier"] = tiers[level["id"]]
    if count_unknowns is not None:
        raw["aggregation"]["stacking"]["count_unknowns"] = count_unknowns
    return Rubric.model_validate(raw)


STACKABLE = rubric_with({"external_reviewed": "Medium", "domain_not_individual": "Medium",
                         "customer_reliance_verified": "Medium"})


def load_fixture(name) -> IntakeResult:
    return IntakeResult.model_validate(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))


# --- approved tool -----------------------------------------------------------

def test_approved_tool_needs_approved_level_and_listing(rubric):
    assert is_approved_tool(ZDR_TOOL, rubric)
    assert not is_approved_tool(None, rubric)
    assert not is_approved_tool(ZDR_TOOL.model_copy(update={"listed_as_approved": False}), rubric)
    assert not is_approved_tool(ZDR_TOOL.model_copy(update={"vendor_handling_level": "vendor_trains"}), rubric)


def test_unregistered_tool_is_prohibited_even_if_everything_else_is_low(rubric):
    result = assess(intake(ALL_LOW), tool=None, rubric=rubric)
    assert result.tier == Tier.Prohibited
    vendor = next(r for r in result.ratings if r.dimension_id == "vendor_handling")
    assert vendor.source == "register" and vendor.driver_level == "vendor_unknown"


def test_all_low_in_approved_tool_is_low_and_final(rubric):
    result = assess(intake(ALL_LOW), tool=ZDR_TOOL, rubric=rubric)
    assert result.tier == Tier.Low
    assert not result.provisional
    assert result.review_cadence_months == 12
    assert [a.id for a in result.approvers] == ["business_owner"]


def test_approved_tool_exception_switches_tier(rubric):
    facts = intake(with_(data_sensitivity=["privileged"]))
    assert assess(facts, tool=ZDR_TOOL, rubric=rubric).tier == Tier.High
    unlisted = ZDR_TOOL.model_copy(update={"listed_as_approved": False})
    assert assess(facts, tool=unlisted, rubric=rubric).tier == Tier.Prohibited


def test_absolute_prohibition_ignores_approved_tool(rubric):
    result = assess(intake(with_(data_sensitivity=["security_secrets"])), tool=ZDR_TOOL, rubric=rubric)
    assert result.tier == Tier.Prohibited
    assert result.controls == [] and result.approvers == []
    assert "general_counsel" in result.prohibited_exception


# --- aggregation -------------------------------------------------------------

def test_worst_level_in_a_dimension_wins(rubric):
    result = assess(intake(with_(personal_data=["customer_basic", "job_applicant"])), tool=ZDR_TOOL, rubric=rubric)
    rating = next(r for r in result.ratings if r.dimension_id == "personal_data")
    assert rating.tier == Tier.High and rating.driver_level == "job_applicant"


def test_two_mediums_stay_medium():
    facts = intake(with_(audience=["external_reviewed"], regulated_domain=["domain_not_individual"]))
    result = assess(facts, tool=ZDR_TOOL, rubric=STACKABLE)
    assert result.tier == Tier.Medium and not result.stacking_applied


def test_three_mediums_stack_to_high():
    facts = intake(with_(audience=["external_reviewed"], regulated_domain=["domain_not_individual"],
                         accuracy_criticality=["customer_reliance_verified"]))
    result = assess(facts, tool=ZDR_TOOL, rubric=STACKABLE)
    assert result.tier == Tier.High and result.stacking_applied
    assert "stacking" in result.reasons[0]


def test_stacking_does_not_lower_or_exceed():
    facts = intake(with_(audience=["external_reviewed"], regulated_domain=["domain_not_individual"],
                         accuracy_criticality=["customer_reliance_verified"],
                         decision_impact=["person_decision_automated"]))
    result = assess(facts, tool=ZDR_TOOL, rubric=STACKABLE)
    assert result.tier == Tier.Prohibited and not result.stacking_applied


def test_stacking_cannot_fire_on_the_current_rubric(rubric):
    """Documents a Stage 6 consequence: no three real levels are Medium any more."""
    mediums = [lv.id for d in rubric.dimensions if d.source == "intake" for lv in d.levels if lv.tier == Tier.Medium]
    assert mediums == ["critical_reliance_verified"]


def test_unknown_dimensions_are_medium_and_provisional(rubric):
    facts = intake({k: v for k, v in ALL_LOW.items() if k != "personal_data"})
    result = assess(facts, tool=ZDR_TOOL, rubric=rubric)
    assert result.tier == Tier.Medium
    assert result.provisional
    assert any("personal_data is unknown" in n for n in result.needs_review)


def test_everything_unknown_is_medium_and_provisional_never_low(rubric):
    result = assess(intake({}), tool=ZDR_TOOL, rubric=rubric)
    assert result.tier == Tier.Medium and not result.stacking_applied and result.provisional


def test_unknowns_stack_when_the_rubric_says_so():
    result = assess(intake({}), tool=ZDR_TOOL, rubric=rubric_with(count_unknowns=True))
    assert result.tier == Tier.High and result.stacking_applied


# --- controls, approvers, flags ----------------------------------------------

def test_controls_are_cumulative_and_triggered(rubric):
    result = assess(intake(with_(audience=["external_direct"])), tool=ZDR_TOOL, rubric=rubric)
    ids = [c.id for c in result.controls]
    assert result.tier == Tier.High
    assert {"human_review", "privacy_review", "incident_kill_switch", "bot_disclosure"} <= set(ids)
    assert "bias_testing" not in ids
    assert next(c for c in result.controls if c.id == "bot_disclosure").why == "triggered by audience.external_direct"
    assert {"business_owner", "privacy", "legal", "ai_governance_committee"} <= {a.id for a in result.approvers}


def test_regulatory_flags_attach_and_stay_verify(rubric):
    result = assess(intake(with_(audience=["external_direct"])), tool=ZDR_TOOL, rubric=rubric)
    flag = next(f for f in result.regulatory_flags if f.id == "bot_disclosure")
    assert flag.matched == ["audience.external_direct"]
    assert flag.citation.startswith("VERIFY")


def test_result_carries_disclaimer_and_is_deterministic(rubric):
    facts = intake(with_(audience=["external_direct"]))
    first, second = assess(facts, ZDR_TOOL, rubric), assess(facts, ZDR_TOOL, rubric)
    assert first == second
    assert "attorney review" in first.disclaimer


# --- end to end on live smoke-test intakes ----------------------------------

@pytest.mark.parametrize("name, expected, provisional", [
    ("email_rewrite", Tier.Medium, True),               # regulated_domain unknown
    ("warranty_chatbot", Tier.High, True),
    ("legal_sharepoint_search", Tier.High, True),        # privileged in an approved tool
    ("productivity_screener", Tier.Prohibited, False),   # employment decision
    ("vague", Tier.Medium, True),                        # unknowns are Medium and no longer stack
])
def test_smoke_test_intakes_in_an_approved_tool(rubric, name, expected, provisional):
    result = assess(load_fixture(name), tool=ZDR_TOOL, rubric=rubric)
    assert result.tier == expected
    assert result.provisional == provisional


def test_every_smoke_test_intake_is_prohibited_without_a_registered_tool(rubric):
    for path in FIXTURES.glob("*.json"):
        assert assess(load_fixture(path.stem), tool=None, rubric=rubric).tier == Tier.Prohibited
