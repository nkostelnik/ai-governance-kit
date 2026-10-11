"""Stage 5 tests: register, sign-off, strikes, triggers, memo. No API calls."""

import json
from datetime import date
from pathlib import Path

import pytest

from ai_governance.intake import IntakeResult, answer_follow_ups
from ai_governance.memo import render_memo
from ai_governance.register import (
    Register,
    ToolEntry,
    add_months,
    assess_use_case,
    confirm_tool,
    detect_triggers,
    flag_for_reassessment,
    grant_exception,
    overdue,
    propagate_terms_change,
    record_new_terms,
    sign_off,
    strike_finding,
)
from ai_governance.rubric import Tier, load_rubric
from ai_governance.vendor import VendorReviewResult

FIXTURES = Path(__file__).parent / "fixtures" / "intakes"
TODAY = date(2026, 10, 10)


@pytest.fixture(scope="module")
def rubric():
    return load_rubric()


def fixture(name) -> IntakeResult:
    return IntakeResult.model_validate(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))


def tool(**overrides) -> ToolEntry:
    fields = dict(id="assistant", name="Approved Assistant", vendor="Fictional Vendor", proposed_level="enterprise_zdr",
                  documents={"terms.txt": "abc"})
    fields.update(overrides)
    return ToolEntry(**fields)


@pytest.fixture
def approved_tool(rubric):
    return confirm_tool(tool(), "enterprise_zdr", "A. Counsel", "legal", rubric, TODAY)


@pytest.fixture
def email(rubric):
    """Email rewrite with its one open question answered: Low in an approved tool."""
    return answer_follow_ups(fixture("email_rewrite"), {"regulated_domain": ["no_regulated_domain"]}, rubric)


# --- tools -------------------------------------------------------------------

def test_counsel_confirms_and_lists_a_clean_tool(approved_tool):
    assert approved_tool.listed_as_approved and approved_tool.approved_on == TODAY
    assert [e.action for e in approved_tool.history][-1] == "listed as approved"


def test_only_tool_confirm_roles_may_confirm(rubric):
    with pytest.raises(PermissionError):
        confirm_tool(tool(), "enterprise_zdr", "B. Owner", "business_owner", rubric, TODAY)


def test_must_have_gap_keeps_tool_unlisted(rubric):
    blocked = confirm_tool(tool(blockers=["retention"]), "enterprise_zdr", "A. Counsel", "legal", rubric, TODAY)
    assert blocked.confirmed_level == "enterprise_zdr" and not blocked.listed_as_approved


def test_unapproved_level_keeps_tool_unlisted(rubric):
    trains = confirm_tool(tool(proposed_level="vendor_trains"), "vendor_trains", "A. Counsel", "legal", rubric, TODAY)
    assert not trains.listed_as_approved


def test_unconfirmed_tool_is_treated_as_unreviewed(rubric):
    assert tool().to_tool_record(rubric).vendor_handling_level == "vendor_unknown"


def test_new_vendor_terms_clear_confirmation(approved_tool):
    review = VendorReviewResult(documents={"terms.txt": "changed"}, requirements=[], blockers=[], flags=[],
                                proposed_vendor_level="enterprise_zdr", level_reason="r", approvable=True,
                                approval_note="n", needs_review=[])
    updated = record_new_terms(approved_tool, review, "system")
    assert updated.confirmed_level is None and not updated.listed_as_approved


# --- use cases and sign-off ----------------------------------------------------

def test_low_use_needs_only_the_business_owner(rubric, email, approved_tool):
    entry = assess_use_case("UC-001", email, approved_tool, "intake", rubric)
    assert entry.result.tier == Tier.Low and entry.status == "awaiting_signoff"
    assert entry.required_signers() == ["business_owner"]
    approved = sign_off(entry, "business_owner", "B. Owner", TODAY, rubric)
    assert approved.status == "approved" and approved.next_review == date(2027, 10, 10)


