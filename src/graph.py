from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import identify_company, gather_financials, gather_market_data, synthesize_report

def build_graph():
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("identify", identify_company)
    workflow.add_node("financials", gather_financials)
    workflow.add_node("market", gather_market_data)
    workflow.add_node("write", synthesize_report)

    # Add Edges (Linear Process)
    workflow.set_entry_point("identify")
    workflow.add_edge("identify", "financials")
    workflow.add_edge("financials", "market")
    workflow.add_edge("market", "write")
    workflow.add_edge("write", END)

    return workflow.compile()