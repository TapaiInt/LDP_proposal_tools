# Final quality gate, Review Notes and consistency checks

Load this file at the start of Stage 4 (finalisation), after all artifacts exist.

## 1. Presales Review Notes — `Presales_Review_Notes_<Client>_V<ver>.md` (internal, never merged into the client proposal)

Include: Missing Information · Assumptions Used (source: input / unanswered question / inferred; include `gaps_assumed`) · Clarifications Required · Internal Risks (estimator risks, confidence, contingency drivers) · Scope Sensitivities · Pending Approvals (including the estimate state: draft / delivery_reviewed / approved) · Technology Decisions Pending · Estimation Dependencies (inputs that would move hours, re-estimation triggers) · Commercial Dependencies (price still `XXXXX`; cost drivers needing pricing) · **Scope ↔ estimate map** (scope module → estimate module, with gaps) · **Uncovered requirement items** and **inferred tasks** (list every id) · **Ensemble spread** when several estimator runs were used (total spread, widest modules) · **Reviewer findings and dispositions** (each finding: accepted / partial / rejected, and why) · **Material deviations from the estimator output** (every place you departed from it) · **Estimator and calculator defects** (check ids and details) · `source_contradictions` and `ambiguities` from intake · "no validated feature blueprint consumed" note · **Reference-commercials comparison** (only when an input proposal carried them and `blind_estimate` was true): compare computed weeks with the input's stated timeline, and total PERT hours with the input's stated price as an implied blended rate (price ÷ PERT hours, arithmetic shown). Information only, never a pricing recommendation; flag implausible figures.

## 2. Judgment checks (you perform)

**Business:** client context accurate; problem and objectives supported by the input; outcomes follow from the problem.
**Scope:** features match validated requirements; roles match functionality; modules logically complete; integrations consistent everywhere; future scope separated; every estimated module is in scope and vice versa.
**Technology:** technology supports the functionality; classifications correct; architecture matches the stack; integrations match the architecture; security fits the data.
**Delivery:** deliverables match scope; responsibilities and dependencies visible; timeline consistent with the estimate; methodology fits the complexity.
**Commercial:** price placeholder only; milestones total 100%; no hours presented as price; no unsupported effort, SLA or payment terms.
**Governance:** assumptions identifiable; clarifications visible; no contradiction hidden; INT claims evidence-based; no unvalidated client requirement introduced; no past client named; no Review-Notes or risk content in the client proposal.

## 3. Scripted checks

Run the consistency check: in the command-line toolkit `python tools/check_consistency.py --dir <output folder> --forbid "<names of other clients>"` (add `--expose-hours` only if hours are intentionally in the proposal), on the platform the `check_consistency` tool with the same options. It writes `consistency_report.json`. Meaning of each id:

| Id | Check |
|---|---|
| X1 | Workbook task count and total match `estimation_derived.json` (recomputed from the workbook's input cells). |
| X2 | Every estimated module appears in proposal Section 8. |
| X3 | Section 18 week figures lie inside the calculator's min–max (± 1 week). |
| X4 | Section 10 contains each proposed stack item. |
| X5 | Section 17 holds every unanswered-question and assumed-gap assumption; Section 16 holds every client dependency. |
| X6 | No money amount in the proposal other than the `XXXXX` placeholder (X6b: placeholder present). |
| X7 | No internal terms or ids in the client proposal (calculator, PERT, sub-agent, `R-n`, confidence, Review Notes). |
| X8 | Milestone percentages total 100 with Advance 20 and final 15. |
| X9 | All 22 numbered sections present. |
| X10 | Registered files (raw agent outputs) unchanged since saving (command line: hashes in `case.json`; platform: `verify_artifacts`). |
| X11 | Review Notes list every uncovered requirement item and inferred task. |
| X12 | Calculator blocking checks pass, or the workbook carries the DRAFT banner. |
| X13 | No forbidden client names in the proposal or the estimate. |
| X15 | No person-hours in the client proposal (unless hours are exposed on purpose). |

Fix every FAIL you can by correcting the artifact (never by editing a raw estimator file). Report what remains. WARN items (placeholder not found, hashes not verified, openpyxl missing) go in the test report.
