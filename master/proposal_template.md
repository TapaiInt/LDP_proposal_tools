Prompt version: 1.5 (2026-10-29) · master/proposal_template.md

# Proposal template, narrative rules, technology and commercial discipline

Load this file at the start of Stage 3 (proposal construction). It defines the structure and rules for the client-ready proposal.

## 1. Standard INT proposal structure (adapt to the opportunity type)

Cover Page · Version Control · 1 Executive Summary · 2 Project Objective (Primary Objective; Platform Goals; Business Objectives) · 3 Our Understanding of the Client's Business Context · 4 Opportunity and Key Challenges (Business, Operational, Technology, Outcomes; Current State Assessment) · 5 Why INT · 6 INT Roles & Responsibilities · 7 Proposed Solution Overview · 8 Functional Requirements / Scope of Work (User Types, Roles and Responsibilities, Modules, Features, User-Specific Functionality, Workflows, Business Rules, Exceptions, Integrations, Reporting, Out of scope, Future Opportunities) · 9 Design Thoughts / User Experience (User Journeys) · 10 Proposed Technology Stack · 11 Solution Architecture · 12 Integration Approach · 13 Security, Access & Governance (Role-Based Access Control) · 14 Implementation Methodology · 15 Deliverables · 16 Dependencies · 17 Assumptions · 18 Project Timeline · 19 Commercial Proposal · 20 Change Management · 21 Ownership of Work · 22 Terms & Conditions.

**Heading format (required, so scripts can find sections):** every section is a markdown heading that starts with its number, for example `## 8. Functional Requirements / Scope of Work`. Use `##` for sections 1–22 and `###` for subsections. Keep all 22 headings even when a section is brief; if one does not apply, write one line saying why.

**Adapt for the type:** an AI solution adds AI architecture, model strategy, orchestration, evaluation, guardrails and data governance; a mobile app adds mobile architecture, device compatibility, distribution and offline; a data platform adds ingestion, quality, governance, lineage; a marketing website adds information architecture, CMS, SEO and content responsibilities.

**Cover page.** Build the best cover from the lead data: the client's company, contact name and role, city, today's date and the version, filling what is known and leaving out what is not (never invent). Write it in exactly this layout (the Word export reads it): the title, the subtitle, the lines, then `---` on its own line to end the cover. Use `[Client Organisation]` when the company name is unknown, and leave out the `Prepared for` line when no contact is known.

```
# <Proposal title>

**Proposal for <Client organisation>, <City>**

Prepared for: <contact name, role>
Date: <d Month yyyy>
Version: V1.0

Presented by INT.
*We Make It Possible*

Sales contact: [Sales contact — to be inserted]

---
```

**Version Control** (`## Version Control`, a table) starts at V1.0 and records the reason for each new version (for example "Scope revised after clarification"). Do not add an "End of proposal" line.

**INT credentials (Section 5 "Why INT") and past work.** Section 5 states three things about INT, taken from `why_int_facts.md` (the master saves it after reading `https://intglobal.com/` with web crawl or web search): **years** (since which year, or the number of years the site states), **domains** (the industries INT serves) and **services** INT offers. Use the site's own wording; add nothing the pages do not state. **Do not mention Machine Learning (or ML)** in Section 5: leave it out of the services and domains even when the site lists it, and make no machine-learning capability claim there. A fact that could not be fetched stays as `[INT credentials — insert from approved collateral]`. Past work, case studies, certifications, awards and client names come only from the provided input; never claim unsupported experience.

Section 5 length by format (§7): Short = one short paragraph and three bullets (years, domains, services); Marketing and Detailed = a fuller narrative that ties INT's domains and services to this client's context, still limited to those three facts.

## 2. Narrative

One connected story: Client Context → Business Problem → Objective → Opportunity → Solution → Scope → Technology & Architecture → Implementation → Dependencies & Assumptions → Timeline → Commercials. Each section reinforces the previous one. No architecture capability that is absent from scope; no integration in the technology section that is absent from scope; no timeline inconsistent with the estimate.

Write for four readers: the **business stakeholder** (why, outcomes), the **technology stakeholder** (architecture, integrations, security, data, deployment, scalability), the **procurement stakeholder** (scope, deliverables, responsibilities, timeline, assumptions, change management) and the **delivery team** (technical scope, dependencies, exclusions, boundaries).

## 3. Technology section

Classify every item as **Client-Mandated**, **Existing**, **INT Recommended** or **To Be Confirmed**, and never present an INT recommendation as a client requirement. Explain the role of each technology in the architecture; do not dump names (not "React + Node.js + PostgreSQL + AWS" but what each one does here). Cover, where relevant: frontend, backend, mobile, database, cloud, hosting, APIs, integration layer, authentication, authorization, security, data architecture, AI/ML/GenAI, analytics, monitoring, logging, DevOps, CI/CD, scalability, availability, backup and recovery.

