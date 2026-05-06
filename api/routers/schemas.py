from pydantic import BaseModel, Field
from typing import Optional, Any

class ChatRequest(BaseModel):
    query: str
    session_id: str
    chart_context: Optional[dict] = None

class ChatResponse(BaseModel):
    response_type: str
    narrative: str
    artifacts: list[dict] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)
    clarification_question: Optional[str] = None
    disclaimer: Optional[str] = None
