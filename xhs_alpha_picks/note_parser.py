"""Utilities for parsing Xiaohongshu MCP payloads into structured notes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence


@dataclass
class XhsNote:
    """A simplified representation of a Xiaohongshu note."""

    note_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    image_texts: Sequence[str] = field(default_factory=list)
    url: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def combined_text(self) -> str:
        """Return a readable string mixing title, description, and OCR snippets."""

        parts: List[str] = []
        if self.title:
            parts.append(self.title.strip())
        if self.description and self.description.strip() not in parts:
            parts.append(self.description.strip())
        if self.image_texts:
            ocr_text = "\n".join(t.strip() for t in self.image_texts if t and t.strip())
            if ocr_text:
                parts.append(f"Image text:\n{ocr_text}")
        return "\n\n".join(part for part in parts if part)


def extract_notes(payload: Any) -> List[XhsNote]:
    """Extract note dictionaries from an arbitrary MCP payload."""

    note_dicts = _collect_note_dicts(payload)
    notes: List[XhsNote] = []
    for raw_note in note_dicts:
        note_id = _first_str(
            raw_note,
            (
                "note_id",
                "id",
                "noteId",
                "nid",
            ),
        )
        if not note_id:
            continue
        title = _first_str(raw_note, ("title", "note_title", "name"))
        description = _first_str(
            raw_note,
            (
                "desc",
                "description",
                "note_desc",
                "content",
                "text",
            ),
        )
        author = _first_str(
            raw_note,
            (
                "user_name",
                "user_nickname",
                "author",
                "nickname",
            ),
        )
        url = _first_str(
            raw_note,
            (
                "note_url",
                "url",
                "share_link",
                "link",
            ),
        )
        image_texts = _collect_text_fragments(raw_note)
        notes.append(
            XhsNote(
                note_id=note_id,
                title=title,
                description=description,
                author=author,
                image_texts=image_texts,
                url=url,
                raw=raw_note,
            )
        )
    return notes


def _collect_note_dicts(payload: Any) -> List[Dict[str, Any]]:
    """Recursively search for items that look like Xiaohongshu notes."""

    matches: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        candidate = _maybe_note(payload)
        if candidate:
            matches.append(candidate)
        for value in payload.values():
            matches.extend(_collect_note_dicts(value))
    elif isinstance(payload, (list, tuple, set)):
        for item in payload:
            matches.extend(_collect_note_dicts(item))
    return matches


def _maybe_note(value: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the dictionary if it resembles a note payload."""

    lowered_keys = {key.lower() for key in value}
    note_keys = {"note_id", "noteid", "id", "noteid"}
    if lowered_keys & note_keys:
        return value
    if "note_id" in value or "noteId" in value or "id" in value:
        return value
    return None


def _first_str(data: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        if key in data and isinstance(data[key], str) and data[key].strip():
            return data[key]
    return None


def _collect_text_fragments(raw_note: Dict[str, Any]) -> List[str]:
    """Collect OCR or image related text fragments."""

    fragments: List[str] = []
    candidate_keys = [
        "image_texts",
        "image_text",
        "ocr_texts",
        "ocr_text",
        "texts",
    ]
    for key in candidate_keys:
        value = raw_note.get(key)
        if isinstance(value, str) and value.strip():
            fragments.append(value)
        elif isinstance(value, Sequence):
            fragments.extend(
                str(item) for item in value if isinstance(item, str) and item.strip()
            )
    # also look for nested OCR structures
    for key, value in raw_note.items():
        if isinstance(value, dict):
            fragments.extend(_collect_text_fragments(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    fragments.extend(_collect_text_fragments(item))
    deduped: List[str] = []
    seen = set()
    for fragment in fragments:
        normalized = fragment.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped

