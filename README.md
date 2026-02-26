# Local LLM Demo (Ollama Local / Anthropic / OpenAI + Optional Zscaler AI Guard)

Very small demo app for local testing and live demos.

## What this demo shows

- Local web chat UI (`python app.py`)
- Multi-provider LLM selector (`Ollama (Local)` default, plus `Anthropic` and `OpenAI`)
- Single-turn / Multi-turn chat mode toggle (provider-agnostic)
- Agentic Mode toggle (provider-agnostic single-agent tool loop)
- Tools (MCP) toggle for agent tool execution (MCP-friendly architecture; see note below)
- Optional Zscaler AI Guard checks with a UI toggle (`Guardrails` ON/OFF)
- HTTP trace sidebar showing request/response payloads (including upstream calls)
- Code Path Viewer (before/after guardrails, auto follows toggle/provider)
- Agent / Tool Trace panel (LLM decisions + tool calls)

## Quick start

1. Start Ollama:
   - `ollama serve`
2. Pull a small model (once):
   - `ollama pull llama3.2:1b`
3. Run app:
   - `python app.py`
4. Open:
   - `http://127.0.0.1:5000`

## Optional Remote Providers (SDK)

The app supports `Anthropic` and `OpenAI` as selectable LLM providers in the UI.

Requirements:

- Install the SDK in your environment:
  - `pip install anthropic`
  - `pip install openai`
- Set your API key:
  - `export ANTHROPIC_API_KEY='your_key_here'`
  - `export OPENAI_API_KEY='your_key_here'`

Optional:

- `export ANTHROPIC_MODEL='claude-sonnet-4-5-20250929'`
- `export OPENAI_MODEL='gpt-4o-mini'`

Notes:

- `Ollama (Local)` remains the default provider
- If a provider SDK or API key is missing and you select `Anthropic` or `OpenAI`, the app returns a clear error and shows the provider trace in `HTTP Trace`

### Optional: Local Corporate TLS / ZIA (Anthropic + AI Guard)

If you are running locally behind corporate TLS interception (for example ZIA), you may need to trust your corporate/Zscaler root CA for outbound HTTPS used by providers (like Anthropic).

This repo includes a Zscaler root CA PEM and a combined CA bundle example for local SE/demo use:

- `certs/zscaler-root-ca.pem`
- `certs/combined-ca-bundle.pem` (built from `certifi` CA bundle + Zscaler root CA)

When needed, start the app with:

- `export SSL_CERT_FILE='/absolute/path/to/certs/combined-ca-bundle.pem'`
- `export REQUESTS_CA_BUNDLE='/absolute/path/to/certs/combined-ca-bundle.pem'`

Notes:

- This is typically a local workstation/corporate network requirement
- It may not be needed when deployed in cloud environments without TLS interception

## UI Features

- `Send`: submits prompt to `/chat`
- `Prompt Presets`: opens a grouped list of curated demo prompts (fills the prompt box only)
- `Clear`: clears prompt, response, status, HTTP trace, code path viewer state, multi-turn conversation transcript, and `Agent / Tool Trace` (but keeps the selected LLM provider)
- `LLM` dropdown: choose `Ollama (Local)`, `Anthropic`, or `OpenAI`
- `Multi-turn Chat` toggle:
  - OFF (default): single-turn prompt/response
  - ON: chat transcript mode with conversation history sent to the selected provider
- `Tools (MCP)` toggle:
  - Enables tool execution for agentic runs
  - Uses a bundled local MCP server (`stdio`) by default
  - Can be redirected to another MCP server via `MCP_SERVER_COMMAND`
- `Agentic Mode` toggle:
  - Enables a realistic single-agent, multi-step loop (LLM decides tool use, runs tool, then finalizes)
  - Works with `Ollama (Local)`, `Anthropic`, and `OpenAI` via the same provider abstraction
- `Multi-Agent Mode` toggle:
  - Placeholder (disabled in UI for now)
  - Planned for later (orchestrator + specialist agents)
