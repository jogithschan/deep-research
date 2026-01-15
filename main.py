import os
from dotenv import load_dotenv
load_dotenv()
from src.graph import build_graph

def main():
    if not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("TAVILY_API_KEY"):
        print("Error: Please set ANTHROPIC_API_KEY and TAVILY_API_KEY in .env file")
        return

    # User Input
    print("--- DEEP RESEARCH AGENT POC ---")
    company = input("Enter Company Name to Research: ")
    
    # Initialize Graph
    app = build_graph()
    
    # Initial State
    initial_state = {"company_name": company}
    
    # Run Graph
    print(f"Starting research on {company}...")
    result = app.invoke(initial_state)
    
    # Output Handling
    filename = f"{company.replace(' ', '_')}_Report.md"
    with open(filename, "w", encoding='utf-8') as f:
        f.write(result["final_report"])
        
    print(f"\n✅ Report generated successfully: {filename}")
    print("-" * 50)
    print("Preview of Executive Summary:")
    print("-" * 50)
    # Simple print of first 500 chars
    print(result["final_report"][:500] + "...")

if __name__ == "__main__":
    main()