"""Process and filter Xiaohongshu notes based on quality, date, and requirements."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import re


@dataclass
class ProcessedNote:
    """A processed note with extracted text, quality check, and metadata."""

    note_id: str
    title: Optional[str] = None
    post_text: Optional[str] = None
    ocr_text: Optional[str] = None
    author: Optional[str] = None
    url: Optional[str] = None
    selection_date: Optional[str] = None
    publish_time: Optional[str] = None
    is_high_quality: bool = False
    quality_score: float = 0.0
    quality_notes: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/CSV export."""
        result = {
            "note_id": self.note_id,
            "title": self.title or "",
            "post_text": self.post_text or "",
            "ocr_text": self.ocr_text or "",
            "author": self.author or "",
            "url": self.url or "",
            "selection_date": self.selection_date or "",
            "publish_time": self.publish_time or "",
            "is_high_quality": self.is_high_quality,
            "quality_score": self.quality_score,
            "quality_notes": "; ".join(self.quality_notes),
        }
        return result


def extract_date_from_note(note: Dict[str, Any]) -> Optional[datetime]:
    """Extract publish/update date from note dictionary."""
    date_keys = [
        "time",
        "timestamp",
        "publish_time",
        "create_time",
        "update_time",
        "date",
        "publish_date",
        "created_at",
        "updated_at",
    ]

    for key in date_keys:
        value = note.get(key)
        if not value:
            continue

        # Try parsing as timestamp (seconds or milliseconds)
        if isinstance(value, (int, float)):
            try:
                # Handle both seconds and milliseconds
                if value > 1e12:  # Likely milliseconds
                    return datetime.fromtimestamp(value / 1000)
                else:  # Likely seconds
                    return datetime.fromtimestamp(value)
            except (ValueError, OSError):
                continue

        # Try parsing as ISO string
        if isinstance(value, str):
            try:
                # Try common ISO formats
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                    try:
                        return datetime.strptime(value[:19], fmt)
                    except ValueError:
                        continue
            except Exception:
                continue

    return None


