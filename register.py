"""Work with the AI register: tools, use cases, sign-offs, and reassessment.

    python register.py list
    python register.py confirm TOOL_ID LEVEL --by "A. Counsel" [--role legal]
    python register.py answer UC-001 DIMENSION LEVEL [LEVEL ...]
    python register.py strike UC-001 DIMENSION LEVEL --by "A. Counsel" --role legal --reason "..."
    python register.py sign UC-001 --role business_owner --by "B. Owner"
    python register.py exception UC-001 --gc "G. Counsel" --committee "AI Committee" --reason "..."
    python register.py trigger UC-001 incident_or_complaint --by "AI lead" --detail "..."
    python register.py overdue
    python register.py memo UC-001

No API calls. Every change is saved to the record's history, and the memo in
output/ is regenerated. Answering or striking re-tiers the use case and
clears earlier sign-offs, because the facts they approved have changed.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from ai_governance.cli_helpers import write_outputs
from ai_governance.intake import answer_follow_ups
from ai_governance.memo import render_memo
from ai_governance.register import (DEFAULT_REGISTER, Register, UseCaseEntry, assess_use_case, confirm_tool,
                                    flag_for_reassessment, grant_exception, overdue, sign_off, strike_finding)
from ai_governance.rubric import load_rubric

ROOT = Path(__file__).resolve().parent


def tool_for(register: Register, entry: UseCaseEntry):
    return register.tool(entry.tool_id) if entry.tool_id else None


def save_and_memo(register: Register, entry: UseCaseEntry, out_dir: Path, rubric) -> None:
    register.save_use_case(entry)
    memo, _ = write_outputs(out_dir, entry.id, render_memo(entry, tool_for(register, entry), rubric),
                            entry.model_dump_json(indent=2))
    print(f"{entry.id}: {entry.result.tier.value}, {entry.status.replace('_', ' ')}. Memo: {memo}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Work with the AI register.")
    parser.add_argument("--register-dir", default=str(DEFAULT_REGISTER))
    parser.add_argument("--out-dir", default=str(ROOT / "output"))
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="override today (YYYY-MM-DD)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")
    p = sub.add_parser("confirm"); p.add_argument("tool_id"); p.add_argument("level")
    p.add_argument("--by", required=True); p.add_argument("--role", default="legal")
    p = sub.add_parser("answer"); p.add_argument("use_id"); p.add_argument("dimension"); p.add_argument("levels", nargs="+")
    p = sub.add_parser("strike"); p.add_argument("use_id"); p.add_argument("dimension"); p.add_argument("level")
    p.add_argument("--by", required=True); p.add_argument("--role", required=True); p.add_argument("--reason", required=True)
    p = sub.add_parser("sign"); p.add_argument("use_id"); p.add_argument("--role", required=True); p.add_argument("--by", required=True)
    p = sub.add_parser("exception"); p.add_argument("use_id")
    p.add_argument("--gc", required=True); p.add_argument("--committee", required=True); p.add_argument("--reason", required=True)
    p = sub.add_parser("trigger"); p.add_argument("use_id"); p.add_argument("trigger")
    p.add_argument("--by", required=True); p.add_argument("--detail", default="")
    sub.add_parser("overdue")
    p = sub.add_parser("memo"); p.add_argument("use_id")
    args = parser.parse_args(argv)

    rubric, register, out_dir = load_rubric(), Register(Path(args.register_dir)), Path(args.out_dir)
    try:
        if args.command == "list":
            for path in sorted((register.root / "tools").glob("*.json")):
                t = register.tool(path.stem)
                print(f"tool {t.id:<20} level {t.confirmed_level or '(unconfirmed: ' + t.proposed_level + ')'}"
                      f"  approved: {'yes' if t.listed_as_approved else 'no'}")
            for e in register.use_cases():
                print(f"{e.id:<8} {e.result.tier.value:<11} {e.status:<22} next review {e.next_review or '-'}  {e.name}")
        elif args.command == "confirm":
            tool = confirm_tool(register.tool(args.tool_id), args.level, args.by, args.role, rubric, args.today)
            register.save_tool(tool)
            print(f"{tool.id}: level {tool.confirmed_level}; listed as approved: {'yes' if tool.listed_as_approved else 'no'}"
                  f" ({tool.history[-1].action}{': ' + tool.history[-1].detail if tool.history[-1].detail else ''})")
        elif args.command in ("answer", "strike"):
            entry = register.use_case(args.use_id)
            strikes = list(entry.strikes)
            if args.command == "answer":
                intake = answer_follow_ups(entry.intake, {args.dimension: args.levels}, rubric)
            else:
                intake, strike = strike_finding(entry.intake, args.dimension, args.level, args.by, args.role,
                                                args.reason, rubric, args.today)
                strikes.append(strike)
            updated = assess_use_case(entry.id, intake, tool_for(register, entry), args.command, rubric,
                                      strikes=strikes, previous=entry)
            save_and_memo(register, updated, out_dir, rubric)
        elif args.command == "sign":
            save_and_memo(register, sign_off(register.use_case(args.use_id), args.role, args.by, args.today, rubric),
                          out_dir, rubric)
        elif args.command == "exception":
            entry = grant_exception(register.use_case(args.use_id),
                                    {"general_counsel": args.gc, "ai_governance_committee": args.committee},
                                    args.reason, args.today, rubric)
            save_and_memo(register, entry, out_dir, rubric)
        elif args.command == "trigger":
            entry = flag_for_reassessment(register.use_case(args.use_id), args.trigger, args.by, args.detail, rubric)
            save_and_memo(register, entry, out_dir, rubric)
        elif args.command == "overdue":
            late = overdue(register.use_cases(), args.today)
            for e in late:
                print(f"{e.id} {e.name}: review was due {e.next_review}")
            print(f"{len(late)} overdue.")
        elif args.command == "memo":
            entry = register.use_case(args.use_id)
            memo, _ = write_outputs(out_dir, entry.id, render_memo(entry, tool_for(register, entry), rubric),
                                    entry.model_dump_json(indent=2))
            print(f"Memo: {memo}")
    except (PermissionError, ValueError, KeyError, FileNotFoundError) as e:
        print(f"Not done: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
