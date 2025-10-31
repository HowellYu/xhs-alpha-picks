import json
from pathlib import Path
from typing import Dict

from xhs_alpha_picks.cli import main
from xhs_alpha_picks.mcp_client import MCPError
from xhs_alpha_picks.note_parser import extract_notes


def build_fake_payload(keyword: str) -> Dict[str, object]:
    return {
        "data": {
            "notes": [
                {
                    "note_id": "n1",
                    "title": f"{keyword} overview",
                    "desc": "Key takeaways from today",
                    "user_nickname": "Researcher",
                    "image_text": "Important OCR detail",
                    "note_url": "https://www.xiaohongshu.com/explore/n1",
                }
            ]
        }
    }
def test_cli_offline_mode(tmp_path: Path, monkeypatch):
    keyword = "alpha pick 2099-01-01"
    payload = build_fake_payload(keyword)

    output_path = tmp_path / "payload.json"

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def ping(self):
            return None

        def search_notes(self, keyword: str, limit: int, raw_payload: Dict[str, object] | None = None):
            assert keyword == "alpha pick 2099-01-01"
            return {"notes": extract_notes(payload), "raw": payload}

    monkeypatch.setattr("xhs_alpha_picks.cli.XiaohongshuMCPClient", DummyClient)

    from io import StringIO

    buffer = StringIO()
    exit_code = main(
        [
            "--keyword",
            keyword,
            "--offline",
            "--count",
            "1",
            "--save-json",
            str(output_path),
        ],
        stream=buffer,
    )

    assert exit_code == 0
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == payload
    text = buffer.getvalue()
    assert "Retrieved 1 notes" in text
    assert keyword in text


def test_cli_check_connection_success(monkeypatch):
    class DummyClient:
        base_url = "http://example.com"
        search_path = "/mcp/tools/search"
        search_url = "http://example.com/mcp/tools/search"
        timeout = 30

        def __init__(self, *args, **kwargs):
            pass

        def ping(self):
            return None

    monkeypatch.setattr("xhs_alpha_picks.cli.XiaohongshuMCPClient", DummyClient)

    from io import StringIO

    buffer = StringIO()
    exit_code = main(["--check-connection"], stream=buffer)

    assert exit_code == 0
    assert "is reachable" in buffer.getvalue()


def test_cli_check_connection_failure(monkeypatch):
    class DummyClient:
        base_url = "http://example.com"
        search_path = "/mcp/tools/search"
        search_url = "http://example.com/mcp/tools/search"
        timeout = 30

        def __init__(self, *args, **kwargs):
            pass

        def ping(self):
            raise MCPError("boom")

    monkeypatch.setattr("xhs_alpha_picks.cli.XiaohongshuMCPClient", DummyClient)

    from io import StringIO

    buffer = StringIO()
    exit_code = main(["--check-connection"], stream=buffer)

    assert exit_code == 2
    assert "boom" in buffer.getvalue()


def test_cli_ping_failure(monkeypatch):
    class DummyClient:
        base_url = "http://example.com"
        search_path = "/mcp/tools/search"
        search_url = "http://example.com/mcp/tools/search"
        timeout = 30

        def __init__(self, *args, **kwargs):
            pass

        def ping(self):
            raise MCPError("connection refused")

    monkeypatch.setattr("xhs_alpha_picks.cli.XiaohongshuMCPClient", DummyClient)

    from io import StringIO

    buffer = StringIO()
    exit_code = main(["--keyword", "alpha pick 2099-01-01"], stream=buffer)

    assert exit_code == 2
    text = buffer.getvalue()
    assert "unreachable" in text
    assert "connection refused" in text


def test_cli_debug_prints_connection(monkeypatch):
    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def connection_info(self):
            return {
                "base_url": "http://localhost:18060",
                "search_path": "/mcp/tools/search",
                "search_url": "http://localhost:18060/mcp/tools/search",
                "timeout": 30.0,
                "has_mcp_api_key": False,
            }

        def ping(self):
            return None

        def search_notes(self, keyword: str, limit: int, raw_payload=None):
            return {"notes": [], "raw": {}}

    monkeypatch.setattr("xhs_alpha_picks.cli.XiaohongshuMCPClient", DummyClient)

    from io import StringIO

    buffer = StringIO()
    exit_code = main(["--debug"], stream=buffer)

    assert exit_code == 0
    text = buffer.getvalue()
    assert "MCP connection configuration" in text
    assert "Base URL: http://localhost:18060" in text
    assert "Search URL: http://localhost:18060/mcp/tools/search" in text
    assert "No notes found" in text
