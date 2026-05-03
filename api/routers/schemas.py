from pydantic import BaseModel, Field
from typing import Optional, Any

class ChatRequest(BaseModel):
    query: str
    session_id: str
    chart_context: Optional[dict] = None

class ChatResponse(BaseModel):
    response_type: str
    narrative: Optional[str] = None
    data: Optional[Any] = None
    chart_spec: Optional[dict] = None
    clarification_question: Optional[str] = None
    disclaimer: Optional[str] = None
