# Running the CMP-UC-002 Invoice-to-Pay Prototype

This guide explains how to run the FastAPI backend, React front end, Neuro SAN network, and evaluation checks.

All commands are run from the repository root unless stated otherwise.

## 1. Backend API

Install backend dependencies:

```powershell
python -m pip install fastapi "uvicorn[standard]" pydantic pytest httpx
```

Generate deterministic seed data:

```powershell
python apps/invoice_to_pay/data/generator/generate_seed.py
```

Start the FastAPI backend:

```powershell
python -m uvicorn apps.invoice_to_pay.backend.app.main:app --host 0.0.0.0 --port 8095
```

On startup the app processes the whole 2,000-invoice seed set (about seven seconds) so that the
exception, dispute, payment, notification and audit views have data on first load. Startup is not
instant as a result; that is deliberate.

Open the API docs:

```text
http://localhost:8095/docs
```

### API endpoints

Core invoice and workflow routes:

```text
GET  /api/health
GET  /api/invoices?limit=20&status=Queried&supplier_id=SUP-001
GET  /api/invoices/{id}
POST /api/invoices/{id}/reprocess
GET  /api/invoices/{id}/trace
GET  /api/invoices/{id}/audit
GET  /api/invoices/{id}/evidence-pack
POST /api/invoices/{id}/approve
POST /api/invoices/{id}/return-to-supplier
POST /api/invoices/{id}/resubmit
POST /api/payments/{id}/release
GET  /api/exceptions
POST /api/exceptions/{id}/execute-action
POST /api/exceptions/{id}/override
```

`return-to-supplier` needs a `reason` and moves the invoice to `Awaiting information`, raising
dispute `DSP-RTS-<invoice>` and a supplier notification. It returns 400 without a reason and
409 for an invoice already paid. `resubmit` closes that query and re-runs the whole pipeline, so
the corrected invoice earns a fresh status; it returns 409 when no return query is open.

`execute-action` is single-use: the first call stamps `resolved_at` and `resolution` on the
exception, and a second call returns 409 rather than re-sending the query.

Reference and analytics routes used by the front-end modules:

```text
GET  /api/claims                         Claims with invoice and value aggregates
GET  /api/claims/{id}/overview           360 degree view of one claim
GET  /api/suppliers                      Supplier scorecards
GET  /api/rate-cards                     Registry with staleness and usage
GET  /api/analytics/supplier-matrix      Supplier by service-type variance heat map
GET  /api/disputes                       Dispute queries
GET  /api/payments                       Payments and segregation-of-duties state
GET  /api/payments/board                 Approvals swim-lane board
GET  /api/notifications                  Outbound notification log
GET  /api/redactions                     GDPR and PII redaction log
GET  /api/audit                          Immutable log plus hash chain status
GET  /api/settings                       Thresholds and redaction rules
GET  /api/agent-network                  Agent topology read from the HOCON
GET  /api/search?q=                      Cross-module search for the global bar
GET  /api/analytics/kpis
GET  /api/analytics/leakage
GET  /api/analytics/benefits
GET  /api/analytics/exception-trends
GET  /api/analytics/cycle-time
WS   /ws/invoice-stream
```

Process a straight-through sample invoice:

```powershell
curl -X POST http://localhost:8095/api/invoices/INVREC-000001/reprocess
```

Process an out-of-tolerance sample invoice:

```powershell
curl -X POST http://localhost:8095/api/invoices/INVREC-000071/reprocess
```

## 2. Front end UI

In a second terminal:

```powershell
cd apps/invoice_to_pay/frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5174
```

The front end expects the backend at `http://localhost:8095`. To override the defaults:

```powershell
$env:VITE_API_BASE="http://localhost:8095"
$env:VITE_WS_BASE="ws://localhost:8095"
npm run dev
```

### Modules and routes

Navigation is hash-based, so every module is directly linkable:

