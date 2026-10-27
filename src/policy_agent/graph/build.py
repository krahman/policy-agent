"""Graph assembly: nodes, conditional edges and the human-approval interrupt (PRD §6, §9.3)."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from policy_agent.graph.nodes import Deps, make_nodes
from policy_agent.graph.state import MAX_REPAIRS, AgentState


def build_graph(deps: Deps, checkpointer: BaseCheckpointSaver | None = None):
    n = make_nodes(deps)
    g = StateGraph(AgentState)
    for name, fn in n.items():
        g.add_node(name, fn)

    g.add_edge(START, "guard_input")
    g.add_conditional_edges(
        "guard_input", lambda s: "refuse" if s["route"] == "unsafe" else "route", ["refuse", "route"]
    )
    g.add_conditional_edges(
        "route",
        lambda s: {"answerable": "act", "ambiguous": "clarify", "out_of_scope": "abstain"}.get(s["route"], "refuse"),
        ["act", "clarify", "abstain", "refuse"],
    )
    g.add_edge("act", "assess")
    g.add_conditional_edges("assess", lambda s: s["next_node"], ["plan", "synthesize", "abstain"])
    g.add_edge("plan", "act")
    g.add_edge("synthesize", "validate")

    def after_validate(s) -> str:
        retry = s["violations"] and s["repairs"] <= MAX_REPAIRS and not (s.get("answer") or {}).get("downgraded")
        if retry and not _final(s):
            return "synthesize"
        return "report" if s.get("want_report") else END

    def _final(s) -> bool:  # a passing answer has no violations; a downgraded one is final too
        return not s["violations"] or bool((s.get("answer") or {}).get("downgraded"))

    g.add_conditional_edges("validate", after_validate, ["synthesize", "report", END])
    for terminal in ("clarify", "abstain", "refuse"):
        g.add_conditional_edges(terminal, lambda s: "report" if s.get("want_report") else END, ["report", END])
    g.add_edge("report", END)
    return g.compile(checkpointer=checkpointer)
