# CMP-UC-002 — Automated Invoice and Outlay Validation, Matching and Payment
## Build Specification for an End-to-End Agentic Application (Neuro SAN + Custom Front End)

**Document type:** Build handover specification for an autonomous coding agent (Codex / Claude Code)
**Source use case:** `[CMP-UC-002] Automated Invoice and Outlay Validation, Matching and Payment`
**Orchestration layer:** Neuro SAN (Cognizant AI Lab, HOCON-defined multi-agent networks)
**LLM provider:** Azure OpenAI (model-agnostic; deployment supplied via environment variables)
**Target audience for the running app:** UK insurance claims finance and operations teams

---

## 0. How to use this document

This specification is self-contained. A coding agent should be able to build the full application from this file alone, without access to the original use case document.

Build order recommendation:

1. Data model and synthetic dataset generator
2. Neuro SAN agent network (HOCON) and coded tools
3. FastAPI orchestration and API layer
4. React front end (left navigation, fluid animation, drilldowns, graphics)
5. Evaluation harness and test suite

Everything in Sections 2–4 is derived directly from the source use case and is **mandatory scope**. Sections 5 onwards define how it is to be built.

---

## 1. Executive summary

Invoices and outlays are a major source of cost, operational effort and leakage risk within Claims. Inconsistent invoice formats and manual validation drive delays, rework and variable application of rates and entitlements.

This application delivers an end-to-end automated **invoice-to-pay** capability that extracts, validates and processes supplier invoices at scale. Compliant invoices flow straight through to payment; only genuine exceptions are routed to handlers. The result is reduced cycle time, reduced administrative effort and reduced cost leakage.

The capability must be **tightly governed with audit controls**. Auditability is not an optional feature of this build — it is a first-class requirement that constrains every agent, every API and every UI action.

---

## 2. Current state (the problem the application replaces)

This section exists so the coding agent understands what "before" looks like, and so the UI can contrast it in demo narrative screens.

### 2.1 Invoice intake and handling today

Invoices and outlays are received from multiple external parties:

- Repairers
- Hire suppliers
- Storage and recovery providers

Invoices arrive in **inconsistent formats** and through **multiple channels** — email, supplier portals, and attachments.

### 2.2 Manual processing steps performed today

Claims colleagues must manually:

- Open and read invoices
- Redact sensitive data where required
- Re-rate and validate charges against:
  - Agreed supplier rates
  - Policy entitlements and authorisations
- Contact suppliers to resolve discrepancies
- Generate or request supporting documentation
- Key invoice data into ICE and/or finance systems
- Send updates to insurers and customers
- Track outstanding items and payment status manually

### 2.3 Key pain points

**Inefficiency and delay**
- High volumes of manual handling
- Long invoice-to-payment cycle times

**Leakage and inconsistency**
- Variable application of rates and tolerances
- Increased risk of overpayment or missed discrepancies

**Administrative burden**
- Significant handler time spent on chasing, reconciliation and data entry

---

## 3. To-be state — functional scope (mandatory)

A fully automated invoice-to-pay workflow, with human involvement limited to genuine exceptions. Each sub-section below is a mandatory capability of the application.

### 3.1 Automated invoice capture and classification

- Invoices are automatically captured from agreed channels (email, portal upload, attachment drop).
- Each invoice is **classified by supplier and document type**.
- Each invoice is **matched to the correct claim in ICE** using:
  - Claim references
  - Supplier references
  - Intelligent matching logic (fuzzy / probabilistic matching where direct references are absent or malformed)

### 3.2 Structured data extraction

Invoice content is extracted and structured into standard fields, including at minimum:

- Supplier details
- Service dates and service types
- Line-level charges and amounts
- VAT
- Hire days
- Storage days
- Recovery fees

The extraction output must be a stable, versioned JSON schema (see Section 8.2) consumed by all downstream agents.

### 3.3 Automated redaction and data protection

- Auto-redaction is applied based on **predefined GDPR/PII rules**.
- A **full audit trail** records:
  - What was redacted
  - Why it was redacted

Redaction rules must be configuration-driven (editable in the UI under Settings), not hard-coded.

### 3.4 Re-rating and validation

A validation engine checks charges against:

- Contracted rate cards
- Policy coverage and entitlements
- Prior authorisations
- Defined tolerances

Outcomes:

| Condition | Outcome |
|---|---|
| Within tolerance | Auto-approve |
| Outside tolerance | Auto-generate a dispute query **highlighting the specific line items in question** |

The dispute query must identify line items individually — a whole-invoice rejection is not acceptable behaviour.

### 3.5 Automated approval and payment

Approved invoices are automatically:

- Passed into the payment workflow via **integration or RPA**, as appropriate
- Marked as **approved and paid in ICE through write-back**

The application must model both integration and RPA paths, with the path selectable per supplier in configuration.

### 3.6 Automated communications and status updates

Status-based notifications are triggered automatically to:

- Suppliers
- Insurers
- Customers (where relevant)

Supported statuses (these are the canonical status values for the data model and the UI):

- `Received`
- `Queried`
- `Approved`
- `Paid`
- `Awaiting information`

### 3.7 Exception-only handling