```text
#/dashboard        Animated KPI counters, radial gauges, flowing pipeline, exception mix
#/queue            Invoice work queue; accepts ?status= ?reason= ?supplier= ?search=
#/invoice/<id>     Invoice drilldown: document viewer, line validation, agent trace
#/claims           Claim 360 list, ranked by supplier spend on the claim
#/claim/<id>       Claim 360 view: reserve gauge, suppliers, authorisations, timeline
#/exceptions       Five-reason taxonomy, pre-filled actions, override
#/disputes         Open queries with the specific line items named
#/approvals        Authorisation queue and segregation-of-duties enforcement
#/suppliers        Supplier scorecards
#/rate-cards       Effective-dated registry with staleness
#/analytics        Leakage, exception trends, cycle time, supplier variance heat map
#/benefits         FTE benefit model against the 2,000/month baseline
#/audit            Event log, redaction log, decision replay
#/agent-studio     Interactive agent network graph parsed from the HOCON
#/settings         Thresholds and GDPR redaction rules
```

### Interactive visuals

- **Global search** sits in the shell, so it is on every screen. `Ctrl`+`K` focuses it from
  anywhere, two characters start a debounced query, and results are grouped into invoices, claims,
  suppliers, rate cards, exceptions and modules. Arrow keys and `Enter` navigate straight to the
  matching drilldown. Because modules are indexed too, it doubles as a jump-to-page palette.
- **Invoice drilldown** can send an invoice back to the supplier for verification and resubmission.
  The button opens a two-step composer: pick a standard reason, add optional detail, tick the lines
  to recheck (pre-selected from the lines outside tolerance), and read the exact query the supplier
  will receive before it is sent. Once sent, the drilldown shows the open query and offers
  **Record resubmission and re-validate** instead, which closes the query and reruns the pipeline.
  A paid invoice cannot be recalled this way.
- **Exceptions** mark a next action complete the moment it executes: the card gains a green tick and
  the Execute button disappears, so the same query cannot be sent twice.
- **Agent Studio** renders the twelve-agent topology as a live SVG graph you can manipulate: drag a
  node to rearrange it, scroll to zoom at the cursor, drag the background in Pan mode, click to pin
  a node's details, double-click to isolate its branch, and press **Play a run** to watch the front
  man fan out with packets travelling along the edges.
- **Approvals and payments** is a four-lane board: Needs authorisation, Awaiting release, Released
  and written back, and Blocked. Work moves left to right and nothing crosses into Released without
  a second identity. The first lane is genuinely populated, because the auto-approval engine settles
  compliant invoices during warm-up while high-value invoices are held back for a human by
  specification TC-05.
- **Rate Cards** is a card grid rather than a table. Each card carries the supplier, version, whether
  it is the version in force, how many invoice lines and invoices were validated against it, the
  value checked, the variance it found, and an effective-window bar with markers for the review date
  and today. Cards that are stale *and* still in force are called out at the top, because those are
  the ones validating live invoices against a contract nobody has re-confirmed.
- **Claim 360** answers "what did this one accident actually cost us". A claim usually attracts
  several invoices from different suppliers, so the view shows a reserve-utilisation gauge, spend
  split by service type, every supplier on the claim, approved units against billed units, and the
  full audit timeline. This is where the classic overcharge is most visible: 10 days of hire car
  approved, 14 days billed.
- **Analytics** carries a supplier by service-type variance heat map. Darker cells mean more money
  stopped; every cell also prints its value, so colour is never the only carrier of meaning.
- **Dashboard** shows straight-through rate and rate-card compliance as arc gauges with their
  targets marked, plus a pipeline whose stages animate and drill into the work queue.
- Animation respects `prefers-reduced-motion`, so the whole interface stills for anyone who has
  asked their operating system to reduce motion.

Type-check and production build:

```powershell
npm run build
```

### Demo flow

1. Open `#/dashboard` and click any KPI card or pipeline stage to drill into a filtered queue.
2. Click a queue row to open the drilldown. Toggle Redacted versus Original in the document viewer.
3. In the drilldown, use **Why this decision?** to reveal the reasoning and the evidence citations.
4. Open `#/approvals`, set the acting identity to the same user that authorised a payment and press
   **Release**. The API rejects it and the rejection is audited. Switch identity and it succeeds.
5. Open `#/audit`, select any event, and read the replay view with before and after state.
6. Open `#/agent-studio` to see the twelve-agent topology parsed from the registry file.