def extract_ocr_text(note: Dict[str, Any]) -> str:
    """Extract all OCR text from images in the note."""
    ocr_texts: List[str] = []
    seen = set()

    def _collect_ocr(data: Any, path: str = "") -> None:
        if isinstance(data, dict):
            for key, value in data.items():
                key_lower = key.lower()
                if any(ocr_key in key_lower for ocr_key in ["ocr", "image_text", "img_text"]):
                    if isinstance(value, str) and value.strip():
                        normalized = value.strip()
                        if normalized not in seen:
                            seen.add(normalized)
                            ocr_texts.append(normalized)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str) and item.strip():
                                normalized = item.strip()
                                if normalized not in seen:
                                    seen.add(normalized)
                                    ocr_texts.append(normalized)
                            elif isinstance(item, dict):
                                _collect_ocr(item, f"{path}.{key}")
                else:
                    _collect_ocr(value, f"{path}.{key}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                _collect_ocr(item, f"{path}[{i}]")

    _collect_ocr(note)
    return "\n\n".join(ocr_texts)


def extract_post_text(note: Dict[str, Any]) -> str:
    """Extract the main post text content."""
    text_keys = ["desc", "description", "content", "text", "note_desc", "title"]
    texts: List[str] = []

    # Get title
    for key in ["title", "note_title", "name"]:
        value = note.get(key)
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
            break

    # Get description/content
    for key in text_keys:
        value = note.get(key)
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
            break

    return "\n".join(texts)


def check_alpha_picks_quality(note: ProcessedNote) -> tuple[bool, float, List[str]]:
    """
    Check if a note represents high-quality Alpha Picks content.
    
    Quality criteria:
    - Should mention multiple stock selections (not just 1-2)
    - Should reference Seeking Alpha or Alpha Picks service
    - Should have selection dates
    - Should have substantial content (text + OCR)
    """
    quality_notes: List[str] = []
    score = 0.0

    combined_text = (note.post_text or "").lower() + " " + (note.ocr_text or "").lower()

    # Check for Seeking Alpha / Alpha Picks reference
    has_seeking_alpha = any(
        term in combined_text
        for term in ["seeking alpha", "alpha picks", "alpha pick", "seekingalpha"]
    )
    if has_seeking_alpha:
        score += 0.3
        quality_notes.append("References Seeking Alpha/Alpha Picks")
    else:
        quality_notes.append("Missing Seeking Alpha reference")

    # Check for multiple selections (count numbers that might be stock picks)
    # Look for patterns like "1.", "2.", numbers in lists, or multiple stock symbols
    selection_patterns = [
        r"\d+[\.\)]\s*[A-Z]{2,5}",  # "1. AAPL", "2) TSLA"
        r"[A-Z]{2,5}[\s,]+[A-Z]{2,5}",  # "AAPL TSLA", "AAPL, TSLA"
        r"第[一二三四五六七八九十\d]+[只个股个]",  # Chinese: "第一只", "第3个"
        r"(\d+)[个只支项]",  # Chinese: "3个", "5只"
    ]

    selection_count = 0
    for pattern in selection_patterns:
        matches = re.findall(pattern, combined_text)
        if matches:
            # Try to extract numbers
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match.isdigit():
                    selection_count = max(selection_count, int(match))
                else:
                    # Count distinct stock-like symbols
                    symbols = re.findall(r"[A-Z]{2,5}", match)
                    selection_count = max(selection_count, len(symbols))

    if selection_count >= 3:
        score += 0.4
        quality_notes.append(f"Contains {selection_count}+ selections")
    elif selection_count >= 1:
        score += 0.2
        quality_notes.append(f"Contains {selection_count} selection(s) - low quality")
    else:
        quality_notes.append("No clear multiple selections found")

    # Check for selection date
    date_patterns = [
        r"\d{4}[-/]\d{2}[-/]\d{2}",  # YYYY-MM-DD
        r"\d{2}[-/]\d{2}[-/]\d{4}",  # MM-DD-YYYY
        r"(\d{4})\.(\d{2})\.(\d{2})",  # YYYY.MM.DD
        r"(\d{1,2})[月/](\d{1,2})[日]",  # Chinese: "1月1日"
    ]

    has_date = any(re.search(pattern, combined_text) for pattern in date_patterns)
    if has_date or note.selection_date:
        score += 0.2
        quality_notes.append("Contains selection date")
    else:
        quality_notes.append("Missing selection date")

    # Check content completeness
    has_substantial_content = (
        len(note.post_text or "") > 50 and len(note.ocr_text or "") > 50
    ) or len(combined_text) > 200
    if has_substantial_content:
        score += 0.1
        quality_notes.append("Has substantial content")
    else:
        quality_notes.append("Content may be incomplete")

    # High quality threshold: at least 0.7 score and multiple selections
    is_high_quality = score >= 0.7 and selection_count >= 3

    return is_high_quality, score, quality_notes


def process_notes(
    raw_notes: List[Dict[str, Any]],
    days_filter: int = 2,
    max_results: int = 1,
    filter_today: bool = False,
    filter_latest_date: bool = False,
) -> tuple[List[ProcessedNote], datetime | None]:
    """
    Process and filter notes based on date, quality, and requirements.
    
    Args:
        raw_notes: List of raw note dictionaries from MCP
        days_filter: Only keep notes from last N days (default: 2)
        max_results: Maximum number of high-quality results to return (default: 1)
        filter_today: If True, only keep notes from today
        filter_latest_date: If True, find the latest date in notes and filter to that date
    
    Returns:
        Tuple of (processed notes, target date for logging)
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    if filter_today:
        cutoff_date = today
        target_date = today
    elif filter_latest_date:
        # First pass: extract all dates to find the latest
        all_dates: List[datetime] = []
        for raw_note in raw_notes:
            note_date = extract_date_from_note(raw_note)
            if note_date:
                # Also check selection date from text
                title = raw_note.get("title") or ""
                desc = raw_note.get("desc") or ""
                post_text = str(title) + " " + str(desc)
                date_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", post_text)
                if date_match:
                    try:
                        date_str = date_match.group(1).replace("/", "-")
                        parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                        all_dates.append(parsed_date.replace(hour=0, minute=0, second=0, microsecond=0))
                    except ValueError:
                        pass
                all_dates.append(note_date.replace(hour=0, minute=0, second=0, microsecond=0))
        
        if all_dates:
            target_date = max(all_dates)
            cutoff_date = target_date
        else:
            # Fallback to today if no dates found
            target_date = today
            cutoff_date = today - timedelta(days=days_filter)
    else:
        cutoff_date = today - timedelta(days=days_filter)
        target_date = None
    
    processed: List[ProcessedNote] = []

    for raw_note in raw_notes:
        note_id = raw_note.get("note_id") or raw_note.get("id") or raw_note.get("noteId", "")
        if not note_id:
            continue

        # Extract date
        note_date = extract_date_from_note(raw_note)
        
        # Also check selection date from text (this might be more accurate)
        # Ensure we always have strings (handle None values)
        title = raw_note.get("title") or ""
        desc = raw_note.get("desc") or ""
        post_text = str(title) + " " + str(desc)
        date_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", post_text)
        selection_date_from_text: datetime | None = None
        if date_match:
            try:
                date_str = date_match.group(1).replace("/", "-")
                selection_date_from_text = datetime.strptime(date_str, "%Y-%m-%d")
                selection_date_from_text = selection_date_from_text.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                pass
        
        # Use selection date from text if available, otherwise use note_date
        effective_date = selection_date_from_text or note_date
        
        # Filter by date
        if effective_date:
            effective_date_normalized = effective_date.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_date_normalized = cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0) if cutoff_date else None
            
            if filter_today or filter_latest_date:
                # For today/latest mode, only keep notes matching exactly
                if effective_date_normalized != cutoff_date_normalized:
                    continue
            else:
                # For days_filter mode, keep notes from cutoff_date onwards
                if effective_date_normalized < cutoff_date_normalized:
                    continue
        elif filter_today or filter_latest_date:
            # If we require exact date match but no date found, skip
            continue

        # Extract texts
        post_text = extract_post_text(raw_note)
        ocr_text = extract_ocr_text(raw_note)

        # Extract selection date from text (look for dates in title/description)
        combined = (post_text + " " + ocr_text).lower()
        date_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", combined)
        selection_date = date_match.group(1) if date_match else None

        # Get publish time string
        publish_time = note_date.strftime("%Y-%m-%d %H:%M:%S") if note_date else None

        # Create processed note
        processed_note = ProcessedNote(
            note_id=str(note_id),
            title=raw_note.get("title") or raw_note.get("note_title") or raw_note.get("name"),
            post_text=post_text,
            ocr_text=ocr_text,
            author=raw_note.get("user_nickname") or raw_note.get("user_name") or raw_note.get("author"),
            url=raw_note.get("note_url") or raw_note.get("url") or raw_note.get("share_link"),
            selection_date=selection_date,
            publish_time=publish_time,
            raw=raw_note,
        )

        # Quality check
        is_high_quality, score, quality_notes = check_alpha_picks_quality(processed_note)
        processed_note.is_high_quality = is_high_quality
        processed_note.quality_score = score
        processed_note.quality_notes = quality_notes

        processed.append(processed_note)

    # Sort by quality score (descending) and then by date (descending)
    processed.sort(
        key=lambda n: (
            n.is_high_quality,
            n.quality_score,
            n.publish_time or "",
        ),
        reverse=True,
    )

    # Return top N results, prioritizing high quality but including others if needed
    # This ensures we always have something to summarize even if quality is lower
    high_quality = [n for n in processed if n.is_high_quality]
    if high_quality:
        # If we have high quality notes, return them (up to max_results)
        return high_quality[:max_results], target_date
    else:
        # If no high quality, return top N by score anyway (for logging/summary purposes)
        return processed[:max_results] if processed else [], target_date

