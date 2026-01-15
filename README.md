# Deep Research Agent PoC

A targeted AI agent that performs autonomous investment research by synthesizing financial filings (PDFs) with market intelligence (Web Search).

## Key Features
- **Waterfall Data Retrieval:** Prioritizes official PDF Annual Reports; falls back to web search if unavailable.
- **Conflict Detection:** explicitly analyzes discrepancies between internal financial reporting and external market sentiment.
- **Entity Resolution:** Handles ambiguous company names (e.g., distinguishing "Peloton Minerals" from "Peloton Interactive").
- **Stateful Architecture:** Built on LangGraph to manage research context and data confidence levels.

## Architecture
1. **Identify Node:** Resolves company identity.
2. **Financial Node:** Fetches/Parses PDFs or performs targeted financial scraping.
3. **Market Node:** Aggregates news, sentiment, and competitor analysis.
4. **Synthesizer Node:** Reason over inputs to produce the final Markdown report.

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Add API Keys to `main.py` or `.env`.
3. Run: `python main.py`