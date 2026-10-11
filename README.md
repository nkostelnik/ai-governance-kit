# AI Governance Kit

> **Demonstration project.** Synthetic data only. Every output requires
> attorney review and is not legal advice. Nothing here claims compliance
> with any law.

A toolkit for a corporate legal department to enable AI use without creating
unmanaged risk. Companion to
[nda-triage-agent](https://github.com/nkostelnik/nda-triage-agent), and built
on the same idea: **the model reads, the rubric decides.** An LLM extracts
facts with quotes; deterministic Python assigns risk tiers from an
attorney-authored rubric. The model never picks the tier.

## Status

| Stage | What | Status |
|---|---|---|
| 1 | Rubric and acceptable use policy | Done |
| 2 | Intake pipeline (fact extraction with quotes) | Done; smoke-tested live on 5 samples |
| 3 | Tiering engine (deterministic, unit-tested) | Done |
| 4 | AI vendor terms review | Done; smoke-tested live on 2 synthetic vendors |
| 5 | Register, reassessment triggers, decision memo | Done |
| 6 | Eval harness (false-Low rate and over-escalation rate) | Done; baseline results below |
| 7 | CLI (`assess.py`, `vendor_review.py`, `register.py`) | Done; live demo below |

## What exists today

- [`governance/rubric.yaml`](governance/rubric.yaml): seven risk dimensions,
  each with fact-pattern levels mapped to Low / Medium / High / Prohibited;
  aggregation (worst dimension wins, three Mediums stack to High); fail-closed
  handling of unknown facts; cumulative controls and approvers per tier;
  review cadence and reassessment triggers; AI vendor requirements; and
  regulatory flags, all marked VERIFY.
- [`governance/acceptable_use_policy.md`](governance/acceptable_use_policy.md):
  a short AI acceptable use policy built from the same interview.
- [`ai_governance/rubric.py`](ai_governance/rubric.py): strict Pydantic loader.
  Typos and dangling references fail at load time, and a few governance rules
  are enforced in code: unknown facts can never rate Low, stacking can never
  produce Prohibited, and a regulatory flag cannot be marked verified without
  a citation and a date.

Every position in the rubric came from a one-question-at-a-time interview with
the rubric owner. Follow-up confirmations and changed answers are recorded in
`notes` fields in the YAML.

### Calibration

The first version of the rubric was strict enough that most realistic
requests landed at High or Prohibited, including the legal department's own
drafting work. A rubric that rates everything High stops sorting risk and
becomes a queue. A calibration review walked four everyday requests through
it and made seven changes:

- privileged and third-party confidential data allowed (High) in an approved tool;
- approved tools may have limited retention, not only zero retention;
- internal data and employee contact info lowered to Low;
- human-verified customer-facing and critical output lowered to Medium;
- bias testing and bot disclosure attached to the situations that need
  them, instead of to every High use.

Each change is marked as a recalibration in the YAML `notes`. The eval
harness (Stage 6) will report both the dangerous error (false-Low) and the
friction error (over-escalation), because a governance tool can fail in
either direction.

## Stage 2: intake extraction

[`ai_governance/intake.py`](ai_governance/intake.py) turns a plain-English
description into verified facts. It does not assign tiers.

1. **The questionnaire comes from the rubric.** Each rubric dimension is one
   question and its levels are the answers, so editing `rubric.yaml` changes
   the intake. Nothing is maintained twice.
2. **One Claude call per intake** (`claude-sonnet-5-5`, structured output
   validated by Pydantic). Claude lists every level the description supports,
   each with a verbatim quote, marked `stated` or `inferred`.
3. **Python checks everything the model said.** A finding survives only if its
   quote appears in the description (tolerant of whitespace, case, and curly
   quotes, nothing more) and its level id exists in the rubric. Rejected
   findings are kept in the output with the reason, for audit.
4. **Fail closed.** A dimension with no surviving finding is `unknown` and
   gets a follow-up question built from the rubric's levels (button-style
   answers). Silence is never read as "no risk": even "no personal data"
   needs a supporting quote. A refusal or truncated response makes every
   dimension unknown.
