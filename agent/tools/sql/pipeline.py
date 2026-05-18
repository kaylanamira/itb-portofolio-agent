"""Option A — domain-agnostic SQL pipeline as a LangGraph subgraph over SQLState."""

from __future__ import annotations

from typing import Any, Callable, Optional

from langgraph.graph import StateGraph, END

from agent.tools.sql.state import SQLState
from agent.tools.sql.tool import SQLTool


def build_sql_pipeline(
    schema_linker_prompt: str,
    entity_resolver: Callable[[dict], Any],
    few_shot_examples: Callable[[Optional[str]], str],
    schema_context: str,
    default_table: str,
    max_attempts: int = 3,
    human_message_builder: Optional[Callable] = None,
    domain_rules: str = "",
):
    """
    Builds a compiled LangGraph subgraph for the SQL pipeline.

    Input: domain-specific callables and config.
    Output: compiled StateGraph[SQLState].
    """
    tool = SQLTool(
        schema_linker_prompt=schema_linker_prompt,
        entity_resolver=entity_resolver,
        few_shot_examples=few_shot_examples,
        schema_context=schema_context,
        default_table=default_table,
        max_attempts=max_attempts,
        human_message_builder=human_message_builder,
        domain_rules=domain_rules,
    )

    async def schema_linker(state: SQLState) -> dict:
        result = await tool.link_schema(
            question=state["question"],
            user_scope=state["user_scope"],
            plan_step_context=state.get("plan_step_context"),
        )
        return {
            "detected_entities": result["detected_entities"],
            "relevant_tables": result["relevant_tables"],
            "schema_context": schema_context,
        }

    async def sql_generator(state: SQLState) -> dict:
        sql = await tool.generate_sql(
            question=state["question"],
            detected_entities=state.get("detected_entities"),
            user_scope=state["user_scope"],
            relevant_tables=state.get("relevant_tables", [default_table]),
            query_type=state.get("query_type"),
            plan_step_context=state.get("plan_step_context"),
            error_history=state.get("error_history", []),
            attempt_count=state.get("attempt_count", 0),
        )
        return {"generated_sql": sql}

    async def sql_validator(state: SQLState) -> dict:
        result = await tool.validate_sql(state.get("generated_sql", ""))
        if result["validation_status"] != "pass":
            return {
                "validation_status": result["validation_status"],
                "validation_errors": [result["error"]],
                "error_history": [{
                    "attempt": state.get("attempt_count", 0),
                    "sql": state.get("generated_sql", ""),
                    "error": result["error"],
                    "type": result["error_type"],
                }],
            }
        return {"validation_status": "pass"}

    async def sql_executor(state: SQLState) -> dict:
        return await tool.execute_sql(
            generated_sql=state.get("generated_sql", ""),
            user_scope=state["user_scope"],
            relevant_tables=state.get("relevant_tables"),
        )

    async def answer_validator(state: SQLState) -> dict:
        result = await tool.validate_answer(
            question=state["question"],
            generated_sql=state.get("generated_sql", ""),
            sql_result=state.get("sql_result"),
            sql_row_count=state.get("sql_row_count", 0),
            plan_step_context=state.get("plan_step_context"),
        )
        if not result["answer_is_valid"]:
            return {
                "answer_is_valid": False,
                "error_history": [{
                    "attempt": state.get("attempt_count", 0),
                    "sql": state.get("generated_sql", ""),
                    "error": f"Answer validation failed: {result.get('reason', '')}",
                    "type": "answer_invalid",
                }],
            }
        return {"answer_is_valid": True}

    async def error_handler(state: SQLState) -> dict:
        new_attempt = state.get("attempt_count", 0) + 1
        if new_attempt <= max_attempts:
            return {
                "attempt_count": new_attempt,
                "generated_sql": None,
                "sql_result": None,
                "sql_error": None,
            }
        return {
            "attempt_count": new_attempt,
            "is_aborted": True,
            "abort_reason": "MAX_RETRIES_EXCEEDED",
        }

    def route_after_validation(state: SQLState) -> str:
        if state.get("validation_status") == "pass":
            return "sql_executor"
        return "error_handler"

    def route_after_executor(state: SQLState) -> str:
        if state.get("sql_error") is None:
            return "answer_validator"
        return "error_handler"

    def route_after_answer_validator(state: SQLState) -> str:
        if state.get("answer_is_valid", False):
            return END
        return "error_handler"

    def route_after_error_handler(state: SQLState) -> str:
        if state.get("is_aborted", False) or state.get("attempt_count", 0) >= max_attempts:
            return END
        return "sql_generator"

    graph = StateGraph(SQLState)
    graph.add_node("schema_linker", schema_linker)
    graph.add_node("sql_generator", sql_generator)
    graph.add_node("sql_validator", sql_validator)
    graph.add_node("sql_executor", sql_executor)
    graph.add_node("answer_validator", answer_validator)
    graph.add_node("error_handler", error_handler)

    graph.set_entry_point("schema_linker")
    graph.add_edge("schema_linker", "sql_generator")
    graph.add_edge("sql_generator", "sql_validator")

    graph.add_conditional_edges("sql_validator", route_after_validation, {
        "sql_executor": "sql_executor",
        "error_handler": "error_handler",
    })
    graph.add_conditional_edges("sql_executor", route_after_executor, {
        "answer_validator": "answer_validator",
        "error_handler": "error_handler",
    })
    graph.add_conditional_edges("answer_validator", route_after_answer_validator, {
        END: END,
        "error_handler": "error_handler",
    })
    graph.add_conditional_edges("error_handler", route_after_error_handler, {
        "sql_generator": "sql_generator",
        END: END,
    })

    return graph.compile()
