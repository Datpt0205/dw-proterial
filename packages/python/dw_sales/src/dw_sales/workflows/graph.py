"""The versioned graph, registered on the runtime seam.

Typed state and a version in the registry key, because a run records the graph
version it started on and a resume replays that exact one.
"""

from __future__ import annotations

from typing import Any, TypedDict

GRAPH_ID = "sales"
GRAPH_VERSION = "1.0.0"


class SalesState(TypedDict, total=False):
    subject: str
    summary: str


def build_graph() -> Any:
    """Built lazily so importing this module needs no LangGraph at test time."""
    from langgraph.graph import END, START, StateGraph

    def summarise(state: SalesState) -> SalesState:
        return {"summary": state.get("subject", "").strip()}

    graph: StateGraph[SalesState, None, SalesState, SalesState] = StateGraph(SalesState)
    graph.add_node("summarise", summarise)
    graph.add_edge(START, "summarise")
    graph.add_edge("summarise", END)
    return graph.compile()
