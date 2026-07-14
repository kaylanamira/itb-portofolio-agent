import asyncio
import sys

from core.database import init_db_pool, close_db_pool
from core.scope import UserScope, ScopeEntry, UserRole
from agent.tools.rag.pipeline import run_rag
from agent.tools.rag.retrieval.hybrid_retriever import HybridRetriever
from core.sql_executor import PsycopgExecutor


async def check_raw_retrieval(query: str, user_scope: UserScope):
    retriever = HybridRetriever(PsycopgExecutor())
    results = await retriever.retrieve(query=query, user_scope=user_scope)
    print(f"\n=== Raw hybrid retrieval: {len(results)} chunks ===")
    for i, chunk in enumerate(results, 1):
        print(f"--- Result {i} (chunk_id: {chunk['chunk_id']}) ---")
        print(f"{chunk['chunk_text'][:300]}\n")


async def check_full_pipeline(query: str, user_scope: UserScope):
    result = await run_rag(query=query, user_scope=user_scope)
    print("\n=== Full RAG pipeline result ===")
    print(f"rag_query:            {result.rag_query}")
    print(f"hyde_used:            {result.hyde_used}")
    print(f"filters_applied:      {result.filters_applied}")
    print(f"retrieval_action:     {result.retrieval_action} (confidence={result.retrieval_confidence:.2f})")
    print(f"faithfulness_action:  {result.faithfulness_action} (score={result.faithfulness_score:.2f})")
    print(f"attempts:             {result.attempts}")
    print(f"chunks_used:          {len(result.chunks_used)}")
    print(f"\nanswer:\n{result.answer}\n")
    print(f"citations: {result.citations}")


async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "Bagaimana pendapat mahasiswa mengenai praktikum?"

    await init_db_pool()
    try:
        admin_entry = ScopeEntry(user_role_id=1, role=UserRole.ADMIN)
        user_scope = UserScope(user_id=1, active_role=admin_entry)

        print(f"Query: {query!r}")
        await check_raw_retrieval(query, user_scope)
        await check_full_pipeline(query, user_scope)
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
