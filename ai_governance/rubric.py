"""Load and validate governance/rubric.yaml.

The YAML is written by a lawyer, not a programmer, so it is validated strictly:
unknown keys are rejected (catches typos like `tier_if_aproved_tool`), every
cross-reference must point at something that exists, and a few governance
rules are enforced in code so a bad edit cannot quietly weaken them:

- an unknown fact can never be rated Low (fail closed);
- stacking can never produce Prohibited;
- a regulatory flag cannot be marked verified without a citation and a date.

A bad rubric fails at load time with a readable error.
"""

from datetime import date
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

DEFAULT_RUBRIC = Path(__file__).resolve().parent.parent / "governance" / "rubric.yaml"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tier(str, Enum):
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Prohibited = "Prohibited"

    @property
    def rank(self) -> int:
        return list(Tier).index(self)


class Level(Strict):
    id: str
    description: str
    tier: Tier
    tier_if_approved_tool: Tier | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def approved_tool_tier_only_relaxes_prohibited(self):
        if self.tier_if_approved_tool is None:
            return self
        if self.tier != Tier.Prohibited:
            raise ValueError(f"level {self.id!r}: tier_if_approved_tool is only allowed on Prohibited levels")
        if self.tier_if_approved_tool.rank >= self.tier.rank:
            raise ValueError(f"level {self.id!r}: tier_if_approved_tool must be lower than Prohibited")
        return self


class Dimension(Strict):
    id: str
    name: str
    description: str
    levels: list[Level]
    notes: str | None = None

    @model_validator(mode="after")
    def level_ids_unique(self):
        ids = [lv.id for lv in self.levels]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"dimension {self.id!r} has duplicate level ids: {sorted(dupes)}")
        return self

    def level(self, level_id: str) -> Level:
        for lv in self.levels:
            if lv.id == level_id:
                return lv
        raise KeyError(f"{self.id}.{level_id}")


class Stacking(Strict):
    min_count: int
    at_tier: Tier
    raises_to: Tier

    @model_validator(mode="after")
    def sensible(self):
        if self.min_count < 2:
            raise ValueError("stacking.min_count must be at least 2")
        if self.raises_to == Tier.Prohibited:
            raise ValueError("stacking may not raise a use case to Prohibited")
        if self.raises_to.rank <= self.at_tier.rank:
            raise ValueError("stacking.raises_to must be higher than stacking.at_tier")
        return self


class Aggregation(Strict):
    method: Literal["worst_dimension_wins"]
    stacking: Stacking | None = None


class Unknowns(Strict):
    rating: Tier
    flag: Literal["needs_review"]
    finalize_with_open_questions: bool
    notes: str | None = None

    @model_validator(mode="after")
    def fail_closed(self):
        if self.rating == Tier.Low:
            raise ValueError("unknowns.rating may not be Low: unresolved facts must fail closed")
        return self


class ApprovedTool(Strict):
    vendor_handling_levels: list[str]
    requires_register_listing: bool
    notes: str | None = None


class TierMap(Strict):
    """Controls or approvers, listed as additions per tier."""

    cumulative: bool
    catalog: dict[str, str]
    by_tier: dict[Tier, list[str]]
    notes: str | None = None

    @model_validator(mode="after")
    def ids_in_catalog(self):
        if Tier.Prohibited in self.by_tier:
            raise ValueError("Prohibited is a stop, not a tier with controls or approvers")
        for tier, ids in self.by_tier.items():
            unknown = set(ids) - set(self.catalog)
            if unknown:
                raise ValueError(f"{tier.value} lists ids not in the catalog: {sorted(unknown)}")
        return self

    def for_tier(self, tier: Tier) -> list[str]:
        """Everything required at `tier`, including lower tiers when cumulative."""
        if not self.cumulative:
            return list(self.by_tier.get(tier, []))
        result: list[str] = []
        for t in Tier:
            if t.rank > tier.rank:
                break
            result += [i for i in self.by_tier.get(t, []) if i not in result]
        return result


class TriggeredControl(Strict):
    control: str
    triggered_by: list[str]   # "dimension_id.level_id"


