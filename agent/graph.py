from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.query_rewriter import query_rewriter
from agent.nodes.query_classifier import query_classifier, route_after_classification
from agent.nodes.schema_linker import schema_linker
from agent.nodes.sql_generator import sql_generator
from agent.nodes.sql_validator import sql_validator, route_after_validation
from agent.nodes.sql_executor import sql_executor, route_after_executor
from agent.nodes.answer_validator import answer_validator, route_after_answer_validator
from agent.nodes.response_formatter import response_formatter
from agent.nodes.error_handler import error_handler, route_after_error_handler
from agent.nodes.clarification_handler import clarification_handler

async def rag_retriever(state: AgentState) -> dict:
    return {"rag_chunks": [], "rag_query": state.get("effective_query")}

portfolio_graph = StateGraph(AgentState)

portfolio_graph.add_node("query_rewriter", query_rewriter)
portfolio_graph.add_node("query_classifier", query_classifier)
portfolio_graph.add_node("schema_linker", schema_linker)
portfolio_graph.add_node("sql_generator", sql_generator)
portfolio_graph.add_node("sql_validator", sql_validator)
portfolio_graph.add_node("sql_executor", sql_executor)
portfolio_graph.add_node("answer_validator", answer_validator)
portfolio_graph.add_node("response_formatter", response_formatter)
portfolio_graph.add_node("error_handler", error_handler)
portfolio_graph.add_node("clarification_handler", clarification_handler)
portfolio_graph.add_node("rag_retriever", rag_retriever)

portfolio_graph.set_entry_point("query_rewriter")

portfolio_graph.add_edge("query_rewriter", "query_classifier")

portfolio_graph.add_conditional_edges("query_classifier", route_after_classification, {
    "schema_linker": "schema_linker",
    "response_formatter": "response_formatter",
    "clarification_handler": "clarification_handler",
    "rag_retriever": "rag_retriever",
})

portfolio_graph.add_edge("schema_linker", "sql_generator")
portfolio_graph.add_edge("sql_generator", "sql_validator")

portfolio_graph.add_conditional_edges("sql_validator", route_after_validation, {
    "sql_executor": "sql_executor",
    "error_handler": "error_handler",
})

portfolio_graph.add_conditional_edges("sql_executor", route_after_executor, {
    "answer_validator": "answer_validator",
    "error_handler": "error_handler",
})

portfolio_graph.add_conditional_edges("answer_validator", route_after_answer_validator, {
    "response_formatter": "response_formatter",
    "error_handler": "error_handler",
})

portfolio_graph.add_conditional_edges("error_handler", route_after_error_handler, {
    "sql_generator": "sql_generator",
    "response_formatter": "response_formatter",
})

portfolio_graph.add_edge("rag_retriever", "response_formatter")
portfolio_graph.add_edge("clarification_handler", END)
portfolio_graph.add_edge("response_formatter", END)

portfolio_graph = portfolio_graph.compile()
