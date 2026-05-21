import asyncio
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
import time
import logging

logging.basicConfig(level=logging.DEBUG)

async def main():
    llm = get_llm("step_reasoning")
    print(f"Using model: {llm.model_name}")
    start = time.time()
    try:
        response = await llm.ainvoke([
            SystemMessage(content="Reply with JSON: {\"fully_answered\": true}"),
            HumanMessage(content="Test")
        ])
        print(f"Time: {time.time() - start:.2f}s")
        print(f"Response: {response.content}")
    except Exception as e:
        print(f"Error: {e}")
        print(f"Time: {time.time() - start:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
