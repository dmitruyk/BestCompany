"""Custom tools for agents - browser fetch, web search."""
import json
from typing import Optional

import requests
from strands import tool


@tool
def fetch_url_summary(url: str, max_chars: int = 2000) -> str:
    """
    Fetch and summarize the content of a given URL.
    Use for market research, competitor analysis, or trend validation.

    Args:
        url: The full URL to fetch (e.g. https://example.com/article).
        max_chars: Maximum characters to return (default 2000).

    Returns:
        Text summary of the page content, or an error message if fetch failed.
    """
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        text = resp.text
        # Simple truncation - in production consider proper HTML parsing
        if len(text) > max_chars:
            text = text[:max_chars] + "... [truncated]"
        return f"Content from {url}:\n{text}"
    except requests.RequestException as e:
        return f"Error fetching {url}: {str(e)}"


def get_web_search_tool():  # type: ignore[no-untyped-def]
    """
    Return a web search tool if ddgs or duckduckgo_search is installed.
    Prefers ddgs (duckduckgo-search was renamed).
    """
    def _make_web_search(ddgs_class):
        @tool
        def web_search(query: str, max_results: int = 5) -> str:
            """
            Search the web for information.
            Use for market research, competitor discovery, and trend validation.

            Args:
                query: Search query string.
                max_results: Maximum number of results (default 5).

            Returns:
                JSON string of search results (title, link, snippet).
            """
            results = []
            try:
                for r in ddgs_class().text(query, max_results=max_results):
                    results.append(
                        {
                            "title": r.get("title", ""),
                            "link": r.get("href", ""),
                            "snippet": r.get("body", ""),
                        }
                    )
                return json.dumps(results, indent=2)
            except Exception as e:
                return json.dumps({"error": str(e), "results": []})

        return web_search

    for pkg in ("ddgs", "duckduckgo_search"):
        try:
            mod = __import__(pkg)
            ddgs_class = getattr(mod, "DDGS", None)
            if ddgs_class:
                return _make_web_search(ddgs_class)
        except ImportError:
            continue
    return None


def run_web_searches(queries: list[str], max_results_per_query: int = 5) -> str:
    """
    Run web searches server-side (used when model tool-calling is unavailable, e.g. Ollama).
    Returns combined JSON string of all results.
    """
    all_results: list[dict[str, str]] = []
    for pkg in ("ddgs", "duckduckgo_search"):
        try:
            mod = __import__(pkg)
            ddgs_class = getattr(mod, "DDGS", None)
            if not ddgs_class:
                continue
            for query in queries:
                try:
                    for r in ddgs_class().text(query, max_results=max_results_per_query):
                        all_results.append(
                            {
                                "query": query,
                                "title": r.get("title", ""),
                                "link": r.get("href", ""),
                                "snippet": r.get("body", ""),
                            }
                        )
                except Exception as e:
                    all_results.append(
                        {"query": query, "error": str(e), "title": "", "link": "", "snippet": ""}
                    )
            return json.dumps(all_results, indent=2)
        except ImportError:
            continue
    return json.dumps({"error": "No web search backend (ddgs/duckduckgo_search) available", "results": []})
