import re
import json
import logging

logger = logging.getLogger(__name__)

def extract_json_from_llm(text: str) -> dict:
    """Safely extract JSON from LLM responses, even if wrapped in markdown code blocks."""
    text = text.strip()
    
    # Attempt to extract from markdown blocks
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        text = match.group(1).strip()
        
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from LLM: {e}\nRaw text was:\n{text}")
        raise
