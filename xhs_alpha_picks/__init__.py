"""Tools for querying Xiaohongshu notes via an open-source MCP server."""

from .config import Settings
from .mcp_client import XiaohongshuMCPClient
from .summarizer import DeepSeekSummarizer, build_summary_prompt
from .note_parser import XhsNote, extract_notes

__all__ = [
    "Settings",
    "XiaohongshuMCPClient",
    "DeepSeekSummarizer",
    "build_summary_prompt",
    "XhsNote",
    "extract_notes",
]
