import asyncio
from core.database import init_db_pool, close_db_pool
from core.sql_executor import PsycopgExecutor
from core.scope import UserScope, ScopeEntry, UserRole
from agent.tools.rag.retrieval.hybrid_retriever import HybridRetriever

# uv run python test_retriever.py
async def main():
    await init_db_pool()
    try:
        executor = PsycopgExecutor()
        retriever = HybridRetriever(executor)
        
        # We use the admin scope to bypass RLS, just like in ingestion
        admin_entry = ScopeEntry(user_role_id=1, role=UserRole.ADMIN)
        user_scope = UserScope(user_id=1, active_role=admin_entry)
        
        query = "Bagaimana pendapat mahasiswa mengenai praktikum?"
        print(f"Searching for: '{query}'\n")
        
        results = await retriever.retrieve(
            query=query,
            user_scope=user_scope,
            source_types=["komentar_mahasiswa"]
        )
        
        print(f"Found {len(results)} chunks:\n")
        for i, chunk in enumerate(results, 1):
            print(f"--- Result {i} (Chunk ID: {chunk['chunk_id']}) ---")
            print(f"Text: {chunk['chunk_text']}\n")
            
    finally:
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())
