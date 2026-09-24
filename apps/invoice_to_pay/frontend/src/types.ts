export type Kpis = {
  invoices_received: number;
  straight_through_count: number;
  straight_through_pct: number;
  exceptions_open: number;
  queried_or_awaiting_information: number;
  payments_released_count: number;
  payments_released_gbp: number;
  leakage_prevented_gbp: number;
  median_invoice_to_payment_cycle_time_days: number;
  rate_card_compliance_rate: number;
  exceptions_by_reason: Record<string, number>;
};

export type InvoiceLine = {
  id: string;
  line_no: number;
  service_type: string;
  service_date_from: string;
  service_date_to: string;
  units: number;
  unit_rate_gbp: number;
  amount_gbp: number;
  vat_gbp: number;
  extracted_confidence: number;
  rate_card_line_id: string | null;
  expected_amount_gbp: number;
  variance_gbp: number;
  variance_pct: number;
  tolerance_outcome: string;
  validation_status: string;
  evidence: Array<Record<string, unknown>>;
};

export type Invoice = {
  id: string;
  invoice_number: string;
  supplier_id: string;
  claim_id: string | null;
  channel: string;
  received_at: string;
  status: string;
  gross_gbp: number;
  net_gbp: number;
  vat_gbp: number;
  match_confidence: number;
  match_method: string;
  exception_reason?: string | null;
  straight_through: boolean;
  layout_id: string;
  document_text: string;
  redacted_document_uri?: string | null;
  redaction_summary?: Array<Record<string, unknown>>;
  validation_summary?: { outside_line_ids?: string[] };
  lines: InvoiceLine[];
  decision?: Decision;
  supplier?: Supplier;
  claim?: Record<string, unknown> | null;
  trace?: AgentTrace[];
  redactions?: RedactionLog[];
  exceptions?: ExceptionRecord[];
  disputes?: DisputeQuery[];
  notifications?: NotificationRecord[];
};

export type Decision = {
  decision: string;
  confidence: number;
  reasoning: string;
  evidence: Array<Record<string, unknown>>;
  affected_lines: string[];
  model_version: string;
  prompt_version: string;
};

export type Supplier = { id: string; name: string; type: string; contact: string; payment_path: string; template_id: string; active: boolean };

export type SupplierScorecard = {
  supplier: Supplier;
  invoice_count: number;
  invoice_value_gbp: number;
  dispute_rate: number;
  straight_through_rate: number;
  rate_card_compliance_rate: number;
  variance_at_risk_gbp: number;
  has_extraction_template: boolean;
};

export type RateCard = {
  id: string; supplier_id: string; version: string; effective_from: string; effective_to: string;
  review_due_date: string; status: string; is_stale: boolean; line_count: number; lines_validated_against: number;
  supplier_name: string; supplier_type: string; is_in_force: boolean; version_count_for_supplier: number;
  invoices_validated_against: number; value_checked_gbp: number; variance_found_gbp: number;
  days_to_review: number; days_since_effective: number; rate_span_gbp: [number, number];
  lines: Array<{ id: string; service_type: string; unit: string; rate_gbp: number; max_units: number; conditions: string }>;
};

export type PaymentBoardItem = {
  payment_id: string | null;
  invoice_id: string; invoice_number: string; claim_id: string | null;
  supplier_id: string; supplier_name: string;
  amount_gbp: number; vat_gbp: number; path: string;
  authorised_by: string | null; released_by: string | null; released_at: string | null;
  ice_writeback_status: string; reference: string | null; status: string;
  above_threshold: boolean; exception_reason: string | null; duplicate_of: string | null;
  is_high_value: boolean; reason: string;
};

export type PaymentBoard = {
  lanes: Array<{ key: string; title: string; description: string; count: number; value_gbp: number; items: PaymentBoardItem[]; truncated: number }>;
  high_value_threshold_gbp: number;
  total_value_gbp: number;
};

export type ExceptionRecord = {
  id: string; invoice_id: string; reason: string; explanation: string;
  next_action: { type?: string; target?: string; draft_content?: string; line_ids?: string[]; candidates?: Array<Record<string, unknown>> };
  assigned_to: string; priority: number; opened_at: string; resolved_at?: string | null; resolution?: string | null;
};

export type DisputeQuery = { id: string; invoice_id: string; line_ids: string[]; query_text: string; basis: string; sent_at?: string | null; response_received_at?: string | null; outcome?: string | null };

export type RedactionLog = { id: string; invoice_id: string; field_or_region: string; rule_id: string; reason: string; redacted_at: string };

export type AgentTrace = {
  id: string; invoice_id: string; agent_name: string; sequence: number;
  input_json: Record<string, unknown>; output_json: Record<string, unknown>;
  confidence: number; prompt_version: string; model_version: string; duration_ms: number;
};

export type AuditEvent = {
  id: string; entity_type: string; entity_id: string; event_type: string; actor: string; actor_id: string;
  before_json: Record<string, unknown>; after_json: Record<string, unknown>; occurred_at: string;
  previous_hash: string; hash: string;
};

export type AuditResponse = { hash_chain_valid: boolean; total: number; events: AuditEvent[] };

