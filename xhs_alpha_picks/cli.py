"""Command-line interface for Xiaohongshu alpha pick research."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from .config import get_settings
from .mcp_client import MCPError, XiaohongshuMCPClient, iter_note_summaries
from .summarizer import DEFAULT_SYSTEM_PROMPT, DeepSeekSummarizer, build_summary_prompt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keyword",
        "-k",
        help="Keyword to search. Defaults to 'alpha pick {today}'.",
    )
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=5,
        help="Number of notes to request (default: 5).",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        help="Custom prompt template. Use {keyword} as a placeholder.",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="Read the prompt template from a file.",
    )
    parser.add_argument(
        "--system-prompt",
        help="Override the DeepSeek system prompt.",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Print the raw MCP payload as JSON.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip DeepSeek summarisation (useful for quick tests).",
    )
    parser.add_argument(
        "--save-json",
        type=Path,
        help="Write the raw MCP payload to a file.",
    )
    parser.add_argument(
        "--check-connection",
        action="store_true",
        help="Verify the MCP server is reachable and exit.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print MCP connection details before running.",
    )
    parser.add_argument(
        "--mcp-api-key",
        help="Override the MCP API key (falls back to XHS_MCP_API_KEY).",
    )
    return parser


def _print_note_dump(notes: Iterable[str], stream) -> None:
    for entry in notes:
        stream.write("\n" + entry + "\n")
        stream.write("-" * 40 + "\n")


def main(argv: Optional[list[str]] = None, *, stream=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    stream = stream or sys.stdout

    settings = get_settings()
    keyword = args.keyword or f"alpha pick {date.today():%Y-%m-%d}"
    prompt_template: Optional[str] = None
    if args.prompt_file:
        prompt_template = args.prompt_file.read_text(encoding="utf-8")
    elif args.prompt:
        prompt_template = args.prompt
    prompt_text = build_summary_prompt(
        keyword,
        base_prompt=prompt_template or "Summarise how '{keyword}' is discussed in these notes.",
    )

    client = XiaohongshuMCPClient(settings=settings, api_key=args.mcp_api_key)
    if args.debug:
        info = getattr(client, "connection_info", lambda: {
            "base_url": getattr(client, "base_url", "<unknown>"),
            "search_path": getattr(client, "search_path", "<unknown>"),
            "search_url": getattr(client, "search_url", "<unknown>"),
            "timeout": getattr(client, "timeout", "<unknown>"),
            "has_mcp_api_key": bool(getattr(client, "api_key", None)),
        })()
        stream.write("MCP connection configuration:\n")
        stream.write(f"  Base URL: {info.get('base_url', '<unknown>')}\n")
        stream.write(f"  Search path: {info.get('search_path', '<unknown>')}\n")
        stream.write(f"  Search URL: {info.get('search_url', '<unknown>')}\n")
        stream.write(f"  Timeout: {info.get('timeout', '<unknown>')}s\n")
        stream.write(
            "  MCP API key: {}\n".format(
                "configured" if info.get("has_mcp_api_key") else "not set"
            )
        )
        stream.write(
            "  DeepSeek API key: {}\n".format(
                "configured" if settings.deepseek_api_key else "not set"
            )
        )

    if args.check_connection:
        try:
            client.ping()
        except MCPError as exc:
            stream.write(f"Connection check failed: {exc}\n")
            return 2
        stream.write(f"MCP server at {client.base_url} is reachable.\n")
        return 0

    try:
        client.ping()
    except MCPError as exc:
        stream.write(
            "Error: MCP server is unreachable. "
            "Run with --check-connection for more details.\n"
        )
        stream.write(f"Details: {exc}\n")
        if not args.debug:
            stream.write(
                "Re-run with --debug to print the derived MCP connection settings.\n"
            )
        return 2

    try:
        result = client.search_notes(keyword, limit=max(args.count, 1))
    except MCPError as exc:
        stream.write(f"Error: {exc}\n")
        if not args.debug:
            stream.write(
                "Re-run with --debug to print the derived MCP connection settings.\n"
            )
        return 2

    notes = result["notes"]
    if args.show_raw:
        stream.write(json.dumps(result["raw"], indent=2, ensure_ascii=False) + "\n")
    if args.save_json:
        args.save_json.write_text(json.dumps(result["raw"], indent=2, ensure_ascii=False), encoding="utf-8")
        stream.write(f"Raw payload saved to {args.save_json}\n")

    if not notes:
        stream.write(f"No notes found for keyword: {keyword}\n")
        return 0

    stream.write(f"Retrieved {len(notes)} notes for keyword '{keyword}'.\n")
    _print_note_dump(iter_note_summaries(notes), stream)

    if args.offline:
        stream.write("Offline mode enabled; skipping DeepSeek summarisation.\n")
        return 0

    try:
        summariser = DeepSeekSummarizer(settings=settings)
    except RuntimeError as exc:
        stream.write(f"Skipping DeepSeek summarisation: {exc}\n")
        return 0

    summary = summariser.summarise(
        notes,
        prompt=prompt_text,
        system_prompt=args.system_prompt or DEFAULT_SYSTEM_PROMPT,
    )
    stream.write("\nDeepSeek summary\n=================\n")
    stream.write(summary.response_text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

