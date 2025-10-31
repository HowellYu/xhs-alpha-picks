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


