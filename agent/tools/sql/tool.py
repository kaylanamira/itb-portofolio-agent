"""SQLTool — domain-agnostic Text-to-SQL pipeline."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

import sqlglot
from sqlglot import exp
import asyncio
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
    """
    Text-to-SQL pipeline.

    Constructor params:
        schema_linker_prompt  — system prompt for entity extraction LLM call.
                                Must be fully domain-specific (tables, entities, rules).
        human_message_builder — callable(task, user_scope, plan_context) -> str.
                                Builds the human message for the schema linker.
                                Defaults to a simple passthrough if not provided.
        entity_resolver       — async callable(dict) -> Any.
                                Resolves raw entity dict from LLM to canonical form.
                                Shape of return value is domain-specific; SQLTool
                                only passes it through to _format_entities().
        few_shot_examples     — callable(query_type: str | None) -> str.
                                Returns formatted few-shot SQL examples.
        schema_context        — full DDL/schema text for the target domain.
        default_table         — fallback table name when none detected in query.
        max_attempts          — retry limit for generate→validate→execute loop.
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
    ):
        self.schema_linker_prompt = schema_linker_prompt
        self.entity_resolver = entity_resolver
        self.few_shot_examples = few_shot_examples
        self.schema_context = schema_context
        self.default_table = default_table
        self.executor = executor
        self.max_attempts = max_attempts
        self.domain_rules = domain_rules
        self._human_message_builder = human_message_builder or self._default_human_message

    async def run(self, state: SQLState) -> SQLState:
        """
        Runs the full pipeline: link_schema → (generate → validate → execute → validate_answer) × retry.

        Args:
            state: SQLState with question and user_scope populated.

        Returns:
            Updated SQLState with results, or is_aborted=True on max retries.
        """
        question = state["question"]
        user_scope = state["user_scope"]
        plan_step_context = state.get("plan_step_context")
        plan_context = state.get("plan_context")
        query_type = state.get("query_type")

        schema_result = await self.link_schema(
            question,
            user_scope,
            plan_step_context,
            plan_context,
        )
        detected_entities = schema_result["detected_entities"]
        relevant_tables = schema_result["relevant_tables"]

        state["detected_entities"] = detected_entities
        state["relevant_tables"] = relevant_tables
        state["schema_context"] = self.schema_context
        state["attempt_count"] = 0
        state["is_aborted"] = False
        state.setdefault("error_history", [])

        for attempt_num in range(1, self.max_attempts + 1):
            state["attempt_count"] = attempt_num

            generated_sql = await self.generate_sql(
                question=question,
                detected_entities=detected_entities,
                user_scope=user_scope,
                relevant_tables=relevant_tables,
                query_type=query_type,
                plan_step_context=plan_step_context,
                error_history=state["error_history"],
                attempt_count=attempt_num - 1,
            )
            state["generated_sql"] = generated_sql

            val = await self.validate_sql(generated_sql, user_scope)
            state["validation_status"] = val["validation_status"]

            if val["validation_status"] != "pass":
                error_cat, correction_hint = classify_sql_error(val["error"])
                state["error_history"].append({
                    "attempt": attempt_num - 1,
                    "sql": generated_sql,
                    "error": val["error"],
                    "type": val["error_type"],
                    "error_category": error_cat.value,
                    "correction_hint": correction_hint,
                })
                state["validation_errors"] = state.get("validation_errors", []) + [val["error"]]
                state["generated_sql"] = None
                state["sql_result"] = None
                state["sql_error"] = None
                continue

            exec_result = await self.execute_sql(generated_sql, user_scope, relevant_tables)
            state["sql_with_scope"] = exec_result["sql_with_scope"]
            state["sql_result"] = exec_result["sql_result"]
            state["sql_error"] = exec_result["sql_error"]
            state["sql_row_count"] = exec_result["sql_row_count"]

            if exec_result["sql_error"]:
                error_cat, correction_hint = classify_sql_error(exec_result["sql_error"])
                state["error_history"].append({
                    "attempt": attempt_num - 1,
                    "sql": exec_result["sql_with_scope"],
                    "error": exec_result["sql_error"],
                    "type": "execution_error",
                    "error_category": error_cat.value,
                    "correction_hint": correction_hint,
                })
                state["generated_sql"] = None
                state["sql_result"] = None
                state["sql_error"] = None
                continue

            ans = await self.validate_answer(
                question, generated_sql,
                exec_result["sql_result"], exec_result["sql_row_count"],
                plan_step_context,
            )
            state["answer_is_valid"] = ans["answer_is_valid"]

            if not ans["answer_is_valid"]:
                error_cat, correction_hint = classify_sql_error(
                    f"Answer validation failed: {ans.get('reason', '')}"
                )
                state["error_history"].append({
                    "attempt": attempt_num - 1,
                    "sql": generated_sql,
                    "error": f"Answer validation failed: {ans.get('reason', '')}",
                    "type": "answer_invalid",
                    "error_category": error_cat.value,
                    "correction_hint": correction_hint,
                })
                state["generated_sql"] = None
                state["sql_result"] = None
                state["sql_error"] = None
                continue

            return state

        state["is_aborted"] = True
        state["abort_reason"] = "MAX_RETRIES_EXCEEDED"
        return state

    async def link_schema(
        self,
        question: str,
        user_scope: UserScope,
        plan_step_context: Optional[dict] = None,
        plan_context: Optional[str] = None,
    ) -> dict:
        """
        Runs schema linking: extracts entities and selects relevant tables.

        Args:
            question: The original user question.
            user_scope: Caller's access scope.
            plan_step_context: Current plan step dict (overrides question as the task).
            plan_context: Summary of what previous steps already retrieved,
                          used to guide table selection in multi-step plans.

        Returns:
            Dict with 'detected_entities' and 'relevant_tables'.
        """
        llm = get_llm("schema_linking")
        task = plan_step_context.get("task", question) if plan_step_context else question
        human_content = self._human_message_builder(task, user_scope, plan_context)

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
        plan_context: Optional[str] = None,
    ) -> str:
        lines = [f"User Role: {user_scope.role.value}"]
        if plan_context:
            lines.append(f"\nPrevious steps context: {plan_context}")
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
        """
        Generates SQL from natural language with retry context.

        Args:
            question: original user query.
            detected_entities: resolved entity object.
            user_scope: UserScope for scope injection.
            relevant_tables: tables selected by schema linker.
            query_type: planner query type string.
            plan_step_context: current plan step dict.
            error_history: list of prior attempt errors.
            attempt_count: current retry index.

        Returns:
            SQL string.
        """
        llm = get_llm(task_type="sql_generation", force_json=False)

        scope_desc, scope_hint = self._build_scope_context(user_scope, relevant_tables)
        entities_str = self._format_entities(detected_entities)
        few_shots = self.few_shot_examples(query_type)

        if callable(self.schema_context):
            if asyncio.iscoroutinefunction(self.schema_context):
                schema_str = await self.schema_context(relevant_tables)
            else:
                schema_str = self.schema_context(relevant_tables)
        else:
            schema_str = self.schema_context

        sys_prompt = SQL_GENERATOR_SYSTEM.format(
            schema_context=schema_str,
            domain_rules=self.domain_rules or "(none)",
            detected_entities=entities_str,
            scope_description=scope_desc,
            scope_hint=scope_hint,
            few_shot_examples=few_shots,
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

    async def validate_sql(self, generated_sql: str, user_scope: Optional[UserScope] = None) -> dict:
        """
        Validates SQL for security, syntax, and scope enforcement policy.

        Args:
            generated_sql: SQL string to validate.
            user_scope: Optional UserScope to check against protected tables.

        Returns:
            Dict with 'validation_status' ('pass'|'fail'), 'error', 'error_type'.
        """
        is_safe, sec_err = check_sql_security(generated_sql)
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
            tables = [t.name.lower() for t in parsed.find_all(exp.Table) if t.name]
            protected_tables = [t for t in tables if t not in UserScope.LOOKUP_TABLES]
            
            if protected_tables and "{SCOPE_FILTER}" not in generated_sql:
                return {
                    "validation_status": "fail", 
                    "error": "Missing {SCOPE_FILTER} placeholder for protected tables.", 
                    "error_type": "security_violation"
                }
        except Exception as e:
            return {"validation_status": "fail", "error": f"SQL Parse Error: {str(e)}", "error_type": "parse_error"}

        return {"validation_status": "pass", "error": None, "error_type": None}

    async def execute_sql(
        self,
        generated_sql: str,
        user_scope: UserScope,
        relevant_tables: Optional[list[str]] = None,
    ) -> dict:
        """
        Executes SQL with scope filter injection.

        Args:
            generated_sql: SQL string with {SCOPE_FILTER} placeholder.
            user_scope: UserScope instance providing scope_where().
            relevant_tables: tables referenced in the query; first entry used for scope.

        Returns:
            Dict with 'sql_with_scope', 'sql_result', 'sql_error', 'sql_row_count'.
        """
        try:
            parsed = sqlglot.parse_one(generated_sql, read="postgres")
            tables = [t.name.lower() for t in parsed.find_all(exp.Table) if t.name]
            
            # Policy: if multiple tables, use the first protected table for scope rules, 
            # or default table if none found.
            protected_tables = [t for t in tables if t not in UserScope.LOOKUP_TABLES]
            target_table = protected_tables[0] if protected_tables else (tables[0] if tables else self.default_table)
        except Exception:
            target_table = relevant_tables[0] if relevant_tables else self.default_table

        scope_where, scope_params = user_scope.scope_where(target_table)
        escaped_sql = generated_sql.replace("%", "%%")
        sql_with_scope = escaped_sql.replace("{SCOPE_FILTER}", f"({scope_where})")

        logger.info("Prepared SQL for execution (table=%s):\n%s", target_table, sql_with_scope)

        exec_result = await self.executor.execute(sql_with_scope, scope_params, user_scope)
        
        return {
            "sql_with_scope": sql_with_scope,
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
        plan_step_context: Optional[dict] = None,
    ) -> dict:
        """
        Checks if the SQL result answers the question via LLM.

        Args:
            question: original user query.
            generated_sql: executed SQL string.
            sql_result: rows returned by the query.
            sql_row_count: number of rows returned.
            plan_step_context: current plan step dict.

        Returns:
            Dict with 'answer_is_valid' (bool) and 'reason' (str).
        """
        if sql_result is None:
            return {"answer_is_valid": False, "reason": "SQL returned no result set"}

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
            
            logger.info("Answer validation outcome: is_valid=%s, reason=%s, row_count=%d", is_valid, reason, sql_row_count)
            
            return {
                "answer_is_valid": is_valid,
                "reason": reason,
            }
        except Exception as e:
            logger.error("Answer validation failed: %s", e)
            return {"answer_is_valid": False, "reason": "Validation failed, defaulting to valid."}

    def _build_scope_context(self, user_scope: UserScope, relevant_tables: list[str]) -> tuple[str, str]:
        """
        Builds scope description and hint strings for the SQL generator prompt.

        Args:
            user_scope: UserScope instance.
            relevant_tables: tables selected by schema linker.

        Returns:
            Tuple of (scope_description, scope_hint).
        """
        if not user_scope:
            return "Unknown", "TRUE"

        target_table = relevant_tables[0] if relevant_tables else self.default_table
        scope_where, _ = user_scope.scope_where(target_table)
        hint = scope_where if scope_where != "FALSE" else "TRUE"
        return f"Role: {user_scope.role.value}", f"For {target_table}: {hint}"

    @staticmethod
    def _format_entities(entities: Any) -> str:
        """
        Formats detected entities into string for the SQL generator prompt.

        Uses JSON serialization (not Python repr) so UUID fields appear as
        plain strings that the LLM can use directly in SQL literals.
        """
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
        """
        Extracts a SQL string from an LLM response.

        Handles three output formats:
        1. JSON wrapper: {"sql": "SELECT ..."}
        2. Markdown fence: ```sql\nSELECT ...\n```
        3. CoT comment block + bare SQL:
           /* TABLES: ... JOINS: ... */ SELECT ...

        Args:
            raw_response: raw LLM output string.

        Returns:
            SQL string starting with SELECT or WITH, or 'SELECT 1' if extraction fails.
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
