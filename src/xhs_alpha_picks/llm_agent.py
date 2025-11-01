from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Tuple

from openai import AsyncOpenAI

from .config import Settings
from .mcp_client import connect_via_candidates, locate_search_notes_tool, simplify_call_result


SYSTEM_PROMPT = (
    "You help investment researchers check Xiaohongshu (RED) for notes related to a keyword. "
    "Always call the provided search tool before answering. "
    "Return a concise summary of whether relevant posts exist and highlight notable findings."
)

LLM_TOOL_NAME = "search_xiaohongshu_notes"


@dataclass(slots=True)
class SearchOutcome:
    keyword: str
    summary: str
    raw_results: list[dict]
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
        sort: str = "general",
        note_type: int = 0,
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

            # Map note_type to human-readable description
            note_type_desc = {0: "all types", 1: "video only", 2: "image+text only"}.get(note_type, "all types")
            sort_desc = {"general": "general (综合)", "time_descending": "latest first (最新)", "popularity_descending": "most liked (最多点赞)"}.get(sort, "general")
            
            base_messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Find Xiaohongshu notes that mention '{keyword}'. "
                        f"Search parameters: note_type={note_type_desc}, sort={sort_desc}. "
                        f"Please limit your summary to approximately {count} most relevant notes."
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
                tool_payloads.append(simplified)

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

            usage = {
                "initial": initial_completion.usage.model_dump() if initial_completion.usage else None,
                "summary": final_completion.usage.model_dump() if final_completion.usage else None,
            }

            conversation_log = messages + [summary_message.model_dump()]

            return SearchOutcome(
                keyword=keyword,
                summary=summary_text,
                raw_results=tool_payloads,
                connected_url=connection.connected_url,
                tool_name=tool_name,
                llm_usage=usage,
                llm_messages=conversation_log,
            )