def test_high_use_needs_every_tier_approver(rubric, approved_tool):
    warranty = answer_follow_ups(fixture("warranty_chatbot"), {"regulated_domain": ["no_regulated_domain"]}, rubric)
    entry = assess_use_case("UC-002", warranty, approved_tool, "intake", rubric)
    assert entry.result.tier == Tier.High
    for role in entry.required_signers()[:-1]:
        entry = sign_off(entry, role, f"{role} person", TODAY, rubric)
    assert entry.status == "awaiting_signoff" and entry.missing_signers() == ["ai_governance_committee"]
    entry = sign_off(entry, "ai_governance_committee", "Committee", TODAY, rubric)
    assert entry.status == "approved" and entry.next_review == date(2027, 1, 10)


def test_wrong_role_cannot_sign(rubric, email, approved_tool):
    entry = assess_use_case("UC-001", email, approved_tool, "intake", rubric)
    with pytest.raises(PermissionError):
        sign_off(entry, "legal", "A. Counsel", TODAY, rubric)


def test_provisional_use_cannot_be_signed(rubric, approved_tool):
    entry = assess_use_case("UC-003", fixture("vague"), approved_tool, "intake", rubric)
    assert entry.status == "provisional"
    with pytest.raises(ValueError, match="provisional"):
        sign_off(entry, "business_owner", "B. Owner", TODAY, rubric)


def test_unlisted_tool_makes_approved_tool_data_prohibited(rubric, email):
    blocked = confirm_tool(tool(blockers=["retention"]), "enterprise_zdr", "A. Counsel", "legal", rubric, TODAY)
    entry = assess_use_case("UC-004", email, blocked, "intake", rubric)
    assert entry.status == "prohibited"   # employee names are allowed only in an approved tool


def test_use_on_unlisted_tool_cannot_be_signed_even_if_low(rubric):
    """Public data only: nothing depends on the approved-tool exception, so the tier is Low,
    but the sign-off guard still refuses because the tool is not listed as approved."""
    public_only = answer_follow_ups(fixture("vague"), {
        "data_sensitivity": ["public"], "personal_data": ["no_personal_data"], "decision_impact": ["draft_reviewed"],
        "regulated_domain": ["no_regulated_domain"], "audience": ["personal_use"],
        "accuracy_criticality": ["errors_harmless"]}, rubric)
    blocked = confirm_tool(tool(blockers=["retention"]), "enterprise_zdr", "A. Counsel", "legal", rubric, TODAY)
    entry = assess_use_case("UC-004", public_only, blocked, "intake", rubric)
    assert entry.result.tier == Tier.Low and not entry.result.approved_tool
    with pytest.raises(ValueError, match="not listed as approved"):
        sign_off(entry, "business_owner", "B. Owner", TODAY, rubric)


def test_prohibited_use_needs_joint_exception(rubric, approved_tool):
    entry = assess_use_case("UC-005", fixture("productivity_screener"), approved_tool, "intake", rubric)
    assert entry.status == "prohibited"
    with pytest.raises(PermissionError, match="joint approval"):
        grant_exception(entry, {"general_counsel": "GC"}, "pilot", TODAY, rubric)
    granted = grant_exception(entry, {"general_counsel": "GC", "ai_governance_committee": "Committee"},
                              "Time-limited pilot with audit", TODAY, rubric)
    assert granted.status == "exception_granted"


# --- strikes -----------------------------------------------------------------

def test_requester_side_cannot_strike(rubric):
    with pytest.raises(PermissionError):
        strike_finding(fixture("legal_sharepoint_search"), "accuracy_criticality", "critical_reliance_unverified",
                       "B. Owner", "business_owner", "we verify everything", rubric, TODAY)


def test_strike_needs_a_reason(rubric):
    with pytest.raises(ValueError, match="reason"):
        strike_finding(fixture("legal_sharepoint_search"), "accuracy_criticality", "critical_reliance_unverified",
                       "A. Counsel", "legal", " ", rubric, TODAY)


