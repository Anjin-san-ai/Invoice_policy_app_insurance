"""Tests for the Neuro SAN agent topology exposed to the Agent Studio module."""

from pathlib import Path

from apps.invoice_to_pay.backend.app.services.agent_network import AgentNetworkTopology

NETWORK_PATH = Path("registries/apps/invoice_to_pay.hocon")

# Spec section 11.2 names twelve agents; agent 1 is the front man.
EXPECTED_AGENTS = {
    "Invoice_Orchestrator",
    "Intake_And_Classification_Agent",
    "Extraction_Agent",
    "Redaction_Agent",
    "Claim_Matching_Agent",
    "Rate_Card_Validation_Agent",
    "Entitlement_And_Authorisation_Agent",
    "Tolerance_And_Anomaly_Agent",
    "Settlement_And_Dispute_Agent",
    "Exception_Router_Agent",
    "Communications_Agent",
    "Payment_And_Writeback_Agent",
}


class TestAgentNetworkTopology:
    """Validate the declared agent network matches the mandated topology."""

    def test_all_twelve_agents_are_declared(self) -> None:
        topology = AgentNetworkTopology.describe(NETWORK_PATH)
        names = {node.get("name") for node in topology.get("nodes", []) if node.get("kind") == "llm_agent"}
        assert names == EXPECTED_AGENTS
        assert topology.get("llm_agent_count") == 12

    def test_front_man_is_an_llm_agent(self) -> None:
        """The Front Man must never be a coded or toolbox tool."""
        topology = AgentNetworkTopology.describe(NETWORK_PATH)
        front_men = [node for node in topology.get("nodes", []) if node.get("is_front_man")]
        assert len(front_men) == 1
        assert front_men[0].get("name") == "Invoice_Orchestrator"
        assert front_men[0].get("kind") == "llm_agent"
        assert front_men[0].get("coded_class") is None

    def test_deterministic_logic_stays_in_a_coded_tool(self) -> None:
        topology = AgentNetworkTopology.describe(NETWORK_PATH)
        coded = [node for node in topology.get("nodes", []) if node.get("kind") == "coded_tool"]
        assert len(coded) == 1
        assert coded[0].get("coded_class") == "coded_tools.invoice_to_pay.invoice_pipeline_tool.InvoicePipelineTool"

    def test_execution_budget_is_bounded(self) -> None:
        """Every network must set max_steps and max_execution_seconds."""
        topology = AgentNetworkTopology.describe(NETWORK_PATH)
        assert isinstance(topology.get("max_steps"), int)
        assert isinstance(topology.get("max_execution_seconds"), int)
        assert topology.get("max_steps", 0) > 0
        assert topology.get("max_execution_seconds", 0) > 0

    def test_missing_network_file_reports_an_error(self) -> None:
        """A missing file must be reported, never silently swallowed."""
        topology = AgentNetworkTopology.describe(Path("registries/apps/does_not_exist.hocon"))
        assert "error" in topology
        assert topology.get("nodes") == []
