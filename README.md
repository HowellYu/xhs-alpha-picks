# Xiaohongshu Alpha Picks Search & Analysis

Automated pipeline for discovering and analyzing Seeking Alpha's Alpha Picks selections from Xiaohongshu posts. Combines the [open-source Xiaohongshu MCP server](https://github.com/xpzouying/xiaohongshu-mcp) with DeepSeek LLM to extract structured stock selection data.

## Features

-   🔍 Searches Xiaohongshu for Alpha Picks posts using MCP protocol
-   📷 Extracts OCR text from images automatically
-   ✅ Quality filtering: validates multiple picks, dates, Seeking Alpha references
-   📅 Smart date filtering: scan for today's posts or find latest selections
-   💾 Daily logging: saves structured data to date-stamped .txt files
-   🤖 DeepSeek integration: optional LLM-powered summarization

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

**Required:**

```bash
export DEEPSEEK_API_KEY=sk-your-deepseek-key
```

**Optional (defaults shown):**

```bash
export XHS_MCP_BASE_URL=http://127.0.0.1:18060  # MCP server URL
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_MODEL=deepseek-chat
```

### 3. Start Xiaohongshu MCP Server

Clone and run the open-source MCP server from [https://github.com/xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp). Ensure it's listening on port 18060 and you're logged in.

**Why MCP?** The server handles Xiaohongshu authentication, rate limiting, and protocol translation. The CLI talks to it via HTTP (MCP protocol) rather than scraping directly.

### 4. Run the CLI

**Scan for today's Alpha Picks:**

```bash
python cli.py --keyword "Alpha Picks" --today --max-results 1
```

**Find latest Alpha Picks selections:**

```bash
python cli.py --keyword "Alpha Picks" --max-results 2
```

**Customize scan parameters:**

```bash
python cli.py --keyword "Alpha Picks" \
  --days 7 \           # Look back 7 days
  --max-results 3 \    # Keep top 3 high-quality results
  --count 20           # Fetch 20 notes from MCP
```

**Key CLI Options:**

| Flag              | Description                                     |
| ----------------- | ----------------------------------------------- |
| `--keyword TEXT`  | Search keyword (default: "alpha pick {today}")  |
| `--today`         | Filter to today's posts only                    |
| `--days N`        | Filter to last N days (default: 2)              |
| `--max-results N` | Keep top N high-quality results (default: 1)    |
| `--count N`       | Fetch N notes from MCP (default: 10)            |
| `--note-type N`   | 0=all, 1=video, 2=image+text (default: 2)       |
| `--sort TYPE`     | general, time_descending, popularity_descending |
| `--log-dir DIR`   | Log directory (default: `alpha_picks_logs/`)    |
| `--no-log`        | Skip saving to log file                         |
| `--show-json`     | Print processed notes as JSON                   |
| `--show-raw`      | Print raw MCP payload                           |
| `--debug`         | Show connection details                         |

**Note:** `--sort` is set to `time_descending` by default for most recent results.

## Output Format

Logs are saved to `alpha_picks_logs/YYYY-MM-DD_{today|latest}.txt`:

```
Alpha Picks Summary - 2025-10-31
================================================================================
Note 1:
  Title: Seeking Alpha Picks 2025.10.31新增企业
  Author: mir的自由之路
  Selection Date: 2025-10-31

  Post Text:
  [Full post content...]

  OCR Text (from images):
  [Extracted text from images...]
```

## Quality Filtering

Notes are scored for quality based on:

-   ✅ Mentions Seeking Alpha/Alpha Picks service
-   ✅ Contains 3+ stock selections (not just 1-2)
-   ✅ Includes selection dates
-   ✅ Has substantial text + OCR content

Only high-quality notes (score ≥ 0.7) are kept by default.

## Testing

Run offline tests:

```bash
pytest
```

## How It Works

1. **Search**: CLI calls the MCP server's `search_feeds` tool with your keyword
2. **Extract**: Raw note data is parsed, extracting title, description, author, images
3. **OCR**: Text is extracted from images using the MCP server's OCR capabilities
4. **Filter**: Notes are filtered by date (today or latest) and quality (3+ selections, Seeking Alpha reference)
5. **Log**: Structured data is saved to date-stamped `.txt` files with UTF-8 BOM encoding

## Technical Details

-   **Transport**: Uses Streamable HTTP for MCP connections (as per MCP Inspector settings)
-   **Encoding**: Logs use UTF-8 with BOM (`utf-8-sig`) for universal compatibility
-   **Quality Scoring**: 0.0-1.0 based on criteria; ≥0.7 + 3+ picks = high quality
-   **Default Sort**: Always sorts by `time_descending` for most recent results