- `Zscaler AI Guard` toggle (default OFF): enables/disables Zscaler AI Guard flow per request
- `HTTP Trace` panel:
  - Client request to `/chat`
  - Client response from the app
  - Upstream calls (selected provider and, when enabled, Zscaler AI Guard IN/OUT checks)
- `Agent / Tool Trace` panel:
  - Agent LLM decision steps
  - Tool call inputs/outputs
  - Tool-specific request/response traces (for network tools like weather/web fetch/search)
- `Code Path Viewer`:
  - Shows provider-aware before/after code paths
  - Auto mode follows selected provider, chat mode, and Zscaler AI Guard toggle state

Notes:

- Several toggles include UI tooltips (`title` hover text) to explain behavior during demos.

## App Name (optional)

You can customize the browser/app title shown in the UI with an env var:

- `export APP_DEMO_NAME='My AI Demo App'`

If not set, the app defaults to:

- `AI App Demo`

## Optional Zscaler AI Guardrails (toggleable in UI)

The app includes a `Zscaler AI Guard` toggle (default: OFF). When enabled, each chat request uses this flow:

1. Zscaler AI Guard `IN` check (prompt)
2. Selected LLM provider generation (`Ollama (Local)`, `Anthropic`, or `OpenAI`)
3. Zscaler AI Guard `OUT` check (response)

If Zscaler blocks the prompt or response, the app returns a blocked message.

In multi-turn mode, the guardrails flow remains the same but is applied per turn:

1. `IN` check on the latest user message
2. Selected provider is called with conversation history (`messages`)
3. `OUT` check on the generated assistant response

When `Agentic Mode` is enabled:

1. `IN` check runs on the latest user message
2. Agent loop runs (selected provider, optional tools if `Tools (MCP)` is ON)
3. `OUT` check runs on the final agent response

The current demo does **not** apply guardrails to each intermediate tool input/output yet (only user input and final output). This is intentional for a clear baseline and easy future comparison when adding deeper tool-loop guardrail coverage.

This demo app is configured to use the Zscaler Resolve Policy endpoint (not a specific Policy ID in the request payload):

- `https://api.zseclipse.net/v1/detection/resolve-and-execute-policy`

### Local env vars (recommended for labs)

- `ZS_GUARDRAILS_API_KEY` (required when using Guardrails toggle ON)
- `ZS_GUARDRAILS_URL` (default: `https://api.zseclipse.net/v1/detection/resolve-and-execute-policy`)
- `ZS_GUARDRAILS_TIMEOUT_SECONDS` (default: `15`)
- `ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME` (optional; if set, the app forwards a per-conversation ID to AI Guard in this header)

Example (zsh/bash):

- `export ZS_GUARDRAILS_API_KEY='your_local_key_here'`
- `export ZS_GUARDRAILS_URL='https://api.zseclipse.net/v1/detection/resolve-and-execute-policy'` (optional; default shown)
- `export ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME='conversationIdHeaderName'` (optional example)
- `python app.py`

If the API key is not set and `Guardrails` is ON, the app will return a clear error and show the attempted Zscaler request in the HTTP trace panel.

If `ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME` is set, the app sends a stable per-conversation ID (generated in the browser and reset on `Clear`) in that header for both AI Guard `IN` and `OUT` checks. This is visible in the trace panel.

## Zscaler Console Setup (DAS/API Mode)

In Zscaler AI Guard, make sure you have done the following while in DAS/API Mode in the console:

1. Created the App (for example, `Local LLM`)
2. Created the API Key tied to the App (you will use this for `ZS_GUARDRAILS_API_KEY`)
3. Created a Policy Configuration with at least one detector
4. Created a Policy Control tied to the Policy Configuration with criteria for the App/Credentials you set

## Optional env vars

