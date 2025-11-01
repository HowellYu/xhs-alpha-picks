from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from .config import Settings
from .mcp_client import connect_via_candidates, locate_search_notes_tool, simplify_call_result
from .note_processor import process_notes, ProcessedNote


SYSTEM_PROMPT = (
    "You are an expert investment researcher analyzing Xiaohongshu (RED) posts about Seeking Alpha's Alpha Picks service. "
    "Your goal is to find high-quality posts that contain Alpha Picks stock selections from Seeking Alpha. "
    "High-quality posts should: "
    "1. Reference Seeking Alpha or Alpha Picks service "
    "2. Contain multiple stock selections (not just 1-2 picks) "
    "3. Include selection dates "
    "4. Have both text content and images with OCR text extracted. "
    "Always call the provided search tool to retrieve notes. "
    "Focus on finding the most recent and highest quality posts that represent official Alpha Picks selections."
)

LLM_TOOL_NAME = "search_xiaohongshu_notes"


@dataclass(slots=True)
class SearchOutcome:
    keyword: str
    summary: str
    raw_results: list[dict]
    processed_notes: list[ProcessedNote]
    target_date: datetime | None  # Target date for logging (today or latest)
    scan_mode: str  # "today" or "latest"
    connected_url: str
    tool_name: str
    llm_usage: dict | None
    llm_messages: list[dict]