Only invoices that cannot be confidently processed are routed to handlers. The exception taxonomy is fixed and must be implemented exactly:

1. Missing or invalid identifiers
2. Failed claim matching
3. Disputed or out-of-tolerance charges
4. High-value invoices
5. Policy or coverage ambiguity

Every exception record must include:

- A **clear explanation of the issue**
- A **pre-filled "what to do next" action**

The pre-filled action is a structured object (action type, target, draft content) that the handler can execute in one click, not merely free text.

### 3.8 Key improvements the build must demonstrably deliver

- Significant reduction in manual invoice processing effort
- Faster invoice-to-payment cycle times
- More consistent application of rates, tolerances and policy rules
- Reduced cost leakage and overpayment risk
- Improved supplier experience through quicker, clearer responses
- Strong auditability and compliance controls

Each of these must map to a measurable metric surfaced on the analytics dashboard (Section 7.6).

---

## 4. High-level requirements (traceable)

The source use case notes these requirements are **indicative and directional**, not the output of formal requirements gathering. They are to be treated as directional inputs and refined during discovery. They are reproduced here in full and given traceable IDs for the build.

| ID | Requirement | Success metric |
|---|---|---|
| UC-002-HLR-001 | As a Claims Finance Team, I need invoices validated automatically so that incorrect charges are prevented | Not defined in source — to be confirmed in discovery. Build instrumentation to measure: % invoices auto-validated, value of incorrect charges prevented |
| UC-002-HLR-002 | As a Repair Partner, I need faster payment so that cashflow is improved | Not defined in source — instrument: median and 90th percentile invoice-to-payment cycle time |
| UC-002-HLR-003 | As an AI System, I need to match invoices to claim records so that exceptions are flagged | Not defined in source — instrument: match rate, match confidence distribution, exception rate by reason |
| UC-002-HLR-004 | As a Claims Manager, I need visibility of invoice exceptions and trends | Not defined in source — instrument: exception dashboard coverage, trend views by reason, supplier and period |

**Build note:** success metrics are blank in the source. The application must therefore *capture the underlying telemetry* so that targets can be set later without rework. Do not invent contractual targets in the UI; present measured values and allow thresholds to be configured.

---

## 5. Benefit case

- Expected benefit of **up to 3 FTE**, based on a volume of **2,000 claims per month**, with volume expected to increase **10% year on year**.

The application must include a **benefits tracking view** that models realised FTE saving against this baseline, using measured straight-through-processing rate and measured handling time saved. Volume growth of 10% YoY must be a configurable parameter in the model.

---

## 6. RAID items and how the build responds

RAID entries in the source are indicative, not exhaustively validated, and will be refined as delivery progresses. Each one carries a design obligation for this build.

| RAID type | Description | Build response (design obligation) |
|---|---|---|
| Risk | Incorrect OCR or data extraction | Confidence scoring per extracted field; low-confidence fields highlighted in the document viewer; mandatory human confirmation below a configurable confidence threshold; extraction accuracy tracked in the evaluation harness |
| Risk | Supplier disputes if decisions are opaque | Every decision carries structured, line-level reasoning and cites the rate card clause, policy entitlement or authorisation applied. No black-box outputs anywhere in the UI or in supplier communications |
| Assumption | Standard invoice formats exist for major suppliers | Supplier-specific extraction templates for major suppliers, with a generic fallback extractor. Template coverage reported in the admin UI |
| Issue | Long tail of non-standard suppliers | Generic extractor path plus a "learn from correction" loop: handler corrections are captured as labelled data and surfaced as candidate template improvements |
| Dependency | Supplier rate cards | Rate card registry with effective dating and version history; staleness indicator when a rate card is past its review date; validation blocked or flagged when no current rate card exists |
| Dependency | Finance and payment systems | Payment integration abstracted behind an adapter interface with two implementations: direct integration and RPA. A mock adapter must be provided for the demo build |

---

## 7. Data needs, sources and quality considerations

### 7.1 Data needs

- Supplier invoices (PDF, email)
- Agreed rate cards
- Claim financials

### 7.2 Quality considerations that must be handled explicitly

- **Invoice format variability** — handled via supplier templates plus generic fallback, with per-field confidence
- **Timeliness of rate updates** — handled via effective-dated rate cards, staleness warnings, and an alert when an invoice is validated against a rate card older than a configurable threshold

---

## 8. UK-specific constraints (mandatory, non-negotiable)

- **Auditability and SOX-style controls**
- **Payment governance**

Concretely, this means:

- Immutable, append-only audit log for every state change, agent decision, human override and payment action
- Segregation of duties: the identity that raises an approval cannot be the identity that releases the payment, enforced in the API layer
- Full replay capability: for any invoice, reconstruct the exact sequence of agent inputs, outputs, model versions, prompt versions, rate card versions and policy versions used
- Payment release gated behind explicit authorisation controls with value-based thresholds
- GDPR/PII redaction audit trail as described in Section 3.3
- All monetary values in GBP; VAT handled as a first-class field

---

## 9. Personas

### 9.1 Claims Finance Analyst (primary user)
Reviews exception invoices, resolves disputes, approves payments.
Needs: single prioritised work queue, unambiguous exception reasons, one-click pre-filled actions, line-level evidence.

