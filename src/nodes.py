import requests
import os
from langchain_anthropic import ChatAnthropic
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.messages import HumanMessage
from tavily import TavilyClient
from .state import AgentState
from . import ui

# Initialize Tools
llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
tavily = TavilyClient()

def identify_company(state: AgentState):
    """
    Resolves the company name to ensure we are looking at the right entity.
    """
    target = state['company_name']
    ui.print_step(f"Resolving Entity: {target}", status="running")
    
    # Search for definitive identity
    search = tavily.search(query=f"official name ticker sector business description {target}", max_results=1)
    raw_content = search['results'][0]['content']
    
    prompt = f"""
    Based on this search result, provide a clean, 3-sentence profile for {target}.
    Include: Official Legal Name, Stock Ticker (if public), and Primary Industry.
    
    Context: {raw_content}
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    
    # VISUAL: Show the user what we found
    ui.print_artifact("Entity Profile", response.content, style="blue")
    
    return {"company_profile": response.content}

def gather_financials(state: AgentState):
    """
    Waterfall Logic: PDF -> Web Fallback
    """
    ui.print_step("Researching Financials", status="running")
    company = state['company_name']
    
    # --- STRATEGY A: PDF ---
    query_pdf = f"{company} 2023 2024 annual report filetype:pdf"
    results = tavily.search(query=query_pdf, max_results=5)
    
    pdf_url = None
    for res in results['results']:
        if res['url'].endswith('.pdf'):
            pdf_url = res['url']
            break
            
    if pdf_url:
        ui.print_step(f"Found PDF: {pdf_url}", status="complete")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(pdf_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                with open("temp_report.pdf", "wb") as f:
                    f.write(response.content)
                
                loader = PyPDFLoader("temp_report.pdf")
                pages = loader.load()
                
                if len(pages) > 0:

                    essential_text = [p.page_content for p in pages[:5]]

                    financial_keywords = [
                        "consolidated balance sheets", 
                        "consolidated statements of operations", 
                        "consolidated statements of cash flows"
                    ]

                    found_financials = False
                    for i, page in enumerate(pages):
                        content = page.page_content.lower()
                        if any(k in content for k in financial_keywords):
                            # Capture this page and the next 5 pages for context
                            end_index = min(i + 6, len(pages))
                            essential_text.extend([p.page_content for p in pages[i:end_index]])
                            found_financials = True

                    if not found_financials:
                        essential_text = [p.page_content for p in pages[:20]] + [p.page_content for p in pages[-10:]]
                    
                    full_text = "\n".join(essential_text)

                    analysis_prompt = f"""
                    Analyze this Annual Report for {company}.
                    Extract key data (Estimate if exact numbers are messy):
                    1. Revenue & Profit Trends (Last 2 years)
                    2. Balance Sheet Health (Cash vs Debt)
                    3. Key Strategic Risks cited by management
                    
                    TEXT DATA: {full_text[:40000]}
                    """
                    result = llm.invoke([HumanMessage(content=analysis_prompt)])
                    
                    os.remove("temp_report.pdf")
                    
                    # VISUAL: Show the financial summary
                    ui.print_artifact("Financial Analysis (Source: PDF)", result.content, style="green")
                    
                    return {
                        "financial_data": result.content,
                        "pdf_url": pdf_url,
                        "data_confidence": "HIGH (Primary Source)"
                    }
        except Exception as e:
            ui.print_step(f"PDF download failed ({str(e)}). Switching strategy.", status="error")

    # --- STRATEGY B: WEB ---
    ui.print_step("Engaging Fallback Strategy (Web Search)", status="running")
    queries = [
        f"{company} revenue net income 2023 2024",
        f"{company} total debt cash balance sheet 2024",
        f"{company} business risks and challenges 2024"
    ]
    
    web_data = ""
    for q in queries:
        res = tavily.search(query=q, max_results=2)
        for r in res['results']:
            web_data += f"Source: {r['url']}\nContent: {r['content']}\n\n"
            
    fallback_prompt = f"""
    The annual report PDF was unavailable. Reconstruct the financial health of {company} 
    using these search results. 
    Explicitly state that this data is from secondary web sources.
    
    Web Data: {web_data}
    """
    result = llm.invoke([HumanMessage(content=fallback_prompt)])
    
    #Visual: web summary
    ui.print_artifact("Financial Analysis (Source: Web)", result.content, style="yellow")
    
    return {
        "financial_data": result.content,
        "pdf_url": None,
        "data_confidence": "LOW (Secondary Sources)"
    }

def gather_market_data(state: AgentState):
    """
    Gathers News (Narrative) and Social (Sentiment).
    """
    ui.print_step("Analyzing Market Sentiment", status="running")
    company = state['company_name']
    
    news = tavily.search(query=f"major news controversy {company} last 12 months", topic="news", days=365)
    social = tavily.search(query=f"reddit {company} customer employee sentiment review", max_results=5)
    
    context = f"NEWS DATA: {news['results']}\n\nSOCIAL DATA: {social['results']}"
    
    prompt = f"""
    Synthesize the external market view of {company}.
    1. Timeline of key events (M&A, Leadership changes, Products).
    2. Sentiment Analysis: How do customers/employees feel? (Positive/Negative/Neutral).
    3. Competitor Context: Who are they fighting?
    
    Raw Data: {context}
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    
    #Visual: market data
    ui.print_artifact("Market Intelligence", response.content, style="magenta")
    
    return {"market_data": response.content}

