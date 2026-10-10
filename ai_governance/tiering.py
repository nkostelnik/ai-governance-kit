"""Stage 3: apply the rubric to verified facts. Deterministic; no model involved.

Same facts in, same tier out, every time. Every rule below comes from
governance/rubric.yaml; this file only knows how to read it:

1. Each dimension takes the tier of its worst finding. A level with a
   tier_if_approved_tool uses that tier when the tool is approved.
2. An unknown dimension is rated per rubric.unknowns (Medium), flagged.
3. Register-sourced dimensions (vendor_handling) come from the tool's
   register record; no record means approved_tool.unregistered_level.
4. Overall: worst dimension wins; enough Medium dimensions stack to High.
5. Controls and approvers are cumulative by tier, plus triggered controls.
6. Matching regulatory flags are attached, still marked VERIFY.
"""

from typing import Literal

from pydantic import BaseModel

from . import DISCLAIMER
from .intake import Finding, FollowUp, IntakeResult
from .rubric import Level, Rubric, Tier, load_rubric


class ToolRecord(BaseModel):
    """The tool's entry in the AI register (Stage 5 will look this up)."""

    name: str
    vendor_handling_level: str      # result of the vendor terms review
    listed_as_approved: bool


class DimensionRating(BaseModel):
    dimension_id: str
    tier: Tier
    source: Literal["finding", "unknown", "register"]
    driver_level: str | None = None     # the level that set this tier
    driver_quote: str | None = None
    driver_basis: str | None = None
    approved_tool_applied: bool = False


class Requirement(BaseModel):
    id: str
    description: str
    why: str


class FlagHit(BaseModel):
    id: str
    topic: str
    citation: str
    matched: list[str]


class TierResult(BaseModel):
    disclaimer: str = DISCLAIMER
    tier: Tier
    provisional: bool                   # open questions remain; cannot be finalized
    reasons: list[str]
    stacking_applied: bool
    tool: ToolRecord | None
    approved_tool: bool
    ratings: list[DimensionRating]
    controls: list[Requirement]
    approvers: list[Requirement]
    prohibited_exception: str | None
    review_cadence_months: int | None
    regulatory_flags: list[FlagHit]
    needs_review: list[str]
    open_questions: list[FollowUp]


def is_approved_tool(tool: ToolRecord | None, rubric: Rubric) -> bool:
    if tool is None or tool.vendor_handling_level not in rubric.approved_tool.vendor_handling_levels:
        return False
    return tool.listed_as_approved or not rubric.approved_tool.requires_register_listing


def level_tier(level: Level, approved: bool) -> tuple[Tier, bool]:
    """The level's tier, and whether the approved-tool exception was used."""
    if approved and level.tier_if_approved_tool is not None:
        return level.tier_if_approved_tool, True
    return level.tier, False


def rate_findings(dimension_id: str, findings: list[Finding], rubric: Rubric, approved: bool) -> DimensionRating:
    dim = rubric.dimension(dimension_id)
    worst: DimensionRating | None = None
    for f in findings:
        tier, used_exception = level_tier(dim.level(f.level_id), approved)
        if worst is None or tier.rank > worst.tier.rank:
            worst = DimensionRating(dimension_id=dimension_id, tier=tier, source="finding",
                                    driver_level=f.level_id, driver_quote=f.quote, driver_basis=f.basis,
                                    approved_tool_applied=used_exception)
    return worst


def rate_register(dimension_id: str, tool: ToolRecord | None, rubric: Rubric, approved: bool) -> DimensionRating:
    level_id = tool.vendor_handling_level if tool else rubric.approved_tool.unregistered_level
    tier, used_exception = level_tier(rubric.dimension(dimension_id).level(level_id), approved)
    quote = f"Register record for {tool.name}" if tool else "No register record for this tool"
    return DimensionRating(dimension_id=dimension_id, tier=tier, source="register", driver_level=level_id,
                           driver_quote=quote, driver_basis="register", approved_tool_applied=used_exception)