### 9.2 Claims Operations Manager
Monitors throughput, leakage prevented, exception trends, team workload.
Needs: dashboards, trend analysis, drilldown from any metric to the underlying invoices.

### 9.3 Supplier Relationship Manager
Manages supplier disputes and payment performance.
Needs: supplier scorecards, dispute rates, average settlement time, rate card compliance by supplier.

### 9.4 Claims Finance Team Lead / Approver
Holds payment authorisation. Enforces segregation of duties.
Needs: authorisation queue, value thresholds, audit-ready approval record.

### 9.5 Compliance / Audit Officer
Needs: immutable audit trail, redaction log, decision replay, exportable evidence packs.

### 9.6 Supplier (external, read-only in MVP)
Needs: invoice status visibility, clear query explanations, expected payment date.

---

## 10. User journeys

### 10.1 Journey A — Straight-through processing (target path)

```
Invoice captured from channel (email / portal / attachment)
        ↓
Classified by supplier and document type
        ↓
Matched to claim in ICE (claim ref, supplier ref, intelligent matching)
        ↓
Structured extraction (supplier, dates, line charges, VAT, hire/storage/recovery)
        ↓
GDPR/PII auto-redaction + redaction audit entry
        ↓
Re-rating and validation (rate card, coverage, entitlements, prior authorisations, tolerances)
        ↓
Within tolerance → auto-approve
        ↓
Payment workflow (integration or RPA) + ICE write-back (approved & paid)
        ↓
Status notifications to supplier / insurer / customer
        ↓
Status: Paid
```

No human intervention at any step.

### 10.2 Journey B — Out-of-tolerance dispute

```
... validation ...
        ↓
Outside tolerance detected on specific line items
        ↓
Auto-generated dispute query highlighting those specific line items
        ↓
Status: Queried  → supplier notified
        ↓
Supplier response received
        ↓
Re-validation
        ↓
Auto-approve OR route to handler
```

### 10.3 Journey C — Exception handling

```
Invoice cannot be confidently processed
        ↓
Exception raised with:
   - reason (one of the five taxonomy values)
   - clear explanation of the issue
   - pre-filled "what to do next" action
        ↓
Routed to handler work queue, prioritised by value and age
        ↓
Handler reviews document viewer + agent reasoning + evidence
        ↓
Handler executes pre-filled action or overrides with reason
        ↓
Re-validation
        ↓
Approval → payment → notification
```

### 10.4 Journey D — Manager oversight

```
Dashboard
   ↓ drill into any KPI
Filtered invoice list
   ↓ drill into an invoice
Invoice drilldown with agent trace
   ↓ drill into a decision
Evidence: rate card clause, policy entitlement, authorisation, tolerance applied
```

### 10.5 Journey E — Audit replay

```
Select invoice → Audit tab
   ↓
Full chronological event log
   ↓
Select any agent decision
   ↓
Replay view: inputs, prompt version, model version, rate card version, policy version, output, confidence
   ↓
Export evidence pack (PDF + JSON)
```

---

## 11. Neuro SAN agent network

### 11.1 Network topology

```
                        Invoice Orchestrator (front man)
                                    |
   ┌──────────┬──────────┬──────────┼──────────┬──────────┬──────────┐
   │          │          │          │          │          │          │
Intake &   Extraction  Redaction  Claim     Validation  Settlement  Comms &
Classify    Agent       Agent     Matching   Cluster     Agent      Payment
 Agent                             Agent        │                    Agent
                                                │
                                 ┌──────────────┼──────────────┐
                                 │              │              │
                            Rate Card     Entitlement &   Tolerance &
                           Validation     Authorisation    Anomaly
                             Agent          Agent           Agent
                                                                │
                                                        Exception Router
                                                             Agent
```

All agents are defined declaratively in HOCON. Deterministic logic (rate arithmetic, tolerance maths, VAT checks, duplicate detection, payment adapter calls, ICE write-back) must be implemented as **coded tools**, not left to the LLM. The LLM is used for classification, extraction reconciliation, ambiguity resolution, explanation generation and communication drafting.

### 11.2 Agent definitions

#### Agent 1 — Invoice Orchestrator (front man)
- Receives the invoice payload and routes through the pipeline
- Maintains the canonical invoice state object
- Decides straight-through vs exception routing
- Emits the agent trace consumed by the UI

#### Agent 2 — Intake & Classification Agent
- Determines channel of origin (email, portal, attachment)
- Classifies document type (repair invoice, hire invoice, storage invoice, recovery invoice, credit note, statement, supporting document)
- Identifies the supplier
- Flags missing or invalid identifiers → exception reason 1

#### Agent 3 — Extraction Agent
- Applies supplier-specific template where available; generic extractor otherwise
- Produces the structured invoice schema (Section 12.2)
- Emits per-field confidence
- Flags low-confidence fields for human confirmation

**Coded tools:** OCR adapter, template registry lookup, schema validator.

#### Agent 4 — Redaction Agent
- Applies predefined GDPR/PII rules
- Produces redacted document rendition
- Writes redaction audit entries: what was redacted, why it was redacted, rule ID, timestamp

