import os
from agent.orchestrator import main_graph
from agent.graph import portfolio_graph
from agent.tools.sql import build_sql_pipeline
from agent.nodes.sql_pipeline import (
    _portfolio_entity_resolver,
    _portfolio_few_shot_examples,
    load_schema_context,
    SCHEMA_LINKER_SYSTEM_PROMPT,
)
from core.config import settings

def main():
    # 1. Build the SQL Pipeline subgraph dynamically
    print("Compiling SQL Pipeline subgraph...")
    sql_pipeline_graph = build_sql_pipeline(
        schema_linker_prompt=SCHEMA_LINKER_SYSTEM_PROMPT,
        entity_resolver=_portfolio_entity_resolver,
        few_shot_examples=_portfolio_few_shot_examples,
        schema_context=load_schema_context(),
        default_table="v_akademik_kelas",
        max_attempts=settings.MAX_SQL_ATTEMPTS,
    )

    # Ensure output directory exists
    output_dir = "diagram"
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving diagram to './{output_dir}/' directory...")

    # 2. Draw Main Orchestrator Graph
    print("Generating main_graph.png...")
    main_png = main_graph.get_graph(xray=False).draw_mermaid_png()
    with open(os.path.join(output_dir, "main_graph.png"), "wb") as f:
        f.write(main_png)

    # 3. Draw Main Orchestrator Graph with X-Ray (subgraphs expanded!)
    print("Generating main_graph_xray.png...")
    try:
        main_xray_png = main_graph.get_graph(xray=True).draw_mermaid_png()
        with open(os.path.join(output_dir, "main_graph_xray.png"), "wb") as f:
            f.write(main_xray_png)
    except Exception as e:
        print(f"Skipping X-Ray visualizer: {e} (usually requires standard mermaid integration updates)")

    # 4. Draw Portfolio Agent Graph
    print("Generating portfolio_agent_graph.png...")
    portfolio_png = portfolio_graph.get_graph(xray=True).draw_mermaid_png()
    with open(os.path.join(output_dir, "portfolio_agent_graph.png"), "wb") as f:
        f.write(portfolio_png)

    # 5. Draw SQL Pipeline Graph
    print("Generating sql_pipeline_graph.png...")
    sql_png = sql_pipeline_graph.get_graph(xray=True).draw_mermaid_png()
    with open(os.path.join(output_dir, "sql_pipeline_graph.png"), "wb") as f:
        f.write(sql_png)

    print("\nSUCCESS! All graph diagrams have been saved:")
    print(f"  - {output_dir}/main_graph.png")
    print(f"  - {output_dir}/main_graph_xray.png")
    print(f"  - {output_dir}/portfolio_agent_graph.png")
    print(f"  - {output_dir}/sql_pipeline_graph.png")

if __name__ == "__main__":
    main()

# how to run : uv run python utils/visualize_all_graphs.py