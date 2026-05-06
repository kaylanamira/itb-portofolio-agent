from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.query_rewriter import query_rewriter
from agent.nodes.planner import planner, route_after_planner
from agent.sql_pipeline import sql_pipeline, route_after_sql_pipeline
from agent.nodes.step_executor import step_executor, route_from_step_executor
from agent.nodes.step_reasoner import step_reasoner, route_after_reasoning
from agent.nodes.synthesizer import synthesizer
from agent.nodes.clarification_handler import clarification_handler

async def rag_retriever(state: AgentState) -> dict:
    return {"rag_chunks": [{"content": "Placeholder RAG result"}], "rag_query": state.get("effective_query")}

portfolio_graph = StateGraph(AgentState)
portfolio_graph.add_node("query_rewriter", query_rewriter)
portfolio_graph.add_node("planner", planner)
portfolio_graph.add_node("step_executor", step_executor)
portfolio_graph.add_node("sql_pipeline", sql_pipeline)
portfolio_graph.add_node("rag_retriever", rag_retriever)
portfolio_graph.add_node("step_reasoner", step_reasoner)
portfolio_graph.add_node("synthesizer", synthesizer)
portfolio_graph.add_node("clarification_handler", clarification_handler)

portfolio_graph.set_entry_point("query_rewriter")
portfolio_graph.add_edge("query_rewriter", "planner")

portfolio_graph.add_conditional_edges("planner", route_after_planner, {
    "clarification_handler": "clarification_handler",
    "step_executor": "step_executor"
})

portfolio_graph.add_conditional_edges("step_executor", route_from_step_executor, {
    "sql_pipeline": "sql_pipeline",
    "rag_retriever": "rag_retriever",
    "synthesizer": "synthesizer"
})

portfolio_graph.add_conditional_edges("sql_pipeline", route_after_sql_pipeline, {
    "synthesizer": "synthesizer",
    "step_reasoner": "step_reasoner"
})

portfolio_graph.add_edge("rag_retriever", "step_reasoner")

portfolio_graph.add_conditional_edges("step_reasoner", route_after_reasoning, {
    "step_executor": "step_executor",
    "synthesizer": "synthesizer"
})

portfolio_graph.add_edge("clarification_handler", END)
portfolio_graph.add_edge("synthesizer", END)

portfolio_graph = portfolio_graph.compile()
