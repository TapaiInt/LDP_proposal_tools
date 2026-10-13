# Proposal template, narrative rules, technology and commercial discipline

Load this file at the start of Stage 3 (proposal construction). It defines the structure and rules for the client-ready proposal.

## 1. Standard INT proposal structure (adapt to the opportunity type)

Cover Page · Version Control · 1 Executive Summary · 2 Project Objective (Primary Objective; Current vs Future State) · 3 Our Understanding of the Client's Business Context · 4 Opportunity and Key Challenges (Business, Operational, Technology, Outcomes) · 5 Why INT · 6 INT Roles & Responsibilities · 7 Proposed Solution Overview · 8 Functional Requirements / Scope of Work (User Roles, Modules, Features, User-Specific Functionality, Workflows, Business Rules, Exceptions, Integrations, Reporting, Out of scope, Future Opportunities) · 9 Design Thoughts / User Experience · 10 Proposed Technology Stack · 11 Solution Architecture · 12 Integration Approach · 13 Security, Access & Governance · 14 Implementation Methodology · 15 Deliverables · 16 Dependencies · 17 Assumptions · 18 Project Timeline · 19 Commercial Proposal · 20 Change Management · 21 Ownership of Work · 22 Terms & Conditions.

**Heading format (required, so scripts can find sections):** every section is a markdown heading that starts with its number, for example `## 8. Functional Requirements / Scope of Work`. Use `##` for sections 1–22 and `###` for subsections. Keep all 22 headings even when a section is brief; if one does not apply, write one line saying why.

**Adapt for the type:** an AI solution adds AI architecture, model strategy, orchestration, evaluation, guardrails and data governance; a mobile app adds mobile architecture, device compatibility, distribution and offline; a data platform adds ingestion, quality, governance, lineage; a marketing website adds information architecture, CMS, SEO and content responsibilities.

**Cover page:** title, date, "Presented by INT.", "We Make It Possible", `[Sales contact — to be inserted]` unless supplied. **Version Control** table starts at V1.0 and records the reason for each new version (for example "Scope revised after clarification").

**INT credentials (Section 5) and past work:** only from the provided input; otherwise write `[INT credentials — insert from approved collateral]`. Never claim unsupported experience, certifications or case studies.

## 2. Narrative

One connected story: Client Context → Business Problem → Objective → Opportunity → Solution → Scope → Technology & Architecture → Implementation → Dependencies & Assumptions → Timeline → Commercials. Each section reinforces the previous one. No architecture capability that is absent from scope; no integration in the technology section that is absent from scope; no timeline inconsistent with the estimate.

Write for four readers: the **business stakeholder** (why, outcomes), the **technology stakeholder** (architecture, integrations, security, data, deployment, scalability), the **procurement stakeholder** (scope, deliverables, responsibilities, timeline, assumptions, change management) and the **delivery team** (technical scope, dependencies, exclusions, boundaries).

## 3. Technology section

Classify every item as **Client-Mandated**, **Existing**, **INT Recommended** or **To Be Confirmed**, and never present an INT recommendation as a client requirement. Explain the role of each technology in the architecture; do not dump names (not "React + Node.js + PostgreSQL + AWS" but what each one does here). Cover, where relevant: frontend, backend, mobile, database, cloud, hosting, APIs, integration layer, authentication, authorization, security, data architecture, AI/ML/GenAI, analytics, monitoring, logging, DevOps, CI/CD, scalability, availability, backup and recovery.

## 4. Classification of content

Every material input is **Confirmed**, **Proposed**, **Assumption**, **Dependency**, **Clarification Required** or **Future Opportunity**. The client-facing proposal presents Confirmed and clearly framed Proposed content; assumptions (Section 17) and dependencies (Section 16) are separate; Future Opportunities are never committed scope. Never invent requirements, users, integrations, business rules, KPIs, client technology or objectives.

## 5. Timeline and commercials

- **Section 18:** use the calculator's `timeline.weeks_min / weeks_likely / weeks_max` and the phase list from `estimation_derived.json`. Label it **indicative**. If the case file's `estimate_state` is not `approved`, add "subject to estimation approval". Show client-dependency lead times. If the client stated a deadline that conflicts, do not trim the plan; flag it in the Review Notes. If no estimate exists, keep a placeholder.
- **Section 19:** price is a placeholder, `INR XXXXX + applicable taxes`. Never invent pricing, person-days, payment terms, SLAs or contractual commitments. Hours are not prices and do not appear in the client proposal unless `expose_hours_in_proposal` is true.
- Payment milestones use this template:

| Milestone | Payment % |
|---|---|
| Advance — Project Initiation & Mobilization | 20% |
| Milestone 1 — [adapt to project scope] | 20% |
| Milestone 2 — [adapt to project scope] | 25% |
| Milestone 3 — [adapt to project scope] | 20% |
| Milestone 4 — Final Delivery, Go-Live / Handover & Sign-off | 15% |
| **Total** | **100%** |

Keep Advance at 20% and Milestone 4 at 15%. Name Milestones 1–3 after the real phases of this project (requirements, design, development, integration, migration, validation and so on); do not force application-development wording where it does not apply.

## 6. Where estimation outputs go

| Estimation output | Client proposal | Workbook | Review Notes |
|---|---|---|---|
| `requirement_items`, modules, tasks | Informs Section 8 (consistent module names) | Estimation Breakdown, Requirement Coverage | Scope ↔ estimate map; uncovered items; inferred tasks |
| Hours (task O/M/P from the estimator; PERT, totals, overheads, P80 from the calculator) | Not shown unless `expose_hours_in_proposal` | Yes | Totals, ranges, spread |
| `tech_stack` | Section 10 with the role of each technology | Tech Stack | Decisions pending |
| Calculator `timeline`, `team`, `phases` with the estimator's `phases` and `team_plan` | Section 18 (indicative) and Section 6 team shape without hours | Team & Timeline | Assumptions behind it |
| `assumptions`, `gaps_assumed` | Section 17 in client-safe wording | Assumptions | Source tags |
| `exclusions` | Section 8 "Out of scope" and Section 22 | Assumptions (Out of Scope) | — |
| `client_dependencies` | Section 16 | Assumptions (Dependencies) | — |
| `risks`, `confidence`, `re_estimation_triggers` | **Never** | Risks | Internal Risks, Scope Sensitivities |
| `cost_drivers` | Sections 16/17 as "who provides or bears" statements, no prices | Cost Drivers | Commercial dependencies |
| `maintenance_recommendation` | Section 19 or 22 as support/warranty options, no prices | Maintenance | — |
| `optional_addons` | Section 8 "Future Opportunities" | — | — |
| Reviewer findings | **Never** | — | Reviewer findings and dispositions |
