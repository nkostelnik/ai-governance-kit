"""Stage 5: the AI register. Tools, use cases, sign-offs, and reassessment.

Storage is one JSON file per record (register/tools/*.json and
register/use_cases/*.json), validated by Pydantic on every load. A legal
department's AI register is tens to hundreds of records; plain files are
readable by counsel, need no database, and every change shows up as a git
diff, which doubles as the audit trail. SQLite (or a GRC system) would be
the better fit with many concurrent writers or thousands of records.

Who may do what comes from rubric.register_rules:
- strike a finding the model extracted: strike_roles (counsel or the AI
  enablement lead, independent of the requester at every tier);
- confirm a tool's vendor level and list it as approved: tool_confirm_roles;
- sign off a use case: the approvers the tier requires.
Every action is appended to the record's history; nothing is deleted.
"""

import calendar
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .intake import IntakeResult, follow_up_for
from .rubric import DEFAULT_RUBRIC, Rubric, Tier, load_rubric
from .tiering import TierResult, ToolRecord, assess
from .vendor import VendorReviewResult

DEFAULT_REGISTER = Path(__file__).resolve().parent.parent / "register"


class Event(BaseModel):
    at: str            # ISO timestamp, UTC
    actor: str
    role: str
    action: str
    detail: str = ""


def event(actor: str, role: str, action: str, detail: str = "") -> Event:
    return Event(at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 actor=actor, role=role, action=action, detail=detail)


def add_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    year, month = start.year + month // 12, month % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def rubric_fingerprint(path: Path = DEFAULT_RUBRIC) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class ToolEntry(BaseModel):
    id: str
    name: str
    vendor: str
    proposed_level: str                  # from the vendor review's rules
    confirmed_level: str | None = None   # set by an attorney
    listed_as_approved: bool = False
    blockers: list[str] = []
    flags: list[str] = []
    documents: dict[str, str] = {}       # file name -> sha256 of the reviewed terms
    approved_on: date | None = None
    history: list[Event] = []

    def to_tool_record(self, rubric: Rubric) -> ToolRecord:
        """What the tiering engine sees. Unconfirmed means unreviewed."""
        level = self.confirmed_level or rubric.approved_tool.unregistered_level
        return ToolRecord(name=self.name, vendor_handling_level=level, listed_as_approved=self.listed_as_approved)


def tool_from_review(tool_id: str, name: str, vendor: str, review: VendorReviewResult, actor: str) -> ToolEntry:
    return ToolEntry(id=tool_id, name=name, vendor=vendor, proposed_level=review.proposed_vendor_level,
                     blockers=review.blockers, flags=review.flags, documents=review.documents,
                     history=[event(actor, "system", "vendor review recorded", review.level_reason)])


def confirm_tool(tool: ToolEntry, level: str, by: str, role: str, rubric: Rubric, today: date) -> ToolEntry:
    """An attorney confirms the vendor level; the tool is listed as approved if the rubric allows it."""
    if role not in rubric.register_rules.tool_confirm_roles:
        raise PermissionError(f"role {role!r} may not confirm tools")
    rubric.dimension("vendor_handling").level(level)   # KeyError for an unknown level
    tool = tool.model_copy(deep=True)
    tool.confirmed_level = level
    tool.history.append(event(by, role, "level confirmed",
                              f"{level} (proposed {tool.proposed_level})" if level != tool.proposed_level else level))
    blocked = rubric.vendor_review.approval_blocked_by_must_have_gaps and tool.blockers
    if level in rubric.approved_tool.vendor_handling_levels and not blocked:
        tool.listed_as_approved, tool.approved_on = True, today
        tool.history.append(event(by, role, "listed as approved"))
    else:
        reason = f"open must-have gaps: {', '.join(tool.blockers)}" if blocked else f"{level} is not an approved-tool level"
        tool.history.append(event(by, role, "not listed as approved", reason))
    return tool


def record_new_terms(tool: ToolEntry, review: VendorReviewResult, actor: str) -> ToolEntry:
    """A re-run vendor review. If the documents changed, the attorney must confirm again."""
    tool = tool.model_copy(deep=True)
    changed = review.documents != tool.documents
    tool.proposed_level, tool.blockers, tool.flags, tool.documents = (
        review.proposed_vendor_level, review.blockers, review.flags, review.documents)
    if changed:
        tool.confirmed_level, tool.listed_as_approved, tool.approved_on = None, False, None
        tool.history.append(event(actor, "system", "vendor terms changed", "confirmation and approval cleared"))
    return tool


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------

