from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.graph import portfolio_graph
from agent.nodes.intent_classifier import intent_classifier
from agent.nodes.synthesizer import synthesizer

async def wisudawan_agent(state: AgentState):
    return {
        "abort_reason": "Fitur modul Wisudawan ITB saat ini masih dalam tahap pengembangan dan belum dapat diakses."
    }

def route_after_intent(state: AgentState) -> str:
    domain = state.get("domain", "out_of_scope")
    if domain == "portfolio":
        return "portfolio_agent"
    elif domain == "wisudawan":
        return "wisudawan_agent"
    return "out_of_scope"

def build_main_graph():
    g = StateGraph(AgentState)
    g.add_node("intent_classifier", intent_classifier)
    g.add_node("portfolio_agent", portfolio_graph)
    g.add_node("wisudawan_agent", wisudawan_agent)
    g.add_node("out_of_scope", synthesizer)
    
    g.set_entry_point("intent_classifier")
    
    g.add_conditional_edges("intent_classifier", route_after_intent, {
        "portfolio_agent": "portfolio_agent",
        "wisudawan_agent": "wisudawan_agent",
        "out_of_scope": "out_of_scope",
    })
    
    g.add_edge("portfolio_agent", END)
    g.add_edge("wisudawan_agent", "out_of_scope")
    # g.add_edge("wisudawan_agent", END)
    g.add_edge("out_of_scope", END)
    
    return g.compile()

main_graph = build_main_graph()
