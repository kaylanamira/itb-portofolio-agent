from agent.state import QueryType
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.query_rewriter import query_rewriter
from agent.nodes.planner import planner
from agent.nodes.wisudawan_pipeline import wisudawan_pipeline, route_after_wisudawan_pipeline
from agent.nodes.step_reasoner import step_reasoner
from agent.nodes.synthesizer import synthesizer
from agent.nodes.clarification_handler import clarification_handler
from agent.nodes.rag_retriever import rag_retriever


def route_next_step(state: AgentState) -> str:
    if state.get("query_type") == QueryType.CLARIFICATION_NEEDED:
        return "clarification_handler"

    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)

    if idx >= len(plan):
        return "synthesizer"

    tool = plan[idx].get("tool", "sql")
    if tool == "rag":
        return "rag_retriever"
    return "wisudawan_pipeline"


def build_wisudawan_graph():
    graph = StateGraph(AgentState)
    graph.add_node("query_rewriter", query_rewriter)
    graph.add_node("planner", planner)
    graph.add_node("wisudawan_pipeline", wisudawan_pipeline)
    graph.add_node("rag_retriever", rag_retriever)
    graph.add_node("step_reasoner", step_reasoner)
    graph.add_node("synthesizer", synthesizer)
    graph.add_node("clarification_handler", clarification_handler)

    graph.set_entry_point("query_rewriter")
    graph.add_edge("query_rewriter", "planner")

    graph.add_conditional_edges("planner", route_next_step, {
        "clarification_handler": "clarification_handler",
        "wisudawan_pipeline": "wisudawan_pipeline",
        "rag_retriever": "rag_retriever",
        "synthesizer": "synthesizer",
    })

    graph.add_conditional_edges("wisudawan_pipeline", route_after_wisudawan_pipeline, {
        "synthesizer": "synthesizer",
        "step_reasoner": "step_reasoner",
    })

    graph.add_edge("rag_retriever", "step_reasoner")

    graph.add_conditional_edges("step_reasoner", route_next_step, {
        "wisudawan_pipeline": "wisudawan_pipeline",
        "rag_retriever": "rag_retriever",
        "synthesizer": "synthesizer",
    })

    graph.add_edge("clarification_handler", END)
    graph.add_edge("synthesizer", END)

    return graph.compile()


wisudawan_graph = build_wisudawan_graph()