## 3. Neuro SAN agent network

The network file is:

```text
registries/apps/invoice_to_pay.hocon
```

It declares the twelve agents of the specification's section 11.2 over one shared coded tool:

```text
Invoice_Orchestrator (front man)
├── Intake_And_Classification_Agent
├── Extraction_Agent
├── Redaction_Agent
├── Claim_Matching_Agent
├── Rate_Card_Validation_Agent          (validation cluster head)
│   ├── Entitlement_And_Authorisation_Agent
│   └── Tolerance_And_Anomaly_Agent
│       └── Exception_Router_Agent
├── Settlement_And_Dispute_Agent
│   └── Exception_Router_Agent
├── Communications_Agent
└── Payment_And_Writeback_Agent
```

The coded tool is:

```text
coded_tools/invoice_to_pay/invoice_pipeline_tool.py
```

Each agent calls that one tool and asks for its own `stage` view (`intake`, `extraction`,
`redaction`, `matching`, `rate_card`, `entitlement`, `tolerance`, `settlement`, `exception`,
`communications`, `payment`, or `full`), so the deterministic arithmetic never runs in the model
while each agent still reports something specific to its stage.

### Prerequisites on this machine

The `ns` console script is not on `PATH` here. Use the module form:

```powershell
python -m neuro_san_studio validate registries/apps/invoice_to_pay.hocon
python -m neuro_san_studio run --server-http-port 8081 --nsflow-port 4174
```

Two environment requirements apply:

- **Registry entry.** The server does not discover `registries/apps/manifest.hocon`, so the network
  is registered in the top-level `registries/manifest.hocon`.
- **TLS trust.** Corporate TLS interception makes `httpx` fail with `CERTIFICATE_VERIFY_FAILED`,
  because it does not read the Windows certificate store. Export the machine's trusted roots to a
  PEM file and point the server at it before starting:

  ```powershell
  # Set both before starting the server, in the same shell.
  $env:SSL_CERT_FILE="C:\path\to\corp-ca-bundle.pem"
  $env:REQUESTS_CA_BUNDLE=$env:SSL_CERT_FILE
  ```

- **LLM provider.** Only Azure OpenAI has real credentials in `.env`; the plain OpenAI, Anthropic
  and Gemini keys are still placeholders. The network therefore overrides the shared
  `llm_config.fallbacks` chain with the Azure deployment. Note that `fallbacks` must be replaced
  explicitly, because HOCON merges objects and setting sibling keys alone has no effect.

The server takes roughly two minutes to load all registries. Confirm the network is registered:

```powershell
(Invoke-RestMethod "http://localhost:8081/api/v1/list").agents |
  Where-Object { $_.agent_name -eq "apps/invoice_to_pay" }
```

### Running a query

Interactive chat:

```powershell
python -m neuro_san_studio chat apps/invoice_to_pay
```

Non-interactively over HTTP:

```powershell
$body = '{"user_message":{"text":"Process invoice INVREC-000071 end to end and return the decision, affected line items and evidence."}}'
Invoke-WebRequest -UseBasicParsing -Method Post -ContentType "application/json" -Body $body `
  -Uri "http://localhost:8081/api/v1/apps/invoice_to_pay/streaming_chat"
```

Example prompts:

```text
Process invoice INVREC-000001 and explain the decision.
Process invoice INVREC-000071 and show affected line items.
Which lines on INVREC-000071 are outside tolerance?
```

A narrow question routes to a single stage agent. A full end-to-end request fans out to eight
down-chain agents, which is why `max_execution_seconds` is 300 rather than 30. The deterministic
pipeline itself completes in milliseconds; the time is LLM round-trips.

The nsflow UI is at `http://localhost:4174` and renders all thirteen nodes (twelve LLM agents plus
the coded tool).

## 4. Evaluation and tests

Run the evaluation harness over the whole seeded estate:

```powershell
python apps/invoice_to_pay/evaluation/harness.py --summary
```

Drop `--summary` for the full JSON report, which is also written to
`apps/invoice_to_pay/evaluation/reports/latest.json`. Use `--sample-size 250` for a quick run.