**Coded tool:** deterministic PII rule engine (regex + named entity rules), rule set versioned.

#### Agent 5 — Claim Matching Agent
- Matches invoice to claim in ICE using claim reference, supplier reference, and intelligent matching logic
- Returns matched claim, match method and match confidence
- Failure → exception reason 2 (failed claim matching)

**Coded tools:** exact reference lookup, fuzzy matcher, candidate ranker.

#### Agent 6 — Rate Card Validation Agent
- Re-rates every line item against the contracted rate card effective on the service date
- Validates hire days, storage days, recovery fees, repair rates, VAT
- Returns line-level variance in GBP and percent
- Flags stale rate card usage

**Coded tools:** rate card registry (effective-dated), re-rating calculator, VAT calculator.

#### Agent 7 — Entitlement & Authorisation Agent
- Validates against policy coverage and entitlements
- Validates prior authorisations exist and cover the charged scope
- Ambiguity → exception reason 5 (policy or coverage ambiguity)

#### Agent 8 — Tolerance & Anomaly Agent
- Applies defined tolerances to each line-level variance
- Within tolerance → recommend auto-approve
- Outside tolerance → mark the specific offending line items
- Detects duplicate invoices, abnormal charging patterns, split invoicing, value outliers
- High-value invoice → exception reason 4

**Coded tools:** tolerance rule engine, duplicate detector, statistical outlier detector.

#### Agent 9 — Settlement & Dispute Agent
- Produces one of: `AUTO_APPROVE`, `QUERY`, `ROUTE_TO_HANDLER`
- For `QUERY`: generates the dispute query highlighting the specific line items in question, with the rate/entitlement basis for each
- Produces structured reasoning and evidence citations for every decision

#### Agent 10 — Exception Router Agent
- Assigns exception reason from the fixed five-value taxonomy
- Writes the clear explanation of the issue
- Generates the pre-filled "what to do next" action as a structured, executable object
- Prioritises the queue by value and age

#### Agent 11 — Communications Agent
- Generates status-based notifications to suppliers, insurers and customers (where relevant)
- Status set: Received, Queried, Approved, Paid, Awaiting information
- Tone and content templated per audience; every outbound message logged

#### Agent 12 — Payment & Write-back Agent
- Routes approved invoices into the payment workflow via integration or RPA, per supplier configuration
- Performs ICE write-back marking the invoice approved and paid
- Enforces segregation of duties and value-threshold authorisation before release

**Coded tools:** payment adapter interface (`IntegrationAdapter`, `RpaAdapter`, `MockAdapter`), ICE write-back adapter.

### 11.3 Neuro SAN implementation requirements

- One HOCON file per agent network, stored under `registries/` and referenced in `manifest.hocon`
- Coded tools under `coded_tools/invoice_to_pay/`
- Every agent must return structured JSON conforming to a declared schema; no free-text-only responses between agents
- Sly-data must be used for any PII passing between agents so sensitive values are not exposed to the model
- Agent trace must be persisted per invoice for the UI trace panel and audit replay
- LLM configuration is environment-driven (Azure OpenAI endpoint, key, API version, deployment name) — never hard-coded in HOCON

---

## 12. Technical architecture

### 12.1 Stack

```
React 18 + TypeScript + Tailwind + shadcn/ui + Framer Motion + Recharts
        ↓  REST + WebSocket (live status streaming)
FastAPI (Python 3.11+)
        ↓
Neuro SAN HTTP service (agent networks + coded tools)
        ↓
Azure OpenAI (deployment via env vars)
        ↓
PostgreSQL (transactional)  |  Blob/local object store (documents)  |  Vector store (policy & rate card retrieval)
        ↓
Adapters: ICE (claims), Finance/Payment (integration + RPA), Email/Portal intake
```

All external systems (ICE, finance, payment, email, supplier portal) must be implemented as **mock adapters** behind interfaces so the demo runs fully offline.

### 12.2 Core data model

**`supplier`** — id, name, type (repairer | hire | storage | recovery), contact, payment_path (integration | rpa), template_id, active

**`rate_card`** — id, supplier_id, version, effective_from, effective_to, review_due_date, status, lines[]

**`rate_card_line`** — id, rate_card_id, service_type, unit (per_day | per_item | per_hour | fixed), rate_gbp, max_units, conditions

**`claim`** — id, ice_claim_ref, policy_id, customer_id, incident_date, status, reserve_gbp, paid_to_date_gbp

**`policy`** — id, cover_type, coverage_limits, entitlements[], excess_gbp, effective_from, effective_to

**`authorisation`** — id, claim_id, supplier_id, service_type, authorised_units, authorised_value_gbp, authorised_by, authorised_at

**`invoice`** — id, invoice_number, supplier_id, claim_id (nullable), channel, received_at, document_uri, redacted_document_uri, status (Received | Queried | Approved | Paid | Awaiting information), gross_gbp, net_gbp, vat_gbp, match_confidence, match_method, straight_through (bool)

**`invoice_line`** — id, invoice_id, line_no, service_type, service_date_from, service_date_to, units (hire_days | storage_days | qty), unit_rate_gbp, amount_gbp, vat_gbp, extracted_confidence, rate_card_line_id, expected_amount_gbp, variance_gbp, variance_pct, tolerance_outcome (within | outside), validation_status

