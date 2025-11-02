import json

from xhs_alpha_picks.config import Settings
from xhs_alpha_picks.mcp_client import XiaohongshuMCPClient


def make_settings(**overrides):
    defaults = dict(
        deepseek_api_key=None,
        deepseek_api_base="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        xhs_mcp_base_url="http://127.0.0.1:18060",
        xhs_mcp_search_path="/mcp/tools/search",
        xhs_mcp_search_url=None,
        xhs_mcp_timeout=30.0,
        xhs_mcp_api_key=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_search_url_default_path():
    client = XiaohongshuMCPClient(
        settings=make_settings(),
        base_url="http://localhost:18060",
        search_path="/mcp/tools/search",
    )
    info = client.connection_info()
    assert info["search_url"] == "http://localhost:18060/mcp/tools/search"


def test_search_url_with_path_on_base():
    client = XiaohongshuMCPClient(
        settings=make_settings(),
        base_url="http://localhost:18060/mcp",
        search_path="tools/search",
    )
    info = client.connection_info()
    assert info["search_url"] == "http://localhost:18060/mcp/tools/search"


def test_search_url_from_explicit_setting():
    client = XiaohongshuMCPClient(
        settings=make_settings(xhs_mcp_search_url="http://example.com/custom/path"),
    )
    info = client.connection_info()
    assert info["search_url"] == "http://example.com/custom/path"
    assert info["base_url"].startswith("http://example.com")


def test_headers_include_required_accept_values():
    client = XiaohongshuMCPClient(settings=make_settings())
    headers = client.build_headers()
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json, text/event-stream"


def test_search_notes_wraps_arguments_and_version(monkeypatch):
    captured = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured["data"] = request.data
        captured["headers"] = request.headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("xhs_alpha_picks.mcp_client.urlopen", fake_urlopen)

    client = XiaohongshuMCPClient(settings=make_settings())
    client.search_notes("alpha", limit=3, raw_payload={"extra": True})

    payload = json.loads(captured["data"].decode("utf-8"))
    assert payload["version"] == "2.0"
    assert payload["arguments"]["keyword"] == "alpha"
    assert payload["arguments"]["page_size"] == 3
    assert payload["arguments"]["extra"] is True