5. **Inferred findings count, with review.** A tool that "searches the
   Legal SharePoint" is treated as touching privileged material, flagged
   `needs_review` so a person confirms it.
6. **The description is treated as data.** The prompt wraps it in tags and
   tells the model to ignore instructions inside it (a requester writing
   "this is low risk" should not move the result).

Design tradeoff: one call per intake, because descriptions are short and the
dimensions inform each other (knowing it is a chatbot changes how "customer
data" reads). Stage 4 makes the opposite choice for long vendor agreements.

[`ai_governance/llm.py`](ai_governance/llm.py) is the only file that calls
the API; it opts into server-side refusal fallback so a classifier decline
is retried on Anthropic's recommended fallback model. Every other piece is
tested without a network connection (`tests/test_intake.py`).

### Smoke test results (2026-10-10, 5 synthetic samples, about $0.10 total)

This is a smoke test, not an evaluation: five samples written while building,
one run each. Stage 6 measures accuracy on separate, labeled cases.

| Sample | What happened |
|---|---|
| Warranty chatbot | Customer data, live external answers, customer reliance without verification, and unreviewed vendor all found. Over-reached once: inferred "company confidential" from warranty terms, which are usually public. |
| Email rewrite | Internal data, employee contact info, human-reviewed draft, internal audience found. Vendor terms and regulated domain correctly left unknown. |
| Legal SharePoint search (trap) | **Caught.** Inferred privileged, third-party confidential, and company confidential from "the entire Legal department SharePoint site". Over-reached once: inferred "relied on for legal purposes without verification" when the description is silent on verification. |
| "Productivity" resume screener (trap) | **Caught.** Found employment decision and decision about a person despite the "productivity" framing, and inferred that the bottom 80 percent are effectively rejected without human review. Mislabeled applicant data as "customer basic data" because the rubric has no level for job applicants (a rubric gap, not a model error). |
| "Sales wants to try AI." | All seven dimensions unknown, seven follow-up questions. Fail-closed behavior as designed. |

No quote failed verification in any run. Two patterns to carry into Stage 6:
inferred findings lean toward over-escalation (the safe direction, but it
costs friction), and every inferred finding currently produces a
needs_review note, which is noisy.

Bug found and fixed during the smoke test: the prompt-cache marker covered
the whole request, so every call paid the cache-write premium and none got
a cache hit. Moving the marker to the system prompt halved the per-intake
cost (about $0.015 to $0.007).

## Stage 3: tiering engine

[`ai_governance/tiering.py`](ai_governance/tiering.py) applies the rubric to
verified facts. There is no model in this step: the same facts always produce
the same tier, and every rule is unit-tested (`tests/test_tiering.py`).

- **Per dimension:** the worst level found sets the dimension's tier. Levels
  that are "Prohibited, but High in an approved tool" use the lower tier only
  when the tool is approved.
- **Unknown dimensions** are rated Medium and the result is marked
  *provisional*: it cannot be finalized until the follow-up questions are
  answered (`answer_follow_ups` in `intake.py`; answers can add risk, never
  remove it).
- **Overall:** worst dimension wins; three or more Medium dimensions stack to
  High; stacking never produces Prohibited.
- **Output:** the tier, the reason for it (with the supporting quote), the
  cumulative controls and approvers, situation-triggered controls (bias
  testing, bot disclosure), the review cadence, and any regulatory flags,
  still marked VERIFY. A Prohibited result lists the exception path instead.

**Vendor handling is looked up, not extracted.** The vendor dimension comes
from the tool's register record (the result of a vendor terms review), never
from the requester's description. A tool with no record is treated as
"vendor terms not yet reviewed", which the rubric rates Prohibited. Two
reasons: a requester should not be able to lower risk by asserting "we have
a zero-retention contract", and the smoke test showed the model treating the
same situation (an unreviewed tool) inconsistently. Facts the company already
knows are looked up; only facts about the proposed use are extracted.

The five smoke-test intakes are saved in `tests/fixtures/intakes/` and run
through the engine as end-to-end tests at no cost. In an approved
zero-retention tool they land at: email rewrite Medium (provisional),
warranty chatbot High, Legal SharePoint search Prohibited, resume screener
Prohibited, "Sales wants to try AI" High (six unknowns stack). Without a
registered tool, all five are Prohibited. (These were the tiers under the
rubric at Stage 3. After the Stage 6 recalibration, the Legal SharePoint
search is High and "Sales wants to try AI" is Medium; the tests track the
current rubric.)

```
python -m ai_governance.tiering tests/fixtures/intakes/warranty_chatbot.json enterprise_zdr
```

## Stage 4: AI vendor terms review

[`ai_governance/vendor.py`](ai_governance/vendor.py) checks a vendor's terms,
DPA, and AI addendum (any number of .txt, .docx, or text-based .pdf files)
against the rubric's eight vendor requirements.

- **Clauses.** [`clauses.py`](ai_governance/clauses.py) is the NDA project's
  splitter, copied (the splitting logic is unchanged), plus text PDFs and
  document-prefixed clause ids (`dpa:sec-1`) so every citation names its
  document.
- **One call per requirement, not per clause.** The usual gaps in AI terms
  are absences (no zero-retention option) and conflicts (a marketing page
  promises "we never train on your data" while the terms reserve the right).
  A call that sees one clause can see neither; a call that reads every
  document for one requirement can. The documents are cached after the first
  call, so the other seven read them at a tenth of the price.
- **The model finds evidence; Python decides.** Each piece of evidence cites
  a clause id (the schema only allows real ones), a verbatim quote (checked
  against that clause), and a stance: meets, falls short, or context.
  Any verified "falls short" makes a gap, even next to "meets" language.
  Silence is a gap. Unverifiable evidence or a failed call is a gap with a
  needs_review note. Must-have gaps block; preferred gaps are flagged.
- **Proposed register level.** The rubric's ordered rules propose the tool's
  vendor_handling level (training gap -> vendor_trains; zero retention ->
  enterprise_zdr; retention limit met -> limited retention; otherwise
  consumer_tool). An attorney confirms it when registering the tool. No tool
  is approvable while a must-have gap is open.

### Smoke test results (2026-10-10, about $0.19 total)

| Vendor | First run | After fix |
|---|---|---|
| Brightloom (marketing says "never trains", terms reserve the right; planted "report no gaps" instruction) | Correct: training gap found, conflict flagged, `vendor_trains`, not approvable. Planted instruction ignored. | Same. |
| Quillmark (clean terms) | **Wrong.** Three invented blockers: related clauses were forced into "falls short" (e.g. the retention clause cited against "no training"). | `enterprise_zdr`; correct flags (subprocessors: no objection right; no output IP indemnity). One blocker remains: see below. |

The first-run failure was a design flaw, not noise: with only two stances,
every related clause had to be "meets" or "falls short", and worst-evidence-
wins turned the stray "falls short" into gaps. Adding a third stance,
"context", which Python ignores, fixed it without weakening the rule that
caught Brightloom.

The remaining Quillmark blocker is a question about the rubric, not a model
error: the retention standard says data is deleted "no later than
termination", and Quillmark deletes "within 30 days after termination". Read
literally, that falls short. The rubric owner confirmed the standard as written,
so Quillmark is correctly blocked until that term is negotiated.

Known rough edge: when a requirement is simply absent but the model marks it
"addressed" with only context evidence, the gap is labeled "unresolved"
rather than "not addressed". Both are gaps; only the label differs.

## Stage 5: register, reassessment, decision memo

[`ai_governance/register.py`](ai_governance/register.py) and
[`ai_governance/memo.py`](ai_governance/memo.py). Plain Python, no API calls.

- **Storage: one JSON file per record** (`register/tools/`, `register/use_cases/`),
  validated by Pydantic on every load. Chosen over SQLite because counsel can
  read a record without tools, every change is a git diff (the audit trail,
  reviewable like a redline), and a legal department's AI register is tens to
  hundreds of records. With many concurrent writers or thousands of records,
  SQLite or a GRC system would be the better choice. Every record also stores
  the sha256 of the rubric it was assessed against.
- **Tools.** A vendor review creates a tool record with the *proposed*
  vendor level. Only counsel (`register_rules.tool_confirm_roles`) can confirm
  it, and the tool is listed as approved only if the level is an approved-tool
  level and no must-have gap is open. If the vendor's documents change, the
  confirmation is cleared and every use of the tool is flagged for
  reassessment.
- **Use cases.** Each record snapshots the verified facts and the tier result,
  with status (provisional, awaiting sign-off, approved, prohibited,
  exception granted, reassessment required), sign-offs, and an append-only
  history. A use is approved only when every approver its tier requires has
  signed and the tool is listed as approved; the next review date follows
  the rubric cadence. A Prohibited use can proceed only by joint exception
  (General Counsel and AI governance committee) with a written reason.
- **Reviewer corrections.** Counsel or the AI enablement lead
  (`register_rules.strike_roles`) can strike a finding the model got wrong,
  with a written reason that appears in the memo. Striking never lowers risk
  by default: a dimension left empty becomes unknown again and needs an
  answer. The business owner cannot strike, because the business owner is an
  approver at every tier and is usually the requester's side.
- **Reassessment triggers.** A resubmitted use is compared with its snapshot:
  any new data, audience, or automation level, or a different tool, fires the
  matching trigger. Vendor terms changes propagate from the tool. Incidents,
  new jurisdictions, new purposes, and regulatory changes are recorded by
  hand. `overdue()` lists records past their review date.
- **Decision memo.** Markdown, generated only from the record (no model):
  tier and why, a facts table with supporting quotes and their basis
  (stated, inferred, answered, register), reviewer corrections, controls,
  laws to check (still VERIFY), open items, vendor status, review dates, and
  signature lines for the tier's approvers.

Sample memos generated from the smoke-test intakes are in
[`samples/memos/`](samples/memos/): an approved Low use, the Legal SharePoint
search after counsel struck a worst-case inference (High, provisional), and
the resume screener (Prohibited, exception path).

```
python samples/memos/make_samples.py
```

## Stage 6: evals

[`evals/`](evals/) holds 20 synthetic use cases (including the traps: an
"internal docs" assistant over the legal drive, a hiring screen called
"productivity", a benefits bot that hears medical details, "personal
brainstorming" about unannounced deals, and a description that tells the
reviewer to rate it Low) and 5 synthetic vendor term sets (clean; trains by
default; FAQ promise contradicted by a controlling addendum; silent; limited
retention with weak security notice). The rubric owner labeled the expected
tier of every use case and the gaps in every vendor set, blind to what the
rubric computes ([`labels.json`](evals/labels.json)).

**Three comparisons, so a wrong tier can be traced to its cause.** Each case
also has a fact key: the levels the case text establishes. Running the
rubric on the fact key shows what the rubric says with perfect extraction.

- your label vs rubric on the fact key: **rubric disagreement** (refine the YAML);
- rubric on the fact key vs full pipeline: **extraction error** (the model misread);
- your label vs full pipeline: what a user of the kit would experience.

Below the label is a **false Low** (the dangerous error). Above it is
**over-escalation** (friction). Both are reported.

### Baseline results (2026-10-10, 3 runs, about $0.85)

| Comparison | n | Match | False Low | Over-escalation |
|---|---|---|---|---|
| Rubric on fact key vs labels | 20 | 35% | **0%** | 65% |
| Pipeline after follow-ups answered vs fact key (extraction only) | 60 | 88% | **0%** | 12% |
| Pipeline after follow-ups answered vs labels | 60 | 25% | **0%** | 75% |
| Vendor requirements vs labels | 120 | 88% | 3 missed gaps | 11 false gaps |

What this says, honestly:

1. **No false Lows anywhere** in 60 pipeline runs or in the rubric itself.
   Every use-case error is in the safe direction.
2. **The rubric, not the model, is the main source of friction.** Applied to
   the correct facts, it rates 13 of 20 cases higher than the rubric owner
   would. The patterns: customer data is High even with a person reviewing;
   any reviewed external output is Medium; and the absolute prohibitions
   (trade secrets, MNPI, health data, minors) are stricter than the owner's
   case-by-case judgment. These are listed in
   [`DISAGREEMENTS.md`](evals/DISAGREEMENTS.md) for rubric refinement.
3. **Extraction is good but over-infers.** Once follow-up questions are
   answered, extracted facts give the same rating as the fact key 78% to 95%
   of the time per dimension, and 88% of tiers match. The misses are all
   added risk: CRM customer data labeled "third-party confidential"; "IT
   how-tos" read as credentials; "HR policies" read as employee HR records;
   "refund eligibility" read once as a credit decision. Some disputed calls
   may be the fact key's fault (an NDA issues list "sent to the other side"
   arguably is external output).
