# AI Runtime Security Demo

Local demo web app for testing LLM providers, Zscaler AI Guard (DAS/API + Proxy), agentic/multi-agent workflows, MCP/tools, and rich traces.

## What's New (Recent)

- `v1.5.36`
  - Fixed native Windows one-click updates for Python 3.11/3.12 installs by allowing untracked runtime files such as `.venv` while continuing to block tracked local edits.
  - Windows updates now install dependencies only after the running process releases its files, relaunch through a detached helper, and write restart diagnostics to `logs/update.log`.
  - Added a health-based browser wait and Windows CI coverage across Python 3.11, 3.12, and 3.13.

- `v1.5.35`
  - Code Path Viewer now builds the code path from the executed trace: it stays empty until a prompt is sent, then renders one numbered panel per replay step in execution order (request, AI Guard checks, agent loop, tools, response). Completed steps stay solid, the active step is highlighted with its code lines, and upcoming steps are dimmed. Panels are clickable to jump the replay, and stepping auto-scrolls the active panel into view.

- `v1.5.34`
  - Redesigned the first-time Setup Wizard into a five-step guided flow (Basics, AI Guard, LLMs, Demo Flow, Finish) that saves app settings to `.env.local` and remembers per-browser demo defaults (provider, guard mode, agent mode, tools, chat/response modes) in local storage.
  - Added a Code Replay stepper to the Code Path Viewer that walks through the selected trace (request, AI Guard checks, agent loop, tool/MCP events, response) and highlights the matching code panel and lines for each step.
  - Provider dropdowns now flag unconfigured providers with a `(configure)` label and tooltip, and fall back to a configured provider instead of failing on a disabled selection.
  - Added `?reset_local_state=1` URL parameter to clear per-browser demo defaults and wizard state.
  - Default app port is now `5050` (matching `.env.example`); set `PORT` in `.env.local` to override.

Older release notes live in [RELEASE_NOTES.md](RELEASE_NOTES.md). Keep this README section to the latest three versions so the project overview stays easy to scan.

## What You Can Demo

- Multi-provider chat (local + cloud)
- Zscaler AI Guard toggle and mode switch (API/DAS vs Proxy)
- Single-turn and multi-turn behavior
- Agentic execution with MCP/tool calls
- Multi-agent execution with bounded specialist spawning, review, and finalization
- Tools/MCP behavior using the bundled local MCP server or a custom MCP server command
- HTTP trace + agent/tool trace + prompt/instruction inspector
- Flow graph and code path viewer
- Demo Wizard recipes for quickly explaining which toggles to use for baseline chat, AI Guard, agentic tools, multi-agent research, local workspace tasks, and realistic employee-created agent use cases
- Version awareness + one-click updater (local admin only)

Agent role shorthand:
- `Agentic`: one planner loop that may call MCP tools before answering.
- `Multi-Agent`: an orchestrator selects bounded specialists such as Researcher, Tool Auditor, Security Reviewer, and Domain Analyst, then reviewer/finalizer steps produce the answer.
- `Topology`: switches whether orchestration runs inline, in an isolated worker, or as per-role worker calls for multi-agent demos.

## In-App Update Notifier + One-Click Update

- The UI now checks your configured git remote/branch for updates and shows:
  - `Update: latest`
  - `Update: available`
  - `Update: check failed`
- Update button behavior:
  - Runs `git fetch` + `git pull --ff-only` from configured remote/branch
  - Installs requirements with the current Python environment
  - Restarts the app
- Safety checks before applying update:
  - Requires localhost admin request
  - Refuses update when tracked files have local changes; ignored/untracked runtime files do not falsely block updates
  - Refuses update when current branch does not match configured update branch
- Native Windows updates install dependencies after the running process releases its files, then relaunch the app through a detached helper. Restart diagnostics are written to `logs/update.log`.
- Local settings are preserved:
  - `.env.local` is not overwritten by this update flow

Defaults:
- Git remote: `origin`
- Git branch: `main`
- Update check interval: `1 hour`

### Docker Upgrade Note

- In-app update is intentionally disabled for Docker deployments.
- Docker users should update with:
  1. `git pull`
  2. `docker compose up -d --build`
- Docker settings persistence expects your host settings file to be mounted into the container as `.env.local`.

