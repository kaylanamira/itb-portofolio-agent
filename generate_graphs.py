from agent.sql_pipeline import sql_pipeline
import os
from agent.orchestrator import main_graph
from agent.graph import portfolio_graph

def generate_graphs():
    os.makedirs("diagram", exist_ok=True)

    print("Generating main_graph.mermaid...")
    with open("diagram/main_graph.mermaid", "w") as f:
        f.write(main_graph.get_graph().draw_mermaid())

    print("Generating sql_graph.mermaid...")
    with open("diagram/sql_graph.mermaid", "w") as f:
        f.write(sql_pipeline.get_graph().draw_mermaid())
        
    print("Generating portfolio_graph.mermaid...")
    with open("diagram/portfolio_graph.mermaid", "w") as f:
        f.write(portfolio_graph.get_graph().draw_mermaid())
        
    print("Done! Mermaid graphs saved to diagram/ directory.")

if __name__ == "__main__":
    generate_graphs()

# how to run : uv run python generate_graphs.py
# how to see : copy the contents of those files and paste them into https://mermaid.live/.