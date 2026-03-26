"""
Agentic Quote Browser
=====================
Browses https://quotes.toscrape.com/ using OpenRouter + Playwright.
OpenRouter is OpenAI-compatible, so we use the openai SDK.

Final Project Extension: the agent always returns the source URL for every
quote it finds, so results are verifiable and shareable.

Setup:
    set OPENROUTER_API_KEY=sk-or-...   (Windows CMD)
    $env:OPENROUTER_API_KEY="sk-or-..." (PowerShell)

Usage:
    python agent.py "Find all quotes about love"
    python agent.py "What did Albert Einstein say?"
    python agent.py           # interactive prompt
"""

import asyncio
import json
import os
import sys
from openai import OpenAI
from playwright.async_api import async_playwright, Page

# ── OpenRouter client ─────────────────────────────────────────────────────────

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

MODEL = "anthropic/claude-3.5-haiku"   # cheap + fast; change freely

page: Page = None  # shared browser page, injected before the agentic loop

# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": (
                "Navigate the browser to a URL. "
                "Always start at https://quotes.toscrape.com/ and follow internal links."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to visit"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_content",
            "description": (
                "Return the current URL and all quotes (text, author, tags) on the page. "
                "Call this after every navigation."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_links",
            "description": (
                "Return up to 60 links (text + href) on the current page. "
                "Useful for discovering tag pages, author pages, and pagination."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_link",
            "description": (
                "Click a link by its visible text. "
                "Examples: 'Next', 'Albert Einstein', 'love'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Visible text of the link to click",
                    }
                },
                "required": ["text"],
            },
        },
    },
]

# ── Tool implementations (Playwright) ─────────────────────────────────────────

async def navigate(url: str) -> str:
    await page.goto(url, wait_until="networkidle")
    return f"Navigated to: {page.url}"


async def get_page_content() -> str:
    url = page.url
    quote_elements = await page.query_selector_all(".quote")

    if not quote_elements:
        body = await page.inner_text("body")
        return f"Current URL: {url}\n\n(No quotes found)\n\n{body[:1500]}"

    lines = [f"Current URL: {url}", f"Found {len(quote_elements)} quotes:\n"]
    for i, el in enumerate(quote_elements, 1):
        text_el = await el.query_selector(".text")
        auth_el = await el.query_selector(".author")
        tag_els = await el.query_selector_all(".tag")

        text   = (await text_el.inner_text()).strip() if text_el else ""
        author = (await auth_el.inner_text()).strip() if auth_el else ""
        tags   = [await t.inner_text() for t in tag_els]

        lines.append(f"{i}. {text}")
        lines.append(f"   — {author}  |  tags: {', '.join(tags)}")
        lines.append(f"   source URL: {url}\n")

    return "\n".join(lines)


async def get_links() -> str:
    anchors = await page.query_selector_all("a")
    items = []
    for a in anchors:
        text = (await a.inner_text()).strip()
        href = await a.get_attribute("href") or ""
        if text and href:
            items.append(f"  [{text}] → {href}")
    return "Links on this page:\n" + "\n".join(items[:60])


async def click_link(text: str) -> str:
    loc = page.get_by_role("link", name=text, exact=True)
    if await loc.count():
        await loc.first.click()
        await page.wait_for_load_state("networkidle")
        return f"Clicked '{text}' → now at {page.url}"

    loc = page.get_by_role("link", name=text, exact=False)
    if await loc.count():
        await loc.first.click()
        await page.wait_for_load_state("networkidle")
        return f"Clicked link containing '{text}' → now at {page.url}"

    slug = text.lower().replace(" ", "-")
    loc = page.locator(f'a[href*="{slug}"]')
    if await loc.count():
        await loc.first.click()
        await page.wait_for_load_state("networkidle")
        return f"Clicked href containing '{slug}' → now at {page.url}"

    return f"Link not found: '{text}'"


async def execute_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "navigate":         lambda: navigate(inputs["url"]),
        "get_page_content": lambda: get_page_content(),
        "get_links":        lambda: get_links(),
        "click_link":       lambda: click_link(inputs["text"]),
    }
    fn = dispatch.get(name)
    return await fn() if fn else f"Unknown tool: {name}"


# ── Agentic loop ──────────────────────────────────────────────────────────────

SYSTEM = """You are an agentic web browser specialising in quotes.toscrape.com.

Rules:
1. Always start by navigating to https://quotes.toscrape.com/
2. After every navigation call get_page_content to read the page.
3. When you report quotes to the user you MUST include the source URL
   (shown as "source URL:" in get_page_content results) so they can
   visit the exact page.
4. Explore pagination (click 'Next'), tag pages, and author pages as
   needed to fully answer the query.
5. Stop when you have collected enough information to answer the query.
"""


async def run_agent(query: str, headless: bool = False):
    global page

    print(f"\n{'═'*60}")
    print(f" Query: {query}")
    print(f"{'═'*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        page = await browser.new_page()

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": query},
        ]

        while True:
            response = client.chat.completions.create(
                model=MODEL,
                tools=TOOLS,
                messages=messages,
            )

            msg = response.choices[0].message
            messages.append(msg)  # append the full message object (openai accepts this)

            finish = response.choices[0].finish_reason

            # ── Final answer ──────────────────────────────────────────────
            if finish == "stop" or not msg.tool_calls:
                print("─" * 60)
                print(msg.content or "(no text)")
                print("─" * 60)
                break

            # ── Tool calls ────────────────────────────────────────────────
            for tc in msg.tool_calls:
                name   = tc.function.name
                inputs = json.loads(tc.function.arguments)
                preview = json.dumps(inputs, ensure_ascii=False)[:80]
                print(f"  ▶ {name}({preview})")

                result = await execute_tool(name, inputs)
                print(f"    {result.splitlines()[0][:100]}\n")

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })

        await browser.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY environment variable is not set.")
        print("  PowerShell: $env:OPENROUTER_API_KEY='sk-or-...'")
        print("  CMD:        set OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        print("Agentic Quote Browser  —  quotes.toscrape.com")
        print(f"Model: {MODEL}")
        print("─" * 50)
        print("Example queries:")
        print("  • Find 5 quotes about love with their URLs")
        print("  • What did Albert Einstein say?")
        print("  • List the top tags on this site")
        print("  • Find inspirational quotes from page 3")
        print()
        query = input("Enter your query: ").strip()
        if not query:
            query = "Find 3 quotes about life and show me the URL of each page"

    asyncio.run(run_agent(query))


if __name__ == "__main__":
    main()
