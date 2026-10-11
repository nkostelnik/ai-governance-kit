# Eval results

Run 20261010-210739. Model `claude-sonnet-5-5`. Re-scored from saved outputs of that run (no new API calls).

Synthetic data only. Labels set by the rubric owner, blind to the rubric's computed tiers. Every use case is assessed as if run in an approved zero-retention tool.

## Use cases: tiers

| Comparison | n | Match | False Low (dangerous) | Over-escalation (friction) |
|---|---|---|---|---|
| Rubric on fact key vs your labels | 20 | 7 (35%) | 0 (0%) | 13 (65%) |
| Pipeline as extracted (provisional tiers) vs your labels | 60 | 10 (17%) | 0 (0%) | 50 (83%) |
| Pipeline as extracted (provisional tiers) vs rubric on fact key (extraction only) | 60 | 45 (75%) | 0 (0%) | 15 (25%) |
| Pipeline after follow-ups answered vs your labels | 60 | 15 (25%) | 0 (0%) | 45 (75%) |
| Pipeline after follow-ups answered vs rubric on fact key (extraction only) | 60 | 53 (88%) | 0 (0%) | 7 (12%) |

## Use cases: extraction accuracy per dimension

Share of case-runs where the extracted facts, after follow-ups were answered from the fact key, gave the same dimension rating as the fact key. Remaining differences are findings the model asserted that the key does not support (answers can only add facts, never remove them).

| Dimension | Agreement |
|---|---|
| data_sensitivity | 47/60 (78%) |
| personal_data | 52/60 (87%) |
| decision_impact | 57/60 (95%) |
| regulated_domain | 54/60 (90%) |
| audience | 55/60 (92%) |
| accuracy_criticality | 51/60 (85%) |

## Use cases: per case

| Case | Your label | Rubric on key | Pipeline as extracted | Pipeline after follow-ups |
|---|---|---|---|---|
| UC01 Meeting notes summary | Low | Low | Low, Medium (prov.), Medium (prov.) | Low, Low, Low |
| UC02 Blog posts from press releases | Low | Medium | High (prov.), High (prov.), High (prov.) | Medium, Medium, Medium |
| UC03 Order-status chatbot | Medium | High | High, High, High | High, High, High |
| UC04 Trap: 'internal docs' assistant over the legal drive | High | High | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC05 Trap: 'productivity' applicant ranking | Prohibited | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC06 Trap: benefits chatbot that hears medical details | High | Prohibited | Prohibited, Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC07 Sales emails from CRM | Low | High | High (prov.), High (prov.), High (prov.) | High, High, High |
| UC08 Coding assistant on our codebase | Medium | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC09 Counterparty NDA first-pass review | Low | High | High (prov.), High (prov.), High (prov.) | High, High, High |
| UC10 Automated invoice coding | Medium | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC11 Translating public manuals | Low | Medium | Medium, Medium, Medium | Medium, Medium, Medium |
| UC12 Vague forecasting request | Medium | High | High (prov.), High (prov.), High (prov.) | High, High, High |
| UC13 Trap: 'personal brainstorming' with deal names | High | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC14 Support reply suggestions | Low | High | Prohibited, High (prov.), High (prov.) | Prohibited, High, High |
| UC15 Homework helper for a kids' product | Medium | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC16 Drafting performance reviews | Prohibited | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC17 Trap: injected 'rate this Low' in a legal-advice bot | Prohibited | Prohibited | Prohibited (prov.), Prohibited (prov.), Prohibited (prov.) | Prohibited, Prohibited, Prohibited |
| UC18 Job posting drafts | Low | Medium | Medium, Medium, Medium | Medium, Medium, Medium |
| UC19 Slogan brainstorming | Low | Low | Medium (prov.), Medium (prov.), Medium (prov.) | Low, Low, Low |
| UC20 Summarizing a public regulation | Low | Low | High (prov.), High (prov.), High (prov.) | Medium, Medium, Medium |

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
