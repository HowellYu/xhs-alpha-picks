"""HTTP client for the open-source Xiaohongshu MCP server."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .config import Settings, get_settings
from .note_parser import XhsNote, extract_notes


class MCPError(RuntimeError):
    """Raised when the MCP server responds with an error."""


class XiaohongshuMCPClient:
    """Thin wrapper around the open-source Xiaohongshu MCP HTTP API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        base_url: Optional[str] = None,
        search_path: Optional[str] = None,
        timeout: Optional[float] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.base_url = base_url or self.settings.xhs_mcp_base_url.rstrip("/") + "/"
        self.search_path = (search_path or self.settings.xhs_mcp_search_path).lstrip("/")
        self.timeout = timeout or self.settings.xhs_mcp_timeout
        self.api_key = api_key or self.settings.xhs_mcp_api_key

    def build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _endpoint(self, path: str) -> str:
        return urljoin(self.base_url, path)

    def search_notes(
        self,
        keyword: str,
        *,
        limit: int = 10,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invoke the MCP search tool and return parsed notes alongside raw payload."""

        payload: Dict[str, Any] = {
            "keyword": keyword,
            "page": 1,
            "page_size": limit,
        }
        if raw_payload:
            payload.update(raw_payload)
        url = self._endpoint(self.search_path)
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self.build_headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_body = response.read()
        except HTTPError as exc:
            raise MCPError(f"MCP server error {exc.code}: {exc.read().decode('utf-8', 'ignore')}") from exc
        except URLError as exc:
            raise MCPError(f"Failed to reach MCP server: {exc}") from exc
        try:
            data = json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MCPError("Failed to decode MCP response as JSON") from exc
        notes = extract_notes(data)
        return {"notes": notes, "raw": data}


def iter_note_summaries(notes: Iterable[XhsNote]) -> List[str]:
    """Return formatted strings ready for prompting or console printing."""

    formatted: List[str] = []
    for index, note in enumerate(notes, 1):
        header_parts = [f"Note {index}"]
        if note.author:
            header_parts.append(f"by {note.author}")
        if note.url:
            header_parts.append(note.url)
        header = " - ".join(header_parts)
        formatted.append(
            f"{header}\nID: {note.note_id}\n{note.combined_text() or 'No text payload available.'}"
        )
    return formatted

