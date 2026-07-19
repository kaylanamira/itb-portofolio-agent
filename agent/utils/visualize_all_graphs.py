import os
from agent.orchestrator import main_graph
from agent.graph import portfolio_graph
from agent.nodes.sql_pipeline import _portfolio_sql_pipeline
from core.config import settings

def main():
    # 1. Use the existing SQL Pipeline subgraph
    print("Loading SQL Pipeline subgraph...")
    sql_pipeline_graph = _portfolio_sql_pipeline

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
        from langchain_core.runnables.graph_mermaid import draw_mermaid_png
        mermaid_text = main_graph.get_graph(xray=1).draw_mermaid()
        
        # Customizations:
        # 1. Remove catalog_lookup
        # 2. Add box around sql_pipeline, rag_retriever, chart_interpreter
        lines = mermaid_text.split('\n')
        new_lines = []
        tools = [
            "portfolio_agent\\3asql_pipeline(sql_pipeline)",
            "portfolio_agent\\3arag_retriever(rag_retriever)",
            "portfolio_agent\\3achart_interpreter(chart_interpreter)"
        ]
        tools_inserted = False

        for line in lines:
            if "catalog_lookup" in line:
                continue
            
            is_tool_def = any(t in line and not "-->" in line and not "-.->" in line for t in tools)
            if is_tool_def:
                if not tools_inserted:
                    new_lines.append("\tsubgraph tools_box [Tools]")
                    for t in tools:
                        new_lines.append(f"\t{t}")
                    new_lines.append("\tend")
                    tools_inserted = True
                continue
                
            new_lines.append(line)

        new_mermaid = '\n'.join(new_lines)
        main_xray_png = draw_mermaid_png(new_mermaid)
        
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

# how to run : uv run python -m agent.utils.visualize_all_graphs