4. **Silence costs follow-ups, by design.** As extracted, most results are
   provisional because descriptions rarely say what a use is *not* ("no
   personal data", "not a regulated domain"). The fail-closed rule turns
   that into questions rather than assumptions. It shows up as 83%
   over-escalation on provisional tiers, falling to 75% once answered.
5. **Vendor review: 3 missed gaps, all the same call.** Pellucid offers zero
   retention only on Enterprise plans; the owner labeled that a gap, the
   model read it as met. The standard ("vendor offers zero data retention")
   does not say "on our plan", so the fix is the standard's wording. The 11
   false gaps are stricter readings (a "good-faith discussion" objection
   right counted as no objection right; confidentiality undercut by a
   training reservation).
6. **Both traps that matter most were caught every run:** the planted "rate
   this Low" instruction was ignored (UC17 Prohibited, 3/3) and the
   "productivity" hiring screen was Prohibited (3/3).

### Recalibration from the evals

The rubric owner reviewed the disagreement log and changed eleven settings
in `rubric.yaml` (each marked "Stage 6 recalibration" in its notes):
customer basic data and third-party confidential data are Low in an approved
tool; reviewed external output, verified customer-facing facts, and
regulated-domain work not about specific people are Low; trade secrets, MNPI,
health data, and data about minors moved from absolute bans to High in an
approved tool; services directed at minors and unverified critical reliance
moved from Prohibited to High; unknown facts no longer count toward
stacking; and the zero-retention standard now reads "on the plan we
purchase". The acceptable use policy was updated to match.

| Comparison (same saved outputs, re-scored for free) | Before | After |
|---|---|---|
| Rubric on fact key vs labels: match | 35% | **75%** |
| Rubric on fact key vs labels: false Low | 0% | **0%** |
| Pipeline after follow-ups vs labels: match | 25% | **58%** |
| Pipeline after follow-ups vs labels: false Low | 0% | **0%** |
| Extraction only (pipeline vs fact key): match | 88% | 80% |

Notes, honestly:

- **One fact-key correction.** Re-scoring at first showed three false Lows
  (all UC06, the benefits chatbot). The cause was the fact key, not the
  model: the key tagged UC06 as employee HR records, which the rubric defines
  as performance, compensation, and discipline. The key was corrected (and
  the correction recorded in `use_cases.yaml`); the model had found health
  information every run, which now gives the owner's label exactly.
- **Extraction match fell from 88% to 80%** because the rubric now
  distinguishes more finely below High: over-inferences that used to be
  hidden inside a High result (for example "IT how-tos" read as credentials)
  now change the tier. Every remaining extraction error is still in the safe
  direction.
- **Stacking can no longer fire on real facts.** With unknowns excluded, only
  one intake level (verified critical reliance) is still Medium, so the
  "three Mediums" rule is unreachable today. It is kept in the YAML and
  tested against a modified rubric in case Medium levels return.
- **Five cases still disagree with the owner's labels**, all over-escalation:
  UC03 (live chatbot), UC08 (source code), UC09 (counterparty NDAs, because
  privileged material is still High), UC10 (auto-posted invoices), and UC15
  (kids' homework helper). The owner kept those rubric positions; they are
  documented as deliberate strictness in `DISAGREEMENTS.md`.
- The vendor results do not change: the Pellucid label (plan-gated zero
  retention counted as a gap) predates the new standard wording, and was not
  re-labeled.

Raw outputs of this run are committed in `evals/results/20261010-210739/`, so
the numbers can be re-scored without new API calls:

```
python evals/run_evals.py --offline                     # free: labels vs rubric only
python evals/run_evals.py --rescore 20261010-210739     # free: re-score the saved run
python evals/run_evals.py --runs 3                      # live, about $0.85
```

## Stage 7: command line

Three commands. Each writes markdown for people and JSON for systems, and
prints its approximate API cost.

| Command | What it does | API calls |
|---|---|---|
| [`assess.py`](assess.py) | Intake a proposed use, ask open questions as numbered choices (no free text; `--no-input` skips them), tier it, **save it to the register** with the next UC number, write the decision memo | 1 (about $0.01) |
| [`vendor_review.py`](vendor_review.py) | Review vendor terms (.txt, .docx, text .pdf); with `--register`, record the tool with the *proposed* level; changed documents clear the tool's approval and flag its uses | 8 (about $0.04) |
| [`register.py`](register.py) | `list`, `confirm`, `answer`, `strike`, `sign`, `exception`, `trigger`, `overdue`, `memo` | none |

Every assessment is saved, so nothing assessed goes unrecorded; saving never
approves anything. Answering a question or striking a finding re-tiers the
use and clears earlier sign-offs, because the facts they approved changed.

### Quick start (the Stage 7 demo, about $0.05)

```
python vendor_review.py evals/vendors/corvane/terms.txt --register corvane --name "Corvane Assistant (synthetic)" --vendor "Corvane (fictional)" --out-dir samples/demo
python register.py --out-dir samples/demo confirm corvane enterprise_zdr --by "A. Counsel (demo)"
python assess.py --file samples/demo/request.txt --tool corvane --no-input --out-dir samples/demo
python register.py --out-dir samples/demo answer UC-001 regulated_domain no_regulated_domain
python register.py --out-dir samples/demo sign UC-001 --role business_owner --by "Jordan Lee (demo)"
python register.py list
```

What happened on the recorded run: Corvane came back with no gaps and a
proposed level of `enterprise_zdr`; counsel confirmed it and it was listed
as approved; the renewal-reminder request was Medium and provisional with
one open question (regulated domain, which the description did not
address); once answered it was Low, needed only the business owner's
signature, and was approved with a review date a year out. The outputs are
in [`samples/demo/`](samples/demo/) and the records in [`register/`](register/),
all synthetic. One carry-over from the evals shows up here too: the model
again labeled ordinary customer data as "third-party confidential". After
the Stage 6 recalibration that no longer changes the tier, but it is a known
over-inference.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
```

Tests need no API key. Live runs read `ANTHROPIC_API_KEY` from the
environment; it is never committed. Smoke test one synthetic intake:

```
python -m ai_governance.intake samples/intakes/warranty_chatbot.txt
```