Status = Literal["provisional", "awaiting_signoff", "approved", "prohibited", "exception_granted", "reassessment_required"]


class Strike(BaseModel):
    dimension_id: str
    level_id: str
    quote: str
    by: str
    role: str
    reason: str
    on: date


class Signoff(BaseModel):
    role: str
    name: str
    on: date


class UseCaseEntry(BaseModel):
    id: str
    name: str
    owner: str | None
    department: str | None
    tool_id: str | None
    intake: IntakeResult            # facts after answers and strikes
    result: TierResult
    rubric_sha256: str
    status: Status
    strikes: list[Strike] = []
    signoffs: list[Signoff] = []
    approved_on: date | None = None
    next_review: date | None = None
    pending_triggers: list[str] = []
    history: list[Event] = []

    def required_signers(self) -> list[str]:
        return [a.id for a in self.result.approvers]

    def missing_signers(self) -> list[str]:
        signed = {s.role for s in self.signoffs}
        return [r for r in self.required_signers() if r not in signed]


def strike_finding(intake: IntakeResult, dimension_id: str, level_id: str, by: str, role: str, reason: str,
                   rubric: Rubric, today: date) -> tuple[IntakeResult, Strike]:
    """Remove a wrong finding. A dimension left empty becomes unknown again, with its follow-up question."""
    if role not in rubric.register_rules.strike_roles:
        raise PermissionError(f"role {role!r} may not strike findings")
    if not reason.strip():
        raise ValueError("a strike needs a written reason")
    found = [f for f in intake.answers.get(dimension_id, []) if f.level_id == level_id]
    if not found:
        raise KeyError(f"no finding {dimension_id}.{level_id} to strike")
    result = intake.model_copy(deep=True)
    result.answers[dimension_id] = [f for f in result.answers[dimension_id] if f.level_id != level_id]
    result.needs_review = [n for n in result.needs_review if not n.startswith(f"{dimension_id}.{level_id} ")]
    if not result.answers[dimension_id]:
        del result.answers[dimension_id]
        result.unknown_dimensions.append(dimension_id)
        result.follow_ups.append(follow_up_for(rubric, dimension_id))
    return result, Strike(dimension_id=dimension_id, level_id=level_id, quote=found[0].quote,
                          by=by, role=role, reason=reason, on=today)


def assess_use_case(use_id: str, intake: IntakeResult, tool: ToolEntry | None, actor: str,
                    rubric: Rubric | None = None, strikes: list[Strike] | None = None,
                    previous: "UseCaseEntry | None" = None) -> UseCaseEntry:
    """Tier the use case and open (or re-open) its register record. Sign-offs start empty."""
    rubric = rubric or load_rubric()
    result = assess(intake, tool.to_tool_record(rubric) if tool else None, rubric)
    if result.tier == Tier.Prohibited:
        status = "prohibited"
    elif result.provisional:
        status = "provisional"
    else:
        status = "awaiting_signoff"
    history = list(previous.history) if previous else []
    history.append(event(actor, "system", "assessed", f"{result.tier.value}, {status}"))
    return UseCaseEntry(
        id=use_id, name=intake.profile.use_case_name.value or use_id,
        owner=intake.profile.business_owner.value, department=intake.profile.department.value,
        tool_id=tool.id if tool else None, intake=intake, result=result,
        rubric_sha256=rubric_fingerprint(), status=status,
        strikes=list(strikes or []), history=history,
    )


def sign_off(entry: UseCaseEntry, role: str, name: str, today: date, rubric: Rubric) -> UseCaseEntry:
    if entry.status != "awaiting_signoff":
        raise ValueError(f"{entry.id} is {entry.status}; only awaiting_signoff records can be signed")
    if role not in entry.required_signers():
        raise PermissionError(f"{role!r} is not a required approver at {entry.result.tier.value}")
    if not entry.result.approved_tool:
        raise ValueError(f"{entry.id}: the tool is not listed as approved, so the use cannot be approved")
    entry = entry.model_copy(deep=True)
    entry.signoffs = [s for s in entry.signoffs if s.role != role] + [Signoff(role=role, name=name, on=today)]
    entry.history.append(event(name, role, "signed off"))
    if not entry.missing_signers():
        entry.status, entry.approved_on = "approved", today
        entry.next_review = add_months(today, rubric.review.cadence_months[entry.result.tier])
        entry.history.append(event("system", "system", "approved", f"next review {entry.next_review}"))
    return entry


