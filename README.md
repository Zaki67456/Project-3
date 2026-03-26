# Agentic Quote Browser

An AI-powered agent that browses [quotes.toscrape.com](https://quotes.toscrape.com) using Claude (via OpenRouter) and Playwright. The agent navigates the site, searches for quotes, and returns results with their source URLs.

## Requirements

- Python 3.9+
- An [OpenRouter](https://openrouter.ai) API key

## Installation

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Configuration

Set your OpenRouter API key before running:

**PowerShell:**
```powershell
$env:OPENROUTER_API_KEY="sk-or-..."
```

**CMD:**
```cmd
set OPENROUTER_API_KEY=sk-or-...
```

## Usage

```bash
python agent.py "Find all quotes about love"
python agent.py "What did Albert Einstein say?"
python agent.py "List the top tags on this site"
python agent.py           # interactive prompt
```

## How it works

The agent uses Claude 3.5 Haiku (via OpenRouter) with 4 browser tools:

| Tool | Description |
|------|-------------|
| `navigate` | Go to a URL |
| `get_page_content` | Read quotes on the current page |
| `get_links` | List all links on the current page |
| `click_link` | Click a link by its visible text |

For every quote found, the agent returns the **source URL** so results are verifiable.
