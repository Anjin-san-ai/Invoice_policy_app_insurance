"""Theo, the back-office assistant.

Theo answers a handler's questions about the live estate — a claim, an invoice, a dispute, a
payment or the total outlay. Every answer is computed from the repository, never generated prose
about numbers it has not seen: the text is a template, the figures come from the data, and each
answer carries the screens that prove it.

Intent matching is keyword based for the same reasons the customer intake agent is deterministic —
instant, key-free and reproducible for a demo. When Azure OpenAI is configured the wording can be
improved on top, but the numbers are always the repository's.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class BackOfficeAssistant:
    """Answers natural-language questions about claims, invoices, suppliers and exceptions."""

    # Suggested prompts shown on the empty state, in the order a handler would want them.
    SUGGESTIONS = (
        "What needs my attention today?",
        "Which claims are waiting on triage?",
        "Tell me about CLM-00002",
        "What is our total outlay?",
        "What exceptions are open?",
        "What is in dispute with suppliers?",
        "What is waiting for payment approval?",
        "Which suppliers have the most variance?",
        "Are any policies out of date?",
    )

    def __init__(self, repository: Any, analytics: Any, claims: Any, board: Any, search: Any) -> None:
        self.repository = repository
        self.analytics = analytics
        self.claims = claims
        self.board = board
        self.search = search

    def ask(self, question: str) -> dict[str, Any]:
        """Answer one question, returning text, figures and the screens that back it up."""
        text = (question or "").strip()
        if not text:
            raise ValueError("Ask me something about the claim estate")
        lowered = text.lower()
        logger.info("Theo asked: %s", text)

        # A reference in the question is the strongest signal there is: answer about that record.
        reference = self._reference_in(text)
        if reference:
            return self._entity(text, reference)

        for matcher, handler in (
            (("attention", "today", "priorit", "what should i", "worklist"), self._attention),
            (("triage", "awaiting", "new claim", "unassigned"), self._triage),
            (("over reserve", "overreserve", "exceed", "reserve"), self._reserve),
            (("exception", "failed", "routed"), self._exceptions),
            (("straight", "stp", "touchless", "no human"), self._straight_through),
            (("leakage", "saved", "prevented", "overcharg"), self._leakage),
            (("policy", "policies", "rate card", "stale", "out of date"), self._policies),
            (("outlay", "spend", "cost", "how much have we"), self._outlay),
            # Disputes and payments are tested before suppliers: "in dispute with suppliers" is a
            # question about disputes, and a supplier-ranking answer would be the wrong reply.
            (("dispute", "queried", "query"), self._disputes),
            (("payment", "approval", "release", "pay"), self._payments),
            (("supplier", "vendor", "garage", "repairer"), self._suppliers),
            (("photo", "image", "evidence"), self._evidence),
        ):
            if any(term in lowered for term in matcher):
                return handler(text)

        return self._fallback(text)

    # ------------------------------------------------------------------ answers

    def _attention(self, question: str) -> dict[str, Any]:
        """The handler's worklist: what is actually blocked on a person."""
        stats = self.claims.statistics()
        kpis = self.analytics.kpis()
        open_exceptions = kpis.get("exceptions_open", 0)
        awaiting = stats.get("awaiting_triage", 0)
        to_release = self._lane_count("release")
        to_authorise = self._lane_count("authorise")
        by_reason = kpis.get("exceptions_by_reason", {}) or {}
        worst_reason = max(by_reason.items(), key=lambda item: item[1], default=("", 0))
        return self._answer(
            question,
            f"There are four things sitting on a person right now. {awaiting} claim"
            f"{' needs' if awaiting == 1 else 's need'} triage, {open_exceptions} exception"
            f"{' is' if open_exceptions == 1 else 's are'} open, {to_authorise} high-value payment"
            f"{' is' if to_authorise == 1 else 's are'} held for authorisation, and {to_release} "
            f"{'is' if to_release == 1 else 'are'} authorised but waiting on a second identity to release.",
            [
                {"label": "Claims awaiting triage", "value": str(awaiting)},
                {"label": "Open exceptions", "value": str(open_exceptions)},
                {"label": "Held for authorisation", "value": str(to_authorise)},
                {"label": "Awaiting release", "value": str(to_release)},
            ],
            [
                {"label": "Triage claims", "route": "/claims"},
                {"label": "Work exceptions", "route": "/exceptions"},
                {"label": "Release payments", "route": "/approvals"},
            ],
            bullets=[
                f"Triage first: an untriaged claim blocks every supplier on it, and the customer is "
                f"waiting on the notification. {stats.get('portal_claims', 0)} of the estate's claims came "
                "in through the customer portal.",
                f"The largest exception category is {worst_reason[0].replace('_', ' ') or 'none'}"
                + (f" with {worst_reason[1]} open." if worst_reason[1] else "."),
                f"{stats.get('over_reserve_count', 0)} claims are now invoiced above the reserve set for "
                f"them, against £{stats.get('reserve_gbp', 0):,.0f} reserved in total.",
                f"Nothing is stuck financially: £{kpis.get('leakage_prevented_gbp', 0):,.0f} of overcharging "
                "was already stopped by the validation agents without anyone touching it.",
            ],
            follow_ups=[
                "Which claims are waiting on triage?",
                "What exceptions are open?",
                "What is waiting for payment approval?",
            ],
        )

    def _triage(self, question: str) -> dict[str, Any]:
        """Claims a customer has submitted that nobody has picked up."""
        rows = [row for row in self.claims.list_claims(limit=200) if row.get("needs_triage")]
        names = ", ".join(
            f"{row.get('claim', {}).get('id')} ({row.get('claim', {}).get('customer_name')})" for row in rows[:5]
        )
        body = (
            f"{len(rows)} claim{'' if len(rows) == 1 else 's'} waiting on triage: {names}."
            if rows
            else "Nothing is waiting on triage. Every claim has been picked up."
        )
        return self._answer(
            question,
            body,
            [
                {"label": "Awaiting triage", "value": str(len(rows))},
                {"label": "Customer raised", "value": str(sum(1 for row in rows if row.get("claim", {}).get("origin") == "customer_portal"))},
                {"label": "Photographs supplied", "value": str(sum(row.get("photo_count", 0) for row in rows))},
            ],
            [{"label": "Open Claim 360", "route": "/claims"}]
            + [
                {"label": f"Open {row.get('claim', {}).get('id')}", "route": f"/claim/{row.get('claim', {}).get('id')}"}
                for row in rows[:3]
            ],
            bullets=[
                f"{row.get('claim', {}).get('id')}: {row.get('claim', {}).get('customer_name')} · "
                f"{str(row.get('claim', {}).get('incident_type', '')).replace('_', ' ')} on "
                f"{row.get('claim', {}).get('incident_date')} at "
                f"{row.get('claim', {}).get('incident_location') or 'an unstated location'} · "
                f"{row.get('claim', {}).get('severity', '').replace('_', ' ')} · "
                f"{row.get('photo_count', 0)} photographs · vehicle is "
                f"{row.get('claim', {}).get('vehicle_drivable') or 'not recorded'}"
                for row in rows[:5]
            ]
            or ["Every claim in the estate has been picked up by a handler."],
            follow_ups=(
                [f"Tell me about {rows[0].get('claim', {}).get('id')}", "What needs my attention today?"]
                if rows
                else ["What needs my attention today?"]
            ),
        )

    def _reserve(self, question: str) -> dict[str, Any]:
        """Claims whose invoiced value has passed the reserve set for them."""
        stats = self.claims.statistics()
        rows = self.claims.list_claims(limit=200)
        breached = [
            row
            for row in rows
            if row.get("claim", {}).get("reserve_gbp", 0) > 0
            and row.get("invoiced_gbp", 0) > row.get("claim", {}).get("reserve_gbp", 0)
        ]
        breached.sort(key=lambda row: row.get("invoiced_gbp", 0) - row.get("claim", {}).get("reserve_gbp", 0), reverse=True)
        worst = ", ".join(str(row.get("claim", {}).get("id")) for row in breached[:5])
        return self._answer(
            question,
            f"{len(breached)} claim{'' if len(breached) == 1 else 's'} are invoiced above their reserve"
            + (f", worst first: {worst}." if worst else ".")
            + f" Across the estate, £{stats.get('invoiced_gbp', 0):,.0f} is invoiced against"
            f" £{stats.get('reserve_gbp', 0):,.0f} reserved, or {stats.get('reserve_utilisation_pct', 0)}%.",
            [
                {"label": "Over reserve", "value": str(len(breached))},
                {"label": "Reserve utilisation", "value": f"{stats.get('reserve_utilisation_pct', 0)}%"},
                {"label": "Total reserved", "value": f"£{stats.get('reserve_gbp', 0):,.0f}"},
                {"label": "Total invoiced", "value": f"£{stats.get('invoiced_gbp', 0):,.0f}"},
            ],
            [{"label": "Open Claim 360", "route": "/claims"}]
            + [
                {"label": f"Open {row.get('claim', {}).get('id')}", "route": f"/claim/{row.get('claim', {}).get('id')}"}
                for row in breached[:3]
            ],
        )

    def _exceptions(self, question: str) -> dict[str, Any]:
        """The open exception mix by reason."""
        kpis = self.analytics.kpis()
        by_reason = kpis.get("exceptions_by_reason", {}) or {}
        ranked = sorted(by_reason.items(), key=lambda item: item[1], reverse=True)
        top = ", ".join(f"{reason.replace('_', ' ')} ({count})" for reason, count in ranked[:4])
        return self._answer(
            question,
            f"{kpis.get('exceptions_open', 0)} exceptions are open. By reason: {top}."
            if ranked
            else "No exceptions are open.",
            [{"label": reason.replace("_", " "), "value": str(count)} for reason, count in ranked[:4]],
            [{"label": "Work the queue", "route": "/exceptions"}]
            + [
                {"label": f"Triage {reason.replace('_', ' ')}", "route": f"/exceptions?reason={reason}"}
                for reason, _ in ranked[:2]
            ],
            bullets=[
                f"{reason.replace('_', ' ').capitalize()}: {count} open — {self._reason_advice(reason)}"
                for reason, count in ranked[:5]
            ]
            or ["Nothing is in the exception queue."],
            follow_ups=["What is in dispute with suppliers?", "Which suppliers have the most variance?"],
        )

    @staticmethod
    def _reason_advice(reason: str) -> str:
        """One line on what a handler actually does about each exception reason."""
        return {
            "missing_or_invalid_identifiers": "the invoice cannot be matched, so it needs the supplier to resubmit with a claim reference",
            "failed_claim_matching": "no claim matched above the confidence threshold, so a handler must bind it by hand",
            "disputed_or_out_of_tolerance": "charges exceed the contracted rate, so query the specific lines with the supplier",
            "high_value": "over the high-value threshold, so it is held for a human to authorise by policy",
            "policy_or_coverage_ambiguity": "the policy may not entitle the service billed, so cover needs confirming first",
        }.get(reason, "review and route it")

    def _straight_through(self, question: str) -> dict[str, Any]:
        """Straight-through rate against the target."""
        kpis = self.analytics.kpis()
        rate = kpis.get("straight_through_pct", 0.0)
        verdict = "ahead of" if rate >= 70 else "behind"
        return self._answer(
            question,
            f"{rate:.1f}% of invoices settle with no human involvement, which is {verdict} the 70% target. "
            f"That is {kpis.get('straight_through_count', 0):,} of {kpis.get('invoices_received', 0):,} invoices.",
            [
                {"label": "Straight through", "value": f"{rate:.1f}%"},
                {"label": "Target", "value": "70%"},
                {"label": "Invoices", "value": f"{kpis.get('invoices_received', 0):,}"},
                {"label": "Median cycle", "value": f"{kpis.get('median_invoice_to_payment_cycle_time_days', 0)} d"},
            ],
            [{"label": "See analytics", "route": "/analytics"}, {"label": "Paid invoices", "route": "/queue?status=Paid"}],
            bullets=[
                f"Median time from invoice received to payment is "
                f"{kpis.get('median_invoice_to_payment_cycle_time_days', 0)} days.",
                f"{kpis.get('exceptions_open', 0)} invoices needed a human because a check failed, and "
                f"{kpis.get('queried_or_awaiting_information', 0)} are queried with the supplier.",
                f"Rate-card compliance is {(kpis.get('rate_card_compliance_rate', 0) * 100):.1f}% of lines "
                "within the contracted tolerance, which is what makes touchless payment safe.",
            ],
            follow_ups=["What exceptions are open?", "How much leakage have we prevented?"],
        )

    def _leakage(self, question: str) -> dict[str, Any]:
        """Variance stopped before payment, and where it came from."""
        leakage = self.analytics.leakage()
        by_service = leakage.get("by_service_type", {}) or {}
        ranked = sorted(by_service.items(), key=lambda item: item[1], reverse=True)
        top = ", ".join(f"{service} £{value:,.0f}" for service, value in ranked[:4])
        total = leakage.get("total_gbp", sum(by_service.values()))
        return self._answer(
            question,
            f"£{total:,.0f} of overcharging was caught before payment. The biggest sources are {top}.",
            [{"label": service, "value": f"£{value:,.0f}"} for service, value in ranked[:4]],
            [{"label": "See analytics", "route": "/analytics"}, {"label": "Benefits tracker", "route": "/benefits"}],
            bullets=[
                f"{service}: £{value:,.0f} of variance stopped on lines outside the contracted rate"
                for service, value in ranked[:5]
            ]
            + [
                "This is money that was invoiced but never paid, because the re-rating agent caught the "
                "line before it reached the payment board.",
            ],
            follow_ups=["Which suppliers have the most variance?", "Are any policies out of date?"],
        )

    def _suppliers(self, question: str) -> dict[str, Any]:
        """Suppliers ranked by the variance they are generating."""
        scorecards = self.analytics.supplier_scorecards()
        ranked = sorted(scorecards, key=lambda row: row.get("variance_at_risk_gbp", 0), reverse=True)
        # A scorecard nests the supplier record, so the name is one level down.
        top = ", ".join(
            f"{row.get('supplier', {}).get('name')} (£{row.get('variance_at_risk_gbp', 0):,.0f})"
            for row in ranked[:4]
        )
        return self._answer(
            question,
            f"Across {len(scorecards)} suppliers, the most variance sits with {top}.",
            [
                {
                    "label": str(row.get("supplier", {}).get("name")),
                    "value": f"£{row.get('variance_at_risk_gbp', 0):,.0f}",
                }
                for row in ranked[:4]
            ],
            [{"label": "Supplier scorecards", "route": "/suppliers"}, {"label": "Variance matrix", "route": "/analytics"}],
            bullets=[
                f"{row.get('supplier', {}).get('name')} ({row.get('supplier', {}).get('type')}): "
                f"{row.get('invoice_count', 0)} invoices worth £{row.get('invoice_value_gbp', 0):,.0f}, "
                f"£{row.get('variance_at_risk_gbp', 0):,.0f} variance at risk, "
                f"{(row.get('rate_card_compliance_rate', 0) * 100):.0f}% rate compliance, "
                f"{(row.get('dispute_rate', 0) * 100):.0f}% dispute rate"
                for row in ranked[:5]
            ],
            follow_ups=["Are any policies out of date?", "How much leakage have we prevented?"],
        )

    def _policies(self, question: str) -> dict[str, Any]:
        """Policies past their review date that are still being used to validate charges."""
        registry = self.analytics.rate_card_registry()
        stale = [card for card in registry if card.get("is_stale")]
        stale_in_force = [card for card in stale if card.get("is_in_force")]
        return self._answer(
            question,
            f"{len(stale)} of {len(registry)} policies are past their review date, and "
            f"{len(stale_in_force)} of those are still in force — those are the ones to worry about, "
            "because live invoices are being validated against contracts nobody has re-confirmed."
            if stale
            else f"All {len(registry)} policies are within their review window.",
            [
                {"label": "Policies", "value": str(len(registry))},
                {"label": "Past review", "value": str(len(stale))},
                {"label": "Stale and in force", "value": str(len(stale_in_force))},
            ],
            [{"label": "Open Policies", "route": "/rate-cards"}],
            bullets=[
                f"{card.get('id')} for {card.get('supplier_name')}: review was due "
                f"{card.get('review_due_date')}, still validating "
                f"{card.get('lines_validated_against', 0):,} lines and has found "
                f"£{card.get('variance_found_gbp', 0):,.0f} of variance"
                for card in stale_in_force[:5]
            ]
            or ["Every policy is inside its review window, so no charge is being validated against a stale contract."],
            follow_ups=["Which suppliers have the most variance?", "How much leakage have we prevented?"],
        )

    def _payments(self, question: str) -> dict[str, Any]:
        """The payment board: what is authorised, blocked or waiting."""
        lanes = self._lanes()
        return self._answer(
            question,
            "On the payment board: "
            + ", ".join(f"{lane.get('count', 0)} {str(lane.get('title')).lower()}" for lane in lanes)
            + ". Releasing requires a different identity from the one that authorised it.",
            [
                {"label": str(lane.get("title")), "value": f"{lane.get('count', 0)} · £{lane.get('value_gbp', 0):,.0f}"}
                for lane in lanes
            ],
            [{"label": "Approvals and payments", "route": "/approvals"}],
            bullets=[
                f"{lane.get('title')}: {lane.get('count', 0)} payments worth "
                f"£{lane.get('value_gbp', 0):,.0f} — {lane.get('description')}"
                for lane in lanes
            ],
            follow_ups=["What is our total outlay?", "What needs my attention today?"],
        )

    def _outlay(self, question: str) -> dict[str, Any]:
        """Total outlay: what the estate has cost and where it is sitting."""
        stats = self.claims.statistics()
        kpis = self.analytics.kpis()
        lanes = self._lanes()
        released = next((lane.get("value_gbp", 0) for lane in lanes if lane.get("key") == "released"), 0)
        held = next((lane.get("value_gbp", 0) for lane in lanes if lane.get("key") == "authorise"), 0)
        blocked = next((lane.get("value_gbp", 0) for lane in lanes if lane.get("key") == "blocked"), 0)
        return self._answer(
            question,
            f"£{stats.get('invoiced_gbp', 0):,.0f} has been invoiced against claims. Of that, "
            f"£{released:,.0f} has been paid out, £{held:,.0f} is held pending authorisation and "
            f"£{blocked:,.0f} was stopped before it left. £{kpis.get('leakage_prevented_gbp', 0):,.0f} "
            "of overcharging was caught by the validation agents.",
            [
                {"label": "Invoiced", "value": f"£{stats.get('invoiced_gbp', 0):,.0f}"},
                {"label": "Paid out", "value": f"£{released:,.0f}"},
                {"label": "Held", "value": f"£{held:,.0f}"},
                {"label": "Stopped", "value": f"£{blocked:,.0f}"},
            ],
            [
                {"label": "Approvals and payments", "route": "/approvals"},
                {"label": "Benefits tracker", "route": "/benefits"},
            ],
            bullets=[
                f"Reserve position: £{stats.get('reserve_gbp', 0):,.0f} is reserved across "
                f"{stats.get('total_claims', 0)} claims, so the estate is running at "
                f"{stats.get('reserve_utilisation_pct', 0)}% of reserve.",
                f"{stats.get('over_reserve_count', 0)} claims are invoiced above their own reserve and "
                "need a handler to either re-reserve or challenge the spend.",
                f"Average outlay per claim is roughly "
                f"£{(stats.get('invoiced_gbp', 0) / max(1, stats.get('total_claims', 1))):,.0f}.",
                f"The £{blocked:,.0f} that was stopped never left the business: those invoices were "
                "blocked as duplicates or outside tolerance before any payment was raised.",
            ],
            follow_ups=[
                "Which claims are over reserve?",
                "How much leakage have we prevented?",
                "Which suppliers have the most variance?",
            ],
        )

    def _entity(self, question: str, reference: str) -> dict[str, Any]:
        """Answer about one specific claim, invoice, supplier or policy by reference."""
        upper = reference.upper()
        claim = self.repository.claims.get(upper)
        if claim is not None:
            rows = [row for row in self.claims.list_claims(limit=300) if row.get("claim", {}).get("id") == upper]
            row = rows[0] if rows else {}
            orders = self.repository.claim_work_orders(upper)
            return self._answer(
                question,
                f"{upper} is {claim.customer_name or 'an unnamed policyholder'}'s "
                f"{claim.incident_type.replace('_', ' ')} claim from {claim.incident_date}, currently "
                f"{claim.workflow_status.replace('_', ' ')}. It carries {row.get('invoice_count', 0)} invoices "
                f"worth £{row.get('invoiced_gbp', 0):,.0f} against a £{claim.reserve_gbp:,.0f} reserve, with "
                f"{len(orders)} supplier work order{'' if len(orders) == 1 else 's'} and "
                f"{row.get('photo_count', 0)} photographs on file.",
                [
                    {"label": "Stage", "value": claim.workflow_status.replace("_", " ")},
                    {"label": "Invoiced", "value": f"£{row.get('invoiced_gbp', 0):,.0f}"},
                    {"label": "Reserve", "value": f"£{claim.reserve_gbp:,.0f}"},
                    {"label": "Variance", "value": f"£{row.get('variance_gbp', 0):,.0f}"},
                ],
                [{"label": f"Open {upper}", "route": f"/claim/{upper}"}],
                bullets=[
                    f"Policyholder: {claim.customer_name or 'not recorded'} · "
                    f"{claim.insurance_number or 'no insurance number'} · "
                    f"{claim.contact_number or 'no contact number'}",
                    f"Incident: {claim.description[:190]}{'…' if len(claim.description) > 190 else ''}",
                    f"Assessment: {claim.severity.replace('_', ' ')}; vehicle "
                    f"{claim.vehicle_registration or 'registration not recorded'} is "
                    f"{claim.vehicle_drivable or 'of unrecorded mobility'}; services requested: "
                    f"{', '.join(claim.recommended_services) or 'none yet'}",
                    (
                        "Suppliers instructed: "
                        + ", ".join(
                            f"{self._supplier_name(order.supplier_id)} ({order.service_type}, {order.status.replace('_', ' ')})"
                            for order in orders
                        )
                        if orders
                        else "No suppliers instructed yet — this claim still needs triage."
                    ),
                    f"Reported {claim.reported_at or 'at an unrecorded time'} via "
                    f"{claim.report_channel.replace('_', ' ') or 'an unrecorded channel'} by "
                    f"{claim.reported_by or 'an unrecorded reporter'}.",
                ],
                follow_ups=["What needs my attention today?", "Which claims are over reserve?"],
            )

        invoice = self.repository.get_invoice(upper) or next(
            (item for item in self.repository.invoices.values() if item.invoice_number.upper() == upper), None
        )
        if invoice is not None:
            outside = [line for line in invoice.lines if line.tolerance_outcome == "outside"]
            variance = sum(abs(line.variance_gbp) for line in outside)
            return self._answer(
                question,
                f"{invoice.invoice_number} is £{invoice.gross_gbp:,.2f} gross from "
                f"{self._supplier_name(invoice.supplier_id)}, status {invoice.status}, on claim "
                f"{invoice.claim_id or 'no matched claim'}. "
                + (
                    f"{len(outside)} line{'' if len(outside) == 1 else 's'} are outside tolerance, "
                    f"£{variance:,.2f} of variance."
                    if outside
                    else "Every line is within contracted tolerance."
                )
                + (f" Exception raised: {invoice.exception_reason.replace('_', ' ')}." if invoice.exception_reason else ""),
                [
                    {"label": "Status", "value": invoice.status},
                    {"label": "Gross", "value": f"£{invoice.gross_gbp:,.2f}"},
                    {"label": "Lines outside", "value": str(len(outside))},
                    {"label": "Variance", "value": f"£{variance:,.2f}"},
                ],
                [{"label": f"Open {invoice.invoice_number}", "route": f"/invoice/{invoice.id}"}]
                + ([{"label": f"Open {invoice.claim_id}", "route": f"/claim/{invoice.claim_id}"}] if invoice.claim_id else []),
            )

        supplier = self.repository.get_supplier(upper)
        if supplier is not None:
            card = next(
                (row for row in self.analytics.supplier_scorecards() if row.get("supplier", {}).get("id") == upper),
                {},
            )
            return self._answer(
                question,
                f"{supplier.name} is a {supplier.type} paid by {supplier.payment_path}. They have sent "
                f"{card.get('invoice_count', 0)} invoices worth £{card.get('invoice_value_gbp', 0):,.0f}, with "
                f"£{card.get('variance_at_risk_gbp', 0):,.0f} of variance at risk and a "
                f"{(card.get('rate_card_compliance_rate', 0) * 100):.1f}% rate compliance.",
                [
                    {"label": "Invoices", "value": str(card.get("invoice_count", 0))},
                    {"label": "Value", "value": f"£{card.get('invoice_value_gbp', 0):,.0f}"},
                    {"label": "Variance at risk", "value": f"£{card.get('variance_at_risk_gbp', 0):,.0f}"},
                    {"label": "Straight through", "value": f"{(card.get('straight_through_rate', 0) * 100):.0f}%"},
                ],
                [{"label": "Supplier scorecards", "route": "/suppliers"}, {"label": "Their invoices", "route": f"/queue?supplier={upper}"}],
            )

        return self._fallback(question)

    def _disputes(self, question: str) -> dict[str, Any]:
        """Invoices queried with a supplier."""
        kpis = self.analytics.kpis()
        disputes = list(self.repository.disputes.values())
        return self._answer(
            question,
            f"{kpis.get('queried_or_awaiting_information', 0)} invoices are queried or awaiting information, "
            f"with {len(disputes)} dispute thread{'' if len(disputes) == 1 else 's'} open with suppliers.",
            [
                {"label": "Queried invoices", "value": str(kpis.get("queried_or_awaiting_information", 0))},
                {"label": "Dispute threads", "value": str(len(disputes))},
            ],
            [{"label": "Open disputes", "route": "/disputes"}, {"label": "Queried queue", "route": "/queue?status=Queried"}],
            bullets=[
                "A dispute is raised automatically when a line is outside the contracted tolerance, "
                "with the specific line and the variance quoted to the supplier.",
                f"£{self.analytics.kpis().get('leakage_prevented_gbp', 0):,.0f} of the disputed value has "
                "already been withheld, so none of it has left the business.",
                "Nothing on this list is waiting on us: each one is with the supplier for a corrected "
                "invoice or an explanation.",
            ],
            follow_ups=["Which suppliers have the most variance?", "What exceptions are open?"],
        )

    def _evidence(self, question: str) -> dict[str, Any]:
        """Photographic evidence held against claims."""
        stats = self.claims.statistics()
        with_photos = len(self.repository.claim_attachments)
        return self._answer(
            question,
            f"{stats.get('photographs', 0)} incident photographs are held across {with_photos} claims, "
            "which is what lets a handler instruct suppliers without a physical inspection.",
            [
                {"label": "Photographs", "value": str(stats.get("photographs", 0))},
                {"label": "Claims with evidence", "value": str(with_photos)},
            ],
            [{"label": "Open Claim 360", "route": "/claims"}],
        )

    def _fallback(self, question: str) -> dict[str, Any]:
        """Search the estate, so an unmatched question still does something useful."""
        hits = self.search.search(question, limit=6)
        groups = hits.get("groups", {}) or {}
        flattened = [hit for items in groups.values() for hit in (items or [])]
        if flattened:
            return self._answer(
                question,
                f"I could not map that to a report, but I found {len(flattened)} matching record"
                f"{'' if len(flattened) == 1 else 's'} in the estate.",
                [],
                [{"label": str(hit.get("title")), "route": str(hit.get("route"))} for hit in flattened[:5]],
            )
        return self._answer(
            question,
            "I could not match that to anything I track. Try asking about claims awaiting triage, "
            "claims over reserve, open exceptions, straight-through processing, leakage, suppliers, "
            "policies, or payments awaiting release.",
            [],
            [{"label": "Dashboard", "route": "/dashboard"}],
        )

    # ------------------------------------------------------------------ helpers

    def _lanes(self) -> list[dict[str, Any]]:
        """Return the payment board lanes. The board returns a list, not a map, of lanes."""
        board = self.board.board(limit_per_lane=1)
        lanes = board.get("lanes")
        return list(lanes) if isinstance(lanes, list) else []

    def _lane_count(self, key: str) -> int:
        """Return how many payments sit in one lane."""
        for lane in self._lanes():
            if lane.get("key") == key:
                return int(lane.get("count", 0))
        return 0

    def _supplier_name(self, supplier_id: str) -> str:
        """Return a supplier's display name, falling back to the id."""
        supplier = self.repository.get_supplier(supplier_id)
        return supplier.name if supplier is not None else supplier_id

    @staticmethod
    def _reference_in(text: str) -> str:
        """Return the first claim, invoice or supplier reference mentioned in the question."""
        match = re.search(r"\b(CLM-\d{3,6}|INVREC-\d{4,8}|INV-\d{4,8}|SUP-\d{2,4})\b", text, re.IGNORECASE)
        return match.group(1) if match else ""

    @staticmethod
    def _answer(
        question: str,
        text: str,
        metrics: list[dict[str, str]],
        links: list[dict[str, str]],
        bullets: list[str] | None = None,
        follow_ups: list[str] | None = None,
    ) -> dict[str, Any]:
        """Shape one answer.

        `bullets` carry the detail behind the headline sentence and `follow_ups` are the questions
        a handler usually asks next, so an answer leads somewhere instead of ending the exchange.
        """
        return {
            "question": question,
            "text": text,
            "metrics": metrics,
            "links": links,
            "bullets": bullets or [],
            "follow_ups": follow_ups or [],
        }
