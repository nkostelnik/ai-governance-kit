import copy

import pytest
import yaml
from pydantic import ValidationError

from ai_governance.rubric import DEFAULT_RUBRIC, Rubric, Tier, load_rubric


@pytest.fixture
def raw():
    with open(DEFAULT_RUBRIC, encoding="utf-8") as f:
        return yaml.safe_load(f)


def dim(raw, dimension_id):
    return next(d for d in raw["dimensions"] if d["id"] == dimension_id)


def test_governance_rubric_loads():
    rubric = load_rubric()
    assert len(rubric.dimensions) == 7
    confidential = rubric.dimension("data_sensitivity").level("company_confidential")
    assert confidential.tier == Tier.Prohibited
    assert confidential.tier_if_approved_tool == Tier.High


def test_interview_answers_survive_loading():
    rubric = load_rubric()
    assert rubric.dimension("accuracy_criticality").level("critical_reliance_unverified").tier == Tier.Prohibited
    assert rubric.aggregation.stacking.min_count == 3
    assert rubric.unknowns.rating == Tier.Medium
    assert rubric.dimension("data_sensitivity").level("trade_secrets").tier_if_approved_tool is None


def test_calibration_changes_survive_loading():
    rubric = load_rubric()
    data = rubric.dimension("data_sensitivity")
    assert data.level("internal").tier == Tier.Low
    assert data.level("privileged").tier_if_approved_tool == Tier.High
    assert data.level("third_party_confidential").tier_if_approved_tool == Tier.High
    assert rubric.dimension("personal_data").level("employee_contact").tier_if_approved_tool == Tier.Low
    assert rubric.dimension("accuracy_criticality").level("customer_reliance_verified").tier == Tier.Medium
    assert rubric.dimension("accuracy_criticality").level("critical_reliance_verified").tier == Tier.Medium
    assert "enterprise_limited_retention" in rubric.approved_tool.vendor_handling_levels


def test_controls_and_approvers_are_cumulative():
    rubric = load_rubric()
    high_controls = rubric.controls.for_tier(Tier.High)
    assert "human_review" in high_controls      # inherited from Low
    assert "privacy_review" in high_controls    # inherited from Medium
    assert "incident_kill_switch" in high_controls
    assert "incident_kill_switch" not in rubric.controls.for_tier(Tier.Medium)
    assert "bias_testing" not in high_controls  # triggered by situation, not tier
    assert rubric.approvers.for_tier(Tier.Low) == ["business_owner"]
    assert "legal" in rubric.approvers.for_tier(Tier.High)


def test_every_regulatory_flag_is_unverified():
    # Nothing in this demo rubric has been confirmed by counsel yet.
    assert all(f.status == "VERIFY" for f in load_rubric().regulatory_flags)


def test_typo_in_key_is_rejected(raw):
    bad = copy.deepcopy(raw)
    level = dim(bad, "data_sensitivity")["levels"][2]
    level["tier_if_aproved_tool"] = level.pop("tier_if_approved_tool")
    with pytest.raises(ValidationError):
        Rubric.model_validate(bad)


def test_unknown_facts_cannot_be_rated_low(raw):
    bad = copy.deepcopy(raw)
    bad["unknowns"]["rating"] = "Low"
    with pytest.raises(ValidationError, match="fail closed"):
        Rubric.model_validate(bad)


def test_stacking_cannot_reach_prohibited(raw):
    bad = copy.deepcopy(raw)
    bad["aggregation"]["stacking"]["raises_to"] = "Prohibited"
    with pytest.raises(ValidationError, match="Prohibited"):
        Rubric.model_validate(bad)


def test_approved_tool_tier_only_on_prohibited_levels(raw):
    bad = copy.deepcopy(raw)
    dim(bad, "data_sensitivity")["levels"][1]["tier_if_approved_tool"] = "Low"  # internal is Medium
    with pytest.raises(ValidationError, match="only allowed on Prohibited"):
        Rubric.model_validate(bad)


def test_control_not_in_catalog_is_rejected(raw):
    bad = copy.deepcopy(raw)
    bad["controls"]["by_tier"]["High"].append("vibes_check")
    with pytest.raises(ValidationError, match="not in the catalog"):
        Rubric.model_validate(bad)


def test_flag_pointing_at_missing_level_is_rejected(raw):
    bad = copy.deepcopy(raw)
    bad["regulatory_flags"][0]["applies_to"].append("personal_data.no_such_level")
    with pytest.raises(ValidationError, match="unknown level"):
        Rubric.model_validate(bad)


def test_flag_cannot_be_verified_without_citation_and_date(raw):
    bad = copy.deepcopy(raw)
    bad["regulatory_flags"][0]["status"] = "verified"
    with pytest.raises(ValidationError, match="real citation"):
        Rubric.model_validate(bad)


def test_approved_tool_must_name_real_vendor_levels(raw):
    bad = copy.deepcopy(raw)
    bad["approved_tool"]["vendor_handling_levels"].append("pinky_promise")
    with pytest.raises(ValidationError, match="unknown level"):
        Rubric.model_validate(bad)


def test_triggered_controls_load():
    triggered = {t.control: t.triggered_by for t in load_rubric().controls.triggered}
    assert triggered["bias_testing"] == ["decision_impact.person_decision_human"]
    assert triggered["bot_disclosure"] == ["audience.external_direct"]


def test_triggered_control_not_in_catalog_is_rejected(raw):
    bad = copy.deepcopy(raw)
    bad["controls"]["triggered"][0]["control"] = "vibes_check"
    with pytest.raises(ValidationError, match="not in the catalog"):
        Rubric.model_validate(bad)


def test_triggered_control_pointing_at_missing_level_is_rejected(raw):
    bad = copy.deepcopy(raw)
    bad["controls"]["triggered"][0]["triggered_by"] = ["audience.no_such_level"]
    with pytest.raises(ValidationError, match="unknown level"):
        Rubric.model_validate(bad)
