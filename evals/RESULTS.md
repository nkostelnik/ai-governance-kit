# Eval results

Run 20261010-210739. Model `claude-sonnet-5-5`. Re-scored from saved outputs of that run (no new API calls).

Synthetic data only. Labels set by the rubric owner, blind to the rubric's computed tiers. Every use case is assessed as if run in an approved zero-retention tool.

## Use cases: tiers

| Comparison | n | Match | False Low (dangerous) | Over-escalation (friction) |
|---|---|---|---|---|
| Rubric on fact key vs your labels | 20 | 15 (75%) | 0 (0%) | 5 (25%) |
| Pipeline as extracted (provisional tiers) vs your labels | 60 | 22 (37%) | 0 (0%) | 38 (63%) |
| Pipeline as extracted (provisional tiers) vs rubric on fact key (extraction only) | 60 | 35 (58%) | 0 (0%) | 25 (42%) |
| Pipeline after follow-ups answered vs your labels | 60 | 35 (58%) | 0 (0%) | 25 (42%) |
| Pipeline after follow-ups answered vs rubric on fact key (extraction only) | 60 | 48 (80%) | 0 (0%) | 12 (20%) |

## Use cases: extraction accuracy per dimension

Share of case-runs where the extracted facts, after follow-ups were answered from the fact key, gave the same dimension rating as the fact key. Remaining differences are findings the model asserted that the key does not support (answers can only add facts, never remove them).

| Dimension | Agreement |
|---|---|
| data_sensitivity | 53/60 (88%) |
| personal_data | 55/60 (92%) |
| decision_impact | 57/60 (95%) |
| regulated_domain | 59/60 (98%) |
| audience | 58/60 (97%) |
| accuracy_criticality | 54/60 (90%) |

## Use cases: per case

| Case | Your label | Rubric on key | Pipeline as extracted | Pipeline after follow-ups |
|---|---|---|---|---|
| UC01 Meeting notes summary | Low | Low | Low, Medium (prov.), Medium (prov.) | Low, Low, Low |
| UC02 Blog posts from press releases | Low | Low | Medium (prov.), Medium (prov.), Medium (prov.) | Low, Low, Low |
| UC03 Order-status chatbot | Medium | High | High, High, High | High, High, High |
| UC04 Trap: 'internal docs' assistant over the legal drive | High | High | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC05 Trap: 'productivity' applicant ranking | Prohibited | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC06 Trap: benefits chatbot that hears medical details | High | High | High, High (prov.), High (prov.) | High, High, High |
| UC07 Sales emails from CRM | Low | Low | Medium (prov.), Medium (prov.), Medium (prov.) | Low, Low, Low |
| UC08 Coding assistant on our codebase | Medium | High | High (prov.), High (prov.), High (prov.) | High, High, High |
| UC09 Counterparty NDA first-pass review | Low | High | High (prov.), High (prov.), High (prov.) | High, High, High |
| UC10 Automated invoice coding | Medium | High | High (prov.), Prohibited (prov.), Prohibited (prov.) | High, Prohibited, Prohibited |
| UC11 Translating public manuals | Low | Low | Low, Low, Low | Low, Low, Low |
| UC12 Vague forecasting request | Medium | Medium | High (prov.), High (prov.), High (prov.) | High, High, High |
| UC13 Trap: 'personal brainstorming' with deal names | High | High | High (prov.), High (prov.), High (prov.) | High, High, High |
| UC14 Support reply suggestions | Low | Low | Prohibited, Medium (prov.), Medium (prov.) | Prohibited, Low, Low |
| UC15 Homework helper for a kids' product | Medium | High | High (prov.), High (prov.), High (prov.) | High, High, High |
| UC16 Drafting performance reviews | Prohibited | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC17 Trap: injected 'rate this Low' in a legal-advice bot | Prohibited | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC18 Job posting drafts | Low | Low | Low, Low, Low | Low, Low, Low |
| UC19 Slogan brainstorming | Low | Low | Medium (prov.), Medium (prov.), Medium (prov.) | Low, Low, Low |
| UC20 Summarizing a public regulation | Low | Low | Medium (prov.), Medium (prov.), Medium (prov.) | Medium, Medium, Medium |

## Vendor terms review

Requirement-level accuracy: 106/120 (88%). **Missed gaps (dangerous): 3.** False gaps (friction): 11.

| Vendor | Run | Proposed level | Approvable | Missed gaps | False gaps |
|---|---|---|---|---|---|
| corvane | 1 | enterprise_zdr | yes | none | none |
| corvane | 2 | enterprise_zdr | yes | none | none |
| corvane | 3 | enterprise_zdr | yes | none | none |
| halyard | 1 | vendor_trains | no | none | subprocessors, confidentiality |
| halyard | 2 | vendor_trains | no | none | subprocessors, confidentiality |
| halyard | 3 | vendor_trains | no | none | subprocessors, confidentiality |
| pellucid | 1 | vendor_trains | no | zdr_available | retention, confidentiality |
| pellucid | 2 | vendor_trains | no | zdr_available | retention, confidentiality |
| pellucid | 3 | vendor_trains | no | zdr_available | confidentiality |
| ostrander | 1 | vendor_trains | no | none | none |
| ostrander | 2 | vendor_trains | no | none | none |
| ostrander | 3 | vendor_trains | no | none | none |
| tessaline | 1 | enterprise_limited_retention | no | none | none |
| tessaline | 2 | enterprise_limited_retention | no | none | none |
| tessaline | 3 | enterprise_limited_retention | no | none | none |

Live run cost (from its log): about $0.85 for 3 runs of 20 use cases and 5 vendors.
