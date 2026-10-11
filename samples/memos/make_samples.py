"""Regenerate the sample memos from the saved smoke-test intakes. No API calls.

    python samples/memos/make_samples.py
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ai_governance.intake import IntakeResult, answer_follow_ups  # noqa: E402
from ai_governance.memo import render_memo  # noqa: E402
from ai_governance.register import ToolEntry, assess_use_case, confirm_tool, sign_off, strike_finding  # noqa: E402
from ai_governance.rubric import load_rubric  # noqa: E402

rubric, today, out = load_rubric(), date(2026, 10, 10), Path(__file__).parent


def fixture(name: str) -> IntakeResult:
    path = ROOT / "tests" / "fixtures" / "intakes" / f"{name}.json"
    return IntakeResult.model_validate(json.loads(path.read_text(encoding="utf-8")))


tool = confirm_tool(ToolEntry(id="approved-assistant", name="Approved Assistant (synthetic)", vendor="Fictional Vendor Inc.",
                              proposed_level="enterprise_zdr", flags=["subprocessors"]),
                    "enterprise_zdr", "A. Counsel", "legal", rubric, today)

# 1. Email rewrite: the one open question answered, then signed by the business owner.
email = answer_follow_ups(fixture("email_rewrite"), {"regulated_domain": ["no_regulated_domain"]}, rubric)
uc1 = sign_off(assess_use_case("UC-001", email, tool, "intake", rubric), "business_owner", "B. Owner", today, rubric)
(out / "UC-001_email_rewrite.md").write_text(render_memo(uc1, tool, rubric), encoding="utf-8")

# 2. Legal SharePoint search: counsel strikes a worst-case inference; the question reopens.
struck, strike = strike_finding(fixture("legal_sharepoint_search"), "accuracy_criticality", "critical_reliance_unverified",
                                "A. Counsel", "legal", "The description is silent on verification; the model inferred the worst case.",
                                rubric, today)
uc2 = assess_use_case("UC-002", struck, tool, "intake", rubric, strikes=[strike])
(out / "UC-002_legal_sharepoint_search.md").write_text(render_memo(uc2, tool, rubric), encoding="utf-8")

# 3. Resume screener: prohibited, exception path shown.
uc3 = assess_use_case("UC-003", fixture("productivity_screener"), tool, "intake", rubric)
(out / "UC-003_resume_screener.md").write_text(render_memo(uc3, tool, rubric), encoding="utf-8")

print(f"UC-001 {uc1.result.tier.value} {uc1.status} | UC-002 {uc2.result.tier.value} {uc2.status} | "
      f"UC-003 {uc3.result.tier.value} {uc3.status}")
