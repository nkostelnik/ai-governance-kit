import json
from pathlib import Path

import yaml

from ai_governance.eval_metrics import compare, dimension_agreement, score_gaps, score_tiers
from ai_governance.intake import Finding, IntakeResult, Profile, ProfileField
from ai_governance.rubric import Tier, load_rubric
from ai_governance.tiering import ToolRecord, assess

EVALS = Path(__file__).resolve().parent.parent / "evals"
TOOL = ToolRecord(name="t", vendor_handling_level="enterprise_zdr", listed_as_approved=True)


def test_compare_names_the_direction_of_the_error():
    assert compare(Tier.High, Tier.Low) == "false_low"
    assert compare(Tier.Low, Tier.High) == "over_escalation"
    assert compare(Tier.Medium, Tier.Medium) == "match"


def test_score_tiers_counts_and_rates():
    s = score_tiers([(Tier.Low, Tier.Low), (Tier.High, Tier.Medium), (Tier.Low, Tier.Prohibited), (Tier.Low, Tier.Low)])
    assert (s.n, s.match, s.false_low, s.over_escalation) == (4, 2, 1, 1)
    assert s.false_low_rate == 0.25


def test_score_gaps_separates_missed_from_false():
    s = score_gaps([(True, True), (True, False), (False, True), (False, False)])
    assert (s.correct, s.missed_gaps, s.false_gaps) == (2, 1, 1)


def intake(answers):
    rubric = load_rubric()
    found = {d: [Finding(level_id=lv, quote="q", basis="stated") for lv in lvs] for d, lvs in answers.items()}
    dims = [d.id for d in rubric.dimensions if d.source == "intake"]
    return IntakeResult(description="d", profile=Profile(**{f: ProfileField(value=None, quote=None) for f in Profile.model_fields}),
                        answers=found, unknown_dimensions=[d for d in dims if d not in answers],
                        needs_review=[], rejected=[], follow_ups=[])


def test_dimension_agreement_treats_unknown_as_disagreement():
    key = assess(intake({"audience": ["personal_use"], "personal_data": ["no_personal_data"]}), TOOL)
    pipe = assess(intake({"audience": ["internal_shared"]}), TOOL)   # same tier for audience; personal_data unknown
    agreement = dimension_agreement(key, pipe)
    assert agreement["audience"] is True
    assert agreement["personal_data"] is False
    assert "vendor_handling" not in agreement


def test_eval_files_are_consistent():
    rubric = load_rubric()
    cases = yaml.safe_load((EVALS / "use_cases.yaml").read_text(encoding="utf-8"))["cases"]
    labels = json.loads((EVALS / "labels.json").read_text(encoding="utf-8"))
    assert {c["id"] for c in cases} == set(labels["use_cases"])
    for c in cases:
        for dim, levels in c["facts"].items():
            for level in levels:
                rubric.dimension(dim).level(level)   # every fact key level exists
    requirement_ids = {r.id for r in rubric.vendor_requirements}
    for vendor, gaps in labels["vendors"].items():
        assert (EVALS / "vendors" / vendor).is_dir()
        assert set(gaps) <= requirement_ids
