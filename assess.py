"""Assess a proposed AI use case.

    python assess.py "Marketing wants a chatbot that answers warranty questions..." --tool approved-assistant
    python assess.py --file intake.txt --tool approved-assistant --no-input

Runs intake (one Claude call), asks any follow-up questions as numbered
choices, tiers the use with the rubric, saves it to the register with the
next UC number, and writes a decision memo (markdown) and the full record
(JSON) to output/. Requires attorney review; not legal advice.
"""

import argparse
import sys
from pathlib import Path

from ai_governance import DISCLAIMER, llm
from ai_governance.cli_helpers import ask_follow_ups, next_use_case_id, write_outputs
from ai_governance.intake import run_intake
from ai_governance.memo import render_memo
from ai_governance.register import DEFAULT_REGISTER, Register, assess_use_case
from ai_governance.rubric import load_rubric

ROOT = Path(__file__).resolve().parent


def main(argv=None, call=llm.parse, input_fn=input, interactive=None) -> int:
    parser = argparse.ArgumentParser(description="Assess a proposed AI use case.")
    parser.add_argument("description", nargs="?", help="the proposed use, in plain English")
    parser.add_argument("--file", help="read the description from a text file instead")
    parser.add_argument("--tool", help="register id of the AI tool the use would run on")
    parser.add_argument("--no-input", action="store_true", help="do not ask follow-up questions")
    parser.add_argument("--register-dir", default=str(DEFAULT_REGISTER))
    parser.add_argument("--out-dir", default=str(ROOT / "output"))
    args = parser.parse_args(argv)

    if bool(args.description) == bool(args.file):
        parser.error("give a description or --file, not both")
    description = Path(args.file).read_text(encoding="utf-8") if args.file else args.description

    rubric, register = load_rubric(), Register(Path(args.register_dir))
    tool = None
    if args.tool:
        try:
            tool = register.tool(args.tool)
        except FileNotFoundError:
            print(f"No tool {args.tool!r} in the register. Run vendor_review.py with --register first.", file=sys.stderr)
            return 2

    recorder = llm.CostRecorder(call)
    intake = run_intake(description, rubric, call=recorder)

    if interactive is None:
        interactive = sys.stdin.isatty()
    if intake.follow_ups and interactive and not args.no_input:
        print(f"{len(intake.follow_ups)} question(s) could not be answered from the description.")
        intake = ask_follow_ups(intake, rubric, input_fn=input_fn)

    use_id = next_use_case_id(register)
    entry = assess_use_case(use_id, intake, tool, "assess.py", rubric)
    register.save_use_case(entry)
    memo_path, json_path = write_outputs(Path(args.out_dir), use_id, render_memo(entry, tool, rubric),
                                         entry.model_dump_json(indent=2))

    r = entry.result
    print(f"\n{use_id}: {entry.name}")
    print(f"Tier: {r.tier.value} ({entry.status.replace('_', ' ')})")
    for reason in r.reasons:
        print(f"  {reason}")
    if tool is None:
        print("  Note: no --tool given, so vendor terms are treated as unreviewed (Prohibited).")
    if intake.follow_ups:
        print(f"Open questions: {len(intake.follow_ups)}. Answer later with: python register.py answer {use_id} ...")
    print(f"Memo: {memo_path}\nRecord: {json_path}\nRegister: saved as {use_id}")
    print(f"API cost: about ${recorder.cost:.3f}")
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
