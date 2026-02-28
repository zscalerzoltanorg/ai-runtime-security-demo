# AI Runtime Security Demo

Local demo web app for testing LLM providers, Zscaler AI Guard (DAS/API + Proxy), agentic/multi-agent workflows, MCP/tools, and rich traces.

## What's New (Recent)

- `branch: codex/low-risk-learning-features` (preview, not merged)
  - Added flow replay controls (`Prev Trace` / `Next Trace`) to inspect prior captured runs in-session.
  - Added `Export Evidence` to download a JSON evidence pack (selected trace + explainer summary + flow graph nodes/edges).
  - Enhanced Flow Explainer with `Performance & Cost Signals` (token totals, estimated latency, AI Guard check/block counts).
  - Added `Attack Sandbox (Learning)` prompt preset pack for safe policy/testing demos.

- `v1.0.3` (02-28-26)
  - Added a new **Flow Explainer** modal (theme-aware) with deterministic, trace-driven summaries:
    - what happened
    - security outcome (allow/block + stage/mode)
    - tool activity (local vs network, errors)
    - step-by-step timeline
  - Reworked **Prompt Presets** into a modal workflow with in-modal config (gear icon), persisted custom detector prompts, reset-to-defaults, and cleaner grouped/collapsible layout.
  - Improved UI/UX polish across themes (especially Dark/Neon), plus modal consistency and save behaviors in settings/preset flows.
  - Refined graph/guardrails behavior for clearer proxy vs DAS/API path visualization and endpoint transparency.
- `v1.0.2` (02-27-26)
  - Fixed flow graph behavior for AI Guard block paths (Proxy + DAS/API) so edges reflect real request flow.
  - Added provider/upstream endpoint hints in flow graph tooltips.
  - Fixed DAS/API `OUT` block handling so blocked model output is redacted from user-visible block responses and trace payload previews.
- `v1.0.1` (02-27-26)
  - Added UI themes (Classic, Zscaler Blue, Dark, Neon) with persistent selection.
  - Improved dark/neon modal and panel styling.
  - Added auto build/version badge near title (git tag/commit based).

Note: this section is intentionally compact. Keep only recent releases here and avoid a long historical changelog in this repo.

## What You Can Demo

- Multi-provider chat (local + cloud)
- Zscaler AI Guard toggle and mode switch (API/DAS vs Proxy)
- Single-turn and multi-turn behavior
- Agentic and multi-agent execution
- Tools/MCP behavior
- HTTP trace + agent/tool trace + prompt/instruction inspector
- Flow graph and code path viewer

## Provider Validation Status

Tested end-to-end in this demo environment:

- Ollama (Local)
- Anthropic
- OpenAI
- LiteLLM

Present in UI but not yet fully validated end-to-end in this environment:

- AWS Bedrock
- AWS Bedrock Agent
- Google Gemini
- Google Vertex
- Perplexity
- xAI (Grok)
- Azure AI Foundry

---

## Recommended Setup (No Docker Required)

This project is designed to run directly with Python.

### macOS / Linux

1. Install prerequisites:
   - Python 3.11+
   - Git
2. Clone:
   - `git clone https://github.com/zscalerzoltanorg/ai-runtime-security-demo.git`
   - `cd ai-runtime-security-demo`
3. Bootstrap:
   - `./scripts/bootstrap_mac_linux.sh`
   - This script creates `.venv`, installs Python deps, creates `.env.local` (if missing), installs Ollama when possible, starts `ollama serve`, and pulls `llama3.2:1b`.
