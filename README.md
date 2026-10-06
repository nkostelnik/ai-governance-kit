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
| 2 | Intake pipeline (fact extraction with quotes) | Not started |
| 3 | Tiering engine (deterministic, unit-tested) | Not started |
| 4 | AI vendor terms review | Not started |
| 5 | Register, reassessment triggers, decision memo | Not started |
| 6 | Eval harness (false-Low rate and over-escalation rate) | Not started |
| 7 | CLI (`assess.py`, `vendor_review.py`) | Not started |

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

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
```

No API key is needed yet. Later stages read `ANTHROPIC_API_KEY` from the
environment; it is never committed.
