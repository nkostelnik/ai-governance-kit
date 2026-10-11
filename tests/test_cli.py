"""Stage 7 tests: the three command-line scripts, end to end, with Claude faked."""

import json
from datetime import date
from pathlib import Path

import pytest

import assess
import register as register_cli
import vendor_review
from ai_governance import llm
from ai_governance.cli_helpers import next_use_case_id, parse_choice
from ai_governance.intake import DimensionAnswer, Finding, Profile, ProfileField, RawExtraction
from ai_governance.register import Register, ToolEntry, confirm_tool
from ai_governance.rubric import load_rubric

DESCRIPTION = ("Sales reps want AI to draft follow-up emails to customers using purchase history. "
               "Reps edit every email before sending it.")
QUILLMARK = Path(__file__).resolve().parent.parent / "samples" / "vendors" / "quillmark"


def fake_intake_call(system, user, output_format):
    """Supports three dimensions; the other three come back unknown."""
    def stated(dim, level, quote):
        return DimensionAnswer(dimension_id=dim, findings=[Finding(level_id=level, quote=quote, basis="stated")],
                               unclear_because=None)
    profile = Profile(**{f: ProfileField(value=None, quote=None) for f in Profile.model_fields})
    profile.use_case_name = ProfileField(value="Sales follow-up emails", quote=None)
    raw = RawExtraction(profile=profile, dimensions=[
        stated("personal_data", "customer_basic", "purchase history"),
        stated("decision_impact", "draft_reviewed", "Reps edit every email before sending it."),
        stated("audience", "external_reviewed", "follow-up emails to customers"),
    ])
    return llm.LLMResult(parsed=raw, stop_reason="end_turn", input_tokens=100, output_tokens=100)


def fake_vendor_call(system, question, output_format, cached_context=None):
    return llm.LLMResult(parsed=output_format(addressed=False, evidence=[]), stop_reason="end_turn")


@pytest.fixture
def dirs(tmp_path):
    reg = tmp_path / "register"
    rubric = load_rubric()
    tool = confirm_tool(ToolEntry(id="assistant", name="Assistant", vendor="Fictional", proposed_level="enterprise_zdr"),
                        "enterprise_zdr", "A. Counsel", "legal", rubric, date(2026, 10, 10))
    Register(reg).save_tool(tool)
    return ["--register-dir", str(reg), "--out-dir", str(tmp_path / "out")], reg, tmp_path / "out"


def scripted(*answers):
    it = iter(answers)
    return lambda prompt="": next(it)


# --- helpers ---------------------------------------------------------------------

def test_parse_choice():
    assert parse_choice("1, 3", 4) == [0, 2]
    assert parse_choice("", 4) == []
    assert parse_choice("5", 4) is None
    assert parse_choice("one", 4) is None


# --- assess.py -------------------------------------------------------------------

def test_assess_asks_follow_ups_saves_and_writes_memo(dirs, capsys):
    common, reg, out = dirs
    # Three unknown dimensions, in rubric order: data_sensitivity, regulated_domain, accuracy_criticality.
    # First answer is invalid and must be re-asked.
    answers = scripted("99", "2", "1", "2")
    code = assess.main([DESCRIPTION, "--tool", "assistant", *common], call=fake_intake_call,
                       input_fn=answers, interactive=True)
    assert code == 0
    entry = Register(reg).use_case("UC-001")
    assert entry.status == "awaiting_signoff" and entry.result.tier.value == "Low"
    assert (out / "UC-001.md").read_text(encoding="utf-8").startswith("# AI use-case decision memo")
    assert "Please enter numbers" in capsys.readouterr().out


def test_assess_auto_numbers_and_no_input_stays_provisional(dirs):
    common, reg, _ = dirs
    for _ in range(2):
        assess.main([DESCRIPTION, "--tool", "assistant", "--no-input", *common], call=fake_intake_call)
    ids = [e.id for e in Register(reg).use_cases()]
    assert ids == ["UC-001", "UC-002"]
    assert Register(reg).use_case("UC-002").status == "provisional"
    assert next_use_case_id(Register(reg)) == "UC-003"