**`exception`** — id, invoice_id, reason (missing_or_invalid_identifiers | failed_claim_matching | disputed_or_out_of_tolerance | high_value | policy_or_coverage_ambiguity), explanation, next_action (structured), assigned_to, priority, opened_at, resolved_at, resolution

**`dispute_query`** — id, invoice_id, line_ids[], query_text, basis (rate_card | entitlement | authorisation | tolerance), sent_at, response_received_at, outcome

**`redaction_log`** — id, invoice_id, field_or_region, rule_id, reason, redacted_at

**`agent_trace`** — id, invoice_id, agent_name, sequence, input_json, output_json, confidence, prompt_version, model_version, started_at, completed_at, duration_ms

**`audit_event`** — id, entity_type, entity_id, event_type, actor (user | agent), actor_id, before_json, after_json, occurred_at, immutable hash chain field

**`payment`** — id, invoice_id, amount_gbp, path (integration | rpa), authorised_by, released_by, released_at, ice_writeback_status, reference

**`notification`** — id, invoice_id, audience (supplier | insurer | customer), status_trigger, channel, content, sent_at

### 12.3 API surface (indicative)

```
POST   /api/invoices/ingest                  Ingest invoice from channel
GET    /api/invoices                         List + filter + sort + paginate
GET    /api/invoices/{id}                    Full invoice with lines, validation, trace
POST   /api/invoices/{id}/reprocess          Re-run the agent pipeline
GET    /api/invoices/{id}/trace              Agent trace for the trace panel
GET    /api/invoices/{id}/audit              Immutable audit log
GET    /api/invoices/{id}/evidence-pack      Export PDF + JSON evidence pack

GET    /api/exceptions                       Prioritised work queue
POST   /api/exceptions/{id}/execute-action   Execute the pre-filled next action
POST   /api/exceptions/{id}/override         Human override (reason mandatory)

POST   /api/invoices/{id}/approve            Approve (segregation-of-duties enforced)
POST   /api/payments/{id}/release            Release payment (threshold authorisation)

GET    /api/suppliers                        Supplier list + scorecard
GET    /api/rate-cards                       Rate card registry + staleness
POST   /api/rate-cards                       Upload new effective-dated rate card

GET    /api/analytics/kpis                   Dashboard KPIs
GET    /api/analytics/leakage                Leakage prevented trends
GET    /api/analytics/benefits               FTE benefit model vs baseline

WS     /ws/invoice-stream                    Live status + agent progress streaming
```

---

## 13. Front-end specification

### 13.1 Design language (mandatory house style)

- **Persistent left navigation** — icon + label, collapsible, active-state indicator, no top-nav-only layouts
- **Fluid animation throughout** — Framer Motion page transitions, animated pipeline progression, animated agent trace reveal, animated counters on KPI cards, skeleton loaders. The interface must feel alive, not static enterprise CRUD
- **Drilldown everywhere** — every KPI, chart segment, pipeline stage and table row drills into a filtered view, and from there into a record-level view. No dead ends
- **Graphics wherever possible** — pipeline diagrams, agent network graph, document viewer with OCR overlay, variance waterfalls, supplier heatmaps, sparklines in table cells
- **Card-based information architecture** — matrix/card layouts for grouped information rather than dense text blocks
- **Clear visual separation** — section headings, generous whitespace, consistent card chrome
- No em-dashes in UI copy. No slogan-style marketing callouts. Professional, plain language.

### 13.2 Left navigation modules

```
Dashboard
Invoice Work Queue
Exceptions
Disputes
Approvals & Payments
Suppliers
Rate Cards
Analytics
Benefits Tracker
Audit Trail
Agent Studio
Settings
```

### 13.3 Dashboard

**Animated KPI cards** (each drills down):
- Invoices received (period)
- Straight-through processed (count + %)
- Exceptions open (by reason)
- Queried / awaiting information
- Payments released (count + GBP)
- Leakage prevented (GBP)
- Median invoice-to-payment cycle time
- Rate card compliance rate

**Animated processing pipeline** — horizontal flow with live counts at each stage:

```
Received → Extracted → Redacted → Matched → Validated → Approved → Paid
```

Each stage is clickable and filters the work queue. Invoices animate along the pipeline as their status changes via the WebSocket stream.

**Exception mix donut** and **leakage trend line**, both drillable.

### 13.4 Invoice Work Queue

- Sortable, filterable table: invoice no, supplier, claim ref, value, VAT, status, match confidence, age, exception reason
- Confidence shown as a visual bar, not a bare number
- Inline sparkline for supplier recent dispute rate
- Bulk actions where safe; single-record actions for anything with financial effect
- Row click opens the drilldown with a smooth transition

### 13.5 Invoice drilldown (the centrepiece screen)

**Top ribbon:** invoice number, supplier, claim reference, gross / net / VAT, status chip, match confidence, exception reason if any, straight-through indicator.

**Three-pane layout:**

*Left pane — Document viewer*
- Original and redacted renditions with a toggle
- OCR field overlay with bounding boxes
- Low-confidence fields highlighted in amber, click to confirm or correct
- Redaction markers with hover showing what was redacted and why