def synthesize_report(state: AgentState):
    """
    The 'Brain'. Connects Financials + Market Data + Profile into a cohesive story.
    """
    ui.print_step("Synthesizing Final Report", status="running")
    
    # Simple Conflict Check for UI Visual
    has_conflict = "conflict" in state.get('financial_data', '').lower() or "discrepancy" in state.get('market_data', '').lower()
    ui.print_conflict_alert(has_conflict)
    
    prompt = f"""
    You are a Deep Research Agent. 
    Write a comprehensive Investment Research Report for {state['company_profile']}.
    
    INPUTS:
    - Data Confidence Level: {state.get('data_confidence', 'Unknown')}
    - Financial Analysis: {state['financial_data']}
    - Market Intelligence: {state['market_data']}
    - Source URL: {state.get('pdf_url', 'N/A')}
    
    STRICT REPORT STRUCTURE:
    
    # Investment Report: [Company Name]
    **Report Date:** [Current Month Year]
    **Data Confidence Level:** [High/Medium/Low - Explain why]
    **Analyst Rating:** [Buy/Hold/Sell/Critical Warning]
    
    ## Executive Summary
    - High-level verdict (2-3 sentences).
    - Key strengths and immediate risks.
    - Investment Thesis (Why care?)

    ## Conflict Analysis: Internal vs. External View
    - **CRITICAL SECTION:** Create a table comparing Management's View (Financials/10-K) vs Market Reality (News/Sentiment).
    - Highlight specific discrepancies (e.g., "CEO says growth, employees say layoffs").
    - Assess the severity of each conflict.

    ## Financial Highlights
    - **Revenue & Profitability:** Key numbers, growth rates, margins (cite sources).
    - **Balance Sheet Strength:** Cash vs Debt, Liquidity, Credit risk.
    - **Key Ratios (Estimated):** If exact numbers missing, provide qualitative estimates based on context.
    
    ## Opportunities & Risks
    - **Strategic Opportunities:** AI, Expansion, New Products.
    - **Critical Risks:** Operational, Regulatory, Cultural, Financial.
    - **Emerging Threats:** Competitors, Macro factors.

    ## Analyst Note: Data Quality & Limitations
    - Explicitly state what data was found vs missing.
    - Rate source reliability (PDF vs Web).
    - Highlight any temporal mismatches (e.g., 2024 financials vs 2025 news).
    - Recommended Next Steps for Due Diligence.

    ## Conclusion & Recommendation
    - Final Verdict.
    - Target Investor Profile (Who is this for?).
    - 12-Month Outlook (Bull/Bear/Base cases).
    
    TONE: Professional, objective, critical. Avoid marketing fluff. Use Markdown tables and bolding for readability.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    
    ui.print_step("Report Generation Complete", status="complete")
    
    return {"final_report": response.content}