## 4. Classification of content

Every material input is **Confirmed**, **Proposed**, **Assumption**, **Dependency**, **Clarification Required** or **Future Opportunity**. The client-facing proposal presents Confirmed and clearly framed Proposed content; assumptions (Section 17) and dependencies (Section 16) are separate; Future Opportunities are never committed scope. Never invent requirements, users, integrations, business rules, KPIs, client technology or objectives.

## 5. Timeline and commercials

- **Section 18:** use the calculator's `timeline.weeks_min / weeks_likely / weeks_max` and the phase list from `estimation_derived.json`. Label it **indicative**. If the case file's `estimate_state` is not `approved`, add "subject to estimation approval". Show client-dependency lead times. If the client stated a deadline that conflicts, do not trim the plan; flag it in the Review Notes. If no estimate exists, keep a placeholder in client-safe words, for example "Indicative timeline: to be confirmed after the technical assessment and estimation approval." Never explain the gap with internal process (agents, tools, calculator, "this run", "could not be produced"); the reason belongs in the Review Notes only.
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

## 7. Proposal format: length and depth by profile

The master asks two questions in discovery and stores the answers as `proposal_profile`: **Is this an enterprise client?** and **which format**. The options depend on the first answer.

| Enterprise client | Format | Pages | What changes |
|---|---|---|---|
| Yes | Short Brochure | 15–20 | Crisp and visual: short paragraphs, bullets and tables, one idea per block. Sections 9–15 are a half page each. |
| Yes | Marketing | 15–25 | Persuasive, outcome-led narrative: fuller Sections 1–5 (context, challenges, Why INT), tighter technical sections. |
| Yes | Detailed | 30–45 | Full depth in every section. Section 9 (Design Thoughts / User Experience) and Section 11 (Solution Architecture) set out the design approach we will follow to design the application: design principles, user journeys, key screens or components, design system, review and sign-off steps. Sections 12–15 in full (integration approach, security and governance, methodology, deliverables). |
| No | Short | 15–20 | As Short Brochure. |
| No | Marketing | 30–50 | As Marketing, with a fuller narrative and more depth in Sections 7–9 and 14. |

Rules for every format:
- All 22 section headings stay (scripts check them). The format changes depth, not structure. A section that does not apply still gets its one line.
- Aim at about 350 words per page, counting tables, the cover and Version Control. Page ranges are targets, not promises: the Word export does not count pages. Never pad to reach a range and never cut required scope to fit one; state the format and the estimated page count in the Review Notes.
- Never lengthen with invented content: no filler, no repeated text, no unsupported claims (see Section 4 of this module).
- A long proposal (Marketing, Detailed) does not fit in one tool call. Save it in parts: the first call creates `Proposal_<Client>_<ShortTitle>_V<ver>.md` with the cover and sections 1–5 (`overwrite: true`), and each next call adds the next group of sections with `append: true`, in order (for example 6–11, 12–17, 18–22). Read the result of every call; if a part failed, repeat that part only, never start over. After the last part check the saved file's `total_chars` with `get_artifact` (`max_chars` 1) before `check_consistency`.

## 8. Required content elements (the scripted checks X16–X21 read these exact headings, tables and pictures)

**8.1 Executive Summary (Section 1): 3 to 4 paragraphs of prose.** No bullets, tables or numbers that are not in the sources. Four paragraphs normally; three when little is known (Short formats).
1. The client's situation and the problem, from discovery.
2. What INT proposes, in plain words: the platform, who uses it, and the system of record where there is one.
3. How it works: the main capabilities, the integrations and the guiding principles (what stays as it is).
4. How INT will deliver it and what the client gains, in client-safe language (no hours, prices, agents or tools).

**8.2 Project Objective (Section 2):** a short `**Primary objective**` paragraph, then two subsections:
- `### Platform Goals`: 3 to 7 bullets written `- **Label:** one sentence`, each a capability the platform will provide (what the system does).
- `### Business Objectives`: 3 to 7 bullets in the same form, each an outcome for the client (what the client gains). Each objective must be reachable through at least one platform goal and one module in Section 8. Do not copy the goals into the objectives.

**8.3 Current State Assessment (Section 4):** a `### Current State Assessment` subsection with one or two lead sentences and this table, 4 to 10 rows (4 to 6 in Short formats):

| Current-state finding | Source | Proposed solution | Scope reference |
|---|---|---|---|

- **Source** is exactly `Client-stated` (from the lead or a discovery answer), `Observed` (read from a document or a public page in this run, with its URL or file named in the Review Notes) or `Assumption` (also listed in Section 17).
- **Scope reference** is the name of the Section 8 module or subsection that delivers the solution. Every key challenge named in Section 4 has a row; every row points at real scope.
- Never invent a finding. With no known current state, write one row `Current state to be validated in discovery | Assumption | ... | ...`. For a client with an existing public website and web tools available, crawl it and add `Observed` rows (page titles and metadata, navigation and structure, content gaps visible in the HTML); make no claim that needs a measuring tool (Core Web Vitals, rankings).

