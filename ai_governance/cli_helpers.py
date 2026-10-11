"""Small helpers shared by the command-line scripts (assess.py, vendor_review.py,
register.py). Kept separate so they can be unit-tested without a terminal.
"""

import re
from pathlib import Path
from typing import Callable

from .intake import IntakeResult, answer_follow_ups
from .register import Register
from .rubric import Rubric
from .vendor import VendorReviewResult


def next_use_case_id(register: Register) -> str:
    """UC-001, UC-002, ... one higher than the highest id already in the register."""
    numbers = [int(m.group(1)) for e in register.use_cases() if (m := re.fullmatch(r"UC-(\d+)", e.id))]
    return f"UC-{max(numbers, default=0) + 1:03d}"


def parse_choice(text: str, count: int) -> list[int] | None:
    """'1, 3' -> [0, 2]. Blank -> []. Anything invalid -> None (ask again)."""
    text = text.strip()
    if not text:
        return []
    picks = []
    for part in text.split(","):
        part = part.strip()
        if not part.isdigit() or not 1 <= int(part) <= count:
            return None
        if int(part) - 1 not in picks:
            picks.append(int(part) - 1)
    return picks


def ask_follow_ups(intake: IntakeResult, rubric: Rubric, input_fn: Callable[[str], str] = input,
                   print_fn: Callable[..., None] = print) -> IntakeResult:
    """Ask each open question as numbered choices. No free text: answers are rubric levels.
    A blank answer leaves the dimension unknown (it stays Medium and provisional)."""
    answers: dict[str, list[str]] = {}
    for fu in intake.follow_ups:
        print_fn(f"\n{fu.question}")
        for n, option in enumerate(fu.options, 1):
            print_fn(f"  {n}. {option.description}")
        while True:
            picks = parse_choice(input_fn("Choose one or more numbers (e.g. 1,3), or press Enter to skip: "),
                                 len(fu.options))
            if picks is not None:
                break
            print_fn("  Please enter numbers from the list, separated by commas.")
        if picks:
            answers[fu.dimension_id] = [fu.options[i].level_id for i in picks]
    return answer_follow_ups(intake, answers, rubric) if answers else intake


def write_outputs(out_dir: Path, stem: str, markdown: str, json_text: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md, js = out_dir / f"{stem}.md", out_dir / f"{stem}.json"
    md.write_text(markdown, encoding="utf-8")
    js.write_text(json_text, encoding="utf-8")
    return md, js


def render_vendor_report(result: VendorReviewResult, rubric: Rubric, title: str) -> str:
    def cell(text: str) -> str:
        return text.replace("|", "/").replace("\n", " ")

    out = [f"# AI vendor terms review: {title}", "", f"> **{result.disclaimer}**", "",
           "## Result", "",
           f"- Proposed vendor handling level: **{result.proposed_vendor_level}**. {result.level_reason}",
           f"- {result.approval_note}",
           f"- Blockers (must-have gaps): {', '.join(result.blockers) or 'none'}",
           f"- Negotiation flags (preferred gaps): {', '.join(result.flags) or 'none'}",
           "", "## Requirements", "",
           "| Requirement | Severity | Result | Evidence (clause: quote) |", "|---|---|---|---|"]
    for r in result.requirements:
        outcome = "met" if r.outcome == "met" else f"**gap** ({r.gap_kind})"
        evidence = "; ".join(f"{e.stance} {e.clause_id}: \"{cell(e.quote)}\""
                             for e in r.evidence if e.stance != "context") or "none"
        out.append(f"| {r.name} | {r.severity.replace('_', '-')} | {outcome} | {evidence} |")
    if result.needs_review:
        out += ["", "## Needs attorney review", ""] + [f"- {cell(n)}" for n in result.needs_review]
    out += ["", "## Documents reviewed", ""] + [f"- {name} (sha256 {sha[:12]})" for name, sha in result.documents.items()]
    out += ["", "---", result.disclaimer, ""]
    return "\n".join(out)
