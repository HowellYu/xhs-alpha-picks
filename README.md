# Xiaohongshu Alpha Pick Search Prototype

This workspace contains a minimal DeepSeek-powered workflow to check whether the
Xiaohongshu MCP server returns notes for a given keyword (for example,
today's “alpha pick”).

## Quick start

1. Install dependencies (ideally inside a virtual environment):
   ```bash
   pip install -r requirements.txt
   ```
2. Ensure the DeepSeek key is available:
   ```bash
   export DEEPSEEK_API_KEY=sk-your-key
   ```
3. Start the Xiaohongshu MCP server locally (documentation:
   https://xhs-mcp.aicu.icu/). By default it should expose
   `http://localhost:9999/mcp`. Override with `XHS_MCP_BASE_URL` if needed.
4. Run the keyword check:
   ```bash
   python -m xhs_alpha_picks.cli --keyword "alpha pick $(date +%Y-%m-%d)" --count 5 --show-raw
   ```

The CLI connects to the MCP server, asks DeepSeek to call the
“搜索小红书笔记” tool, and prints a short summary. Raw tool payloads can be
shown with `--show-raw` for debugging or downstream processing.