def test_assess_without_tool_is_prohibited_and_says_why(dirs, capsys):
    common, reg, _ = dirs
    assess.main([DESCRIPTION, "--no-input", *common], call=fake_intake_call)
    assert Register(reg).use_case("UC-001").result.tier.value == "Prohibited"
    assert "treated as unreviewed" in capsys.readouterr().out


def test_assess_unknown_tool_fails_cleanly(dirs):
    common, _, _ = dirs
    assert assess.main([DESCRIPTION, "--tool", "nope", *common], call=fake_intake_call) == 2


# --- register.py -------------------------------------------------------------------

def test_register_answer_sign_and_strike(dirs, capsys):
    common, reg, out = dirs
    assess.main([DESCRIPTION, "--tool", "assistant", "--no-input", *common], call=fake_intake_call)
    for dim, level in [("data_sensitivity", "internal"), ("regulated_domain", "no_regulated_domain"),
                       ("accuracy_criticality", "errors_moderate")]:
        assert register_cli.main([*common, "answer", "UC-001", dim, level]) == 0
    assert Register(reg).use_case("UC-001").status == "awaiting_signoff"

    # The requester side may not strike; counsel may.
    assert register_cli.main([*common, "strike", "UC-001", "audience", "external_reviewed", "--by", "B. Owner",
                              "--role", "business_owner", "--reason", "x"]) == 1
    assert register_cli.main([*common, "sign", "UC-001", "--role", "business_owner", "--by", "B. Owner"]) == 0
    entry = Register(reg).use_case("UC-001")
    assert entry.status == "approved" and entry.next_review is not None
    assert "B. Owner" in (out / "UC-001.md").read_text(encoding="utf-8")

    assert register_cli.main([*common, "--today", "2099-01-01", "overdue"]) == 0
    assert "1 overdue." in capsys.readouterr().out


def test_register_trigger_reopens(dirs):
    common, reg, _ = dirs
    assess.main([DESCRIPTION, "--tool", "assistant", "--no-input", *common], call=fake_intake_call)
    assert register_cli.main([*common, "trigger", "UC-001", "incident_or_complaint", "--by", "AI lead"]) == 0
    assert "incident_or_complaint" in Register(reg).use_case("UC-001").pending_triggers


# --- vendor_review.py ----------------------------------------------------------------

def test_vendor_review_registers_tool_and_flags_uses_on_new_terms(dirs, tmp_path):
    common, reg, out = dirs
    files = [str(QUILLMARK / "terms.txt"), str(QUILLMARK / "dpa.txt")]
    assert vendor_review.main([*files, "--register", "quill", "--name", "Quill", *common], call=fake_vendor_call) == 0
    tool = Register(reg).tool("quill")
    assert tool.confirmed_level is None and tool.proposed_level == "vendor_trains"   # nothing addressed
    report = (out / "vendor-quill.md").read_text(encoding="utf-8")
    assert report.startswith("# AI vendor terms review: Quill") and "Not legal advice" in report
    assert json.loads((out / "vendor-quill.json").read_text(encoding="utf-8"))["blockers"]

    # A use on the tool, then the vendor's terms change: the use is flagged.
    assess.main([DESCRIPTION, "--tool", "quill", "--no-input", *common], call=fake_intake_call)
    changed = tmp_path / "terms.txt"
    changed.write_text((QUILLMARK / "terms.txt").read_text(encoding="utf-8") + "\n9. New clause. Changed.\n",
                       encoding="utf-8")
    vendor_review.main([str(changed), str(QUILLMARK / "dpa.txt"), "--register", "quill", *common], call=fake_vendor_call)
    assert "vendor_terms_change" in Register(reg).use_case("UC-001").pending_triggers
