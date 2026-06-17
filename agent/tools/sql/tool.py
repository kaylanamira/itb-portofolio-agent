"""SQLTool — Text-to-SQL pipeline.

Handles: schema linking → SQL generation → validation → execution → answer validation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

import asyncio
import sqlglot
from langchain_core.messages import SystemMessage, HumanMessage

from agent.llm import get_llm
from agent.prompts.sql_generator import SQL_GENERATOR_SYSTEM, SQL_GENERATOR_RETRY
from agent.prompts.answer_validator import ANSWER_VALIDATOR_PROMPT
from agent.tools.security import check_sql_security
from agent.tools.error_taxonomy import classify_sql_error
from agent.tools.fuzzy_search import FuzzyResolutionError
from agent.state import DetectedEntities
from agent.tools.sql.state import SQLState
from core.sql_executor import QueryExecutor
from core.scope import UserScope
from core.utils import extract_json_from_llm

logger = logging.getLogger(__name__)


class SQLTool:
    """Text-to-SQL pipeline.

    Args:
        schema_linker_prompt: System prompt for entity extraction LLM call.
        entity_resolver: Async callable that resolves raw entity dict to canonical form.
        few_shot_examples: Callable that returns formatted few-shot SQL examples.
        schema_context: DDL/schema text or async callable returning it.
        default_table: Fallback table name when none detected.
        executor: QueryExecutor implementation for SQL execution.
        max_attempts: Retry limit for the generate→validate→execute loop.
        human_message_builder: Builds the human message for schema linker.
        domain_rules: Domain-specific SQL generation rules.
    """

    def __init__(
        self,
        schema_linker_prompt: str,
        entity_resolver: Callable[[dict], Any],
        few_shot_examples: Callable[[Optional[str]], str],
        schema_context: str | Callable[[list[str]], str],
        default_table: str,
        executor: QueryExecutor,
        max_attempts: int = 3,
        human_message_builder: Optional[Callable] = None,
        domain_rules: str = "",
        system_prompt_template: str = SQL_GENERATOR_SYSTEM,
    ):
        self.schema_linker_prompt = schema_linker_prompt
        self.entity_resolver = entity_resolver
        self.few_shot_examples = few_shot_examples
        self.schema_context = schema_context
        self.default_table = default_table
        self.executor = executor
        self.max_attempts = max_attempts
        self.domain_rules = domain_rules
        self.system_prompt_template = system_prompt_template
        self._human_message_builder = human_message_builder or self._default_human_message

    async def link_schema(
        self,
        question: str,
        user_scope: UserScope,
        plan_step_context: Optional[dict] = None,
        prior_steps_context: Optional[str] = None,
    ) -> dict:
        """Extracts entities and selects relevant tables from the query.

        Args:
            question: The original user question.
            user_scope: Caller's access scope.
            plan_step_context: Current plan step dict.
            prior_steps_context: Summary of what previous steps already retrieved.

        Returns:
            Dict with 'detected_entities' and 'relevant_tables'.
        """
        llm = get_llm("schema_linking")
        task = plan_step_context.get("task", question) if plan_step_context else question
        human_content = self._human_message_builder(task, user_scope, prior_steps_context)

        messages = [
            SystemMessage(content=self.schema_linker_prompt),
            HumanMessage(content=human_content),
        ]
        response = await llm.ainvoke(messages)

        try:
            content = extract_json_from_llm(response.content)
            entities_dict = content.get("detected_entities") or {}
            relevant_tables = content.get("relevant_tables") or [self.default_table]
        except Exception:
            entities_dict = {}
            relevant_tables = [self.default_table]

        try:
            resolved = await self.entity_resolver(entities_dict)
        except FuzzyResolutionError as exc:
            logger.warning("Fuzzy resolution error in link_schema: %s", exc)
            valid_fields = DetectedEntities.model_fields.keys()
            filtered = {k: v for k, v in entities_dict.items() if k in valid_fields and v is not None}
            resolved = DetectedEntities(**filtered)

        return {
            "detected_entities": resolved,
            "relevant_tables": relevant_tables,
        }

    @staticmethod
    def _default_human_message(
        task: str,
        user_scope: UserScope,
        prior_steps_context: Optional[str] = None,
    ) -> str:
        lines = [f"User Role: {user_scope.role.value}"]
        if prior_steps_context:
            lines.append(f"\nPrevious steps context: {prior_steps_context}")
        lines.append(f"\nUSER QUERY: {task}")
        return "\n".join(lines)

    async def generate_sql(
        self,
        question: str,
        detected_entities: Any,
        user_scope: UserScope,
        relevant_tables: list[str],
        query_type: Optional[str] = None,
        plan_step_context: Optional[dict] = None,
        error_history: Optional[list[dict]] = None,
        attempt_count: int = 0,
    ) -> str:
        """Generates SQL from natural language with retry context.

        Args:
            question: Original user query.
            detected_entities: Resolved entity object.
            user_scope: UserScope for role context.
            relevant_tables: Tables selected by schema linker.
            query_type: Planner query type string.
            plan_step_context: Current plan step dict.
            error_history: List of prior attempt errors.
            attempt_count: Current retry index.

        Returns:
            SQL string.
        """
        llm = get_llm(task_type="sql_generation", force_json=False)

        entities_str = self._format_entities(detected_entities)
        few_shots = self.few_shot_examples(query_type)

        if callable(self.schema_context):
            if asyncio.iscoroutinefunction(self.schema_context):
                schema_str = await self.schema_context(relevant_tables)
            else:
                schema_str = self.schema_context(relevant_tables)
        else:
            schema_str = self.schema_context

        sys_prompt = self.system_prompt_template.format(
            schema_context=schema_str,
            domain_rules=self.domain_rules or "(none)",
            detected_entities=entities_str,
            user_role=user_scope.role.value if user_scope else "SYSTEM",
            few_shot_examples=few_shots
        )

        if attempt_count > 0 and error_history:
            last_error = error_history[-1]
            sys_prompt += "\n" + SQL_GENERATOR_RETRY.format(
                attempt_count=attempt_count,
                max_attempts=self.max_attempts,
                previous_sql=self._truncate(last_error.get("sql", ""), 1200),
                last_error=self._truncate(last_error.get("error", ""), 800),
                error_category=last_error.get("error_category", "unknown"),
                correction_hint=last_error.get("correction_hint", "Re-examine the query structure."),
                error_history=self._format_retry_error_history(error_history),
            )

        task = plan_step_context.get("task", question) if plan_step_context else question
        messages = [
            SystemMessage(content=sys_prompt),
            HumanMessage(content=f"Original Query: {question}\n\nTask for this step: {task}"),
        ]

        response = await llm.ainvoke(messages)
        return self._extract_sql(response.content)

    async def validate_sql(
        self,
        generated_sql: str,
        allowed_schemas: frozenset[str] | None = None,
    ) -> dict:
        """Validates SQL for security and syntax.

        Args:
            generated_sql: SQL string to validate.
            allowed_schemas: Override schema allowlist. None uses the module default.

        Returns:
            Dict with 'validation_status', 'error', 'error_type'.
        """
        is_safe, sec_err = check_sql_security(generated_sql, allowed_schemas=allowed_schemas)
        if not is_safe:
            error_type = "parse_error" if sec_err and sec_err.startswith("SQL Parse Error") else "security_violation"
            return {"validation_status": "fail", "error": sec_err, "error_type": error_type}

        try:
            parsed = sqlglot.parse_one(generated_sql, read="postgres")
            is_select = isinstance(parsed, sqlglot.exp.Select)
            is_cte = isinstance(parsed, sqlglot.exp.With) and isinstance(parsed.this, sqlglot.exp.Select)
            if not (is_select or is_cte):
                raise ValueError("Query must be a SELECT statement.")
                
            # AST Scope Validation: ensuring {SCOPE_FILTER} is used if any protected table is queried
            # tables = [t.name.lower() for t in parsed.find_all(exp.Table) if t.name]
            # protected_tables = [t for t in tables if t not in UserScope.LOOKUP_TABLES]
            
            # if protected_tables and "{SCOPE_FILTER}" not in generated_sql:
            #     return {
            #         "validation_status": "fail", 
            #         "error": "Missing {SCOPE_FILTER} placeholder for protected tables.", 
            #         "error_type": "security_violation"
            #     }
        except Exception as e:
            return {"validation_status": "fail", "error": f"SQL Parse Error: {str(e)}", "error_type": "parse_error"}

        return {"validation_status": "pass", "error": None, "error_type": None}

    async def execute_sql(
        self,
        generated_sql: str,
        user_scope: UserScope,
    ) -> dict:
        """Executes SQL via the configured executor.

        RLS session variables are set by the executor automatically.

        Args:
            generated_sql: Valid SQL string (no placeholders needed).
            user_scope: UserScope for RLS session variable injection.

        Returns:
            Dict with 'sql_result', 'sql_error', 'sql_row_count'.
        """
        logger.info("Executing SQL:\\n%s", generated_sql)

        exec_result = await self.executor.execute(generated_sql, user_scope)

        return {
            "sql_result": exec_result.rows,
            "sql_error": exec_result.error,
            "sql_row_count": exec_result.row_count,
        }

    async def validate_answer(
        self,
        question: str,
        generated_sql: str,
        sql_result: Optional[list[dict]],
        sql_row_count: int,
        user_scope: Optional[Any] = None,
        detected_entities: Optional[Any] = None,
        plan_step_context: Optional[dict] = None,
    ) -> dict:
        if sql_result is None:
            return {"answer_is_valid": False, "reason": "SQL returned no result set"}

        if sql_row_count == 1 and sql_result and all(v is None for v in sql_result[0].values()):
            from agent.tools.sql.scope_classifier import classify_empty_result
            reason = classify_empty_result(user_scope, detected_entities) if user_scope else "LEGITIMATE_NO_DATA"
            print(f"[DEBUG empty_result] trigger=all_null_row | no_ps={getattr(getattr(user_scope, 'active_role', None), 'no_ps', None)} | no_prodi={getattr(detected_entities, 'no_prodi', None)} | resolved_prodi_id={getattr(detected_entities, 'resolved_prodi_id', None)} | reason={reason}")
            return {"answer_is_valid": True, "reason": reason, "empty_result_reason": reason}

        if sql_row_count == 0:
            from agent.tools.sql.scope_classifier import classify_empty_result
            reason = classify_empty_result(user_scope, detected_entities) if user_scope else "LEGITIMATE_NO_DATA"
            print(f"[DEBUG empty_result] trigger=zero_rows | no_ps={getattr(getattr(user_scope, 'active_role', None), 'no_ps', None)} | no_prodi={getattr(detected_entities, 'no_prodi', None)} | resolved_prodi_id={getattr(detected_entities, 'resolved_prodi_id', None)} | reason={reason}")
            return {"answer_is_valid": True, "reason": reason, "empty_result_reason": reason}

        try:
            llm = get_llm("answer_validation")
            task = plan_step_context.get("task", question) if plan_step_context else question
            step_desc = f"Plan Step: {plan_step_context.get('step', 'unknown')}" if plan_step_context else "Single-step query"

            prompt_content = ANSWER_VALIDATOR_PROMPT.format(
                raw_query=f"[{step_desc}] {task}",
                generated_sql=generated_sql,
                row_count=sql_row_count,
                sql_result=str(sql_result)[:1000],
            )

            response = await llm.ainvoke([
                SystemMessage(content="You are an AI answer relevance validator."),
                HumanMessage(content=prompt_content),
            ])

            result = extract_json_from_llm(response.content)
            is_valid = result.get("is_valid", True)
            reason = result.get("reason", "Answer checked.")

            logger.info("Answer validation: is_valid=%s, reason=%s, rows=%d", is_valid, reason, sql_row_count)

            return {"answer_is_valid": is_valid, "reason": reason}
        except Exception as e:
            logger.error("Answer validation failed: %s", e)
            return {"answer_is_valid": False, "reason": "Validation failed, defaulting to valid."}

    @staticmethod
    async def error_handler(state: SQLState, max_attempts: int=3) -> dict:
        new_attempt = state.get("attempt_count", 0) + 1
        if new_attempt < (max_attempts):
            return {
                "attempt_count": new_attempt,
                "generated_sql": None,
                "sql_result": None,
                "sql_error": None,
                "sql_row_count": None,
                "answer_is_valid": None,
            }
        return {
            "attempt_count": new_attempt,
            "is_aborted": True,
            "abort_reason": "MAX_RETRIES_EXCEEDED",
        }

    @staticmethod
    def _format_entities(entities: Any) -> str:
        """Formats detected entities for the SQL generator prompt."""
        if not entities:
            return "None detected"
        if hasattr(entities, "model_dump"):
            return json.dumps(entities.model_dump(mode="json"), indent=2, default=str)
        if hasattr(entities, "dict"):
            return json.dumps(entities.dict(), indent=2, default=str)
        return str(entities)

    @staticmethod
    def _truncate(value: Any, max_chars: int) -> str:
        text = str(value or "")
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "\n... [truncated]"

    @classmethod
    def _format_retry_error_history(cls, error_history: list[dict], max_items: int = 2) -> str:
        recent = error_history[-max_items:]
        compact = []
        for err in recent:
            compact.append({
                "attempt": err.get("attempt"),
                "type": err.get("type"),
                "error_category": err.get("error_category"),
                "correction_hint": err.get("correction_hint"),
                "error": cls._truncate(err.get("error", ""), 500),
                "sql": cls._truncate(err.get("sql", ""), 700),
            })
        return json.dumps(compact, indent=2, default=str)

    @staticmethod
    def _extract_sql(raw_response: str) -> str:
        """Extracts a SQL string from an LLM response.

        Handles JSON wrapper, markdown fences, and CoT comment blocks.

        Returns:
            SQL string starting with SELECT/WITH, or 'SELECT 1' on failure.
        """
        raw = raw_response.strip()
        try:
            content = extract_json_from_llm(raw)
            if isinstance(content, dict) and "sql" in content:
                return content["sql"]
        except (json.JSONDecodeError, AttributeError):
            pass

        cleaned = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()

        statement_match = re.search(r"(?im)^\s*(WITH|SELECT)\b", cleaned)
        if statement_match:
            return cleaned[statement_match.start():].strip()

        fallback_match = re.search(r"\b(WITH|SELECT)\b", cleaned, re.IGNORECASE)
        if fallback_match:
            return cleaned[fallback_match.start():].strip()

        return "SELECT 1"