## Attachments (Multimodal) Support

- The demo UI allows selecting any file type.
- Browser uploads are preserved as native file payloads where the selected provider supports them; the app no longer extracts uploaded text-file contents into the prompt by default.
- For OpenAI Chat Completions, PDF attachments are sent as native `type: file` content parts with base64 file data when they fit under `MAX_FILE_DATA_URL_CHARS`.
- Images are sent as native image payloads only when the selected provider/model supports vision. Otherwise, they are attached as file metadata.
- Other binary/unknown file types are accepted as bounded metadata, with a small data URL preview when they fit under `MAX_FILE_DATA_URL_CHARS`. Providers may ignore those contents unless they support native file inputs.
- API/DAS guard checks receive the typed prompt plus attachment metadata. For end-to-end file-content visibility in AI Guard, use Proxy mode with a provider path that supports native file payloads.
- Provider/model notes:
  - Ollama is model-dependent for native image support.
  - Non-PDF OpenAI files and unsupported provider file types receive attachment metadata rather than locally extracted contents.

## Adversarial Presets (How To Use)

- Open `Prompt Presets` and use the `Attack Sandbox` group.
- Click a preset card to copy that prompt into the input box.
- For presets with sample files:
  - Click `Attach Sample` to auto-load the local sample file(s) from `attack_sandbox_samples/`.
- For multi-turn attack presets:
  - Click `Run 2-step`.
  - If chat mode is `Single Turn`, the UI automatically switches to `Multi Turn`.
  - The app sends turn 1, waits for the response, then sends turn 2.
  - If step 1 fails, step 2 is not sent.
- Recommended demo setup for attack validation:
  - `Zscaler AI Guard: On`
  - For inline blocking tests: `Mode: Proxy`
  - For out-of-band detector observations: `Mode: API/DAS`

## Background Demo Traffic

Use the traffic generator when you want the local web app to produce varied AI Guard traffic without clicking through the UI:

```bash
python3 scripts/traffic_generator.py --base-url http://127.0.0.1:5050 --count 25
```

Defaults keep AI Guard on, read the running app settings from `/settings`, infer configured providers/direct keys/proxy keys, skip Anthropic unless `--include-anthropic` is passed, and randomize API/DAS vs proxy, Resolve vs Execute, single-turn vs multi-turn, response modes, agentic mode, MCP tools, demo users, and prompt categories across detector families.

Useful controls:

```bash
# High-volume tested log-filler run.
python3 scripts/traffic_burst.py

# Preview the burst recipe without sending requests.
python3 scripts/traffic_burst.py --dry-run --count 10

# Continuous run until Ctrl-C or stop file.
python3 scripts/traffic_generator.py --forever --min-delay 10 --max-delay 45 --jsonl traffic.jsonl

# Stop a continuous run from another terminal.
touch /tmp/ai-runtime-security-demo-traffic.stop

# Cheap/local-heavy run.
python3 scripts/traffic_generator.py --provider-weights ollama=10,openai=2,bedrock_invoke=1 --count 50

# Auto-discover configured providers from the web app settings.
python3 scripts/traffic_generator.py --provider-weights auto --count 25

# Run up to 3 conversations concurrently, each with its own conversation ID.
python3 scripts/traffic_generator.py --count 30 --parallel 3 --min-delay 5 --max-delay 15

# Heavier detector-category coverage.
python3 scripts/traffic_generator.py --count 40 --detector-rate 0.9 --response-detector-rate 0.55

# Run for about an hour with random bursts and longer pauses.
python3 scripts/traffic_generator.py --duration-hours 1 --parallel 2 --min-delay 20 --max-delay 90 --pause-every 15 --pause-min 120 --pause-max 300 --detector-rate 0.9 --response-detector-rate 0.6 --coverage-mode balanced --jsonl traffic-$(date +%Y%m%d-%H%M%S).jsonl

# Force proxy-only traffic for providers with configured proxy keys.
python3 scripts/traffic_generator.py --guard-modes proxy --provider-weights openai=1 --count 10

# Force API/DAS Resolve traffic.
python3 scripts/traffic_generator.py --guard-modes api_das --das-modes resolve --count 10

# Use your own demo users in X-Demo-User.
python3 scripts/traffic_generator.py --demo-users alex@example.com,sam@example.com --count 20

# Preview randomized plans without sending requests.
python3 scripts/traffic_generator.py --dry-run --count 10
```

