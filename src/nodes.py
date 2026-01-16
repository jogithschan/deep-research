import requests
import os
import json
from datetime import datetime
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

    if not search['results']:
        return {"company_profile": f"Could not identify {target}", "company_sector": ""}
    
    raw_content = search['results'][0]['content']

    prompt = f"""
    Analyze {target}. Return a JSON with:
    - name: Official Name
    - ticker: Ticker (or None)
    - sector: Specific Industry (e.g. "Consumer Electronics", "Software", "Financial Services")
    - description: Brief profile
    
    Context: {raw_content}
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    
    # JSON Parse
    try:
        data = json.loads(response.content.replace('```json', '').replace('```', '').strip())
        profile = f"{data['name']} ({data['ticker']}) - {data['sector']}\n{data['description']}"
        sector = data['sector']
        ticker = data['ticker']
    except:
        profile = response.content
        sector = "Business" # fallback

    ui.print_artifact("Entity Profile", profile, style="blue")
    
    return {
        "company_profile": profile, 
        "company_sector": sector,
        "ticker": ticker
    }

def gather_financials(state: AgentState):
    ui.print_step("Researching Financials", status="running")
    company = state['company_name']
    ticker = state.get('ticker', '')
    
    # --- STRATEGY A: PDF  ---
    if ticker and ticker != "None":
        query_pdf = f"{company} {ticker} annual report 2025 financial statements Item 8 -proxy filetype:pdf"
    else:
        query_pdf = f"{company} annual report 2025 financial statements filetype:pdf"
    
    results = tavily.search(query=query_pdf, max_results=3)
    
    pdf_url = None
    pdf_data = None
    
    # Try to find a valid PDF
    for res in results['results']:
        if res['url'].endswith('.pdf'):
            pdf_url = res['url']
            
            # --- ATTEMPT DOWNLOAD & PARSE ---
            try:
                ui.print_step(f"Analyzing PDF: {pdf_url}", status="running")
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                response = requests.get(pdf_url, headers=headers, timeout=15)
                
                with open("temp_report.pdf", "wb") as f:
                    f.write(response.content)
                
                loader = PyPDFLoader("temp_report.pdf")
                pages = loader.load()
                
                # Smart Slicing: Look for "Consolidated" tables specifically
                essential_text = []
                financial_keywords = ["consolidated balance sheets", "consolidated statements of operations", "consolidated statements of cash flows"]
                
                for i, page in enumerate(pages):
                    content = page.page_content.lower()
                    # We look for keywords AND numbers (to avoid Table of Contents)
                    if any(k in content for k in financial_keywords) and any(char.isdigit() for char in content):
                        # Grab this page + next 3
                        end_index = min(i + 4, len(pages))
                        essential_text.extend([p.page_content for p in pages[i:end_index]])
                
                if not essential_text:
                    mid = len(pages) // 2
                    essential_text = [p.page_content for p in pages[:5]] + \
                                     [p.page_content for p in pages[mid:mid+5]] + \
                                     [p.page_content for p in pages[-10:]]

                full_text = "\n".join(essential_text)
                
                # Extraction Prompt
                analysis_prompt = f"""
                Extract specific financial tables for {company} from the text below.
                
                CRITICAL: Output THREE Markdown tables for the last 2 available years.
                1. **Income Statement** (Revenue, Net Income, EPS)
                2. **Balance Sheet** (Assets, Debt, Equity)
                3. **Cash Flow** (Operating, Free Cash Flow)
                
                If the text does NOT contain the actual financial numbers, strictly return: "DATA_UNAVAILABLE"

                TEXT DATA: {full_text[:50000]}
                """
                
                result = llm.invoke([HumanMessage(content=analysis_prompt)])
                os.remove("temp_report.pdf")

                # --- VALIDATION STEP ---
                # If the LLM says data is missing, or returns N/A for Revenue, reject the PDF
                if "DATA_UNAVAILABLE" in result.content or "Total Revenue | N/A" in result.content:
                    ui.print_step("PDF lacked financial tables. Skipping...", status="error")
                    pdf_url = None # Reset to trigger fallback
                    continue # Try next PDF or go to Web
                
                ui.print_artifact("Financial Analysis (Source: PDF)", result.content, style="green")
                return {
                    "financial_data": result.content,
                    "pdf_url": pdf_url,
                    "data_confidence": "HIGH (Primary Source)"
                }

            except Exception as e:
                ui.print_step(f"PDF Parse Failed: {str(e)}", status="error")
                continue

    # --- STRATEGY B: WEB FALLBACK (Runs if PDF fails or yields N/A) ---
    ui.print_step("Engaging Targeted Financial Search (Web)", status="running")
    
    # Specific queries to fill the specific tables
    queries = [
        f"{company} annual income statement 2025 2024 revenue net income table",
        f"{company} balance sheet 2025 2024 total assets debt equity table",
        f"{company} cash flow statement 2025 2024 operating investing free cash flow table"
    ]
    
    web_data = ""
    for q in queries:
        res = tavily.search(query=q, max_results=2, include_raw_content=True)
        for r in res['results']:
            web_data += f"Source: {r['url']}\nContent: {r['content']}\n\n"
            
    fallback_prompt = f"""
    The official 10-K PDF was unavailable. Reconstruct the financial tables for {company} using these search results.
    
    Task:
    Create THREE Markdown tables for the last 2 years (2025 vs 2024 or similar):
    1. **Income Statement**
    2. **Balance Sheet**
    3. **Cash Flow**
    
    Web Data: {web_data}
    """
    result = llm.invoke([HumanMessage(content=fallback_prompt)])
    
    ui.print_artifact("Financial Analysis (Source: Web)", result.content, style="yellow")
    
    return {
        "financial_data": result.content,
        "pdf_url": None,
        "data_confidence": "LOW (Secondary Web Sources)"
    }

def gather_market_data(state: AgentState):
    """
    Gathers News (Narrative) and Social (Sentiment).
    """
    ui.print_step("Analyzing Market Sentiment", status="running")
    company = state['company_name']
    
    news = tavily.search(query=f"major news controversy {company} last 12 months", topic="news", days=365)
    social = tavily.search(query=f"reddit {company} customer employee sentiment review", max_results=5)
    competitors = tavily.search(query=f"top 3 competitors {company} market share analysis 2025", max_results=3)
    
    context = f"""
    NEWS: {news['results']}
    SENTIMENT: {social['results']}
    COMPETITORS: {competitors['results']}
    """
    
    prompt = f"""
    Synthesize the external market view of {company}.
    1. Timeline of key events (M&A, Leadership changes, Products).
    2. Sentiment Analysis: How do customers/employees feel? (Positive/Negative/Neutral).
    3. Competitor Context: Who are the rivals? How does {company} stack up?
    
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

    today = datetime.now().strftime("%B %d, %Y")
    
    prompt = f"""
    You are a Deep Research Agent. 
    Write a comprehensive Investment Research Report for {state['company_profile']}.
    
    INPUTS:
    - Data Confidence Level: {state.get('data_confidence', 'Unknown')}
    - Financial Data (Contains Tables): {state['financial_data']}
    - Market Intelligence: {state['market_data']}
    - Source URL: {state.get('pdf_url', 'N/A')}
    
    STRICT REPORT STRUCTURE:
    
    # Investment Report: {state.get('company_name')}
    **Report Date:**: {today}
    **Data Confidence Level:** [High/Medium/Low]
    **Analyst Rating:** [Buy/Hold/Sell/Critical Warning]
    
    ## Executive Summary
    - High-level verdict (2-3 sentences).
    - Investment Thesis.

    ## Conflict Analysis: Internal vs. External View
    - **CRITICAL:** Create a table comparing Management's View (Financials) vs Market Reality (Sentiment).
    - Assess severity of conflicts.

    ## Financial Highlights (Detailed)
    - **CRITICAL:** You MUST reproduce the "Income Statement", "Balance Sheet", and "Cash Flow" tables provided in the Financial Data input. 
    - Do not summarize these tables into text; display the full markdown tables for the last 2 years.
    - Below the tables, provide a brief analysis of:
      - Margins (Gross/Net)
      - Liquidity (Cash vs Debt position)
      - Solvency concerns (if any)
    
    ## Opportunities & Risks
    - **Strategic Opportunities:** AI, Expansion, New Products.
    - **Critical Risks:** Operational, Regulatory, Cultural, Financial.
    - **Emerging Threats:** Competitors, Macro factors.

    ## Analyst Note: Data Quality & Limitations
    - Explicitly state what data was found vs missing.
    - Rate source reliability.
    - Recommended Next Steps for Due Diligence.

    ## Conclusion & Recommendation
    - Final Verdict.
    - Target Investor Profile.
    - 12-Month Outlook.
    
    TONE: Professional, objective, critical. Use Markdown tables for all financial data.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    
    ui.print_step("Report Generation Complete", status="complete")
    
    return {"final_report": response.content}