def test_striking_a_wrong_inference_reopens_the_question_not_lower(rubric, approved_tool):
    intake = fixture("legal_sharepoint_search")
    assert assess_use_case("UC-006", intake, approved_tool, "intake", rubric).result.tier == Tier.Prohibited
    struck, strike = strike_finding(intake, "accuracy_criticality", "critical_reliance_unverified", "A. Counsel",
                                    "legal", "Description is silent on verification", rubric, TODAY)
    assert "accuracy_criticality" in struck.unknown_dimensions
    assert not any(n.startswith("accuracy_criticality.critical_reliance_unverified") for n in struck.needs_review)
    assert any(fu.dimension_id == "accuracy_criticality" for fu in struck.follow_ups)
    entry = assess_use_case("UC-006", struck, approved_tool, "intake", rubric, strikes=[strike])
    assert entry.result.tier == Tier.High          # privileged in an approved tool still drives High
    assert entry.status == "provisional"            # the struck dimension must be answered


# --- triggers ----------------------------------------------------------------

def test_triggers_fire_on_any_new_level_and_tool_change(rubric, email, approved_tool):
    entry = assess_use_case("UC-001", email, approved_tool, "intake", rubric)
    assert detect_triggers(entry, email, approved_tool.id, rubric) == []
    changed = answer_follow_ups(email, {"personal_data": ["customer_basic"], "audience": ["external_reviewed"],
                                        "decision_impact": ["automated_action"]}, rubric)
    assert detect_triggers(entry, changed, "other-tool", rubric) == [
        "new_data_type", "expanded_audience", "more_automation", "new_vendor"]


def test_trigger_reopens_an_approved_use(rubric, email, approved_tool):
    entry = sign_off(assess_use_case("UC-001", email, approved_tool, "intake", rubric), "business_owner", "B", TODAY, rubric)
    flagged = flag_for_reassessment(entry, "incident_or_complaint", "AI lead", "customer complaint", rubric)
    assert flagged.status == "reassessment_required" and flagged.pending_triggers == ["incident_or_complaint"]
    with pytest.raises(KeyError):
        flag_for_reassessment(entry, "bad_vibes", "AI lead", "", rubric)


def test_overdue_and_month_math(rubric, email, approved_tool):
    entry = sign_off(assess_use_case("UC-001", email, approved_tool, "intake", rubric), "business_owner", "B", TODAY, rubric)
    assert overdue([entry], date(2027, 10, 11)) == [entry]
    assert overdue([entry], date(2027, 10, 10)) == []
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_register_round_trip_and_terms_change_propagation(tmp_path, rubric, email, approved_tool):
    reg = Register(tmp_path)
    reg.save_tool(approved_tool)
    reg.save_use_case(sign_off(assess_use_case("UC-001", email, approved_tool, "intake", rubric),
                               "business_owner", "B", TODAY, rubric))
    assert reg.tool("assistant") == approved_tool
    assert reg.use_case("UC-001").status == "approved"
    assert propagate_terms_change(reg, "assistant", "system", rubric) == ["UC-001"]
    reloaded = reg.use_case("UC-001")
    assert reloaded.status == "reassessment_required" and "vendor_terms_change" in reloaded.pending_triggers


# --- memo --------------------------------------------------------------------

def test_memo_for_approved_low_use(rubric, email, approved_tool):
    entry = sign_off(assess_use_case("UC-001", email, approved_tool, "intake", rubric), "business_owner", "B. Owner", TODAY, rubric)
    memo = render_memo(entry, approved_tool, rubric)
    assert memo.startswith("# AI use-case decision memo")
    assert "Requires attorney review. Not legal advice." in memo
    assert "**Low**" in memo and "Approved." in memo
    assert "I always read the rewrite" in memo                    # the supporting quote
    assert "| Named business owner accountable for the use case | B. Owner | 2026-10-10 |" in memo
    assert "Next scheduled review: 2027-10-10" in memo
    assert "\u2014" not in memo


def test_memo_for_prohibited_use_shows_exception_path_and_strikes(rubric, approved_tool):
    intake = fixture("legal_sharepoint_search")
    _, strike = strike_finding(intake, "data_sensitivity", "company_confidential", "A. Counsel", "legal",
                               "Covered by the privileged finding", rubric, TODAY)
    entry = assess_use_case("UC-007", fixture("productivity_screener"), approved_tool, "intake", rubric, strikes=[strike])
    memo = render_memo(entry, approved_tool, rubric)
    assert "## Exception path" in memo and "## Required controls" not in memo
    assert "## Reviewer corrections" in memo and "Covered by the privileged finding" in memo
    assert "VERIFY: [citation needed]" in memo