4. If bootstrap cannot install Ollama, install it manually:
   - [https://ollama.com/download](https://ollama.com/download)
   - Then run: `ollama serve` and `ollama pull llama3.2:1b`
5. Run app:
   - `source .venv/bin/activate`
   - `set -a; source .env.local; set +a`
   - `python3 app.py`
   - If `ollama serve` says port `11434` is already in use, Ollama is already running; continue without starting another one.
6. Open:
   - [http://127.0.0.1:5000](http://127.0.0.1:5000)

### Windows (PowerShell)

1. Install prerequisites:
   - Python 3.11+
   - Git for Windows
2. Clone:
   - `git clone https://github.com/zscalerzoltanorg/ai-runtime-security-demo.git`
   - `cd ai-runtime-security-demo`
3. Bootstrap:
   - `./scripts/bootstrap_windows.ps1`
   - This script creates `.venv`, installs Python deps, creates `.env.local` (if missing), installs Ollama via winget when possible, starts `ollama serve`, and pulls `llama3.2:1b`.
4. If bootstrap cannot install Ollama, install it manually:
   - [https://ollama.com/download](https://ollama.com/download)
   - Then run: `ollama serve` and `ollama pull llama3.2:1b`
5. Run app:
   - `.\.venv\Scripts\Activate.ps1`
   - `python app.py`
6. Open:
   - [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## Configuration Philosophy

- Start with local defaults from `.env.example` -> `.env.local`
- Use the in-app **Settings (⚙)** modal for day-to-day config edits (preferred)
- Save settings locally; restart when prompted

You do **not** need to prefill every env variable.
Only set keys/providers you actually want to use.

---

## Minimal Local Defaults

Your `.env.local` should at least have:

```env
PORT=5000
APP_DEMO_NAME='AI Runtime Security Demo'
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:1b
MCP_SERVER_COMMAND=
MCP_TIMEOUT_SECONDS=15
MCP_PROTOCOL_VERSION=2024-11-05
LOCAL_TASKS_BASE_DIR=demo_local_workspace
LOCAL_TASKS_MAX_ENTRIES=200
LOCAL_TASKS_MAX_BYTES=500000
MAX_REQUEST_BYTES=1000000
SSL_CERT_FILE=certs/combined-ca-bundle.pem
REQUESTS_CA_BUNDLE=certs/combined-ca-bundle.pem
```

When `MCP_SERVER_COMMAND` is empty, the app automatically uses the bundled local MCP server.

---

## Optional Provider Credentials (Set Only If Needed)

- Anthropic: `ANTHROPIC_API_KEY`
- OpenAI: `OPENAI_API_KEY`
- LiteLLM: `LITELLM_API_KEY`, `LITELLM_BASE_URL`
- Bedrock: AWS auth via either explicit keys (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + optional `AWS_SESSION_TOKEN`) or ambient local credentials/SSO, plus optional `AWS_REGION` and agent IDs for Bedrock Agent
- Perplexity: `PERPLEXITY_API_KEY`
- xAI: `XAI_API_KEY`
- Gemini: `GEMINI_API_KEY`
- Vertex: `VERTEX_PROJECT_ID` + Google auth
- Azure AI Foundry: `AZURE_AI_FOUNDRY_API_KEY`, `AZURE_AI_FOUNDRY_BASE_URL`

All model overrides are optional and can be configured later.

---

## Zscaler AI Guard (Optional)

### DAS/API mode

- `ZS_GUARDRAILS_API_KEY`
- Optional: `ZS_GUARDRAILS_URL`, `ZS_GUARDRAILS_TIMEOUT_SECONDS`, `ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME`

### Proxy mode

- `ZS_PROXY_BASE_URL` (default shown in `.env.example`)
- Provider-specific proxy keys:
  - `ANTHROPIC_ZS_PROXY_API_KEY`
  - `OPENAI_ZS_PROXY_API_KEY`
  - `KONG_ZS_PROXY_API_KEY`
  - `LITELLM_ZS_PROXY_API_KEY`
  - `BEDROCK_INVOKE_ZS_PROXY_API_KEY`
  - `BEDROCK_AGENT_ZS_PROXY_API_KEY`
  - `PERPLEXITY_ZS_PROXY_API_KEY`
  - `XAI_ZS_PROXY_API_KEY`
  - `GEMINI_ZS_PROXY_API_KEY`
  - `VERTEX_ZS_PROXY_API_KEY`
  - `AZURE_FOUNDRY_ZS_PROXY_API_KEY`

---

## MCP Toolset Snapshot + Provider Tool Wiring

### Why guardrails did not see "available tools" before

Before this change, Anthropic requests were built in `providers.py` (`_anthropic_generate` and `_anthropic_chat_messages`) with:
- `model`
- `messages`
- `temperature`
- `max_tokens`

No `tools` field was attached to provider payloads.  
MCP tool discovery happened only inside the agent loop (`agentic.py`) for local execution planning, so proxy/guardrails could not observe an "available tools" manifest on normal provider calls.

### What changed

- Added `tooling.py`:
  - canonical internal model: `ToolDef { id, name, description, input_schema, source_server }`
  - MCP discovery from configured server(s)
  - structured telemetry event: `type="toolset.snapshot"`
- `/chat` now:
  - emits a toolset snapshot at chat start
  - emits another snapshot immediately before each LLM call
  - includes these events in response payload as `toolset_events` so the UI trace/flow graph can render them
- `providers.py` now includes a provider adapter scaffold:
  - `ProviderAdapter` interface with `build_request`, `parse_response`, `tool_call_to_mcp`
  - implemented `AnthropicAdapter`
  - OpenAI/Bedrock extension notes are included as stubs/comments
- Anthropic request builder now supports attaching mapped tool definitions (behind flags).

### New env knobs

- `TOOLSET_DEBUG_LOGS=true|false`
- `INCLUDE_TOOLS_IN_LLM_REQUEST=true|false` (default `false`)
- `MAX_TOOLS_IN_REQUEST` (default `20`)
- `TOOL_INCLUDE_MODE=all|allowlist|progressive`
- `TOOL_ALLOWLIST=comma,separated,names-or-ids`
- `TOOL_PROGRESSIVE_COUNT` (used when `TOOL_INCLUDE_MODE=progressive`)
- `TOOL_NAME_PREFIX_STRATEGY=serverPrefix|hash|none`

### Universal vs provider-specific

Universal:
- `ToolDef` internal schema (`tooling.py`)
- `toolset.snapshot` event schema and emission timing
- MCP discovery and normalization

Provider-specific:
- payload wiring (`tools` field shape and constraints)
- tool name normalization and reversible mapping
- tool-call parsing format (`tool_use` vs function-calls vs Bedrock-specific shapes)

---

## Local Task Tools (Demo)

This repo includes a small local demo dataset at:

- `demo_local_workspace/`

You can enable local task tools from the UI using:

- `Tools (MCP)` toggle
- `Local Tasks` toggle (enabled only when Agentic or Multi-Agent mode is active)

### Included local task tools

- `local_whoami`: user + host + platform info
- `local_pwd`: current working dir + configured local tasks base dir
- `local_ls`: list directory entries under base dir
- `local_file_sizes`: summarize file sizes under base dir
- `local_curl`: curl-like HTTP request (GET/HEAD/POST, URL + params + headers + optional body)

Tool alias handling is enabled for weaker models:

- `curl` -> `local_curl`
- `ls` / `dir` -> `local_ls`
- `pwd` -> `local_pwd`
- `whoami` -> `local_whoami`
- `du` / `file_sizes` -> `local_file_sizes`

### Cross-platform behavior (macOS/Linux/Windows)

- Local filesystem and user tools use Python stdlib APIs, so behavior is portable.
- Paths are normalized through Python `pathlib` and constrained to `LOCAL_TASKS_BASE_DIR`.
- No shell command execution is required for `whoami`, `pwd`, or directory listing.

### Local task safety boundaries

- Local filesystem actions are restricted to `LOCAL_TASKS_BASE_DIR` (default: `demo_local_workspace`).
- `local_ls` and `local_curl` output size are capped with:
  - `LOCAL_TASKS_MAX_ENTRIES`
  - `LOCAL_TASKS_MAX_BYTES`
- `local_curl` does not use an allowlisted host model (for demo flexibility), but is still constrained by method/time/body limits.

### Guardrails visibility note

- Provider request/response traffic appears in HTTP trace and can be enforced by AI Guard (DAS/API or Proxy mode).
- Local task tool execution appears in Agent/Tool trace + flow graph as tool steps.
- Local tool calls themselves are local runtime actions and are not automatically sent to AI Guard unless you explicitly route/check them in your own policy pipeline.

---

## Update Existing Deployment

If you already have this app running and want the latest GitHub changes, use this sequence.

### Native Python deployment

1. Pull latest code:
   - `git fetch origin`
   - `git pull --ff-only origin main`
2. Activate venv:
   - macOS/Linux: `source .venv/bin/activate`
   - Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
3. Sync dependencies:
   - `python -m pip install -r requirements.txt`
4. Merge new env defaults without overwriting your secrets:
   - compare `.env.example` vs your `.env.local`
   - add only new keys you need (leave existing real keys as-is)
5. Restart app process:
   - stop old `python app.py`
   - restart with your normal command (`python3 app.py` or `python app.py`)

### Docker Compose deployment

1. Pull latest code:
   - `git fetch origin`
   - `git pull --ff-only origin main`
2. Rebuild + restart:
   - `docker compose up -d --build`
3. Verify:
   - `docker compose ps`
   - open [http://127.0.0.1:5000](http://127.0.0.1:5000)

### Recommended quick checks after any update

- Open **Settings (⚙)** and confirm expected provider/model values.
- Send a simple prompt with your usual provider.
- If using guardrails proxy mode, run one blocked and one allowed prompt to confirm behavior.

---

## Security Notes

- `.env`, `.env.*` are git-ignored (`!.env.example` is allowed)
- Do not commit real API keys
- Rotate/revoke temporary keys after demos
- Admin endpoints (`/settings`, `/restart`, status checks) are restricted to localhost-style requests
- Tooling URL safety:
  - `web_fetch` and `http_head` block localhost/private/reserved destinations by default
  - set `ALLOW_PRIVATE_TOOL_NETWORK=true` only if you intentionally need private network tooling in a trusted lab

---

## Docker Option (Optional)

Native install is still the simplest path.  
If you want a containerized setup, this repo now includes `Dockerfile` + `docker-compose.yml`.

What Docker runs:
- `app` container: this demo app server + bundled MCP tool server/client code
- `ollama` container: local Ollama runtime

### Docker prerequisites

- Docker Desktop (Mac/Windows) or Docker Engine + Compose plugin (Linux)

### Run with Docker Compose

1. Create local config file if missing:
   - `cp .env.example .env.local`
2. Build and start:
   - `docker compose up -d --build`
3. Pull the default Ollama model inside the Ollama container:
   - `docker compose exec ollama ollama pull llama3.2:1b`
4. Open app:
   - [http://127.0.0.1:5000](http://127.0.0.1:5000)

### Stop / cleanup

- Stop:
  - `docker compose down`
- Stop + remove Ollama model volume:
  - `docker compose down -v`

### Docker notes

- In Docker mode, the app uses `OLLAMA_URL=http://ollama:11434`.
- Compose binds published ports to loopback by default:
  - `127.0.0.1:5000` (app)
  - `127.0.0.1:11434` (Ollama)
- You can still edit provider keys/models via in-app Settings; values persist in `.env.local`.
- If you change settings that need restart, use the app restart prompt or run:
  - `docker compose restart app`
