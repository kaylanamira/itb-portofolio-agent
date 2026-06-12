import logging
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.graph import portfolio_graph
from agent.wisudawan_graph import wisudawan_graph
from agent.nodes.input_guard import input_guard, route_after_input_guard
from agent.nodes.intent_classifier import intent_classifier, route_after_intent
from agent.nodes.synthesizer import synthesizer

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrator class for managing the ITB Academic Portfolio Agent workflow."""

    def __init__(self):
        self.graph = self.build_main_graph()

    def build_main_graph(self):
        logger.info("Initializing main orchestrator StateGraph...")
        g = StateGraph(AgentState)
        g.add_node("input_guard", input_guard)
        g.add_node("intent_classifier", intent_classifier)
        g.add_node("portfolio_agent", portfolio_graph)
        g.add_node("wisudawan_agent", wisudawan_graph)
        g.add_node("out_of_scope", synthesizer)
        
        g.set_entry_point("input_guard")
        g.add_conditional_edges("input_guard", route_after_input_guard, {
            "intent_classifier": "intent_classifier",
            "out_of_scope": "out_of_scope",
        })
        
        g.add_conditional_edges("intent_classifier", route_after_intent, {
            "portfolio_agent": "portfolio_agent",
            "wisudawan_agent": "wisudawan_agent",
            "out_of_scope": "out_of_scope",
        })
        
        g.add_edge("portfolio_agent", END)
        g.add_edge("wisudawan_agent", END)
        g.add_edge("out_of_scope", END)
        
        logger.info("Compiling the main orchestrator StateGraph...")
        compiled_graph = g.compile()
        logger.info("Main orchestrator graph compiled successfully.")
        return compiled_graph

    def get_graph_visualization(self) -> bytes:
        """Get the LangGraph workflow visualization as PNG.

        This method generates a visual representation of the graph workflow
        using mermaid diagram format, then converts it to PNG.

        :returns: PNG image bytes
        :raises ImportError: If required dependencies (pygraphviz/graphviz) are not installed
        :raises Exception: If graph visualization generation fails
        """
        try:
            logger.info("Generating graph visualization PNG...")
            return self.graph.get_graph().draw_mermaid_png()
        except ImportError as e:
            logger.error("Failed to import dependencies for graph visualization: %s", e)
            raise ImportError(
                "Required dependencies (pygraphviz/graphviz) are not installed."
            ) from e
        except Exception as e:
            logger.error("Failed to generate graph visualization: %s", e)
            raise Exception(
                f"Failed to generate graph visualization: {e}"
            ) from e

    def __getattr__(self, name):
        return getattr(self.graph, name)

main_graph = AgentOrchestrator()
