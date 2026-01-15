from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown

console = Console()

def print_header(company: str):
    console.print(Panel(
        Text(f"DEEP RESEARCH: {company}", justify="center", style="bold white on blue"),
        style="blue"
    ))

def print_step(step_name: str, status: str = "running"):
    """Visualizes the current graph node."""
    colors = {"running": "yellow", "complete": "green", "error": "red"}
    icon = {"running": "⏳", "complete": "✅", "error": "❌"}
    
    console.print(f"[{colors[status]}] {icon[status]} [bold]{step_name}[/bold]...")

def print_artifact(title: str, content: str, style="cyan"):
    # Truncate to 500 chars so panels fit nicely on screen
    preview = content[:500] + "\n... [truncated for display] ..." if len(content) > 500 else content
    
    console.print(Panel(
        preview,
        title=f"[bold]{title}[/bold]",
        title_align="left",
        border_style=style
    ))

def print_conflict_alert(conflict_detected: bool):
    if conflict_detected:
        console.print(Panel(
            "⚠️  CONFLICT DETECTED: Financials and Market Sentiment disagree!",
            style="bold red"
        ))
    else:
        console.print("[dim]No major data conflicts detected.[/dim]")