**8.4 User Types, Roles and Responsibilities (Section 8):** a `### User Types, Roles and Responsibilities` subsection. With more than one kind of user, one table per kind (for example Enterprise users, Contractor users, Employee users), each `| User role | Responsibilities |`. Roles come from the sources and discovery; a role INT adds is written `<Role> (Proposed)`. End with: the final role-to-permission mapping is validated during requirement discovery.

**8.5 Role-Based Access Control (Section 13):** a `### Role-Based Access Control` subsection:
- One sentence: these are proposed permissions, to be validated in discovery.
- A matrix `| Role | <Module 1> | <Module 2> | ... |` with one row for **every** role of 8.4 and the Section 8 modules as columns (group modules to at most 8 columns). Cells use `V` view, `C` create, `E` edit, `A` approve, `X` export, `M` manage and configure, `–` none. Put the legend under the table.
- Bullets for: data scope (own records, own organisation, all), authentication (SSO or MFA as stated by the client, otherwise "to be confirmed"), proxy or delegation if in scope, and audit logging.

**8.6 User journeys (Section 9):** one `### <Journey name>` subsection per journey, in this order: a one-sentence intro; the picture on its own line `![Caption](journey_<name>.png)`; the step table under it. Create the picture first with `render_diagram` (`kind: journey`) and paste the `step_table` it returns, unchanged.
- The journey is drawn as **swimlanes**: one lane per role, so the second field of each step is the **role** (from 8.4, exactly as written there) and the third is the action in a few words ("Reviews the request", not "Review"). At most 6 roles per journey. An end step may carry an outcome instead of a role ("Closed", "Approved"); it is drawn in the lane of the step before it.
- Steps use only modules from Section 8. 4 to 10 steps, at most one loop back (rework, rejection). A step with two or more exits is a decision: label every exit (`S4:Approved, S2:Returned`). A flow longer than 12 steps becomes two journeys.
- How many journeys: Short and Short Brochure = 1 end-to-end flow; Marketing = one per key role, at most 3; Detailed = one per role, at most 5.
- Never leave a journey as a picture alone: the table is the text version for screen readers and the checks.

**8.7 Solution architecture diagram (Section 11), every format:** right after the first paragraph of Section 11, the picture on its own line `![Solution architecture](architecture.png)`, created with `render_diagram` (`kind: architecture`). Then the text explains each layer.
- Layers, top to bottom, using only those that apply: `Users & channels` (the user types of 8.4 and their channels: web, mobile, admin), `Presentation` (front end, API gateway), `Application services` (one box per Section 8 module or group of modules), `Data` (databases, document or file storage, search, analytics), `Platform & security` (hosting, identity and SSO, RBAC, monitoring, backup). An AI solution adds an `AI services` layer (models, orchestration, guardrails) above Data.
- `integrations`: only the systems in Section 12, each with what flows ("Employee master, read"); `integration_note` names the integration style in one line.
- Each box: `name` of at most 4 words, `detail` of a few words, and `tag` = the Section 10 classification (`Client-Mandated`, `Existing`, `INT Recommended`, `To Be Confirmed`); leave `tag` empty for a logical component with no technology choice. 3 to 6 boxes per layer.
- Nothing in the picture that the text does not describe, and no product name that Section 10 does not classify (check X21).

**8.8 Integration sequence (Section 12), Marketing and Detailed only, when there are two or more integrations:** one picture `![Integration flow](integration_sequence.png)` from `render_diagram` (`kind: mermaid`) with a `sequenceDiagram`: the platform and each Section 12 system as participants, one arrow per data exchange, in business words ("Separation event", "Pending dues"). No field lists, no endpoints. If Mermaid reports a parse error, fix the line it names once; otherwise leave the picture out (the Section 12 table still describes the flows).

## Version history

- v1.5 (2026-10-29): Diagrams via render_diagram (headless browser): swimlane journeys, required architecture diagram in Section 11, optional Mermaid integration sequence; check X21
- v1.4 (2026-10-28): Section 8 required content elements with exact headings and tables (summary, goals/objectives, current-state mapping table, roles, RBAC matrix, journeys with diagrams)
- v1.3 (2026-10-28): Format profiles with page ranges (section 7); Why INT sourced from intglobal.com (years, domains, services; no Machine Learning); save long proposals in parts with append
- v1.2 (2026-10-22): Cover built from the lead data (fill what is known, never invent)
- v1.1 (2026-10-22): Exact cover layout for the Word export; client-safe placeholder wording when no estimate exists
- v1.0 (2026-10-12): Initial 22-section template, narrative, technology and commercial rules
