# Local LLM Demo (Multi-Provider + Optional Zscaler AI Guard)

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
   - Ollama ([download](https://ollama.com/download))
2. Clone:
   - `git clone https://github.com/zscalerzoltanorg/local-llm-demo.git`
   - `cd local-llm-demo`
3. Bootstrap:
   - `./scripts/bootstrap_mac_linux.sh`
   - This script installs Ollama when possible, starts `ollama serve`, and pulls `llama3.2:1b`
4. Start Ollama runtime if not already running:
   - `ollama serve`
5. Run app:
   - `set -a; source .env.local; set +a`
   - `python app.py`
6. Open:
   - [http://127.0.0.1:5000](http://127.0.0.1:5000)

### Windows (PowerShell)

1. Install prerequisites:
   - Python 3.11+
   - Git for Windows
   - Ollama ([download](https://ollama.com/download))
2. Clone:
   - `git clone https://github.com/zscalerzoltanorg/local-llm-demo.git`
   - `cd local-llm-demo`
3. Bootstrap:
   - `./scripts/bootstrap_windows.ps1`
   - This script installs Ollama (via winget when available), starts `ollama serve`, and pulls `llama3.2:1b`
4. Start Ollama app/service
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

---

## Docker?

Not required.

Best path today:
- Native Python + `.env.local` + Ollama local runtime

Optional future enhancement:
- Add Docker/Compose for reproducible team onboarding