*Centre pane — Line-level validation*
- Table of line items: service type, dates, units, charged rate, expected rate, variance GBP, variance %, tolerance outcome
- Within tolerance rendered green, outside tolerance rendered amber/red with the specific basis shown
- Variance waterfall graphic summarising where value is at risk
- Each line expands to show the rate card clause, entitlement and authorisation applied

*Right pane — Agent trace*
- Vertical animated timeline of agents that ran
- Per agent: status, duration, confidence, input summary, output summary
- Expandable to full reasoning with evidence citations
- "Why?" control on the final recommendation opening a plain-language explanation

**Action bar:** Approve, Raise query (pre-filled), Request information, Route to handler, Override (reason mandatory), Export evidence pack.

### 13.6 Exceptions workspace

- Prioritised queue by value and age
- Grouped by the five taxonomy reasons, each as a card with count and total value at risk
- Every exception shows the clear explanation and the pre-filled next action with a one-click Execute control
- Bulk triage for homogeneous exception groups

### 13.7 Disputes workspace

- Open queries with the highlighted line items shown inline
- Supplier response tracking, ageing, and auto-revalidation on response
- Dispute outcome analytics by supplier and by basis

### 13.8 Approvals & Payments

- Authorisation queue with value thresholds
- Segregation-of-duties enforcement visible in the UI (approver and releaser shown separately)
- Payment path indicator (integration vs RPA) per invoice
- ICE write-back status with retry control

### 13.9 Suppliers

- Supplier scorecards: volume, value, dispute rate, average settlement time, rate card compliance, extraction template coverage
- Heatmap of variance by supplier and service type
- Drill from any supplier into their invoices

### 13.10 Rate Cards

- Effective-dated registry with version history
- Staleness indicators for cards past review date
- Upload flow with diff view against the previous version
- Impact preview: which open invoices would revalidate differently

### 13.11 Analytics

- Leakage prevented over time, by supplier, by service type, by exception reason
- Straight-through processing rate trend
- Cycle time distribution (median, p90)
- Exception trend analysis for the Claims Manager persona (UC-002-HLR-004)

### 13.12 Benefits Tracker

- Models FTE saving against the 2,000 claims per month baseline
- Configurable 10% YoY volume growth
- Shows realised vs the up-to-3-FTE target
- Drilldown into the handling-time assumptions behind the model

### 13.13 Audit Trail

- Immutable chronological event log, filterable by entity, actor, event type and period
- Decision replay view: inputs, prompt version, model version, rate card version, policy version, output
- Redaction log view
- Evidence pack export

### 13.14 Agent Studio

- Visual agent network graph rendered from the HOCON definition
- Per-agent configuration view (read-only in MVP)
- Live agent execution feed
- Prompt and schema version display

---

## 14. Explainability requirements

Every AI-influenced decision surfaced anywhere in the application must carry:

```json
{
  "decision": "QUERY",
  "confidence": 0.86,
  "reasoning": "Hire charged at 14 days; authorisation covers 10 days.",
  "evidence": [
    {"type": "rate_card", "ref": "RC-HIRE-2026-03", "clause": "Line 4, daily hire rate"},
    {"type": "authorisation", "ref": "AUTH-88213", "detail": "10 days authorised"}
  ],
  "affected_lines": [3, 4],
  "model_version": "...",
  "prompt_version": "..."
}
```

No recommendation may be displayed without its evidence. This is the direct mitigation for the RAID risk "supplier disputes if decisions are opaque".

---

## 15. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | Agent pipeline completes in under 30 seconds per invoice for the demo dataset; UI interactions respond in under 300 ms; API p95 under 1 second |
| Real-time | Status and agent progress stream to the UI over WebSocket |
| Security | RBAC by persona; segregation of duties enforced server-side; secrets only via environment variables |
| Data protection | PII redacted before model exposure; Sly-data used for sensitive inter-agent values |
| Auditability | Append-only audit log with hash chaining; full decision replay |
| Resilience | Retry with backoff on adapter failures; dead-letter queue for failed ingestion; idempotent ingestion by invoice number + supplier |
| Scalability | Stateless API layer; queue-backed agent execution; horizontal scaling |
| Accessibility | WCAG 2.1 AA; keyboard navigable; colour never the sole carrier of meaning |
| Localisation | GBP currency, UK date formats, UK VAT handling |
| Observability | Structured logs, per-agent latency metrics, extraction confidence distribution |

---

## 16. Synthetic demo dataset

Generate deterministic, seeded synthetic data:

- **50 suppliers** across repairer, hire, storage and recovery types
- **60 rate cards** including 8 deliberately stale (past review date) and several with mid-period version changes
- **500 claims** with policies, entitlements and authorisations
- **2,000 invoices** reflecting the stated monthly volume, spread across 6 months
- **Channel mix:** email, portal, attachment
- **Format variability:** at least 6 distinct invoice layouts, including 2 non-standard "long tail" formats that must fall back to the generic extractor
- **Seeded outcomes:**
  - ~70% straight-through
  - ~12% out-of-tolerance disputes with specific offending line items
  - ~6% failed claim matching
  - ~4% missing or invalid identifiers
  - ~4% high value
  - ~4% policy or coverage ambiguity
