# Xiaohongshu Alpha Pick Search Prototype

This project provides a local workflow for querying the open-source
[Xiaohongshu MCP server](https://github.com/xpzouying/xiaohongshu-mcp)
and summarising the retrieved notes with DeepSeek. The default keyword is
“alpha pick {today}”, but both the keyword and prompt are fully
customisable from the CLI.

The code is designed to run locally today and can be deployed to Google
Opal later (no deployment automation is included yet).

## Features

- Talks to the open-source Xiaohongshu MCP server over HTTP.
- Extracts both post body text and OCR text from images.
- Summarises results through DeepSeek (optional offline mode for testing).
- Keyword, prompt, and prompt template can be customised.
- Saves raw MCP payloads for inspection.

## Getting started

1. **Install dependencies** (preferably inside a virtual environment). The
   `openai` package is only required if you plan to run DeepSeek
   summarisation locally:

   ```bash
   pip install -r requirements.txt
   ```

2. **Prepare configuration**

   The application reads settings from environment variables or a `.env`
   file. At minimum you should configure:

   ```bash
   export DEEPSEEK_API_KEY=sk-your-deepseek-key
   export XHS_MCP_BASE_URL=http://127.0.0.1:18060
   # optional: provide the MCP API key if your server requires one
   # export XHS_MCP_API_KEY=your-mcp-api-key
   # optional: override the relative path (defaults to /mcp/tools/search)
   # export XHS_MCP_SEARCH_PATH=/mcp/tools/search
   # optional: provide a fully-qualified search URL if you reverse proxy
   # export XHS_MCP_SEARCH_URL=http://127.0.0.1:18060/mcp/tools/search
   ```

   The default `XHS_MCP_BASE_URL` matches the open-source server’s
   default HTTP port (`18060`). Override `XHS_MCP_SEARCH_PATH` if you
   expose the tool under a different relative URL, or set
   `XHS_MCP_SEARCH_URL` to the exact endpoint if you front it with a
   reverse proxy.

3. **Start the Xiaohongshu MCP server**

   MCP (Model Context Protocol) servers are small HTTP services that act
   as capability adapters for language models. The open-source
   Xiaohongshu MCP server wraps the site’s search endpoints and exposes
   them in a predictable JSON shape so that any MCP-compatible client –
   whether this CLI, an IDE, or Google Opal later on – can call it
   safely. Running the server locally gives you a concrete endpoint to
   query; without it, the CLI has nowhere to send the search request.

   Clone and run the open-source server locally, following the
   instructions from its repository. Ensure it listens on the
   `XHS_MCP_BASE_URL` you configured above.

   The binary’s README calls out two important URLs once the process is
   running locally:

   - `http://localhost:18060/` loads the dashboard (or QR-code login
     page when you start it with `-headless=false`).
   - `http://localhost:18060/mcp/...` exposes the actual MCP HTTP API
     that this client calls. By default the search tool lives at
     `/mcp/tools/search`, which matches this project’s
     `XHS_MCP_SEARCH_PATH` default. If you self-host the server behind a
     reverse proxy, make sure those paths remain reachable.

### Why you still need that “middleman” server

- **MCP is a network protocol, not an in-process SDK.** Even though the
  server simply wraps Xiaohongshu’s private endpoints, the CLI and any
  future MCP clients expect to talk to a live HTTP service that speaks
  the protocol. The server is therefore the MCP “tool” implementation.
- **It centralises scraping credentials and throttling.** The adapter is
  responsible for holding session cookies, solving anti-bot
  requirements, and shaping responses. Offloading that work to the
  server keeps the CLI (and any other clients) stateless and compliant
  with MCP expectations.
- **It is the piece Google Opal will call.** When you deploy later, Opal
  connects to registered MCP endpoints; keeping the adapter as a
  standalone service today guarantees that the same component is
  reusable in that environment without code changes.

4. **Run the CLI**

   ```bash
   python -m xhs_alpha_picks.cli --keyword "alpha pick $(date +%Y-%m-%d)" --count 5
   ```

   Useful flags:

   - `--prompt` or `--prompt-file` to tweak the DeepSeek prompt. Use
     `{keyword}` as a placeholder that resolves to the actual search
     keyword.
   - `--offline` skips DeepSeek and only prints the retrieved notes.
   - `--show-raw` prints the entire MCP payload for debugging.
   - `--save-json raw.json` stores the payload to disk for later use.
   - `--check-connection` performs a quick reachability probe against the
     MCP server and exits without issuing a search. The CLI now performs a
     light-weight reachability check automatically before every search and
     exits early with guidance if the server cannot be reached.
   - `--debug` prints the derived MCP base URL, search path, timeout, and
     API key status so you can confirm the configuration matches the MCP
     server’s README instructions.
   - `--mcp-api-key` lets you supply a key directly on the command line
     (it overrides `XHS_MCP_API_KEY` for the current invocation).

## Testing locally

The project ships with a small test suite that mocks the MCP server and
runs the CLI in offline mode:

```bash
pytest
```

## Next steps

- Integrate deployment automation for Google Opal once the open-source
  MCP server is hosted.
- Extend the CLI to support incremental syncs or scheduling if required.

