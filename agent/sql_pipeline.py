from agent.nodes.schema_linker import schema_linker
from agent.nodes.sql_generator import sql_generator
from agent.nodes.sql_validator import sql_validator, route_after_validation
from agent.nodes.sql_executor import sql_executor, route_after_executor
from agent.nodes.answer_validator import answer_validator, route_after_answer_validator
from agent.nodes.error_handler import error_handler, route_after_error_handler
from langgraph.graph import StateGraph, END
from agent.state import AgentState

sql_pipeline = StateGraph(AgentState)
sql_pipeline.add_node("schema_linker", schema_linker)
sql_pipeline.add_node("sql_generator", sql_generator)
sql_pipeline.add_node("sql_validator", sql_validator)
sql_pipeline.add_node("sql_executor", sql_executor)
sql_pipeline.add_node("answer_validator", answer_validator)
sql_pipeline.add_node("error_handler", error_handler)

sql_pipeline.set_entry_point("schema_linker")
sql_pipeline.add_edge("schema_linker", "sql_generator")
sql_pipeline.add_edge("sql_generator", "sql_validator")

sql_pipeline.add_conditional_edges("sql_validator", route_after_validation, {
    "sql_executor": "sql_executor",
    "error_handler": "error_handler",
})

sql_pipeline.add_conditional_edges("sql_executor", route_after_executor, {
    "answer_validator": "answer_validator",
    "error_handler": "error_handler",
})

sql_pipeline.add_conditional_edges("answer_validator", route_after_answer_validator, {
    "step_reasoner": END,
    "error_handler": "error_handler",
})

sql_pipeline.add_conditional_edges("error_handler", route_after_error_handler, {
    "sql_generator": "sql_generator",
    "synthesizer": END,
})

sql_pipeline = sql_pipeline.compile()

def route_after_sql_pipeline(state: AgentState) -> str:
    if state.get("is_aborted", False):
        return "synthesizer"
    return "step_reasoner"