def grant_exception(entry: UseCaseEntry, signers: dict[str, str], reason: str, today: date, rubric: Rubric) -> UseCaseEntry:
    """Prohibited uses only, with every joint approver the rubric names. signers: role -> name."""
    rule = rubric.approvers.prohibited_exception
    if entry.status != "prohibited" or not rule.allowed:
        raise ValueError("exceptions apply only to prohibited use cases, and only if the rubric allows them")
    missing = [r for r in rule.joint_approval if r not in signers]
    if missing:
        raise PermissionError(f"exception needs joint approval; missing {missing}")
    if not reason.strip():
        raise ValueError("an exception needs a written reason")
    entry = entry.model_copy(deep=True)
    entry.signoffs = [Signoff(role=r, name=signers[r], on=today) for r in rule.joint_approval]
    entry.status, entry.approved_on = "exception_granted", today
    entry.history.append(event(", ".join(signers.values()), "exception", "exception granted", reason))
    return entry


# ---------------------------------------------------------------------------
# Reassessment
# ---------------------------------------------------------------------------


def detect_triggers(previous: UseCaseEntry, new_intake: IntakeResult, new_tool_id: str | None, rubric: Rubric) -> list[str]:
    """Compare a resubmission with the saved snapshot. Any new level fires its trigger."""
    fired = []
    for trigger_id, dims in rubric.register_rules.level_triggers.items():
        for dim_id in dims:
            before = {f.level_id for f in previous.intake.answers.get(dim_id, [])}
            after = {f.level_id for f in new_intake.answers.get(dim_id, [])}
            if after - before:
                fired.append(trigger_id)
                break
    if new_tool_id != previous.tool_id:
        fired.append("new_vendor")
    return fired


def flag_for_reassessment(entry: UseCaseEntry, trigger_id: str, actor: str, detail: str, rubric: Rubric) -> UseCaseEntry:
    if trigger_id not in rubric.review.reassessment_triggers:
        raise KeyError(trigger_id)
    entry = entry.model_copy(deep=True)
    if trigger_id not in entry.pending_triggers:
        entry.pending_triggers.append(trigger_id)
    if entry.status in ("approved", "exception_granted", "awaiting_signoff"):
        entry.status = "reassessment_required"
    entry.history.append(event(actor, "system", f"trigger: {trigger_id}", detail))
    return entry


def overdue(entries: list[UseCaseEntry], today: date) -> list[UseCaseEntry]:
    return [e for e in entries if e.next_review and e.next_review < today]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class Register:
    def __init__(self, root: Path = DEFAULT_REGISTER):
        self.root = Path(root)

    def _path(self, kind: str, record_id: str) -> Path:
        return self.root / kind / f"{record_id}.json"

    def save_tool(self, tool: ToolEntry) -> None:
        self._write(self._path("tools", tool.id), tool)

    def save_use_case(self, entry: UseCaseEntry) -> None:
        self._write(self._path("use_cases", entry.id), entry)

    def tool(self, tool_id: str) -> ToolEntry:
        return ToolEntry.model_validate_json(self._path("tools", tool_id).read_text(encoding="utf-8"))

    def use_case(self, use_id: str) -> UseCaseEntry:
        return UseCaseEntry.model_validate_json(self._path("use_cases", use_id).read_text(encoding="utf-8"))

    def use_cases(self) -> list[UseCaseEntry]:
        folder = self.root / "use_cases"
        return [UseCaseEntry.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(folder.glob("*.json"))] if folder.exists() else []

    def use_cases_of_tool(self, tool_id: str) -> list[UseCaseEntry]:
        return [e for e in self.use_cases() if e.tool_id == tool_id]

    @staticmethod
    def _write(path: Path, record: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")


def propagate_terms_change(register: Register, tool_id: str, actor: str, rubric: Rubric) -> list[str]:
    """After record_new_terms changed a tool's documents, flag every use of that tool."""
    flagged = []
    for entry in register.use_cases_of_tool(tool_id):
        register.save_use_case(flag_for_reassessment(entry, "vendor_terms_change", actor,
                                                     f"vendor terms for {tool_id} changed", rubric))
        flagged.append(entry.id)
    return flagged
