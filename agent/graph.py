from agent.state import QueryType
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.query_rewriter import query_rewriter
from agent.nodes.planner import planner
# from agent.sql_pipeline import sql_pipeline, route_after_sql_pipeline
from agent.nodes.sql_pipeline import sql_pipeline, route_after_sql_pipeline
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
    elif tool == "sql":
        return "sql_pipeline"
        
    return "synthesizer"
def build_portfolio_graph():
    graph = StateGraph(AgentState)
    graph.add_node("query_rewriter", query_rewriter)
    graph.add_node("planner", planner)
    graph.add_node("sql_pipeline", sql_pipeline)
    graph.add_node("rag_retriever", rag_retriever)
    graph.add_node("step_reasoner", step_reasoner)
    graph.add_node("synthesizer", synthesizer)
    graph.add_node("clarification_handler", clarification_handler)

    graph.set_entry_point("query_rewriter")
    graph.add_edge("query_rewriter", "planner")

    graph.add_conditional_edges("planner", route_next_step, {
        "clarification_handler": "clarification_handler",
        "sql_pipeline": "sql_pipeline",
        "rag_retriever": "rag_retriever",
        "synthesizer": "synthesizer"
    })

    graph.add_conditional_edges("sql_pipeline", route_after_sql_pipeline, {
        "synthesizer": "synthesizer",
        "step_reasoner": "step_reasoner"
    })

    graph.add_edge("rag_retriever", "step_reasoner")

    graph.add_conditional_edges("step_reasoner", route_next_step, {
        "sql_pipeline": "sql_pipeline",
        "rag_retriever": "rag_retriever",
        "synthesizer": "synthesizer"
    })

    graph.add_edge("clarification_handler", END)
    graph.add_edge("synthesizer", END)
    # graph.add_edge("synthesizer", "faithfulness_checker")
    # graph.add_edge("faithfulness_checker", END)

    return graph.compile()


portfolio_graph = build_portfolio_graph()
