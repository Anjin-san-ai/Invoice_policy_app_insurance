"""Agent topology reader for the Agent Studio module."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pyhocon import ConfigFactory
from pyhocon.exceptions import ConfigException

logger = logging.getLogger(__name__)

DEFAULT_NETWORK_PATH = Path("registries/apps/invoice_to_pay.hocon")


class AgentNetworkTopology:
    """Derive the agent graph from the Neuro SAN HOCON definition.

    Spec section 13.14 requires the Agent Studio graph to be rendered from the HOCON definition
    rather than a hand-maintained copy, so this reads the registry file directly. The `include` of
    config/llm_config.hocon is resolved relative to registries/, so parsing is done with that as the
    base directory.
    """

    @staticmethod
    def describe(network_path: Path = DEFAULT_NETWORK_PATH) -> dict[str, Any]:
        """Return nodes and edges for the agent network graph."""
        if not network_path.exists():
            logger.error("Agent network file not found: %s", network_path)
            return {"error": f"Agent network file not found: {network_path}", "nodes": [], "edges": []}
        try:
            config = ConfigFactory.parse_file(str(network_path))
        except (ConfigException, OSError) as exc:
            logger.error("Could not parse agent network %s: %s", network_path, exc)
            return {"error": f"Could not parse {network_path}: {exc}", "nodes": [], "edges": []}

        tools = config.get("tools", [])
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        for index, tool in enumerate(tools):
            name = tool.get("name", None)
            if not name:
                logger.warning("Skipping tool at index %d with no name in %s", index, network_path)
                continue
            # pyhocon's ConfigTree.get raises ConfigMissingException unless a default is passed,
            # so every optional key below is read with an explicit default.
            down_chain = list(tool.get("tools", []) or [])
            coded_class = tool.get("class", None)
            function = tool.get("function", {}) or {}
            nodes.append(
                {
                    "name": name,
                    "kind": "coded_tool" if coded_class else "llm_agent",
                    "is_front_man": index == 0 and not coded_class,
                    "description": function.get("description", ""),
                    "coded_class": coded_class,
                    "down_chain": down_chain,
                }
            )
            for target in down_chain:
                edges.append({"source": name, "target": target})

        return {
            "source_file": str(network_path).replace("\\", "/"),
            "llm_class": AgentNetworkTopology._llm_class(config),
            "max_steps": config.get("max_steps", None),
            "max_execution_seconds": config.get("max_execution_seconds", None),
            "llm_agent_count": sum(1 for node in nodes if node.get("kind") == "llm_agent"),
            "coded_tool_count": sum(1 for node in nodes if node.get("kind") == "coded_tool"),
            "nodes": nodes,
            "edges": edges,
        }

    @staticmethod
    def _llm_class(config: Any) -> str | None:
        """Return the configured LLM provider class, reading the fallback chain head if present."""
        llm_config = config.get("llm_config", {}) or {}
        fallbacks = llm_config.get("fallbacks", []) or []
        if fallbacks:
            head = fallbacks[0]
            return f"{head.get('class', 'unknown')}:{head.get('model_name', 'unknown')}"
        return llm_config.get("class", None)
