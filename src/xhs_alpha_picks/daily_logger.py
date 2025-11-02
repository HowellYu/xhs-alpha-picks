"""Daily logging system for Alpha Picks summaries."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from openai import AsyncOpenAI

from .config import Settings
from .note_processor import ProcessedNote


SUMMARY_PROMPT = """Analyze the following Xiaohongshu posts about Seeking Alpha's Alpha Picks service. 
Extract and summarize the key information in a structured format:

1. **Date of Alpha Picks Selection**: Extract the selection date mentioned in the posts (YYYY-MM-DD format)

2. **Added Companies**: List all companies/stock symbols that were ADDED to Alpha Picks. For each company include:
   - Stock symbol/ticker (e.g., AAPL, TSLA, MSFT)
   - Company name if mentioned
   - Recommendation (Buy/Hold/Sell) if specified
   - Brief reasoning or analysis if provided

3. **Removed Companies**: List all companies/stock symbols that were REMOVED from Alpha Picks. For each include:
   - Stock symbol/ticker
   - Company name if mentioned
   - Reason for removal if mentioned

4. **Recommendations Summary**: For each company mentioned (whether added, removed, or updated), include:
   - Stock symbol/ticker
   - Recommendation (Buy/Hold/Sell/Strong Buy/etc.)
   - Price target if mentioned
   - Brief reasoning or analysis

5. **Key Analysis Points**: Extract any important analysis, insights, commentary, or trends about:
   - Overall market outlook
   - Sector trends
   - Individual stock analysis
   - Risk factors
   - Investment themes

Format your response clearly with sections for each category. Make sure to extract information from BOTH the post text AND the OCR text extracted from images, as important details (like stock symbols and recommendations) are often in the images.