class Controls(TierMap):
    triggered: list[TriggeredControl] = []

    @model_validator(mode="after")
    def triggered_controls_in_catalog(self):
        unknown = {t.control for t in self.triggered} - set(self.catalog)
        if unknown:
            raise ValueError(f"triggered controls not in the catalog: {sorted(unknown)}")
        return self


class ProhibitedException(Strict):
    allowed: bool
    joint_approval: list[str] = []
    notes: str | None = None


class Approvers(TierMap):
    low_tier_mode: str
    prohibited_exception: ProhibitedException

    @model_validator(mode="after")
    def exception_approvers_in_catalog(self):
        unknown = set(self.prohibited_exception.joint_approval) - set(self.catalog)
        if unknown:
            raise ValueError(f"prohibited_exception names unknown approvers: {sorted(unknown)}")
        return self


class Review(Strict):
    cadence_months: dict[Tier, int]
    reassessment_triggers: dict[str, str]
    notes: str | None = None

    @model_validator(mode="after")
    def every_allowed_tier_has_cadence(self):
        needed = {Tier.Low, Tier.Medium, Tier.High}
        if set(self.cadence_months) != needed:
            raise ValueError("review.cadence_months must cover exactly Low, Medium, and High")
        return self


class VendorRequirement(Strict):
    id: str
    name: str
    standard: str
    severity: Literal["must_have", "preferred"]
    notes: str | None = None


class RegulatoryFlag(Strict):
    id: str
    topic: str
    applies_to: list[str]   # "dimension_id.level_id"
    status: Literal["VERIFY", "verified"]
    citation: str
    verified_on: date | None = None

    @model_validator(mode="after")
    def no_unverified_legal_claims(self):
        if self.status == "VERIFY" and not self.citation.startswith("VERIFY"):
            raise ValueError(f"flag {self.id!r}: an unverified flag's citation must start with 'VERIFY'")
        if self.status == "verified" and (self.citation.startswith("VERIFY") or self.verified_on is None):
            raise ValueError(f"flag {self.id!r}: a verified flag needs a real citation and a verified_on date")
        return self


class Rubric(Strict):
    version: int
    jurisdiction_scope: str
    tiers: dict[Tier, str]
    aggregation: Aggregation
    unknowns: Unknowns
    approved_tool: ApprovedTool
    dimensions: list[Dimension]
    controls: Controls
    approvers: Approvers
    review: Review
    vendor_requirements: list[VendorRequirement]
    regulatory_flags: list[RegulatoryFlag]

    @model_validator(mode="after")
    def cross_references(self):
        if set(self.tiers) != set(Tier):
            raise ValueError("tiers must describe Low, Medium, High, and Prohibited")

        for kind, ids in [
            ("dimension", [d.id for d in self.dimensions]),
            ("vendor requirement", [r.id for r in self.vendor_requirements]),
            ("regulatory flag", [f.id for f in self.regulatory_flags]),
        ]:
            dupes = {i for i in ids if ids.count(i) > 1}
            if dupes:
                raise ValueError(f"duplicate {kind} ids: {sorted(dupes)}")

        # Pydantic only reports ValueErrors, so lookups that raise KeyError are
        # converted here into readable validation messages.
        for level_id in self.approved_tool.vendor_handling_levels:
            if not self._has_level("vendor_handling", level_id):
                raise ValueError(f"approved_tool points at unknown level 'vendor_handling.{level_id}'")

        refs = [(f"flag {f.id!r}", ref) for f in self.regulatory_flags for ref in f.applies_to]
        refs += [(f"triggered control {t.control!r}", ref) for t in self.controls.triggered for ref in t.triggered_by]
        for owner, ref in refs:
            dim_id, _, level_id = ref.partition(".")
            if not self._has_level(dim_id, level_id):
                raise ValueError(f"{owner} points at unknown level {ref!r}")
        return self

    def _has_level(self, dimension_id: str, level_id: str) -> bool:
        try:
            self.dimension(dimension_id).level(level_id)
            return True
        except KeyError:
            return False

    def dimension(self, dimension_id: str) -> Dimension:
        for d in self.dimensions:
            if d.id == dimension_id:
                return d
        raise KeyError(dimension_id)


def load_rubric(path: str | Path = DEFAULT_RUBRIC) -> Rubric:
    with open(path, encoding="utf-8") as f:
        return Rubric.model_validate(yaml.safe_load(f))