## Learning Labs (Branch Preview)

- **Determinism Lab**
  - Purpose: estimate output consistency under repeated identical inputs.
  - Method: executes the same `/chat` payload N times (from selected trace or current form) and reports response fingerprints, block stage, status, and tool-call counts.
  - Use it for: spotting provider drift, prompt instability, or policy variability.

- **Policy Replay Comparison**
  - Purpose: compare how AI Guard policy decisions change with content normalization/redaction transforms.
  - Method: runs AI Guard checks only (IN/OUT) on selected trace content variants: `as_is`, `normalized`, `redacted`.
  - Important: does **not** call LLM providers or MCP tools again.

- **Tool Permission Profile**
  - Purpose: constrain agentic tool behavior during demos.
  - Profiles:
    - `standard`: default behavior.
    - `read_only`: blocks mutating local HTTP usage (e.g. `local_curl` POST) and external MCP tools.
    - `local_only`: allows bundled local/safe tools, blocks network-bound tools.
    - `network_open`: permissive profile for network tooling demos.

## Provider Validation Status

Tested end-to-end in this demo environment:

- Ollama (Local)
- Anthropic
- OpenAI
- LiteLLM
- Google Gemini

Present in UI but not yet fully validated end-to-end in this environment:

- AWS Bedrock
- AWS Bedrock Agent
- Google Vertex
- Perplexity
- xAI (Grok)
- Azure AI Foundry

---

## Recommended Setup (No Docker Required)

This project is designed to run directly with Python.

Recent `v1.1` update impact:

- No new external dependencies are required (`sqlite3` is Python stdlib).
- App now writes a local `usage_metrics.db` file in the repo root for usage/cost dashboard data.
- New app setting keys are optional and default-safe:
  - `APP_RATE_LIMIT_CHAT_PER_MIN=30`
  - `APP_RATE_LIMIT_ADMIN_PER_MIN=20`
  - `APP_MAX_CONCURRENT_CHAT=3`
  - `USAGE_PRICE_OVERRIDES_JSON=` (optional)

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
   - [http://127.0.0.1:5050](http://127.0.0.1:5050)

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
   - [http://127.0.0.1:5050](http://127.0.0.1:5050)

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
PORT=5050
APP_DEMO_NAME='AI Runtime Security Demo'
APP_RATE_LIMIT_CHAT_PER_MIN=30
APP_RATE_LIMIT_ADMIN_PER_MIN=20
APP_MAX_CONCURRENT_CHAT=3
USAGE_PRICE_OVERRIDES_JSON=
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

When `MCP_SERVER_COMMAND` is empty, the app automatically uses the bundled local MCP server. To test an external MCP server, set `MCP_SERVER_COMMAND` to a stdio launch command for a server you trust. The bundled server includes safe demo tools for arithmetic, time, DNS/HTTP checks, text transforms, local workspace tasks, no-key DuckDuckGo search, Wikipedia lookup, arXiv paper search, and simulated calendar event creation. Multi-agent mode uses an orchestrator that can choose bounded specialist agents (for example researcher, tool auditor, security reviewer, or domain analyst), then runs reviewer/finalizer steps so the flow stays explainable in the graph.

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
- Optional policy execution defaults:
  - `ZS_GUARDRAILS_DAS_MODE` (`resolve` or `execute`)
  - `ZS_GUARDRAILS_POLICY_ID` (required only when DAS mode is `execute`)

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
- Usage dashboard data persists in-container at `/app/usage_metrics.db` for the running app container lifecycle.
- If you want usage metrics to persist across container rebuilds/recreates, mount `/app` or a dedicated volume for `usage_metrics.db`.
- Compose binds published ports to loopback by default:
  - `127.0.0.1:5000` (app)
  - `127.0.0.1:11434` (Ollama)
- You can still edit provider keys/models via in-app Settings; values persist in `.env.local`.
- If you change settings that need restart, use the app restart prompt or run:
  - `docker compose restart app`

- updater test 2026-03-01 10:17:18