If multiple posts are provided, consolidate the information across all posts. If dates differ, organize by date with clear headings."""


async def generate_daily_summary(
    notes: List[ProcessedNote],
    settings: Settings,
    target_date: datetime | None = None,
) -> str:
    """Generate a comprehensive summary of processed notes using DeepSeek."""
    
    if not notes:
        return "No notes provided for summarization."
    
    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    
    # Combine all note content
    notes_content = []
    for i, note in enumerate(notes, 1):
        note_text = f"--- Note {i} ---\n"
        note_text += f"Title: {note.title or 'N/A'}\n"
        note_text += f"Author: {note.author or 'N/A'}\n"
        note_text += f"Selection Date: {note.selection_date or 'N/A'}\n"
        note_text += f"Publish Time: {note.publish_time or 'N/A'}\n"
        note_text += f"URL: {note.url or 'N/A'}\n\n"
        note_text += f"Post Text:\n{note.post_text or 'N/A'}\n\n"
        note_text += f"OCR Text (from images):\n{note.ocr_text or 'N/A'}\n\n"
        note_text += f"Quality Score: {note.quality_score:.2f}\n"
        note_text += f"Quality Notes: {', '.join(note.quality_notes)}\n"
        note_text += "=" * 80 + "\n\n"
        notes_content.append(note_text)
    
    combined_content = "\n".join(notes_content)
    
    # Add date context to prompt
    date_context = ""
    if target_date:
        date_str = target_date.strftime("%Y-%m-%d")
        date_context = f"\n\nIMPORTANT: These posts are from {date_str}. Please mark this date prominently in your summary if it's not already clear from the post content."
    
    # Generate summary using DeepSeek
    completion = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {
                "role": "system",
                "content": "You are an expert financial analyst specializing in summarizing Alpha Picks selections from Seeking Alpha. Extract structured information about stock picks, recommendations, and analysis. Always clearly mark the post date at the beginning of your summary.",
            },
            {
                "role": "user",
                "content": f"{SUMMARY_PROMPT}{date_context}\n\n--- Post Content ---\n\n{combined_content}",
            },
        ],
        temperature=0.3,
    )
    
    summary = completion.choices[0].message.content or "Failed to generate summary."
    return summary


def get_daily_log_path(
    base_dir: str = "alpha_picks_logs",
    date: datetime | None = None,
    mode: str = "today",
) -> Path:
    """
    Get the file path for a daily log file.
    
    Args:
        base_dir: Base directory for logs
        date: Target date for the log
        mode: Either "today" or "latest"
    
    Returns:
        Path to the log file
    """
    log_dir = Path(base_dir)
    log_dir.mkdir(exist_ok=True)
    
    if date is None:
        date = datetime.now()
    
    date_str = date.strftime("%Y-%m-%d")
    filename = f"{date_str}_{mode}.txt"
    return log_dir / filename


def create_raw_dump(notes: List[ProcessedNote], date: datetime | None = None) -> str:
    """Create a raw dump of notes without LLM processing."""
    if date is None:
        date = datetime.now()
    
    lines = []
    lines.append(f"Alpha Picks Summary - {date.strftime('%Y-%m-%d')}")
    lines.append("=" * 80)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Number of Notes: {len(notes)}")
    lines.append("-" * 80)
    lines.append("")
    
    for i, note in enumerate(notes, 1):
        lines.append(f"Note {i}:")
        lines.append(f"  Note ID: {note.note_id}")
        lines.append(f"  Title: {note.title or 'N/A'}")
        lines.append(f"  Author: {note.author or 'N/A'}")
        lines.append(f"  Selection Date: {note.selection_date or 'N/A'}")
        lines.append(f"  Publish Time: {note.publish_time or 'N/A'}")
        lines.append(f"  URL: {note.url or 'N/A'}")
        lines.append(f"  Quality Score: {note.quality_score:.2f}")
        lines.append(f"  High Quality: {note.is_high_quality}")
        lines.append(f"  Quality Notes: {', '.join(note.quality_notes)}")
        lines.append("")
        lines.append("  Post Text:")
        lines.append("  " + "-" * 76)
        if note.post_text:
            # Indent each line
            for line in note.post_text.split('\n'):
                lines.append(f"  {line}")
        else:
            lines.append("  (No post text)")
        lines.append("")
        lines.append("  OCR Text (from images):")
        lines.append("  " + "-" * 76)
        if note.ocr_text:
            # Indent each line
            for line in note.ocr_text.split('\n'):
                lines.append(f"  {line}")
        else:
            lines.append("  (No OCR text)")
        lines.append("")
        lines.append("=" * 80)
        lines.append("")
    
    return "\n".join(lines)


async def save_daily_summary(
    notes: List[ProcessedNote],
    settings: Settings,
    log_dir: str = "alpha_picks_logs",
    date: datetime | None = None,
    mode: str = "today",
    use_raw_dump: bool = True,
) -> Path:
    """
    Save notes to a daily log file.
    
    Args:
        notes: Processed notes to save
        settings: Settings (used only if use_raw_dump=False)
        log_dir: Directory for log files
        date: Target date for the log
        mode: "today" or "latest"
        use_raw_dump: If True, use raw dump instead of LLM summary (faster, no encoding issues)
    """
    
    # Get log file path
    log_path = get_daily_log_path(log_dir, date, mode)
    
    if use_raw_dump:
        # Use raw dump - faster and avoids encoding issues
        content = create_raw_dump(notes, date)
    else:
        # Generate summary using LLM (slower, may have encoding issues)
        summary = await generate_daily_summary(notes, settings, target_date=date)
        
        if date is None:
            date = datetime.now()
        
        header = f"Alpha Picks Summary - {date.strftime('%Y-%m-%d')}\n"
        header += "=" * 80 + "\n\n"
        header += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        header += f"Number of Notes Analyzed: {len(notes)}\n\n"
        header += "-" * 80 + "\n\n"
        
        content = header + summary + "\n\n" + "-" * 80 + "\n\n"
    
    # Append to file if it already exists, otherwise create new
    file_mode = "a" if log_path.exists() else "w"
    
    if file_mode == "a" and not use_raw_dump:
        # Add separator for multiple runs in the same day (only for LLM summaries)
        content = "\n" + "=" * 80 + "\n"
        content += f"Additional Update - {datetime.now().strftime('%H:%M:%S')}\n"
        content += "=" * 80 + "\n\n" + summary + "\n\n"
    
    # Write with UTF-8 BOM for proper encoding detection
    with open(log_path, file_mode, encoding="utf-8-sig", newline='\n') as f:
        f.write(content)
    
    return log_path

