"""DeepSeek-powered summarisation utilities."""

from __future__ import annotations

from typing import Iterable, List, Optional

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore

from dataclasses import dataclass

from .config import Settings, get_settings
from .mcp_client import iter_note_summaries
from .note_parser import XhsNote


DEFAULT_SYSTEM_PROMPT = (
    "You summarise Xiaohongshu notes for a daily investment research digest. "
    "Highlight whether any note is about the day's alpha pick keyword, and "
    "include important details from the body text and OCR text."
)

DEFAULT_USER_PROMPT = (
    "Summarise the following notes. Highlight unique insights, and explicitly "
    "mention if no relevant notes were found."
)


@dataclass
class SummaryResult:
    """Wrapper for summarisation results."""

    prompt: str
    response_text: str
    used_model: str
    total_notes: int


class DeepSeekSummarizer:
    """Call the DeepSeek Responses API to generate textual summaries."""

    def __init__(self, settings: Optional[Settings] = None, *, model: Optional[str] = None) -> None:
        self.settings = settings or get_settings()
        self.model = model or self.settings.deepseek_model
        if not self.settings.deepseek_api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not configured. Export it or pass a Settings with the key."
            )
        if OpenAI is None:
            raise RuntimeError("The 'openai' package is required for DeepSeek summarisation.")
        self.client = OpenAI(api_key=self.settings.deepseek_api_key, base_url=self.settings.deepseek_api_base)

    def summarise(
        self,
        notes: Iterable[XhsNote],
        *,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> SummaryResult:
        note_list = list(notes)
        if not note_list:
            raise ValueError("No notes provided for summarisation")
        user_prompt = prompt or DEFAULT_USER_PROMPT
        sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        notes_blob = "\n\n".join(iter_note_summaries(note_list))
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": sys_prompt,
                },
                {
                    "role": "user",
                    "content": f"{user_prompt}\n\nNotes:\n{notes_blob}",
                },
            ],
            temperature=0.3,
        )
        summary_text = (completion.choices[0].message.content or "").strip()
        return SummaryResult(
            prompt=user_prompt,
            response_text=summary_text,
            used_model=self.model,
            total_notes=len(note_list),
        )


def build_summary_prompt(keyword: str, *, base_prompt: Optional[str] = None) -> str:
    template = base_prompt or DEFAULT_USER_PROMPT
    return template.replace("{keyword}", keyword)