export type Payment = {
  id: string; invoice_id: string; amount_gbp: number; path: string;
  authorised_by: string | null; released_by: string | null; released_at: string | null;
  ice_writeback_status: string; reference: string | null;
};

export type NotificationRecord = { id: string; invoice_id: string; audience: string; status_trigger: string; channel: string; content: string; sent_at: string };

export type Benefits = {
  baseline_claims_per_month: number; volume_growth_yoy_pct: number; target_fte_saving: number;
  realised_fte_saving: number; handling_minutes_saved: number;
  assumptions: { manual_minutes_per_invoice_saved: number; productive_hours_per_fte_month: number };
};

export type Leakage = { by_service_type: Record<string, number>; by_supplier: Record<string, number>; by_exception_reason: Record<string, number> };

export type ExceptionTrends = { count_by_reason: Record<string, number>; value_at_risk_by_reason: Record<string, number>; total_open: number };

export type CycleTime = { median_days: number; p90_days: number; distribution: Record<string, number>; assumed_days_by_status: Record<string, number> };

export type AgentNode = { name: string; kind: string; is_front_man: boolean; description: string; coded_class: string | null; down_chain: string[] };

export type AgentNetwork = {
  source_file: string; llm_class: string | null; max_steps: number; max_execution_seconds: number;
  llm_agent_count: number; coded_tool_count: number; nodes: AgentNode[]; edges: Array<{ source: string; target: string }>;
};

export type SettingsResponse = {
  settings: {
    high_value_threshold_gbp: number; tolerance_pct: number; tolerance_gbp: number;
    min_extraction_confidence: number; min_match_confidence: number; rate_card_stale_days: number;
    redaction_rules: Array<{ id: string; pattern: string; reason: string }>;
  };
  metadata: Record<string, unknown>;
};

export type Claim = {
  id: string; ice_claim_ref: string; policy_id: string; customer_id: string;
  incident_date: string; status: string; reserve_gbp: number; paid_to_date_gbp: number;
};

export type Policy = {
  id: string; cover_type: string; coverage_limits: Record<string, number>;
  entitlements: string[]; excess_gbp: number; effective_from: string; effective_to: string;
};

export type ClaimRow = {
  claim: Claim;
  invoice_count: number;
  supplier_count: number;
  invoiced_gbp: number;
  paid_gbp: number;
  open_count: number;
  variance_gbp: number;
};

export type ClaimFinancials = {
  reserve_gbp: number; invoiced_gbp: number; paid_gbp: number; withheld_gbp: number;
  leakage_prevented_gbp: number; vat_gbp: number; reserve_utilisation_pct: number;
  released_count: number; payment_count: number;
};

export type ClaimSupplier = {
  supplier: Supplier;
  invoice_count: number;
  invoiced_gbp: number;
  disputed_count: number;
  variance_gbp: number;
};

export type ClaimAuthorisation = {
  authorisation: {
    id: string; claim_id: string; supplier_id: string; service_type: string;
    authorised_units: number; authorised_value_gbp: number; authorised_by: string; authorised_at: string;
  };
  charged_units: number;
  charged_value_gbp: number;
  units_over: number;
  value_over_gbp: number;
};

export type ClaimInvoiceCard = {
  id: string; invoice_number: string; supplier_id: string; status: string; channel: string;
  received_at: string; gross_gbp: number; vat_gbp: number; straight_through: boolean;
  exception_reason: string | null; match_confidence: number; line_count: number;
  outside_line_ids: string[]; variance_gbp: number; decision: string | null; service_types: string[];
};

export type ClaimTimelineEvent = {
  id: string; entity_type: string; entity_id: string; event_type: string;
  actor: string; actor_id: string; occurred_at: string;
};

export type ClaimOverview = {
  claim: Claim;
  policy: Policy | null;
  financials: ClaimFinancials;
  suppliers: ClaimSupplier[];
  authorisations: ClaimAuthorisation[];
  invoices: ClaimInvoiceCard[];
  service_mix: Record<string, number>;
  stage_counts: Record<string, number>;
  exceptions: ExceptionRecord[];
  disputes: DisputeQuery[];
  payments: Payment[];
  timeline: ClaimTimelineEvent[];
};

export type SupplierMatrix = {
  columns: string[];
  peak_gbp: number;
  rows: Array<{ supplier_id: string; supplier_name: string; supplier_type: string; values: Record<string, number>; total_gbp: number }>;
};

export type SearchHit = { route: string; title: string; subtitle: string; badge: string };

export type SearchResponse = {
  query: string;
  total: number;
  groups: Array<{ key: string; title: string; count: number; hits: SearchHit[] }>;
};

export const EXCEPTION_REASONS = [
  'missing_or_invalid_identifiers',
  'failed_claim_matching',
  'disputed_or_out_of_tolerance',
  'high_value',
  'policy_or_coverage_ambiguity',
] as const;

export const CANONICAL_STATUSES = ['Received', 'Queried', 'Approved', 'Paid', 'Awaiting information'] as const;

export function reasonLabel(reason: string): string {
  return reason.replace(/_/g, ' ').replace(/^./, (character) => character.toUpperCase());
}

export function gbp(value: number): string {
  return `£${Math.round(value).toLocaleString('en-GB')}`;
}
