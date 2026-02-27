# AI Runtime Security Demo

Local demo web app for testing LLM providers, Zscaler AI Guard (DAS/API + Proxy), agentic/multi-agent workflows, MCP/tools, and rich traces.

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
   - `set -a; source .env.local; set +a`
   - `python app.py`
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
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:1b
MCP_SERVER_COMMAND=
MCP_TIMEOUT_SECONDS=15
MCP_PROTOCOL_VERSION=2024-11-05
MAX_REQUEST_BYTES=1000000
```

When `MCP_SERVER_COMMAND` is empty, the app automatically uses the bundled local MCP server.

---

## Optional Provider Credentials (Set Only If Needed)

- Anthropic: `ANTHROPIC_API_KEY`
- OpenAI: `OPENAI_API_KEY`
- LiteLLM: `LITELLM_API_KEY`, `LITELLM_BASE_URL`
- Bedrock: AWS auth + optional `AWS_REGION`, plus agent IDs for Bedrock Agent
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
- `ZS_PROXY_API_KEY` (or provider-specific keys)
- Optional provider-specific proxy keys:
  - `ANTHROPIC_ZS_PROXY_API_KEY`
  - `OPENAI_ZS_PROXY_API_KEY`
  - `LITELLM_ZS_PROXY_API_KEY`
  - `BEDROCK_INVOKE_ZS_PROXY_API_KEY`
  - `BEDROCK_AGENT_ZS_PROXY_API_KEY`
  - `PERPLEXITY_ZS_PROXY_API_KEY`
  - `XAI_ZS_PROXY_API_KEY`
  - `GEMINI_ZS_PROXY_API_KEY`
  - `VERTEX_ZS_PROXY_API_KEY`
  - `AZURE_FOUNDRY_ZS_PROXY_API_KEY`

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
