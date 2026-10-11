"""Review an AI vendor's terms, DPA, and AI addendum against the rubric's requirements.

    python vendor_review.py terms.docx dpa.pdf
    python vendor_review.py terms.docx dpa.pdf --register halyard --name "Halyard AI" --vendor "Halyard"

One Claude call per requirement. Writes a markdown report and the full
result (JSON) to output/. With --register, records the tool in the register
with the *proposed* vendor level; counsel confirms it with
`python register.py confirm`. If the tool is already registered and its
documents changed, its approval is cleared and every use of it is flagged
for reassessment. Requires attorney review; not legal advice.
"""

import argparse
import sys
from pathlib import Path

from ai_governance import DISCLAIMER, llm
from ai_governance.clauses import parse_documents
from ai_governance.cli_helpers import render_vendor_report, write_outputs
from ai_governance.register import (DEFAULT_REGISTER, Register, propagate_terms_change, record_new_terms,
                                    tool_from_review)
from ai_governance.rubric import load_rubric
from ai_governance.vendor import review

ROOT = Path(__file__).resolve().parent


def main(argv=None, call=llm.parse) -> int:
    parser = argparse.ArgumentParser(description="Review AI vendor terms.")
    parser.add_argument("files", nargs="+", help=".txt, .docx, or text-based .pdf")
    parser.add_argument("--register", metavar="TOOL_ID", help="record the result in the register under this id")
    parser.add_argument("--name", help="tool name for the register (default: TOOL_ID)")
    parser.add_argument("--vendor", help="vendor name for the register (default: TOOL_ID)")
    parser.add_argument("--register-dir", default=str(DEFAULT_REGISTER))
    parser.add_argument("--out-dir", default=str(ROOT / "output"))
    args = parser.parse_args(argv)

    rubric = load_rubric()
    recorder = llm.CostRecorder(call)
    result = review(parse_documents(args.files), rubric, call=recorder)
    result.cost_usd = round(recorder.cost, 4)

    stem = f"vendor-{args.register or Path(args.files[0]).stem}"
    title = args.name or args.register or ", ".join(Path(f).name for f in args.files)
    md, js = write_outputs(Path(args.out_dir), stem, render_vendor_report(result, rubric, title),
                           result.model_dump_json(indent=2))

    print(f"Proposed vendor level: {result.proposed_vendor_level}")
    print(f"{result.approval_note}")
    print(f"Blockers: {', '.join(result.blockers) or 'none'}  Flags: {', '.join(result.flags) or 'none'}")
    if result.needs_review:
        print(f"Needs attorney review: {len(result.needs_review)} item(s) (see report)")

    if args.register:
        register = Register(Path(args.register_dir))
        try:
            existing = register.tool(args.register)
        except FileNotFoundError:
            existing = None
        if existing is None:
            register.save_tool(tool_from_review(args.register, args.name or args.register,
                                                args.vendor or args.register, result, "vendor_review.py"))
            print(f"Registered tool {args.register} (proposed level; not yet confirmed). "
                  f"Counsel confirms with: python register.py confirm {args.register} LEVEL --by NAME")
        else:
            updated = record_new_terms(existing, result, "vendor_review.py")
            register.save_tool(updated)
            if updated.documents != existing.documents:
                flagged = propagate_terms_change(register, args.register, "vendor_review.py", rubric)
                print(f"Vendor terms changed: confirmation cleared; {len(flagged)} use case(s) flagged for reassessment.")
            else:
                print(f"Same documents as before for {args.register}; register record refreshed.")

    print(f"Report: {md}\nResult: {js}\nAPI cost: about ${recorder.cost:.3f}")
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
