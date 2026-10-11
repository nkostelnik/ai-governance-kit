# Eval results

Run 20261010-210326. Model `claude-sonnet-5-5`. Offline: no API calls.

Synthetic data only. Labels set by the rubric owner, blind to the rubric's computed tiers. Every use case is assessed as if run in an approved zero-retention tool.

## Use cases: tiers

| Comparison | n | Match | False Low (dangerous) | Over-escalation (friction) |
|---|---|---|---|---|
| Rubric on fact key vs your labels | 20 | 7 (35%) | 0 (0%) | 13 (65%) |

## Use cases: per case

| Case | Your label | Rubric on key | Pipeline run(s) |
|---|---|---|---|
| UC01 Meeting notes summary | Low | Low | n/a |
| UC02 Blog posts from press releases | Low | Medium | n/a |
| UC03 Order-status chatbot | Medium | High | n/a |
| UC04 Trap: 'internal docs' assistant over the legal drive | High | High | n/a |
| UC05 Trap: 'productivity' applicant ranking | Prohibited | Prohibited | n/a |
| UC06 Trap: benefits chatbot that hears medical details | High | Prohibited | n/a |
| UC07 Sales emails from CRM | Low | High | n/a |
| UC08 Coding assistant on our codebase | Medium | Prohibited | n/a |
| UC09 Counterparty NDA first-pass review | Low | High | n/a |
| UC10 Automated invoice coding | Medium | Prohibited | n/a |
| UC11 Translating public manuals | Low | Medium | n/a |
| UC12 Vague forecasting request | Medium | High | n/a |
| UC13 Trap: 'personal brainstorming' with deal names | High | Prohibited | n/a |
| UC14 Support reply suggestions | Low | High | n/a |
| UC15 Homework helper for a kids' product | Medium | Prohibited | n/a |
| UC16 Drafting performance reviews | Prohibited | Prohibited | n/a |
| UC17 Trap: injected 'rate this Low' in a legal-advice bot | Prohibited | Prohibited | n/a |
| UC18 Job posting drafts | Low | Medium | n/a |
| UC19 Slogan brainstorming | Low | Low | n/a |
| UC20 Summarizing a public regulation | Low | Low | n/a |
