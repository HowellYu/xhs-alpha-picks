"""HTTP client for the open-source Xiaohongshu MCP server."""

from __future__ import annotations

import json
import socket
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
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
        raw_base_url = base_url if base_url is not None else self.settings.xhs_mcp_base_url
        raw_search_path = (
            search_path if search_path is not None else self.settings.xhs_mcp_search_path
        )
        self.timeout = timeout or self.settings.xhs_mcp_timeout
        self.api_key = api_key or self.settings.xhs_mcp_api_key
        explicit_search_url = (
            self.settings.xhs_mcp_search_url if base_url is None and search_path is None else None
        )

        if explicit_search_url:
            self.search_url = explicit_search_url
            parsed = urlsplit(self.search_url)
            self.base_url = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
            self.search_path = parsed.path or "/"
        else:
            self.base_url = (raw_base_url or "").rstrip("/")
            self.search_path = raw_search_path or ""
            path = self.search_path.lstrip("/") if self.search_path else ""
            self.search_url = urljoin(self.base_url.rstrip("/") + "/", path)

    def build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _endpoint(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    def connection_info(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "search_path": self.search_path,
            "search_url": getattr(self, "search_url", self._endpoint(self.search_path)),
            "timeout": self.timeout,
            "has_api_key": bool(self.api_key),
        }

    def ping(self) -> None:
        """Best-effort connectivity probe for the MCP server host."""

        from urllib.parse import urlsplit

        parsed = urlsplit(self.base_url or self.search_url)
        host = parsed.hostname
        if not host:
            raise MCPError(f"Unable to parse MCP base URL: {self.base_url!r}")
        port = parsed.port
        if not port:
            port = 443 if parsed.scheme == "https" else 80
        try:
            with socket.create_connection((host, port), timeout=self.timeout):
                return
        except OSError as exc:
            raise MCPError(
                f"Unable to reach MCP server at {self.base_url} (host {host}:{port}): {exc}"
            ) from exc

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
        url = self._endpoint(getattr(self, "search_url", self.search_path))
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
            error_body = exc.read().decode("utf-8", "ignore")
            raise MCPError(
                f"MCP server error {exc.code} calling {url}: {error_body}"
            ) from exc
        except URLError as exc:
            raise MCPError(f"Failed to reach MCP server at {url}: {exc}") from exc
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

