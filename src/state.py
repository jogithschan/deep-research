from typing import TypedDict, Optional

class AgentState(TypedDict):
    company_name: str           # Input
    company_profile: str        # Resolved Identity
    company_sector: str         # Extracted Sector
    ticker: Optional[str]       # Stock Ticker if available
    financial_data: str         # Analysis from Annual Report/Web
    market_data: str            # News & Sentiment analysis
    final_report: str           # Markdown output
    pdf_url: Optional[str]      # Source URL if found
    data_confidence: str        # "HIGH" (PDF) or "LOW" (Web fallback)