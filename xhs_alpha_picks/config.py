"""Lightweight environment-driven configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


@dataclass
class Settings:
    deepseek_api_key: Optional[str]
    deepseek_api_base: str
    deepseek_model: str
    xhs_mcp_base_url: str
    xhs_mcp_search_path: str
    xhs_mcp_search_url: Optional[str]
    xhs_mcp_timeout: float
    xhs_mcp_api_key: Optional[str]

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            deepseek_api_key=env.get("DEEPSEEK_API_KEY"),
            deepseek_api_base=env.get("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
            deepseek_model=env.get("DEEPSEEK_MODEL", "deepseek-chat"),
            xhs_mcp_base_url=env.get("XHS_MCP_BASE_URL", "http://127.0.0.1:18060"),
            xhs_mcp_search_path=env.get("XHS_MCP_SEARCH_PATH", "/mcp/tools/search"),
            xhs_mcp_search_url=env.get("XHS_MCP_SEARCH_URL"),
            xhs_mcp_timeout=float(env.get("XHS_MCP_TIMEOUT", "30.0")),
            xhs_mcp_api_key=env.get("XHS_MCP_API_KEY"),
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings.from_env()

