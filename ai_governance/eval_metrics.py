"""Stage 6: scoring for the eval harness. Pure functions, unit-tested.

Three comparisons per use case, so a wrong tier can be traced to its cause:

    label     the rubric owner's expected tier (ground truth)
    key       the rubric applied to the case's fact key (perfect extraction)
    pipeline  Claude's extraction, then the rubric

    label vs key       -> rubric disagreement: refine rubric.yaml
    key vs pipeline    -> extraction error: the model misread the case
    label vs pipeline  -> what a user of the kit would actually experience

A predicted tier below the label is a false Low (the dangerous error: risk
waved through). Above the label is over-escalation (friction: a use held up
for controls or approvals it did not need).
"""

from typing import Literal

from pydantic import BaseModel

from .rubric import Tier
from .tiering import TierResult

Outcome = Literal["match", "false_low", "over_escalation"]


def compare(expected: Tier, predicted: Tier) -> Outcome:
    if predicted.rank < expected.rank:
        return "false_low"
    if predicted.rank > expected.rank:
        return "over_escalation"
    return "match"


class TierScore(BaseModel):
    n: int
    match: int
    false_low: int
    over_escalation: int

    @property
    def match_rate(self) -> float:
        return self.match / self.n if self.n else 0.0

    @property
    def false_low_rate(self) -> float:
        return self.false_low / self.n if self.n else 0.0

    @property
    def over_escalation_rate(self) -> float:
        return self.over_escalation / self.n if self.n else 0.0


def score_tiers(pairs: list[tuple[Tier, Tier]]) -> TierScore:
    """pairs: (expected, predicted)."""
    outcomes = [compare(e, p) for e, p in pairs]
    return TierScore(n=len(pairs), match=outcomes.count("match"), false_low=outcomes.count("false_low"),
                     over_escalation=outcomes.count("over_escalation"))


def dimension_agreement(key: TierResult, pipeline: TierResult) -> dict[str, bool]:
    """Per dimension: did extraction produce the same dimension rating as the fact key?
    Compared at the rating level (the tier each dimension contributes), since that is what drives the result."""
    pipe = {r.dimension_id: r for r in pipeline.ratings}
    return {r.dimension_id: pipe[r.dimension_id].tier == r.tier and pipe[r.dimension_id].source == r.source
            for r in key.ratings if r.source != "register"}


class GapScore(BaseModel):
    n: int
    correct: int
    missed_gaps: int      # labeled a gap, predicted met: the dangerous vendor error
    false_gaps: int       # labeled met, predicted gap: friction

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0


def score_gaps(rows: list[tuple[bool, bool]]) -> GapScore:
    """rows: (labeled_gap, predicted_gap)."""
    return GapScore(n=len(rows), correct=sum(l == p for l, p in rows),
                    missed_gaps=sum(l and not p for l, p in rows),
                    false_gaps=sum(p and not l for l, p in rows))
