from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import AsyncIterator, Dict, Iterable, List, Tuple

from mcp.client.session_group import (
    ClientSessionGroup,
    SseServerParameters,
    StreamableHttpParameters,
)
import mcp.types as types

logger = logging.getLogger(__name__)


class MCPConnectionError(RuntimeError):
    """Raised when we fail to establish an MCP session."""


class MCPToolNotFound(RuntimeError):
    """Raised when the expected MCP tool cannot be located."""


_LOG_FALLBACK_MESSAGE = (
    "Failed connecting to MCP server candidate '%s' using %s parameters: %s"
)


@dataclass(slots=True)
class MCPConnection:
    """Holds the active session and associated metadata."""

    group: ClientSessionGroup
    session: types.ClientSession
    connected_url: str


def _server_params_for(url: str):
    """Determine which MCP transport parameters to use based on URL."""
    url_clean = url.rstrip("/")
    # Based on MCP Inspector, the xiaohongshu-mcp server uses Streamable HTTP transport
    # Try StreamableHttpParameters for /mcp endpoints and stream endpoints
    if url_clean.endswith("/mcp") or "/mcp/" in url_clean:
        # Try Streamable HTTP first (as shown in MCP Inspector)
        return StreamableHttpParameters(url=url)
    if url_clean.endswith("/stream") or "/stream" in url_clean:
        return StreamableHttpParameters(url=url)
    # Default to SSE for other endpoints
    return SseServerParameters(url=url)


@asynccontextmanager
async def connect_via_candidates(
    urls: Iterable[str],
) -> AsyncIterator[MCPConnection]:
    """Try connecting to the MCP server using known URL candidates."""

    errors: list[tuple[str, Exception]] = []

    async with ClientSessionGroup() as group:
        session = None
        connected_url = None

        for candidate in urls:
            # Try primary transport method first
            params = _server_params_for(candidate)
            try:
                session = await group.connect_to_server(params)
                connected_url = candidate
                logger.info("Connected to MCP server via %s using %s", candidate, type(params).__name__)
                break
            except Exception as first_exc:  # noqa: BLE001
                # If StreamableHttpParameters failed, try SSE as fallback
                if isinstance(params, StreamableHttpParameters):
                    logger.debug("Streamable HTTP failed for %s, trying SSE: %s", candidate, first_exc)
                    try:
                        sse_params = SseServerParameters(url=candidate)
                        session = await group.connect_to_server(sse_params)
                        connected_url = candidate
                        logger.info("Connected to MCP server via %s using SSE (fallback)", candidate)
                        break
                    except Exception as sse_exc:  # noqa: BLE001
                        # Both transport methods failed for this candidate
                        errors.append((candidate, first_exc))
                        logger.debug(_LOG_FALLBACK_MESSAGE, candidate, type(first_exc).__name__, first_exc)
                else:
                    # Already tried SSE, just record the error
                    errors.append((candidate, first_exc))
                    logger.debug(_LOG_FALLBACK_MESSAGE, candidate, type(first_exc).__name__, first_exc)

        if session is None or connected_url is None:
            detail = {
                "attempted_urls": [url for url, _ in errors],
                "error_chain": [f"{url}: {error}" for url, error in errors],
            }
            raise MCPConnectionError(
                f"Unable to connect to MCP server; attempts failed for {detail['attempted_urls']}"
            )

        try:
            yield MCPConnection(group=group, session=session, connected_url=connected_url)
        finally:
            # Context manager closes connections automatically.
            logger.debug("MCP connection to %s closed", connected_url)


def locate_search_notes_tool(
    tools: Dict[str, types.Tool],
) -> Tuple[str, types.Tool]:
    """Find the Xiaohongshu note search MCP tool."""

    keywords = ("search", "note")
    
    # List of possible tool name patterns
    tool_patterns = [
        "search",  # Simple "search" in name
        "笔记",    # Chinese for "notes"
        "xiaohongshu",  # Service name
        "xhs",     # Service abbreviation
    ]

    for tool_name, tool in tools.items():
        name_lower = tool_name.lower()
        description_lower = (tool.description or "").lower()

        # Check if name contains both keywords
        if all(keyword in name_lower for keyword in keywords):
            return tool_name, tool

        # Check for Chinese keywords
        if "搜索" in description_lower and "笔记" in description_lower:
            return tool_name, tool
        
        # Check if name contains any of the patterns
        if any(pattern in name_lower for pattern in tool_patterns):
            # Additional check: if description suggests it's a search tool
            if any(word in description_lower for word in ["search", "查找", "搜索", "query", "查询"]):
                return tool_name, tool

    # If no match found, raise error with available tools
    available_tools = list(tools.keys())
    raise MCPToolNotFound(
        f"Could not find an MCP tool that looks like the Xiaohongshu note search endpoint. "
        f"Available tools: {available_tools}"
    )


def simplify_call_result(result: types.CallToolResult) -> dict:
    """Convert an MCP CallToolResult into a plain dict for downstream use."""

    payload: dict = {
        "is_error": result.isError,
    }

    if result.structuredContent is not None:
        payload["structured_content"] = result.structuredContent

    text_chunks: list[str] = []
    other_content: list[dict] = []

    for item in result.content:
        match item:
            case types.TextContent(text=text):
                text_chunks.append(text)
            case _:
                other_content.append(item.model_dump())

    if text_chunks:
        payload["text"] = text_chunks
    if other_content:
        payload["content"] = other_content

    return payload

