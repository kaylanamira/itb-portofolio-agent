import logging
from agent.state import AgentState
from agent.llm import get_llm
from agent.prompts.answer_validator import ANSWER_VALIDATOR_PROMPT
from core.utils import extract_json_from_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

async def answer_validator(state: AgentState) -> dict:
    sql_result = state.get("sql_result")
    sql_error = state.get("sql_error")
    row_count = state.get("sql_row_count", 0)
    
    # If there was a SQL execution error, always mark as invalid
    if sql_error is not None:
        return {
            "answer_is_valid": False,
            "error_history": [{
                "attempt": state.get("attempt_count", 0), 
                "sql": state.get("generated_sql", ""),
                "error": sql_error, 
                "type": "execution_error"
            }]
        }
    
    if sql_result is None:
        return {
            "answer_is_valid": False,
            "error_history": [{
                "attempt": state.get("attempt_count", 0),
                "sql": state.get("generated_sql", ""),
                "error": "SQL returned no result set",
                "type": "answer_invalid"
            }]
        }
    
    try:
        llm = get_llm()
        plan = state.get("plan", [])
        idx = state.get("current_step_index", 0)
        current_task = plan[idx].get("task") if plan and idx < len(plan) else state.get("effective_query", "")
        
        prompt_content = ANSWER_VALIDATOR_PROMPT.format(
            raw_query=current_task,
            generated_sql=state.get("generated_sql", ""),
            row_count=row_count,
            sql_result=str(sql_result)[:1000]
        )
        
        response = await llm.ainvoke([
            SystemMessage(content="You are an AI answer relevance validator."),
            HumanMessage(content=prompt_content)
        ])
        
        result = extract_json_from_llm(response.content)
        is_valid = result.get("is_valid", True)
        reason = result.get("reason", "Answer checked for relevance.")
    except Exception as e:
        logger.error(f"Answer validation LLM call failed: {e}")
        is_valid = True
        reason = "Validation failed, defaulting to valid."
    
    if not is_valid:
        logger.warning(f"Answer validation failed: {reason}")
        return {
            "answer_is_valid": False,
            "error_history": [{
                "attempt": state.get("attempt_count", 0),
                "sql": state.get("generated_sql", ""),
                "error": f"Answer relevance validation failed: {reason}",
                "type": "answer_invalid"
            }]
        }
    
    logger.info("Answer validated successfully")
    return {"answer_is_valid": True}

def route_after_answer_validator(state: AgentState) -> str:
    if state.get("answer_is_valid", False):
        return "step_reasoner"
    return "error_handler"
