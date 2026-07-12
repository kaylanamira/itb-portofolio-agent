from core.utils import extract_json_from_llm
from agent.constants.chart_interpreter import (
    CHART_INTERPRETER_ACTION,
    CHART_INTERPRETER_REASONING,
    CHART_INTERPRETER_THOUGHT,
)
from agent.llm import get_llm
from agent.prompts.chart_interpreter import CHART_INTERPRETER_SYSTEM_PROMPT, build_chart_interpreter_human_message
from agent.state import AgentState, StepResult
from langchain_core.messages import HumanMessage, SystemMessage


async def chart_interpreter(state: AgentState) -> dict:
    chart_context = state.get("chart_context")
    chart_context_payload = chart_context.model_dump(exclude_none=True) if chart_context else {}
    query = state.get("effective_query", state.get("raw_query", ""))
    llm = get_llm("chart_interpretation")
    messages = [
        SystemMessage(content=CHART_INTERPRETER_SYSTEM_PROMPT),
        HumanMessage(content=build_chart_interpreter_human_message(query, chart_context_payload)),
    ]
    response = await llm.ainvoke(messages)
    analysis = extract_json_from_llm(response.content)

    # Log trace to a JSON file for debugging
    import json
    import os
    from datetime import datetime
    
    trace_data = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "input_payload": chart_context_payload,
        "raw_response": response.content,
        "extracted_analysis": analysis
    }
    
    trace_file = "chart_interpreter_trace.json"
    traces = []
    if os.path.exists(trace_file):
        try:
            with open(trace_file, "r") as f:
                traces = json.load(f)
        except Exception:
            pass
            
    traces.append(trace_data)
    with open(trace_file, "w") as f:
        json.dump(traces, f, indent=2, default=str)

    return {
        "steps_completed": [
            StepResult(
                step_number=1,
                thought=CHART_INTERPRETER_THOUGHT,
                action=CHART_INTERPRETER_ACTION,
                query=query,
                result={
                    "chart_context": chart_context_payload,
                    "analysis": analysis,
                },
                observation=analysis.get("analysis_summary", ""),
            )
        ],
        "reasoning_history": [CHART_INTERPRETER_REASONING],
    }