class AlphaPickSearchAgent:
    """Coordinates DeepSeek and the MCP tool to fetch Xiaohongshu notes."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    async def search_keyword(
        self,
        keyword: str,
        *,
        count: int = 10,
        sort: str = "time_descending",  # Default to most recent
        note_type: int = 2,  # Default to image+text only (for OCR)
        days_filter: int = 2,  # Filter to last N days
        max_results: int = 1,  # Keep top N high-quality results
        filter_today: bool = False,  # Filter to today only
        filter_latest_date: bool = False,  # Filter to latest date found
    ) -> SearchOutcome:
        """Ask DeepSeek to look for Xiaohongshu notes about the supplied keyword."""

        async with connect_via_candidates(self._settings.mcp_server_candidates) as connection:
            # Access tools from the session group
            # Note: tools should be available after connecting to the MCP server
            tools = connection.group.tools
            tool_name, tool = locate_search_notes_tool(tools)

            tool_spec = {
                "type": "function",
                "function": {
                    "name": LLM_TOOL_NAME,
                    "description": tool.description or "Search for Xiaohongshu notes by keyword.",
                    "parameters": tool.inputSchema,
                },
            }

            # Always use time_descending for most recent notes
            sort = "time_descending"
            
            # Map note_type to human-readable description
            note_type_desc = {0: "all types", 1: "video only", 2: "image+text only"}.get(note_type, "all types")
            sort_desc = "latest first (最新) - sorted by most recent"
            
            base_messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Search for the MOST RECENT Xiaohongshu notes about '{keyword}'. "
                        f"Find posts that contain Alpha Picks stock selections with multiple picks (not just 1-2). "
                        f"IMPORTANT: Use ONLY these filter parameters: note_type and sort_by. "
                        f"Do NOT use publish_time filter - date filtering will be done after retrieval. "
                        f"Search parameters: note_type={note_type_desc}, sort_by={sort_desc}. "
                        f"Return as many recent notes as possible (up to {count} or more if available). "
                        f"The tool will return raw note data with images - we will extract OCR text and filter by date separately."
                    ),
                },
            ]

            initial_completion = await self._client.chat.completions.create(
                model=self._settings.deepseek_model,
                temperature=0,
                messages=base_messages,
                tools=[tool_spec],
                tool_choice="auto",
            )

            choice = initial_completion.choices[0]
            assistant_message = choice.message
            messages = base_messages + [assistant_message.model_dump()]

            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                raise RuntimeError("DeepSeek did not attempt to call the Xiaohongshu search tool.")

            tool_payloads: list[dict] = []

            for call in tool_calls:
                arguments = {}
                if call.type == "function":
                    if call.function.arguments:
                        arguments = json.loads(call.function.arguments)

                # Ensure keyword is set
                arguments["keyword"] = keyword
                
                # Build filters object according to the actual tool schema
                # The tool accepts: filters.note_type, filters.sort_by, etc.
                filters = arguments.get("filters", {})
                
                # Map note_type (0=all, 1=video, 2=image+text) to tool's expected values
                if note_type == 1:
                    filters["note_type"] = "视频"
                elif note_type == 2:
                    filters["note_type"] = "图文"
                else:
                    filters["note_type"] = "不限"
                
                # Map sort parameter to tool's sort_by values
                sort_map = {
                    "general": "综合",
                    "time_descending": "最新",
                    "popularity_descending": "最多点赞",
                }
                filters["sort_by"] = sort_map.get(sort, "综合")
                
                # Only set filters if we have any filter values
                if filters:
                    arguments["filters"] = filters
                
                # Note: The tool doesn't support a "count" parameter directly
                # The DeepSeek LLM might need to be instructed to limit results in its summary

                result = await connection.group.call_tool(tool_name, arguments)
                simplified = simplify_call_result(result)
                
                # Check for errors in tool response
                if simplified.get("is_error"):
                    error_text = "\n".join(simplified.get("text", []))
                    # Log error but continue to try extracting any partial results
                    logger.warning(f"MCP tool returned error: {error_text}")
                    # Still add to payloads in case there's partial data
                
                tool_payloads.append(simplified)
                
                # After search, fetch full details for each note to get OCR and dates
                # Extract note IDs and xsec_tokens from the search result
                temp_notes = []  # List of (note_id, xsec_token) tuples
                if "text" in simplified:
                    for text_chunk in simplified["text"]:
                        if isinstance(text_chunk, str):
                            try:
                                data = json.loads(text_chunk)
                                if isinstance(data, dict) and "feeds" in data:
                                    for feed in data["feeds"]:
                                        note_id = feed.get("id") or feed.get("note_id")
                                        xsec_token = feed.get("xsecToken") or feed.get("xsec_token")
                                        if note_id and xsec_token:
                                            temp_notes.append((note_id, xsec_token))
                            except (json.JSONDecodeError, TypeError):
                                pass
                
                # Fetch full details for each note
                if temp_notes and "get_feed_detail" in tools:
                    detail_tool_name = "get_feed_detail"
                    for note_id, xsec_token in temp_notes[:count]:  # Limit to requested count
                        try:
                            detail_result = await connection.group.call_tool(
                                detail_tool_name,
                                {"feed_id": note_id, "xsec_token": xsec_token}
                            )
                            detail_simplified = simplify_call_result(detail_result)
                            # Add detail to payloads for processing
                            tool_payloads.append(detail_simplified)
                        except Exception:
                            # Skip if detail fetch fails
                            pass

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name if call.type == "function" else call.type,
                        "content": json.dumps(simplified, ensure_ascii=False),
                    }
                )

            final_completion = await self._client.chat.completions.create(
                model=self._settings.deepseek_model,
                temperature=0,
                messages=messages,
            )

            summary_message = final_completion.choices[0].message
            summary_text = (summary_message.content or "").strip()

            # Extract raw notes from tool payloads
            raw_notes: List[Dict[str, Any]] = []
            for payload in tool_payloads:
                # The payload structure from simplify_call_result contains:
                # - text: list of text chunks (often JSON strings)
                # - structured_content: structured data
                # - content: other content
                
                # Try to extract notes from structured content first
                if "structured_content" in payload and payload["structured_content"]:
                    structured = payload["structured_content"]
                    # Recursively find note-like dictionaries
                    raw_notes.extend(self._extract_notes_from_payload(structured))
                
                # Parse JSON from text chunks (the tool returns JSON strings)
                if "text" in payload:
                    for text_chunk in payload["text"]:
                        if isinstance(text_chunk, str):
                            try:
                                # Try parsing as JSON
                                data = json.loads(text_chunk)
                                # Handle the "feeds" structure returned by search
                                if isinstance(data, dict) and "feeds" in data:
                                    for feed in data["feeds"]:
                                        # Convert feed structure to note structure
                                        note = self._convert_feed_to_note(feed)
                                        if note:
                                            raw_notes.append(note)
                                # Handle detailed note structure from get_feed_detail
                                elif isinstance(data, dict) and ("note_detail" in data or "note_id" in data or "id" in data):
                                    # This is a detailed note from get_feed_detail
                                    note = self._convert_detail_to_note(data)
                                    if note:
                                        # Merge with existing note if we have a basic version
                                        existing_idx = None
                                        for idx, existing_note in enumerate(raw_notes):
                                            if existing_note.get("note_id") == note.get("note_id"):
                                                existing_idx = idx
                                                break
                                        if existing_idx is not None:
                                            # Merge details into existing note
                                            raw_notes[existing_idx].update(note)
                                        else:
                                            raw_notes.append(note)
                                else:
                                    raw_notes.extend(self._extract_notes_from_payload(data))
                            except (json.JSONDecodeError, TypeError):
                                pass

            # Process notes: filter by date, extract OCR, quality check
            processed_notes, target_date = process_notes(
                raw_notes,
                days_filter=days_filter,
                max_results=max_results,
                filter_today=filter_today,
                filter_latest_date=filter_latest_date,
            )

            usage = {
                "initial": initial_completion.usage.model_dump() if initial_completion.usage else None,
                "summary": final_completion.usage.model_dump() if final_completion.usage else None,
            }

            conversation_log = messages + [summary_message.model_dump()]

            # Determine scan mode
            scan_mode = "today" if filter_today else ("latest" if filter_latest_date else "range")
            
            return SearchOutcome(
                keyword=keyword,
                summary=summary_text,
                raw_results=tool_payloads,
                processed_notes=processed_notes,
                target_date=target_date,
                scan_mode=scan_mode,
                connected_url=connection.connected_url,
                tool_name=tool_name,
                llm_usage=usage,
                llm_messages=conversation_log,
            )

    def _extract_notes_from_payload(self, data: Any) -> List[Dict[str, Any]]:
        """Recursively extract note dictionaries from payload."""
        notes: List[Dict[str, Any]] = []
        
        if isinstance(data, dict):
            # Check if this dict looks like a note
            if "note_id" in data or "id" in data or "noteId" in data:
                notes.append(data)
            # Handle feeds structure
            elif "feeds" in data:
                for feed in data.get("feeds", []):
                    note = self._convert_feed_to_note(feed)
                    if note:
                        notes.append(note)
            else:
                # Recursively search nested structures
                for value in data.values():
                    notes.extend(self._extract_notes_from_payload(value))
        elif isinstance(data, list):
            for item in data:
                notes.extend(self._extract_notes_from_payload(item))
        
        return notes

    def _convert_feed_to_note(self, feed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert a feed item from the MCP tool to a note dictionary."""
        if not isinstance(feed, dict):
            return None
        
        note: Dict[str, Any] = {}
        note["note_id"] = feed.get("id") or feed.get("note_id") or feed.get("noteId", "")
        
        if not note["note_id"]:
            return None
        
        # Extract from noteCard structure
        note_card = feed.get("noteCard", {})
        note["title"] = note_card.get("displayTitle") or note_card.get("title")
        note["type"] = note_card.get("type", "normal")
        
        # Extract user info
        user = note_card.get("user", {})
        note["user_nickname"] = user.get("nickname") or user.get("nickName")
        note["user_id"] = user.get("userId")
        
        # Extract interaction info
        interact_info = note_card.get("interactInfo", {})
        note["liked_count"] = interact_info.get("likedCount", "0")
        note["comment_count"] = interact_info.get("commentCount", "0")
        note["shared_count"] = interact_info.get("sharedCount", "0")
        
        # Extract cover/image info
        cover = note_card.get("cover", {})
        note["cover_url"] = cover.get("urlDefault") or cover.get("url")
        
        # Extract other fields
        note["model_type"] = feed.get("modelType")
        note["xsec_token"] = feed.get("xsecToken")
        
        # Try to extract time/date
        time_info = feed.get("time") or note_card.get("time") or feed.get("timestamp")
        if time_info:
            note["time"] = time_info
        
        # Copy all raw data
        note["raw"] = feed
        
        return note

    def _convert_detail_to_note(self, detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert a detailed note from get_feed_detail to a note dictionary."""
        if not isinstance(detail, dict):
            return None
        
        note: Dict[str, Any] = {}
        
        # Extract note_id from various possible locations
        note["note_id"] = (
            detail.get("note_id") or 
            detail.get("id") or 
            detail.get("noteId") or
            (detail.get("note_detail", {}) or {}).get("note_id") or
            (detail.get("note_detail", {}) or {}).get("id") or
            ""
        )
        
        if not note["note_id"]:
            return None
        
        # Get note_detail if nested
        note_detail = detail.get("note_detail", detail)
        if not isinstance(note_detail, dict):
            note_detail = detail
        
        # Extract title and description
        note["title"] = (
            note_detail.get("title") or 
            note_detail.get("display_title") or
            note_detail.get("displayTitle") or
            note_detail.get("note_title")
        )
        note["description"] = (
            note_detail.get("desc") or
            note_detail.get("description") or
            note_detail.get("note_desc") or
            note_detail.get("content")
        )
        
        # Extract user info
        user = note_detail.get("user", {})
        note["user_nickname"] = user.get("nickname") or user.get("nickName")
        note["user_id"] = user.get("userId") or user.get("user_id")
        
        # Extract time/date
        time_info = (
            note_detail.get("time") or 
            note_detail.get("timestamp") or
            note_detail.get("create_time") or
            note_detail.get("publish_time") or
            note_detail.get("created_at")
        )
        if time_info:
            note["time"] = time_info
        
        # Extract images and OCR text
        images = note_detail.get("images", [])
        image_texts = []
        for img in images:
            if isinstance(img, dict):
                # Extract OCR text from image
                ocr_text = (
                    img.get("ocr_text") or
                    img.get("image_text") or
                    img.get("text") or
                    img.get("infoList", [])
                )
                if isinstance(ocr_text, str) and ocr_text.strip():
                    image_texts.append(ocr_text.strip())
                elif isinstance(ocr_text, list):
                    for item in ocr_text:
                        if isinstance(item, dict):
                            text = item.get("text") or item.get("ocr_text")
                            if text and isinstance(text, str):
                                image_texts.append(text.strip())
                        elif isinstance(item, str):
                            image_texts.append(item.strip())
        
        if image_texts:
            note["image_texts"] = image_texts
            note["ocr_text"] = "\n\n".join(image_texts)
        
        # Extract URL
        note["url"] = (
            note_detail.get("url") or
            note_detail.get("note_url") or
            note_detail.get("share_link") or
            note_detail.get("link")
        )
        
        # Extract interaction info
        interact_info = note_detail.get("interact_info", note_detail.get("interactInfo", {}))
        note["liked_count"] = interact_info.get("liked_count") or interact_info.get("likedCount", "0")
        note["comment_count"] = interact_info.get("comment_count") or interact_info.get("commentCount", "0")
        note["shared_count"] = interact_info.get("shared_count") or interact_info.get("sharedCount", "0")
        
        # Copy all raw data
        note["raw"] = detail
        
        return note
