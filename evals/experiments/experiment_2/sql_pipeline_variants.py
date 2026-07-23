from langgraph.graph import StateGraph, END
from agent.tools.sql.state import SQLState
from agent.tools.sql.tool import SQLTool
from agent.tools.error_taxonomy import classify_sql_error
from agent.prompts.schema_linker import SCHEMA_LINKER_SYSTEM_PROMPT, PORTFOLIO_SQL_DOMAIN_RULES
from agent.tools.schema_retriever import describe_tables
from agent.state import DetectedEntities
from core.sql_executor import QueryExecutor
from agent.tools.fuzzy_search import fuzzy_resolve_entities
from agent.tools.schema_retriever import FileSchemaRetriever
from agent.nodes.sql_pipeline import portfolio_few_shot_examples

# S1 Static Schema Helper
_S1_STATIC_SCHEMA_CACHE = None

async def _get_s1_static_schema(_: list[str]) -> str:
    global _S1_STATIC_SCHEMA_CACHE
    if not _S1_STATIC_SCHEMA_CACHE:
        retriever = FileSchemaRetriever()
        all_tables = list(retriever._load_and_parse().keys())
        analitik_tables = [t for t in all_tables if t.startswith("analitik.")]
        descriptions = []
        for t in analitik_tables:
            desc = retriever.describe_table(t)
            if not desc:
                continue
            lines = [f"Table: {t}"]
            for line in desc.split("\n"):
                if line.strip().startswith("|") and "`" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 3 and parts[1].startswith("`") and parts[2].startswith("`"):
                        col = parts[1].replace("`", "")
                        dtype = parts[2].replace("`", "")
                        # Ignore table header row
                        if col.lower() != "column" and dtype.lower() != "type":
                            lines.append(f"  - {col} ({dtype})")
            descriptions.append("\n".join(lines))
        _S1_STATIC_SCHEMA_CACHE = "\n\n".join(descriptions)
    return _S1_STATIC_SCHEMA_CACHE

async def _s1_s2_exact_entity_resolver(entities_dict: dict) -> DetectedEntities:
    """Exact match only, no fuzzy search."""
    valid_fields = DetectedEntities.model_fields.keys()
    filtered = {k: v for k, v in entities_dict.items() if k in valid_fields and v}
    return DetectedEntities(**filtered)

async def _s3_fuzzy_entity_resolver(entities_dict: dict) -> DetectedEntities:
    """Full fuzzy search."""
    valid_fields = DetectedEntities.model_fields.keys()
    filtered = {k: v for k, v in entities_dict.items() if k in valid_fields and v}
    raw = DetectedEntities(**filtered)
    try:
        return await fuzzy_resolve_entities(raw)
    except Exception:
        return raw

