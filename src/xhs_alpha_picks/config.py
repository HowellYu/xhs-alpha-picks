from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import List


DEFAULT_MCP_BASE_URL = "http://127.0.0.1:18060"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def _dedupe_preserve_order(urls: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url not in seen:
            ordered.append(url)
            seen.add(url)
    return ordered


@dataclass(slots=True)
class Settings:
    """Runtime configuration pulled from environment variables."""

    deepseek_api_key: str
    deepseek_base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    deepseek_model: str = DEFAULT_DEEPSEEK_MODEL
    mcp_server_candidates: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("Missing DEEPSEEK_API_KEY environment variable.")

        base_url = os.getenv("XHS_MCP_BASE_URL", DEFAULT_MCP_BASE_URL).rstrip("/")
        deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
        deepseek_model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)

        # Try different MCP endpoint formats:
        # The xiaohongshu-mcp server exposes the MCP endpoint at /mcp
        # Try both localhost and 127.0.0.1 variants, and different path formats
        # Based on MCP Inspector, the working URL is http://localhost:18060/mcp
        base_url_127 = base_url  # Keep original
        base_url_localhost = base_url.replace("127.0.0.1", "localhost") if "127.0.0.1" in base_url else base_url.replace("localhost", "127.0.0.1")
        
        candidates = [
            f"{base_url}/mcp",  # Primary: /mcp path (as shown in MCP Inspector)
            f"{base_url_localhost}/mcp",  # Try localhost variant if base was 127.0.0.1
            f"{base_url}/mcp/stream",  # Stream endpoint
            f"{base_url}/stream",  # Alternative stream endpoint
            f"{base_url}/sse",  # SSE endpoint
            base_url,  # Base URL as fallback
        ]

        return cls(
            deepseek_api_key=key,
            deepseek_base_url=deepseek_base_url,
            deepseek_model=deepseek_model,
            mcp_server_candidates=_dedupe_preserve_order(candidates),
        )

