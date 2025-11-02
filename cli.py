from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
import sys

from src.xhs_alpha_picks.config import Settings
from src.xhs_alpha_picks.llm_agent import AlphaPickSearchAgent
from src.xhs_alpha_picks.mcp_client import MCPConnectionError, MCPToolNotFound
from src.xhs_alpha_picks.daily_logger import save_daily_summary


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
        default=2,
        choices=[0, 1, 2],
        help="Note type: 0=all, 1=video, 2=image+text (default: 2 for OCR).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=2,
        help="Filter notes to last N days (default: 2).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=1,
        help="Maximum number of high-quality results to keep (default: 1).",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Filter results to today's date only and generate summary for today.",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="alpha_picks_logs",
        help="Directory to save daily log files (default: 'alpha_picks_logs').",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Skip saving to daily log file.",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Print structured tool output JSON for debugging.",
    )
    parser.add_argument(
        "--show-json",
        action="store_true",
        help="Print processed notes as JSON.",
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

    # Determine scan mode
    filter_today = args.today
    filter_latest_date = not args.today  # If not today, use latest date mode
    
    if filter_today:
        print("📅 SCAN MODE: TODAY - Filtering results to today's date only", file=sys.stderr)
    else:
        print("📅 SCAN MODE: LATEST DATE - Finding latest post(s) by date", file=sys.stderr)

    try:
        outcome = await agent.search_keyword(
            args.keyword,
            count=args.count,
            sort=args.sort,
            note_type=args.note_type,
            days_filter=args.days,
            max_results=args.max_results,
            filter_today=filter_today,
            filter_latest_date=filter_latest_date,
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
    if outcome.target_date:
        date_str = outcome.target_date.strftime("%Y-%m-%d")
        print(f"Target date: {date_str} ({outcome.scan_mode} mode)")
    print(f"Keeping top {args.max_results} high-quality result(s)")
    
    # Display processed notes
    if outcome.processed_notes:
        high_quality_count = sum(1 for n in outcome.processed_notes if n.is_high_quality)
        if high_quality_count > 0:
            print(f"\nFound {high_quality_count} high-quality note(s) (out of {len(outcome.processed_notes)} total):\n")
        else:
            print(f"\nFound {len(outcome.processed_notes)} note(s), but none meet high-quality criteria:\n")
        for i, note in enumerate(outcome.processed_notes, 1):
            print(f"Note {i}:")
            print(f"  Title: {note.title or 'N/A'}")
            print(f"  Author: {note.author or 'N/A'}")
            print(f"  Selection Date: {note.selection_date or 'N/A'}")
            print(f"  Publish Time: {note.publish_time or 'N/A'}")
            print(f"  Quality Score: {note.quality_score:.2f}")
            print(f"  Quality Notes: {', '.join(note.quality_notes)}")
            print(f"  URL: {note.url or 'N/A'}")
            print(f"  Post Text: {(note.post_text or '')[:200]}...")
            print(f"  OCR Text: {(note.ocr_text or '')[:200]}...")
            print()
    else:
        print("\nNo high-quality notes found matching criteria.")
        print("Summary from LLM:\n---------")
        if outcome.summary:
            print(outcome.summary)
        else:
            print("(No summary returned.)")

    # Show JSON output if requested
    if args.show_json:
        print("\nProcessed Notes (JSON):\n----------------")
        notes_data = [note.to_dict() for note in outcome.processed_notes]
        print(json.dumps(notes_data, ensure_ascii=False, indent=2))

    # Save to daily log file (using raw dump for faster, reliable encoding)
    if not args.no_log and outcome.processed_notes:
        print("\nSaving notes to daily log file...")
        try:
            log_path = await save_daily_summary(
                outcome.processed_notes,
                settings,
                log_dir=args.log_dir,
                date=outcome.target_date,
                mode=outcome.scan_mode,
                use_raw_dump=True,  # Use raw dump instead of LLM summary
            )
            print(f"\nSaved daily log to: {log_path}")
            print(f"Log includes: post text, OCR text, selection dates, and quality scores.")
        except Exception as exc:
            print(f"\n[WARNING] Failed to save daily log: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    elif outcome.processed_notes:
        print("\n(Skipping log save as --no-log was specified)")
    elif not outcome.processed_notes:
        print("\n(No notes to log)")

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