def assess(intake: IntakeResult, tool: ToolRecord | None = None, rubric: Rubric | None = None) -> TierResult:
    rubric = rubric or load_rubric()
    approved = is_approved_tool(tool, rubric)
    needs_review = list(intake.needs_review)

    # 1-3. Rate every dimension.
    ratings: list[DimensionRating] = []
    for dim in rubric.dimensions:
        if dim.source == "register":
            ratings.append(rate_register(dim.id, tool, rubric, approved))
        elif intake.answers.get(dim.id):
            ratings.append(rate_findings(dim.id, intake.answers[dim.id], rubric, approved))
        else:
            ratings.append(DimensionRating(dimension_id=dim.id, tier=rubric.unknowns.rating, source="unknown"))
            needs_review.append(f"{dim.id} is unknown: rated {rubric.unknowns.rating.value} until answered.")

    # 4. Worst dimension wins, then stacking.
    tier = max((r.tier for r in ratings), key=lambda t: t.rank)
    reasons = [f"{tier.value}: driven by {describe(r)}" for r in ratings if r.tier == tier]
    stacking_applied = False
    stack = rubric.aggregation.stacking
    if stack:
        at_tier = [r.dimension_id for r in ratings if r.tier == stack.at_tier]
        if len(at_tier) >= stack.min_count and tier.rank < stack.raises_to.rank:
            tier, stacking_applied = stack.raises_to, True
            reasons = [f"{tier.value}: raised by stacking, {len(at_tier)} dimensions rated "
                       f"{stack.at_tier.value} ({', '.join(at_tier)})"]

    # 5-6. What the tier requires.
    matched_levels = {f"{r.dimension_id}.{r.driver_level}" for r in ratings if r.driver_level}
    matched_levels |= {f"{d}.{f.level_id}" for d, fs in intake.answers.items() for f in fs}
    prohibited = tier == Tier.Prohibited
    exception = rubric.approvers.prohibited_exception

    return TierResult(
        tier=tier,
        provisional=bool(intake.unknown_dimensions) and not rubric.unknowns.finalize_with_open_questions,
        reasons=reasons,
        stacking_applied=stacking_applied,
        tool=tool,
        approved_tool=approved,
        ratings=ratings,
        controls=[] if prohibited else required_controls(tier, matched_levels, rubric),
        approvers=[] if prohibited else [
            Requirement(id=a, description=rubric.approvers.catalog[a], why=f"required at {tier.value}")
            for a in rubric.approvers.for_tier(tier)
        ],
        prohibited_exception=(
            f"Exception only by joint approval of: {', '.join(exception.joint_approval)}"
            if prohibited and exception.allowed else None
        ),
        review_cadence_months=None if prohibited else rubric.review.cadence_months[tier],
        regulatory_flags=[
            FlagHit(id=f.id, topic=f.topic, citation=f.citation, matched=sorted(set(f.applies_to) & matched_levels))
            for f in rubric.regulatory_flags if set(f.applies_to) & matched_levels
        ],
        needs_review=needs_review,
        open_questions=intake.follow_ups,
    )


def required_controls(tier: Tier, matched_levels: set[str], rubric: Rubric) -> list[Requirement]:
    controls = [Requirement(id=c, description=rubric.controls.catalog[c], why=f"required at {tier.value}")
                for c in rubric.controls.for_tier(tier)]
    for t in rubric.controls.triggered:
        hits = sorted(set(t.triggered_by) & matched_levels)
        if hits and t.control not in {c.id for c in controls}:
            controls.append(Requirement(id=t.control, description=rubric.controls.catalog[t.control],
                                        why=f"triggered by {', '.join(hits)}"))
    return controls


def describe(rating: DimensionRating) -> str:
    if rating.source == "unknown":
        return f"{rating.dimension_id} (unknown)"
    text = f"{rating.dimension_id}.{rating.driver_level}"
    if rating.driver_quote:
        text += f" (\"{rating.driver_quote}\")"
    if rating.approved_tool_applied:
        text += " [approved-tool tier]"
    return text


if __name__ == "__main__":
    # Try it on a saved intake: python -m ai_governance.tiering INTAKE.json [VENDOR_LEVEL]
    # VENDOR_LEVEL (e.g. enterprise_zdr) stands in for an approved register record until Stage 5.
    import sys

    with open(sys.argv[1], encoding="utf-8") as f:
        facts = IntakeResult.model_validate_json(f.read())
    tool = ToolRecord(name="demo tool", vendor_handling_level=sys.argv[2], listed_as_approved=True) if len(sys.argv) > 2 else None
    result = assess(facts, tool)
    print(f"Tier: {result.tier.value}{' (provisional: open questions)' if result.provisional else ''}")
    print(*result.reasons, sep="\n")
    for label, items in [("Controls", result.controls), ("Approvers", result.approvers)]:
        if items:
            print(f"{label}: " + ", ".join(i.id for i in items))
    if result.prohibited_exception:
        print(result.prohibited_exception)
    for flag in result.regulatory_flags:
        print(f"Flag: {flag.topic} [{flag.citation}]")
    print(result.disclaimer)