- `OLLAMA_MODEL` (default: `llama3.2:1b`)
- `OLLAMA_URL` (default: `http://127.0.0.1:11434`)
- `ANTHROPIC_API_KEY` (required only when `Anthropic` provider is selected)
- `ANTHROPIC_MODEL` (default: `claude-sonnet-4-5-20250929`)
- `OPENAI_API_KEY` (required only when `OpenAI` provider is selected)
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `BRAVE_SEARCH_API_KEY` (required only if using the `brave_search` tool)
- `BRAVE_SEARCH_BASE_URL` (default: `https://api.search.brave.com`)
- `BRAVE_SEARCH_MAX_RESULTS` (default: `5`)
- `AGENTIC_MAX_STEPS` (default: `3`)
- `MCP_SERVER_COMMAND` (optional; shell command used to start an MCP server over `stdio`)
- `MCP_TIMEOUT_SECONDS` (default: `15`)
- `MCP_PROTOCOL_VERSION` (default: `2024-11-05`)
- `APP_DEMO_NAME` (default: `AI App Demo`)

## Tools (Agentic Mode)

Built-in tools currently available when `Tools (MCP)` is enabled:

- `calculator` (local arithmetic, no API key)
- `weather` (uses `wttr.in`, no API key)
- `web_fetch` (fetches URL content and extracts text)
- `brave_search` (Brave Search API, requires `BRAVE_SEARCH_API_KEY`)
- `current_time` (timezone-aware current date/time)
- `dns_lookup` (hostname -> IP addresses)
- `http_head` (HTTP status + response headers for a URL)
- `hash_text` (md5/sha1/sha256/sha512)
- `url_codec` (URL encode/decode)
- `text_stats` (char/word/line counts)
- `uuid_generate` (UUIDv4 values)
- `base64_codec` (encode/decode)

### Brave Search vs Web Fetch

- `brave_search` finds relevant URLs/results for a query (search API)
- `web_fetch` retrieves the content of a specific URL

They are different and often complementary in agentic workflows.

### Example Tool Prompts

- `Use the weather tool to get tomorrow's weather for Franklin, TN 37064 and tell me if I should bring a jacket.`
- `Use the calculator tool to compute (23*19)+7 and return only the number.`
- `Use dns_lookup on api.search.brave.com and return the IP addresses.`
- `Use http_head on https://ollama.com and summarize the status code and server headers.`
- `Use hash_text with sha256 on the text "local demo".`
- `Use url_codec to encode "Franklin TN 37064 coffee shops".`
- `Use text_stats on this text: "one two three\nfour".`
- `Generate 3 UUIDs using uuid_generate.`

## MCP Status (Important)

This build now supports a **real MCP client path over `stdio`** and includes a bundled local MCP tool server for easy local demos.

Current MCP behavior:

- If `MCP_SERVER_COMMAND` is **not** set:
  - The app auto-starts the bundled local MCP server (`mcp_tool_server.py`)
  - Your existing built-in tools (weather, brave search, calculator, etc.) are exposed via MCP
- If `MCP_SERVER_COMMAND` **is** set:
  - The app starts the MCP server process
  - Calls `initialize`
  - Sends `notifications/initialized`
  - Calls `tools/list`
  - Exposes MCP tools to the agent alongside local built-in tools
  - Calls `tools/call` when the agent selects an MCP tool name

Notes:

- Your existing tools do **not** disappear; they are now available through the bundled local MCP server by default
- If a custom MCP server does not expose a tool name, the app still falls back to local built-in tools for that tool
- MCP server startup / tool list events are shown in `Agent / Tool Trace`
- MCP tool call request/response envelopes are included in tool traces

### Example MCP setup (stdio)

By default, no setup is required (the bundled local MCP server is auto-launched).

To use a different MCP server, set the command before starting the app:

- `export MCP_SERVER_COMMAND='python /path/to/your_mcp_server.py'`

Then start the app normally and enable:

- `Agentic Mode` = ON
- `Tools (MCP)` = ON
