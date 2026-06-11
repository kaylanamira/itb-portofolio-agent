import json
from deepeval.models import DeepEvalBaseLLM
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from typing import Any
from agent.llm import get_llm


class CustomDeepEvalLLM(DeepEvalBaseLLM):
    def __init__(self, model_name: str = "llm_evaluation"):
        self.model_name = model_name
        self.llm = get_llm(self.model_name, force_json=False)
    
    def load_model(self):
        return self.llm
        
    def generate(self, prompt: str, schema: BaseModel = None, **kwargs) -> Any:
        model = self.load_model()
        if schema is not None:
            model = model.with_structured_output(schema)
        msg = HumanMessage(content=prompt)
        res = model.invoke([msg])
        if schema is not None:
             return res
        return res.content

    async def a_generate(self, prompt: str, schema: BaseModel = None, **kwargs) -> Any:
        model = self.load_model()
        if schema is not None:
            model = model.with_structured_output(schema)
        msg = HumanMessage(content=prompt)
        res = await model.ainvoke([msg])
        if schema is not None:
             return res
        return res.content
        
    def get_model_name(self):
        return self.model_name

custom_judge = CustomDeepEvalLLM("llm_evaluation")