- **Deliberate anomalies:** 40 duplicate invoices, 25 split-invoice patterns, 30 value outliers
- **PII content** in a subset of documents to exercise the redaction agent
- Sample PDFs rendered so the document viewer and OCR overlay are demonstrable

---

## 17. Evaluation and test cases

### 17.1 Agent-level evaluation harness

| Capability | Metric | Target | Method |
|---|---|---|---|
| Document classification | Accuracy | ≥ 97% | Labelled synthetic set |
| Supplier identification | Accuracy | ≥ 98% | Labelled synthetic set |
| Field extraction | Field-level accuracy | ≥ 95% | Golden extraction set |
| Extraction confidence calibration | ECE | ≤ 0.05 | Reliability curve |
| PII redaction | Recall | ≥ 99% | PII-seeded documents |
| PII redaction | False positive rate | ≤ 3% | PII-seeded documents |
| Claim matching | Accuracy | ≥ 98% | Labelled pairs |
| Claim matching | False match rate | ≤ 0.5% | Adversarial near-duplicates |
| Re-rating arithmetic | Exact match | 100% | Deterministic tool test |
| Tolerance decisions | Accuracy | ≥ 99% | Rule-based oracle |
| Duplicate detection | F1 | ≥ 0.95 | Seeded duplicates |
| Exception reason assignment | Accuracy | ≥ 97% | Labelled exception set |
| Explanation quality | LLM-judge score | ≥ 4/5 | Rubric: specific, cites evidence, actionable |
| Straight-through rate | % | ≥ 70% on demo set | End-to-end run |

### 17.2 Functional test cases

**TC-01 Straight-through** — compliant invoice, valid claim ref, within tolerance → auto-approved, paid, ICE write-back confirmed, supplier notified, zero human touches.

**TC-02 Out-of-tolerance line** — 14 hire days charged, 10 authorised → status Queried, dispute query generated naming **only** line items 3 and 4, basis cites the authorisation.

**TC-03 Missing identifier** — no claim reference and no supplier reference → exception reason `missing_or_invalid_identifiers`, explanation present, pre-filled action = request identifier from supplier.

**TC-04 Failed claim matching** — plausible but non-existent claim reference → exception reason `failed_claim_matching`, candidate claims presented ranked by confidence.

**TC-05 High value** — invoice above configured threshold → exception reason `high_value`, routed for authorisation regardless of tolerance outcome.

**TC-06 Policy ambiguity** — service type not clearly covered → exception reason `policy_or_coverage_ambiguity` with the ambiguous entitlement cited.

**TC-07 Duplicate invoice** — same supplier, same invoice number, resubmitted → blocked, duplicate flagged, original referenced.

**TC-08 Stale rate card** — service date after rate card review date → validation proceeds with staleness warning surfaced in UI and audit.

**TC-09 Non-standard format** — long-tail supplier layout → generic extractor invoked, low-confidence fields flagged, handler correction captured for template learning.

**TC-10 Redaction audit** — PII-bearing invoice → redacted rendition produced, redaction log records what and why for each redaction.

**TC-11 Segregation of duties** — same user attempts approve then release → release rejected by API with explicit reason, event audited.

**TC-12 Human override** — handler overrides an auto-approve → override reason mandatory, original recommendation preserved, both recorded in audit.

**TC-13 Payment path — RPA** — supplier configured for RPA → RPA adapter invoked, ICE write-back completed, status Paid.

**TC-14 Payment failure and retry** — payment adapter fails → retry with backoff, status remains Approved, alert raised, no duplicate payment on retry.

**TC-15 Notification matrix** — each status transition triggers the correct notifications to supplier, insurer and customer where relevant; all logged.

**TC-16 Audit replay** — any invoice can be replayed showing inputs, outputs, and the exact rate card, policy, prompt and model versions used.

**TC-17 Evidence pack export** — generates PDF + JSON containing invoice, validation results, agent trace, audit log and redaction log.

**TC-18 Rate card version change** — invoice with service dates spanning two rate card versions → each line validated against the version effective on its own service date.

### 17.3 UI test cases

- Every KPI card drills down to a correctly filtered list
- Every pipeline stage drills down to that stage's invoices
- Agent trace panel renders in sequence with animation and expands to full reasoning
- Document viewer overlays extracted fields with correct bounding boxes and confidence colouring
- Left navigation persists state and indicates active module
- Page transitions animate without layout shift
- Full keyboard navigation of the work queue and drilldown
- Colour-blind safe rendering of tolerance outcomes (icon + label, not colour alone)

### 17.4 Non-functional test cases

- 2,000-invoice batch ingestion completes without failure
- 50 concurrent pipeline executions remain within latency targets
- WebSocket stream reconnects cleanly after network interruption
- Audit log hash chain verification passes after a full demo run
- No PII present in any model-bound payload (assert on captured prompts)

---

## 18. Delivery phases

### Phase 1 — MVP (build this first)
- Data model and seeded synthetic dataset
- Neuro SAN network: orchestrator, intake/classification, extraction, redaction, claim matching, rate validation, entitlement, tolerance/anomaly, settlement, exception router
- FastAPI layer with the core API surface and WebSocket stream
- Front end: Dashboard, Invoice Work Queue, Invoice Drilldown, Exceptions, Approvals & Payments, Audit Trail
- Mock ICE and mock payment adapters
- Evaluation harness with the metrics in 17.1

### Phase 2
- Communications agent with full notification matrix
- Disputes workspace with supplier response loop
- Suppliers and Rate Cards modules
- Analytics and Benefits Tracker
- Agent Studio visual network graph
- RPA payment path

### Phase 3
- Supplier-facing read-only portal
- Template learning loop from handler corrections
- Predictive leakage and supplier risk scoring
- Conversational copilot over the invoice estate
- Live ICE and finance system integration

---

## 19. Acceptance criteria for handover

The build is complete when:

1. Every capability in Section 3 is implemented and demonstrable end to end
2. All five exception reasons in Section 3.7 are produced correctly, each with a clear explanation and an executable pre-filled action
3. Dispute queries identify specific line items, never whole invoices
4. Both payment paths (integration and RPA) and ICE write-back are exercised
5. All five canonical statuses drive the correct notifications
6. The audit trail supports full decision replay and passes hash chain verification
7. Redaction produces a complete what-and-why audit trail
8. All 18 functional test cases in 17.2 pass
9. The evaluation harness runs and reports against every metric in 17.1
10. The UI implements left navigation, fluid animation, drilldown from every metric, and graphical representation throughout
11. The application runs fully offline against the synthetic dataset with mock adapters
12. No secrets are committed; all LLM configuration is environment-driven

---

## 20. Repository structure

```
invoice-to-pay/
├── README.md
├── .env.example
├── docker-compose.yml
├── agents/
│   ├── registries/
│   │   ├── manifest.hocon
│   │   └── invoice_to_pay.hocon
│   └── coded_tools/
│       └── invoice_to_pay/
│           ├── ocr_adapter.py
│           ├── template_registry.py
│           ├── pii_rule_engine.py
│           ├── claim_matcher.py
│           ├── rerating_calculator.py
│           ├── tolerance_engine.py
│           ├── duplicate_detector.py
│           ├── payment_adapters.py
│           └── ice_writeback.py
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── models/
│   │   ├── services/
│   │   ├── adapters/
│   │   └── audit/
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── layouts/        # left navigation shell
│   │   ├── pages/
│   │   ├── components/
│   │   ├── charts/
│   │   ├── animations/
│   │   └── api/
│   └── tests/
├── data/
│   ├── generator/
│   └── seed/
└── evaluation/
    ├── harness.py
    ├── golden_sets/
    └── reports/
```

---

## 21. Traceability matrix

| Source requirement | Spec section |
|---|---|
| Automated invoice capture and classification | 3.1, 11.2 Agent 2, 13.3 |
| Classified by supplier and document type | 3.1, 11.2 Agent 2 |
| Matched to correct claim in ICE | 3.1, 11.2 Agent 5, TC-04 |
| Structured data extraction (supplier, dates, line charges, VAT, hire/storage/recovery) | 3.2, 11.2 Agent 3, 12.2 |
| Automated GDPR/PII redaction with what/why audit | 3.3, 11.2 Agent 4, TC-10 |
| Re-rating against rate cards, coverage, entitlements, authorisations, tolerances | 3.4, 11.2 Agents 6–8 |
| Within tolerance → auto-approve | 3.4, TC-01 |
| Outside tolerance → dispute query on specific line items | 3.4, 11.2 Agent 9, TC-02 |
| Automated approval and payment via integration or RPA | 3.5, 11.2 Agent 12, TC-13 |
| ICE write-back approved and paid | 3.5, TC-01, TC-13 |
| Status notifications to suppliers, insurers, customers | 3.6, 11.2 Agent 11, TC-15 |
| Five canonical statuses | 3.6, 12.2 |
| Exception-only handling, five reasons | 3.7, 11.2 Agent 10, TC-03–TC-06 |
| Clear explanation + pre-filled next action | 3.7, 13.6 |
| Key improvements measurable | 3.8, 13.11, 13.12 |
| UC-002-HLR-001 to 004 | 4, 13.11, 13.12 |
| Up to 3 FTE benefit at 2,000 claims/month, 10% YoY | 5, 13.12 |
| RAID: OCR accuracy risk | 6, 17.1, TC-09 |
| RAID: opaque decisions risk | 6, 14 |
| RAID: standard formats assumption | 6, 11.2 Agent 3 |
| RAID: long tail of non-standard suppliers | 6, TC-09, 18 Phase 3 |
| RAID: supplier rate cards dependency | 6, 13.10, TC-08, TC-18 |
| RAID: finance and payment systems dependency | 6, 12.1, TC-13, TC-14 |
| Data needs: invoices, rate cards, claim financials | 7.1, 12.2, 16 |
| Quality: invoice format variability | 7.2, TC-09 |
| Quality: timeliness of rate updates | 7.2, TC-08 |
| UK: auditability and SOX-style controls | 8, 13.13, TC-11, TC-16 |
| UK: payment governance | 8, 13.8, TC-11 |
