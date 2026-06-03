"""CLI runner for testing the ITB Academic Portfolio agent locally.

Usage:
    uv run python runner.py "Ada berapa prodi aktif di STEI?"
    uv run python runner.py --role kaprodi --no-ps 135 "Berapa rata-rata IP mahasiswa?"
    uv run python runner.py --role dosen --dosen-id 42 "Kelas apa yang saya ajar semester ini?"
    uv run python runner.py --stream "Bandingkan kehadiran dosen antar prodi STEI"
"""

import argparse
import asyncio
import sys

from agent.orchestrator import main_graph
from agent.state import AgentState
from core.database import init_db_pool, close_db_pool
from core.scope import ScopeEntry, UserRole, UserScope


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ITB Portfolio Agent local runner")
    p.add_argument("query", help="Natural language query to run")
    p.add_argument("--role", default="direktorat", help="User role (e.g. direktorat, kaprodi, dosen)")
    p.add_argument("--user-id", type=int, default=100, dest="user_id")
    p.add_argument("--dosen-id", type=int, default=None, dest="dosen_id")
    p.add_argument("--no-ps", type=int, default=None, dest="no_ps")
    p.add_argument("--kd-fak", type=str, default=None, dest="kd_fak")
    p.add_argument("--stream", action="store_true", help="Stream node-by-node output")
    return p.parse_args()


def _build_scope(args: argparse.Namespace) -> UserScope:
    try:
        role = UserRole(args.role.lower())
    except ValueError:
        print(f"Unknown role '{args.role}'. Valid: {[r.value for r in UserRole]}", file=sys.stderr)
        sys.exit(1)

    active_role = ScopeEntry(
        user_role_id=1,
        role=role,
        dosen_id=args.dosen_id,
        no_ps=args.no_ps,
        kd_fak=args.kd_fak,
        is_prime=True,
    )
    return UserScope(
        user_id=args.user_id,
        active_role=active_role,
        available_roles=[active_role],
    )


def _build_state(query: str, user_scope: UserScope) -> AgentState:
    return AgentState(
        user_scope=user_scope,
        session_id="runner",
        messages=[{"role": "user", "content": query}],
        raw_query=query,
        effective_query=query,
        attempt_count=0,
        max_attempts=3,
        error_history=[],
        is_aborted=False,
    )


async def run_stream(query: str, user_scope: UserScope) -> None:
    state = _build_state(query, user_scope)
    print(f"\nQuery   : {query}")
    print(f"Role    : {user_scope.role.value} (user_id={user_scope.user_id})\n")

    async for _ns, output in main_graph.astream(state, subgraphs=True):
        for node_name, update in output.items():
            print(f"── {node_name.upper()} ──")
            if update.get("plan"):
                print(f"  PLAN      : {update['plan']}")
            if update.get("reasoning_history"):
                print(f"  REASONING : {update['reasoning_history'][-1]}")
            if update.get("generated_sql"):
                print(f"  SQL       :\n{update['generated_sql']}")
            if update.get("sql_error"):
                print(f"  SQL ERROR : {update['sql_error']}")
            if update.get("sql_result") is not None:
                print(f"  ROWS      : {len(update['sql_result'])}")
            if update.get("formatted_response"):
                resp = update["formatted_response"]
                print(f"\n{'='*60}")
                print(f"ANSWER:\n{resp.narrative}")
                if resp.disclaimer:
                    print(f"\nNOTE: {resp.disclaimer}")
                if resp.follow_up_suggestions:
                    print(f"\nSuggestions:")
                    for s in resp.follow_up_suggestions:
                        print(f"  • {s}")


async def run_once(query: str, user_scope: UserScope) -> None:
    state = _build_state(query, user_scope)
    print(f"\nQuery   : {query}")
    print(f"Role    : {user_scope.role.value} (user_id={user_scope.user_id})\n")

    final = await main_graph.ainvoke(state)
    resp = final.get("formatted_response")

    if resp:
        print(f"{'='*60}")
        print(f"ANSWER:\n{resp.narrative}")
        if resp.disclaimer:
            print(f"\nNOTE: {resp.disclaimer}")
        if resp.follow_up_suggestions:
            print(f"\nSuggestions:")
            for s in resp.follow_up_suggestions:
                print(f"  • {s}")
    else:
        print("No formatted_response produced.")


async def main() -> None:
    args = _parse_args()
    user_scope = _build_scope(args)

    await init_db_pool()
    try:
        if args.stream:
            await run_stream(args.query, user_scope)
        else:
            await run_once(args.query, user_scope)
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