def _build_variant_pipeline(
    name: str,
    executor: QueryExecutor,
    use_schema_linker: bool,
    use_dynamic_schema: bool,
    use_few_shot: bool,
    use_fuzzy: bool,
    use_retry: bool,
    use_answer_validator: bool
):
    """Factory to build S1, S2, S3 variants."""
    
    entity_resolver = _s3_fuzzy_entity_resolver if use_fuzzy else _s1_s2_exact_entity_resolver
    few_shot_fn = portfolio_few_shot_examples if use_few_shot else lambda _: "(no examples)"
    schema_context_fn = describe_tables if use_dynamic_schema else _get_s1_static_schema
    max_attempts = 3 if use_retry else 1

    tool = SQLTool(
        schema_linker_prompt=SCHEMA_LINKER_SYSTEM_PROMPT,
        entity_resolver=entity_resolver,
        few_shot_examples=few_shot_fn,
        schema_context=schema_context_fn,
        default_table="analitik.v_akademik_portofolio",
        executor=executor,
        max_attempts=max_attempts,
        domain_rules=PORTFOLIO_SQL_DOMAIN_RULES,
    )

    async def schema_linker_node(state: SQLState) -> dict:
        if not use_schema_linker:
            # S1: bypass linking completely
            retriever = FileSchemaRetriever()
            all_tables = list(retriever._load_and_parse().keys())
            tables = [t for t in all_tables if t.startswith("analitik.")]
            schema_txt = await schema_context_fn(tables)
            return {
                "detected_entities": DetectedEntities(),
                "relevant_tables": tables,
                "schema_context": schema_txt
            }
            
        result = await tool.link_schema(
            question=state["question"],
            user_scope=state["user_scope"],
            plan_step_context=state.get("plan_step_context"),
            prior_steps_context=state.get("plan_context"),
        )
        relevant_tables = result["relevant_tables"]
        if "analitik.v_akademik_portofolio" not in relevant_tables:
            relevant_tables.append("analitik.v_akademik_portofolio")
            
        schema_txt = await schema_context_fn(relevant_tables)
        return {
            "detected_entities": result["detected_entities"],
            "relevant_tables": relevant_tables,
            "schema_context": schema_txt,
        }

    async def sql_generator_node(state: SQLState) -> dict:
        current_attempt = state.get("attempt_count", 0) + 1
        sql = await tool.generate_sql(
            question=state["question"],
            detected_entities=state.get("detected_entities"),
            user_scope=state["user_scope"],
            relevant_tables=state.get("relevant_tables", ["analitik.v_akademik_portofolio"]),
            query_type=state.get("query_type"),
            plan_step_context=state.get("plan_step_context"),
            prior_steps_context=state.get("prior_steps_context"),
            error_history=state.get("error_history", []),
            attempt_count=current_attempt,
        )
        return {"generated_sql": sql, "attempt_count": current_attempt}

    async def sql_validator_node(state: SQLState) -> dict:
        result = await tool.validate_sql(state.get("generated_sql", ""))
        if result["validation_status"] != "pass":
            error_cat, correction_hint = classify_sql_error(result["error"])
            return {
                "validation_status": result["validation_status"],
                "validation_errors": [result["error"]],
                "error_history": [{
                    "attempt": state.get("attempt_count", 0),
                    "sql": state.get("generated_sql", ""),
                    "error": result["error"],
                    "type": result["error_type"],
                    "error_category": error_cat.value,
                    "correction_hint": correction_hint,
                }],
            }
        return {"validation_status": "pass"}

    async def sql_executor_node(state: SQLState) -> dict:
        result = await tool.execute_sql(
            generated_sql=state.get("generated_sql", ""),
            user_scope=state["user_scope"],
        )
        if result.get("sql_error"):
            error_cat, correction_hint = classify_sql_error(result["sql_error"])
            return {
                **result,
                "error_history": [{
                    "attempt": state.get("attempt_count", 0),
                    "sql": state.get("generated_sql", ""),
                    "error": result["sql_error"],
                    "type": "execution_error",
                    "error_category": error_cat.value,
                    "correction_hint": correction_hint,
                }],
            }
        return result

    async def answer_validator_node(state: SQLState) -> dict:
        if not use_answer_validator:
            return {"answer_is_valid": True}
        result = await tool.validate_answer(
            question=state["question"],
            generated_sql=state.get("generated_sql", ""),
            sql_result=state.get("sql_result"),
            sql_row_count=state.get("sql_row_count", 0),
            user_scope=state.get("user_scope"),
            detected_entities=state.get("detected_entities"),
            plan_step_context=state.get("plan_step_context"),
        )
        return {
            "answer_is_valid": result.get("answer_is_valid"),
        }

    def route_validation(state: SQLState) -> str:
        if state.get("validation_status") == "pass":
            return "sql_executor"
        if not use_retry:
            return "error_handler"
        if state.get("attempt_count", 0) >= tool.max_attempts:
            return "error_handler"
        return "sql_generator"

    def route_execution(state: SQLState) -> str:
        if not state.get("sql_error"):
            return "answer_validator"
        if not use_retry:
            return "error_handler"
        if state.get("attempt_count", 0) >= tool.max_attempts:
            return "error_handler"
        return "sql_generator"

    def route_answer_validation(state: SQLState) -> str:
        if state.get("answer_is_valid") is True:
            return END
        if not use_retry:
            return "error_handler"
        if state.get("attempt_count", 0) >= tool.max_attempts:
            return "error_handler"
        return "sql_generator"

    def error_handler_node(state: SQLState) -> dict:
        return {"is_aborted": True, "abort_reason": "Max retries reached or unrecoverable error."}

    builder = StateGraph(SQLState)
    builder.add_node("schema_linker", schema_linker_node)
    builder.add_node("sql_generator", sql_generator_node)
    builder.add_node("sql_validator", sql_validator_node)
    builder.add_node("sql_executor", sql_executor_node)
    builder.add_node("answer_validator", answer_validator_node)
    builder.add_node("error_handler", error_handler_node)

    builder.set_entry_point("schema_linker")
    builder.add_edge("schema_linker", "sql_generator")
    builder.add_edge("sql_generator", "sql_validator")
    
    builder.add_conditional_edges("sql_validator", route_validation, {
        "sql_executor": "sql_executor",
        "sql_generator": "sql_generator",
        "error_handler": "error_handler"
    })
    
    builder.add_conditional_edges("sql_executor", route_execution, {
        "answer_validator": "answer_validator",
        "sql_generator": "sql_generator",
        "error_handler": "error_handler"
    })
    
    builder.add_conditional_edges("answer_validator", route_answer_validation, {
        END: END,
        "sql_generator": "sql_generator",
        "error_handler": "error_handler"
    })
    
    builder.add_edge("error_handler", END)

    return builder.compile()

def build_s1_pipeline(executor: QueryExecutor):
    return _build_variant_pipeline(
        "S1", executor,
        use_schema_linker=False,
        use_dynamic_schema=False,
        use_few_shot=False,
        use_fuzzy=False,
        use_retry=False,
        use_answer_validator=False
    )

def build_s2_pipeline(executor: QueryExecutor):
    return _build_variant_pipeline(
        "S2", executor,
        use_schema_linker=True,
        use_dynamic_schema=True,
        use_few_shot=False,
        use_fuzzy=False,
        use_retry=False,
        use_answer_validator=False
    )

def build_s3_pipeline(executor: QueryExecutor):
    return _build_variant_pipeline(
        "S3", executor,
        use_schema_linker=True,
        use_dynamic_schema=True,
        use_few_shot=True,
        use_fuzzy=True,
        use_retry=True,
        use_answer_validator=True
    )
