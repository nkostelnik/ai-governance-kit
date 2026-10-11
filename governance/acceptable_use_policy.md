# AI Acceptable Use Policy

> **Demonstration policy.** Built for a portfolio project from an attorney's
> interview answers. It is not legal advice, has not been adopted by any
> organization, and requires attorney review before any use. Items marked
> "VERIFY" need a citation confirmed by counsel.

Version 1 (draft). Risk tiers, controls, and approvers referenced here are
defined in [`rubric.yaml`](rubric.yaml); if the two ever disagree, the rubric
controls and this policy should be corrected.

## 1. Purpose

We want people to use AI where it helps, with guardrails that scale with the
risk. This policy sets the baseline rules for everyone, and the AI use-case
intake decides what more a specific use needs.

## 2. Who this covers

Employees, contractors, and vendors acting on our behalf.

## 3. Baseline rules (every AI use)

1. **Use only approved tools.** An approved tool is self-hosted or runs under
   an enterprise contract with no training on our data, a DPA, and either
   zero or limited data retention, and is listed in the AI register. Personal or consumer AI
   accounts (free tiers, click-through terms) may not be used for company work.
2. **Complete training first.** Acknowledge this policy and complete AI
   training before using any AI tool for work.
3. **A person reviews before use.** A human reviews AI output before it is
   relied on, sent, or published.
4. **Disclose AI use.** Tell recipients when content they receive was
   generated with AI.
5. **Register your use.** Every AI use case is recorded in the AI register
   with a named business owner.
6. **Logging.** Approved tools log prompts and outputs for audit. Do not try
   to avoid logging.

## 4. Information you may never put into an AI tool

These are prohibited in any AI tool, approved or not:

- Credentials, secrets, or security configurations
- Employee HR records (performance, compensation, discipline)
- Government IDs or financial account numbers
- Biometric data
- Other sensitive personal data (race, religion, sexual orientation, precise
  geolocation, immigration status)

These are allowed **only in an approved tool**, after the use case is assessed:

- Company confidential information (High tier)
- Trade secrets or proprietary source code (High tier)
- Material non-public information (High tier). Insider trading and
  confidentiality obligations still apply. VERIFY: [citation needed]
- Privileged communications or attorney work product (High tier).
  VERIFY: [citation needed] (whether use in a third-party AI tool affects
  privilege or work product protection).
- Health or medical information (High tier). VERIFY: [citation needed]
- Data about minors (High tier). VERIFY: [citation needed]
- Job applicant data such as resumes and interview notes (High tier). Using AI
  to evaluate, score, or rank candidates remains prohibited (section 5).
- Third-party confidential information held under an NDA or contract (Low
  tier). Check the NDA or contract first; it may restrict this use.
- Customer or consumer basic data (Low tier)
- Employee business contact information (Low tier)

## 5. Prohibited uses

- AI that makes, or effectively makes, a decision about a specific person
  without meaningful human review.
- AI-assisted decisions about people in employment, credit or lending,
  insurance, housing, or health care, even with a human final call.
- Legal services or legal advice to people outside the company.

Education or services directed at minors, and AI output relied on for legal,
regulatory, financial reporting, or safety purposes without verification by a
qualified person, are not prohibited but are always High tier.

An exception to any prohibited use requires the joint approval of the General
Counsel and the AI governance committee, recorded in the register.

## 6. Getting a use case approved

Describe the proposed use in the AI intake. It is rated on seven dimensions
(data sensitivity, personal data, decision impact, regulated domain, audience,
vendor data handling, accuracy criticality) and the highest rating sets the
tier. Three or more Medium ratings make the use High (facts not yet
established do not count toward this).

| Tier | What it takes | Who approves | Review |
|---|---|---|---|
| Low | Baseline rules (section 3) | Business owner self-certifies; AI enablement lead spot-checks | Annually |
| Medium | Plus privacy review and security review | Plus AI enablement lead, Privacy, Information security | Every 6 months |
| High | Plus accuracy testing, ongoing monitoring, incident path and kill switch | Plus assigned counsel and the AI governance committee | Quarterly |
| Prohibited | Not allowed | Exception only by GC and AI governance committee jointly | n/a |

Some controls apply because of the situation, whatever the tier: bias testing
whenever AI output informs a decision about a specific person, and bot
disclosure whenever AI interacts directly with customers or the public.

If the intake cannot establish a fact, that factor is treated as Medium until
answered, and no use case is approved with open questions.

## 7. When to come back

Reassess before any of these changes take effect: a new type of data, a new
vendor or tool, a wider audience, a new purpose, less human review or more
automation, a change to the vendor's terms, an incident or complaint, a new
jurisdiction, or a relevant change in law.

## 8. Specific situations

- **AI meeting recorders and notetakers:** approved tools only, with notice to
  and consent of all participants. VERIFY: [citation needed] (state recording
  consent laws differ on one-party versus all-party consent; this policy
  requires all-party consent regardless).
- **Images, voice, or video depicting real people:** only with the person's
  written consent and Legal approval. VERIFY: [citation needed] (state right
  of publicity and digital replica laws).
- **Customer-facing chatbots and voice agents:** High tier at minimum, and
  people must be told at the start that they are dealing with AI. VERIFY: [citation needed] (state bot disclosure laws).

## 9. Reporting unapproved AI use

Report any unapproved AI use, yours or someone else's, at any time to the AI
enablement lead. Reporting is no-fault: discipline applies only to
concealment, not to the use being reported.

## 10. Violations

Violations are handled under the existing disciplinary policy, up to and
including termination.

## 11. Legal and regulatory references

This policy does not claim compliance with any law. Laws that may bear on AI
use (for example, the Colorado AI Act, NYC Local Law 144, state privacy,
biometric, and children's privacy laws) are listed in the rubric's
`regulatory_flags`, each marked VERIFY: [citation needed] until counsel
confirms the citation and date.
