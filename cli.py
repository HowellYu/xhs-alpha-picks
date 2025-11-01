from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
import sys

from src.xhs_alpha_picks.config import Settings
from src.xhs_alpha_picks.llm_agent import AlphaPickSearchAgent
from src.xhs_alpha_picks.mcp_client import MCPConnectionError, MCPToolNotFound


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python cli.py",
        description="Check Xiaohongshu for notes related to a keyword via DeepSeek and MCP.",
    )
    today_str = datetime.now().strftime("%Y-%m-%d")

    parser.add_argument(
        "--keyword",
        default=f"alpha pick {today_str}",
        help="Keyword to search for (default: 'alpha pick <today>').",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of notes to request from the MCP tool.",
    )
    parser.add_argument(
        "--sort",
        default="general",
        choices=["general", "time_descending", "popularity_descending"],
        help="Sort order for the search results.",
    )
    parser.add_argument(
        "--note-type",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="Note type: 0=all, 1=video, 2=image+text.",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Print structured tool output JSON for debugging.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug information including connection URLs and tool discovery.",
    )

    return parser.parse_args(argv)


async def _run_async(args: argparse.Namespace) -> int:
    try:
        settings = Settings.load()
    except RuntimeError as exc:
        if "DEEPSEEK_API_KEY" in str(exc):
            print(f"[ERROR] {exc}", file=sys.stderr)
            print("\nPlease set DEEPSEEK_API_KEY environment variable.", file=sys.stderr)
            return 1
        raise

    if args.debug:
        print(f"Configuration:", file=sys.stderr)
        print(f"  DeepSeek API Base: {settings.deepseek_base_url}", file=sys.stderr)
        print(f"  DeepSeek Model: {settings.deepseek_model}", file=sys.stderr)
        print(f"  MCP Server Candidates:", file=sys.stderr)
        for url in settings.mcp_server_candidates:
            print(f"    - {url}", file=sys.stderr)

    agent = AlphaPickSearchAgent(settings)

    try:
        outcome = await agent.search_keyword(
            args.keyword,
            count=args.count,
            sort=args.sort,
            note_type=args.note_type,
        )
    except MCPConnectionError as exc:
        print(f"[ERROR] MCP connection failed: {exc}", file=sys.stderr)
        print("\nTried connecting to:", file=sys.stderr)
        for url in settings.mcp_server_candidates:
            print(f"  - {url}", file=sys.stderr)
        print("\nPlease ensure the Xiaohongshu MCP server is running.", file=sys.stderr)
        print("You can check if it's accessible by visiting:", file=sys.stderr)
        base_url = settings.mcp_server_candidates[0] if settings.mcp_server_candidates else "http://127.0.0.1:18060"
        print(f"  {base_url}/", file=sys.stderr)
        return 2
    except MCPToolNotFound as exc:
        print(f"[ERROR] MCP tool lookup failed: {exc}", file=sys.stderr)
        print("\nThe MCP server is connected but doesn't expose the expected search tool.", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[ERROR] Unexpected error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 4

    print(f"Connected MCP server via: {outcome.connected_url}")
    print(f"Using MCP tool: {outcome.tool_name}")
    print(f"Keyword: {outcome.keyword}")
    print("\nSummary:\n---------")
    if outcome.summary:
        print(outcome.summary)
    else:
        print("(No summary returned.)")

    if args.show_raw:
        print("\nRaw MCP payload:\n----------------")
        print(json.dumps(outcome.raw_results, ensure_ascii=False, indent=2))

    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(_run_async(args))
    except RuntimeError as exc:  # noqa: BLE001
        message = str(exc)
        if "DEEPSEEK_API_KEY" in message:
            print(f"[ERROR] {message}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
