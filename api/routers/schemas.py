from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime

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

class SessionSummary(BaseModel):
    session_id: str
    title: Optional[str] = None
    summary: Optional[str] = None
    updated_at: datetime

class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime