from __future__ import annotations

import os
import re
import html
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

from onecode.agent.tools.protocol import ToolResult
from onecode.agent.tools.registry import Tool, ToolSpec

AGENT_SEARCH_BASE_URL = os.environ.get(
    "AGENT_SEARCH_BASE_URL",
    "http://localhost:3939",
)


@dataclass
class WebResult:
    url: str
    title: str
    snippet: str
    content: Optional[str] = None


class WebFetcher:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout, follow_redirects=True)
        return self._client

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self._async_client

    def fetch(self, url: str, prompt: Optional[str] = None) -> str:
        try:
            resp = self._get_client().get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                text = self._extract_text_from_html(resp.text)
            else:
                text = resp.text[:5000]

            if prompt:
                return f"URL: {url}\nContent (relevant to '{prompt}'):\n{text[:3000]}"
            return f"URL: {url}\nContent:\n{text[:3000]}"

        except httpx.TimeoutException:
            return f"Error: Timeout fetching {url}"
        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} for {url}"
        except Exception as e:
            return f"Error: {str(e)} for {url}"

    async def fetch_async(
        self, url: str, prompt: Optional[str] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        if cancel_check and cancel_check():
            return f"Error: Cancelled fetching {url}"
        try:
            resp = await self._get_async_client().get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                text = self._extract_text_from_html(resp.text)
            else:
                text = resp.text[:5000]

            if prompt:
                return f"URL: {url}\nContent (relevant to '{prompt}'):\n{text[:3000]}"
            return f"URL: {url}\nContent:\n{text[:3000]}"

        except httpx.TimeoutException:
            return f"Error: Timeout fetching {url}"
        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} for {url}"
        except Exception as e:
            return f"Error: {str(e)} for {url}"

    def _extract_text_from_html(self, html_content: str) -> str:
        text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]


class WebSearch:
    def __init__(self, timeout: int = 30, agent_search_url: str = AGENT_SEARCH_BASE_URL):
        self.timeout = timeout
        self._fetcher = WebFetcher(timeout)
        self._agent_search_url = agent_search_url

    def search(self, query: str, num_results: int = 5) -> str:
        try:
            return self._search_agent_search(query, num_results)
        except Exception:
            pass

        search_urls = [
            f"https://duckduckgo.com/html/?q={self._quote(query)}",
            f"https://html.duckduckgo.com/html/?q={self._quote(query)}",
        ]

        for url in search_urls:
            try:
                results = self._search_duckduckgo(url, num_results, query)
                if results:
                    return results
            except Exception:
                continue

        return self._search_fallback(query, num_results)

    async def search_async(
        self, query: str, num_results: int = 5,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        if cancel_check and cancel_check():
            return f"Search cancelled for '{query}'"
        try:
            return await self._search_agent_search_async(query, num_results, cancel_check)
        except Exception:
            pass

        search_urls = [
            f"https://duckduckgo.com/html/?q={self._quote(query)}",
            f"https://html.duckduckgo.com/html/?q={self._quote(query)}",
        ]

        for url in search_urls:
            if cancel_check and cancel_check():
                return f"Search cancelled for '{query}'"
            try:
                results = await self._search_duckduckgo_async(url, num_results, query, cancel_check)
                if results:
                    return results
            except Exception:
                continue

        return self._search_fallback(query, num_results)

    def _search_agent_search(self, query: str, num_results: int) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{self._agent_search_url}/search",
                params={"q": query, "count": num_results},
            )
            resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return f"No results found for '{query}'"

        output = [f"Search results for '{query}':\n"]
        for i, r in enumerate(results):
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = (r.get("snippet") or r.get("content") or "")[:200]
            output.append(f"{i+1}. {title}\n   URL: {url}\n   {snippet}")
        return "\n\n".join(output)

    async def _search_agent_search_async(
        self, query: str, num_results: int,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        if cancel_check and cancel_check():
            return f"Search cancelled for '{query}'"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self._agent_search_url}/search",
                params={"q": query, "count": num_results},
            )
            resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return f"No results found for '{query}'"

        output = [f"Search results for '{query}':\n"]
        for i, r in enumerate(results):
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = (r.get("snippet") or r.get("content") or "")[:200]
            output.append(f"{i+1}. {title}\n   URL: {url}\n   {snippet}")
        return "\n\n".join(output)

    def _search_duckduckgo(self, url: str, num_results: int, query: str) -> str:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()

        html_content = resp.text
        results = []

        snippets = re.findall(r'<a class="result__a" href="([^"]+)">([^<]+)</a>', html_content)

        for i, (url, title) in enumerate(snippets[:num_results]):
            snippet_match = re.search(rf'<a class="result__a" href="{re.escape(url)}"[^>]*>[^<]+</a>.*?(?:<p class="result__snippet">([^<]+)</p>|(?:<a class="result__snippet"[^>]*>([^<]+)</a>))?', html_content, re.DOTALL)
            snippet = ""
            if snippet_match:
                snippet = snippet_match.group(1) or snippet_match.group(2) or ""

            title = re.sub(r'<[^>]+>', '', title)
            snippet = re.sub(r'<[^>]+>', '', snippet)
            results.append(f"{i+1}. {title}\n   URL: {url}\n   {snippet[:200]}")

        if results:
            return f"Search results for '{query}':\n\n" + "\n\n".join(results)

        return f"No results found for '{query}'"

    async def _search_duckduckgo_async(
        self, url: str, num_results: int, query: str,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        if cancel_check and cancel_check():
            return ""
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        html_content = resp.text
        results = []

        snippets = re.findall(r'<a class="result__a" href="([^"]+)">([^<]+)</a>', html_content)

        for i, (url, title) in enumerate(snippets[:num_results]):
            snippet_match = re.search(rf'<a class="result__a" href="{re.escape(url)}"[^>]*>[^<]+</a>.*?(?:<p class="result__snippet">([^<]+)</p>|(?:<a class="result__snippet"[^>]*>([^<]+)</a>))?', html_content, re.DOTALL)
            snippet = ""
            if snippet_match:
                snippet = snippet_match.group(1) or snippet_match.group(2) or ""

            title = re.sub(r'<[^>]+>', '', title)
            snippet = re.sub(r'<[^>]+>', '', snippet)
            results.append(f"{i+1}. {title}\n   URL: {url}\n   {snippet[:200]}")

        if results:
            return f"Search results for '{query}':\n\n" + "\n\n".join(results)

        return f"No results found for '{query}'"

    def _search_fallback(self, query: str, num_results: int) -> str:
        """Fallback search using a different method."""
        return f"Web search for '{query}' returned no results. Try using WebFetch to directly access a URL."

    def _quote(self, query: str) -> str:
        import urllib.parse
        return urllib.parse.quote_plus(query)


def webfetch(url: str, prompt: Optional[str] = None) -> str:
    fetcher = WebFetcher()
    return fetcher.fetch(url, prompt)


async def webfetch_async(
    url: str, prompt: Optional[str] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    fetcher = WebFetcher()
    return await fetcher.fetch_async(url, prompt, cancel_check=cancel_check)


def websearch(query: str, num_results: int = 5) -> str:
    searcher = WebSearch()
    return searcher.search(query, num_results)


async def websearch_async(
    query: str, num_results: int = 5,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    searcher = WebSearch()
    return await searcher.search_async(query, num_results, cancel_check=cancel_check)


class WebFetchTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="WebFetch",
            description="Fetch a URL and extract information.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "prompt": {"type": "string", "description": "What to extract from the page"},
                },
                "required": ["url"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        url = tool_input.get("url", "")
        prompt = tool_input.get("prompt")
        content = webfetch(url, prompt)
        is_error = str(content).startswith("Error:")
        return ToolResult(name="WebFetch", output=str(content), is_error=is_error)

    async def run_async(
        self, tool_input: dict[str, Any],
        cancel_check: Callable[[], bool] | None = None,
    ) -> ToolResult:
        url = tool_input.get("url", "")
        prompt = tool_input.get("prompt")
        content = await webfetch_async(url, prompt, cancel_check=cancel_check)
        is_error = str(content).startswith("Error:")
        return ToolResult(name="WebFetch", output=str(content), is_error=is_error)


class WebSearchTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="WebSearch",
            description="Search the web and return results.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "description": "Number of results", "default": 5},
                },
                "required": ["query"],
            },
            is_read_only=True,
        )

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        query = tool_input.get("query", "")
        num_results = tool_input.get("num_results", 5)
        content = websearch(query, num_results)
        is_error = "Error" in str(content) and str(content).startswith("Error")
        return ToolResult(name="WebSearch", output=str(content), is_error=is_error)

    async def run_async(
        self, tool_input: dict[str, Any],
        cancel_check: Callable[[], bool] | None = None,
    ) -> ToolResult:
        query = tool_input.get("query", "")
        num_results = tool_input.get("num_results", 5)
        content = await websearch_async(query, num_results, cancel_check=cancel_check)
        is_error = "Error" in str(content) and str(content).startswith("Error")
        return ToolResult(name="WebSearch", output=str(content), is_error=is_error)