Every metric in specification section 17.1 is measured against an independent oracle, and each one
reports its `method` so a reader can tell a real measurement from an unimplemented capability:

- `extraction_oracle.py` re-parses the raw document text, so extraction, classification, supplier
  identification and claim matching are scored against the document rather than against the same
  structured fields the pipeline populated.
- `pii_oracle.py` declares its own reference patterns, so a broken rule set in settings cannot make
  the pipeline and the oracle agree with each other and both be wrong.
- Re-rating is checked by recomputing units times rate independently; tolerance decisions are
  checked against a rule oracle built from the configured thresholds.

Expected result: **15 of 15 metrics measured and passing**.

Run the test suite:

```powershell
python -m pytest apps/invoice_to_pay/backend/tests apps/invoice_to_pay/evaluation/tests coded_tools/invoice_to_pay/tests -q
```

Expected: **47 passed**, covering straight-through processing, line-level dispute scoping,
segregation of duties, single-release enforcement, duplicate blocking, GDPR redaction and its audit
trail, the agent topology, every stage view of the coded tool, and the harness itself.

## 5. Current validation status

Verified on this machine:

- Backend warm-up processes 2,000 invoices; audit hash chain verifies.
- All five exception reasons are produced: 420 out-of-tolerance, 120 failed matching, 80 missing
  identifiers, 80 high value, 80 policy ambiguity.
- Both payment paths are exercised: 900 integration, 420 RPA.
- GDPR redaction fires on 181 PII-bearing invoices, producing 543 what-and-why log rows.
- The twelve-agent network returns a line-scoped decision naming only `INVREC-000071-L3` and
  `INVREC-000071-L4`, with rate card, claim match and entitlement evidence.
- Front end type-checks and builds clean; all thirteen routes render.
- Segregation of duties: authorise as one identity returns 200, releasing as that same identity
  returns 403, releasing as a second identity returns 200, and a second release returns 409. All
  four outcomes are written to the audit log.
- Evaluation harness: 15 of 15 metrics measured, all meeting their targets, straight-through rate
  0.70 across the full 2,000-invoice estate.

### Data integrity fixes behind those numbers

Three seed-data defects were making the measurements meaningless and are worth knowing about:

- Redaction rule patterns were double-escaped, so `\b` was a literal backslash and no rule could
  ever match. Redaction was silently disabled across the whole estate.
- Line amounts were computed from the generator's own base rate while rate cards used
  `base_rate * uniform(0.9, 1.15)`. Every invoice therefore carried up to 15% variance, and
  straight-through invoices were being disputed by accident. Amounts are now charged against the
  supplier's effective rate card, so a compliant line has exactly zero variance.
- `out_of_tolerance` invoices applied their overcharge to lines 3 and 4, but line count ranged from
  2 to 4, so two-line invoices seeded to dispute were never actually overcharged. The pipeline
  compensated by relabelling a within-tolerance line as `outside`, which produced disputes citing
  lines whose own recorded variance did not justify them. The generator now guarantees at least
  three lines and an overcharge that clears both tolerance thresholds, and that compensating
  relabel has been removed.

### Known gaps against the specification

- Split invoicing, value outlier detection, fuzzy claim matching, OCR bounding boxes, retry and
  backoff, idempotent ingestion, dead-letter handling, RBAC and the template-learning loop are not
  implemented. The seed still carries 25 split-invoice patterns that are not linked to any invoice.
- `current_rate_card()` selects by supplier only, not by service date, so per-line rate card
  version selection (TC-18) and staleness alerting during validation (TC-08) do not work.
- Storage is in-memory, not PostgreSQL plus blob and vector stores.
- Only `Paid`, `Queried` and `Awaiting information` persist as terminal statuses; `Received` and
  `Approved` are transient.
- `explanation_quality_rubric_score` is a deterministic five-point rubric, not the LLM judge the
  specification asks for, because the harness must run fully offline. It is reported under a
  different metric name for that reason.
- Duplicate invoices are blocked and audited but carry no exception reason, because the section 3.7
  taxonomy is fixed at five values and none of them means "duplicate". They appear in the audit
  trail and the invoice decision, not in the Exceptions workspace queue.
