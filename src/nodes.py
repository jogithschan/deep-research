import requests
import os
from langchain_anthropic import ChatAnthropic
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.messages import HumanMessage
from tavily import TavilyClient
from .state import AgentState

# Initialize Tools
# Ensure API keys are loaded in main.py or env
llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)

def get_tavily():
    return TavilyClient() # Will pick up env var when called, not at import

def identify_company(state: AgentState):
    """
    Resolves the company name to ensure we are looking at the right entity.
    """
    tavily = get_tavily()
    target = state['company_name']
    print(f"\n--- 1. IDENTIFYING ENTITY: {target} ---")
    
    # Search for definitive identity
    search = tavily.search(query=f"official name ticker sector business description {target}", max_results=1)
    raw_content = search['results'][0]['content']
    
    prompt = f"""
    Based on this search result, provide a clean, 3-sentence profile for {target}.
    Include: Official Legal Name, Stock Ticker (if public), and Primary Industry.
    
    Context: {raw_content}
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    
    return {"company_profile": response.content}

def gather_financials(state: AgentState):
    """
    Waterfall Logic:
    1. Try to find & download Official Annual Report PDF (High Confidence)
    2. Fallback to Web Search for numbers (Low Confidence)
    """
    tavily=get_tavily()
    print("\n--- 2. GATHERING FINANCIALS ---")
    company = state['company_name']
    
    # --- STRATEGY A: PRIMARY SOURCE (PDF) ---
    query_pdf = f"{company} 2023 2024 annual report filetype:pdf"
    results = tavily.search(query=query_pdf, max_results=5)
    
    pdf_url = None
    # naive filter for PDFs
    for res in results['results']:
        if res['url'].endswith('.pdf'):
            pdf_url = res['url']
            break
            
    if pdf_url:
        print(f"   -> Found PDF: {pdf_url}")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(pdf_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                # Save temporarily
                with open("temp_report.pdf", "wb") as f:
                    f.write(response.content)
                
                # Heuristic: Load first 20 pages (Strategy) + Last 15 pages (Financials)
                # This fits better in context windows than the whole 200pg doc
                loader = PyPDFLoader("temp_report.pdf")
                pages = loader.load()
                
                # Safety check for empty PDFs (scanned images)
                if len(pages) > 0:
                    intro_text = "\n".join([p.page_content for p in pages[:20]])
                    fin_text = "\n".join([p.page_content for p in pages[-15:]])
                    full_text = intro_text + "\n ... [SKIPPED MIDDLE] ... \n" + fin_text
                    
                    print("   -> PDF Downloaded & Parsed. Analyzing...")
                    
                    analysis_prompt = f"""
                    Analyze this Annual Report for {company}.
                    Extract key data (Estimate if exact numbers are messy):
                    1. Revenue & Profit Trends (Last 2 years)
                    2. Balance Sheet Health (Cash vs Debt)
                    3. Key Strategic Risks cited by management
                    
                    TEXT DATA: {full_text[:40000]}
                    """
                    result = llm.invoke([HumanMessage(content=analysis_prompt)])
                    
                    # Clean up
                    os.remove("temp_report.pdf")
                    
                    return {
                        "financial_data": result.content,
                        "pdf_url": pdf_url,
                        "data_confidence": "HIGH (Primary Source)"
                    }
        except Exception as e:
            print(f"   -> PDF Strategy Failed ({str(e)}). Switching to fallback.")

    # --- STRATEGY B: SECONDARY SOURCE (WEB) ---
    print("   -> Using Web Fallback Strategy.")
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
    
    IMPORTANT: Explicitly state that this data is from secondary web sources.
    
    Web Data: {web_data}
    """
    result = llm.invoke([HumanMessage(content=fallback_prompt)])
    
    return {
        "financial_data": result.content,
        "pdf_url": None,
        "data_confidence": "LOW (Secondary Sources)"
    }

def gather_market_data(state: AgentState):
    """
    Gathers News (Narrative) and Social (Sentiment).
    """
    tavily=get_tavily()
    print("\n--- 3. GATHERING MARKET CONTEXT ---")
    company = state['company_name']
    
    # News Search
    news = tavily.search(query=f"major news controversy {company} last 12 months", topic="news", days=365)
    
    # Social/Sentiment Search
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
    
    return {"market_data": response.content}

def synthesize_report(state: AgentState):
    """
    The 'Brain'. Connects Financials + Market Data + Profile into a cohesive story.
    """
    print("\n--- 4. WRITING FINAL REPORT ---")
    
    prompt = f"""
    You are a Deep Research Agent. Write a structured investment report for {state['company_profile']}.
    
    INPUTS:
    - Data Confidence Level: {state.get('data_confidence', 'Unknown')}
    - Financial Analysis: {state['financial_data']}
    - Market Intelligence: {state['market_data']}
    - Source URL: {state.get('pdf_url', 'N/A')}
    
    REQUIREMENTS:
    1. **Executive Summary**: High-level verdict.
    2. **Conflict Analysis**: Compare Financials (Internal View) vs Market (External View). 
       - Example: "Management says growth is strong, but user reviews cite declining quality."
    3. **Financial Highlights**: Use the confidence level to frame this section appropriately.
    4. **Opportunities & Risks**: Synthesized from all sources.
    5. **Analyst Note**: Comment on the data quality/sources used.
    
    OUTPUT FORMAT: Markdown.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    
    return {"final_report": response.content}