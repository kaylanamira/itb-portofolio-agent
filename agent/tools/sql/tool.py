"""SQLTool"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

import sqlglot
from sqlglot import exp
from langchain_core.messages import SystemMessage, HumanMessage
from psycopg import sql as psycopg_sql
from agent.tools.academic_calendar import get_current_academic_period
from agent.llm import get_llm
from agent.prompts.sql_generator import SQL_GENERATOR_SYSTEM, SQL_GENERATOR_RETRY
from agent.prompts.answer_validator import ANSWER_VALIDATOR_PROMPT
from agent.tools.security import check_sql_security
from agent.tools.sql.state import SQLState
from core.database import get_db_connection
from core.scope import UserScope
from core.utils import extract_json_from_llm

logger = logging.getLogger(__name__)


class SQLTool:
    """
    Text-to-SQL pipeline.

    Constructor params:
        schema_linker_prompt — system prompt for entity extraction LLM call.
        entity_resolver — async callable, resolves raw entity dict to canonical form.
        few_shot_examples — callable, returns formatted few-shot examples given query_type.
        schema_context — full schema text for the target domain.
        default_table — fallback table when none detected.
        max_attempts — retry limit for generate-validate-execute loop.
    """

    def __init__(
        self,
        schema_linker_prompt: str,
        entity_resolver: Callable[[dict], Any],
        few_shot_examples: Callable[[Optional[str]], str],
        schema_context: str,
        default_table: str = "mv_kelas",
        max_attempts: int = 3,
    ):
        self.schema_linker_prompt = schema_linker_prompt
        self.entity_resolver = entity_resolver
        self.few_shot_examples = few_shot_examples
        self.schema_context = schema_context
        self.default_table = default_table
        self.max_attempts = max_attempts

    async def run(self, state: SQLState) -> SQLState:
        """
        Full pipeline over SQLState: link_schema → (generate → validate → execute → validate_answer) × retry.

        Input: SQLState with question, user_scope populated.
        Output: updated SQLState with results or abort.
        """
        question = state["question"]
        user_scope = state["user_scope"]
        plan_step_context = state.get("plan_step_context")
        query_type = state.get("query_type")

        schema_result = await self.link_schema(question, user_scope, plan_step_context)
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

            val = await self.validate_sql(generated_sql)
            state["validation_status"] = val["validation_status"]

            if val["validation_status"] != "pass":
                state["error_history"].append({
                    "attempt": attempt_num - 1,
                    "sql": generated_sql,
                    "error": val["error"],
                    "type": val["error_type"],
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
                state["error_history"].append({
                    "attempt": attempt_num - 1,
                    "sql": exec_result["sql_with_scope"],
                    "error": exec_result["sql_error"],
                    "type": "execution_error",
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
                state["error_history"].append({
                    "attempt": attempt_num - 1,
                    "sql": generated_sql,
                    "error": f"Answer validation failed: {ans.get('reason', '')}",
                    "type": "answer_invalid",
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
    ) -> dict:
        """
        Extracts entities and selects relevant tables via LLM.

        Input: question, user_scope, plan_step_context.
        Output: dict with 'detected_entities', 'relevant_tables'.
        """

        llm = get_llm("schema_linking")
        current_semester, current_tahun_ajaran = get_current_academic_period()
        task = plan_step_context.get("task", question) if plan_step_context else question

        human_content = (
            f"CURRENT CONTEXT:\n"
            f"  Semester: {current_semester}\n"
            f"  Tahun Ajaran: {current_tahun_ajaran}\n"
            f"  User Role: {user_scope.role.value}\n\n"
            f"USER QUERY: {task}"
        )

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

        resolved = await self.entity_resolver(entities_dict)

        return {
            "detected_entities": resolved,
            "relevant_tables": relevant_tables,
        }

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

        Input: question, detected_entities, user_scope, relevant_tables,
               query_type, plan_step_context, error_history, attempt_count.
        Output: SQL string.
        """
        llm = get_llm(task_type="sql_generation", force_json=False)

        scope_desc, scope_hint = self._build_scope_context(user_scope, relevant_tables)
        entities_str = self._format_entities(detected_entities)
        few_shots = self.few_shot_examples(query_type)

        sys_prompt = SQL_GENERATOR_SYSTEM.format(
            schema_context=self.schema_context,
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
                previous_sql=last_error.get("sql", ""),
                last_error=last_error.get("error", ""),
                error_history=json.dumps(error_history, indent=2, default=str),
            )

        task = plan_step_context.get("task", question) if plan_step_context else question
        messages = [
            SystemMessage(content=sys_prompt),
            HumanMessage(content=f"Original Query: {question}\n\nTask for this step: {task}"),
        ]

        response = await llm.ainvoke(messages)
        return self._extract_sql(response.content)

    async def validate_sql(self, generated_sql: str) -> dict:
        """
        Validates SQL for security and syntax.

        Input: SQL string.
        Output: dict with 'validation_status', 'error', 'error_type'.
        """
        is_safe, sec_err = check_sql_security(generated_sql)
        if not is_safe:
            return {"validation_status": "fail", "error": sec_err, "error_type": "security_violation"}

        try:
            parsed = sqlglot.parse_one(generated_sql, read="postgres")
            if not isinstance(parsed, sqlglot.exp.Select):
                raise ValueError("Query must be a SELECT statement.")
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

        Input: SQL string, user_scope, relevant_tables.
        Output: dict with 'sql_with_scope', 'sql_result', 'sql_error', 'sql_row_count'.
        """
        try:
            parsed = sqlglot.parse_one(generated_sql, read="postgres")
            tables = [t.name.lower() for t in parsed.find_all(exp.Table) if t.name]
            target_table = tables[0] if tables else self.default_table
            for t in tables:
                if t.startswith("mv_") or t in ("teks_portofolio", "komentar_mahasiswa"):
                    target_table = t
                    break
        except Exception:
            target_table = (relevant_tables[0] if relevant_tables else self.default_table)

        scope_where, scope_params = user_scope.scope_where(target_table)
        escaped_sql = generated_sql.replace('%', '%%')
        sql_with_scope = escaped_sql.replace('{SCOPE_FILTER}', f'({scope_where})')

        logger.info("Executing SQL (table=%s):\n%s", target_table, sql_with_scope)

        try:
            async with get_db_connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        psycopg_sql.SQL("SET LOCAL app.user_id = {}").format(
                            psycopg_sql.Literal(str(user_scope.user_id))
                        )
                    )
                    cursor = await conn.execute(sql_with_scope, scope_params)
                    rows = await cursor.fetchall()

                    if cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        result = [dict(zip(columns, row)) for row in rows]
                    else:
                        result = []

                    return {
                        "sql_with_scope": sql_with_scope,
                        "sql_result": result,
                        "sql_error": None,
                        "sql_row_count": len(result),
                    }
        except Exception as e:
            logger.error("SQL Execution Error: %s", e)
            return {
                "sql_with_scope": sql_with_scope,
                "sql_result": None,
                "sql_error": str(e),
                "sql_row_count": 0,
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
        Checks if SQL result answers the question via LLM.

        Input: question, generated_sql, sql_result, sql_row_count, plan_step_context.
        Output: dict with 'answer_is_valid', 'reason'.
        """
        if sql_result is None:
            return {"answer_is_valid": False, "reason": "SQL returned no result set"}

        try:
            llm = get_llm("answer_validation")
            task = plan_step_context.get("task", question) if plan_step_context else question

            prompt_content = ANSWER_VALIDATOR_PROMPT.format(
                raw_query=task,
                generated_sql=generated_sql,
                row_count=sql_row_count,
                sql_result=str(sql_result)[:1000],
            )

            response = await llm.ainvoke([
                SystemMessage(content="You are an AI answer relevance validator."),
                HumanMessage(content=prompt_content),
            ])

            result = extract_json_from_llm(response.content)
            return {
                "answer_is_valid": result.get("is_valid", True),
                "reason": result.get("reason", "Answer checked."),
            }
        except Exception as e:
            logger.error("Answer validation failed: %s", e)
            return {"answer_is_valid": True, "reason": "Validation failed, defaulting to valid."}

    def _build_scope_context(self, user_scope: UserScope, relevant_tables: list[str]) -> tuple[str, str]:
        """
        Builds scope description and hint for the SQL generator prompt.

        Input: user_scope, relevant_tables.
        Output: (scope_description, scope_hint).
        """
        if not user_scope:
            return "Unknown", "TRUE"

        target_table = relevant_tables[0] if relevant_tables else self.default_table
        scope_where, _ = user_scope.scope_where(target_table)
        return f"Role: {user_scope.role.value}", f"For {target_table}: {scope_where}"

    @staticmethod
    def _format_entities(entities: Any) -> str:
        """
        Formats detected entities into string for the SQL generator prompt.

        Input: entities (Pydantic model, dict, or None).
        Output: string representation.
        """
        if not entities:
            return "None detected"
        if hasattr(entities, "model_dump"):
            return str(entities.model_dump())
        if hasattr(entities, "dict"):
            return str(entities.dict())
        return str(entities)

    @staticmethod
    def _extract_sql(raw_response: str) -> str:
        """
        Extracts SQL from LLM response (JSON or markdown-fenced).

        Input: raw LLM response string.
        Output: SQL string.
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
        sql_str = cleaned.strip()

        if not sql_str or not sql_str.upper().startswith("SELECT"):
            return "SELECT 1"
        return sql_str
