# Local LLM Demo (Python stdlib + Ollama + Optional Zscaler AI Guard)

Very small demo app for local testing and live demos.

## What this demo shows

- Local web chat UI (`python app.py`)
- Local LLM inference via Ollama (`llama3.2:1b` by default)
- Optional Zscaler AI Guard checks with a UI toggle (`Guardrails` ON/OFF)
- HTTP trace sidebar showing request/response payloads (including upstream calls)

## Quick start

1. Start Ollama:
   - `ollama serve`
2. Pull a small model (once):
   - `ollama pull llama3.2:1b`
3. Run app:
   - `python app.py`
4. Open:
   - `http://127.0.0.1:5000`

## UI Features

- `Send`: submits prompt to `/chat`
- `Clear`: clears prompt, response, status, and HTTP trace sidebar
- `Guardrails` toggle (default OFF): enables/disables Zscaler AI Guard flow per request
- `HTTP Trace` panel:
  - Client request to `/chat`
  - Client response from the app
  - Upstream calls (Ollama and, when enabled, Zscaler AI Guard IN/OUT checks)

## Optional Zscaler AI Guardrails (toggleable in UI)

The app includes a `Guardrails` checkbox (default: OFF). When enabled, each chat request uses this flow:

1. Zscaler AI Guard `IN` check (prompt)
2. Ollama local generation
3. Zscaler AI Guard `OUT` check (response)

If Zscaler blocks the prompt or response, the app returns a blocked message.

This demo app is configured to use the Zscaler Resolve Policy endpoint (not a specific Policy ID in the request payload):

- `https://api.zseclipse.net/v1/detection/resolve-and-execute-policy`

### Local env vars (recommended for labs)

- `ZS_GUARDRAILS_API_KEY` (required when using Guardrails toggle ON)
- `ZS_GUARDRAILS_URL` (default: `https://api.zseclipse.net/v1/detection/resolve-and-execute-policy`)
- `ZS_GUARDRAILS_TIMEOUT_SECONDS` (default: `15`)

Example (zsh/bash):

- `export ZS_GUARDRAILS_API_KEY='your_local_key_here'`
- `export ZS_GUARDRAILS_URL='https://api.zseclipse.net/v1/detection/resolve-and-execute-policy'` (optional; default shown)
- `python app.py`

If the API key is not set and `Guardrails` is ON, the app will return a clear error and show the attempted Zscaler request in the HTTP trace panel.

## Zscaler Console Setup (DAS/API Mode)

In Zscaler AI Guard, make sure you have done the following while in DAS/API Mode in the console:

1. Created the App (for example, `Local LLM`)
2. Created the API Key tied to the App (you will use this for `ZS_GUARDRAILS_API_KEY`)
3. Created a Policy Configuration with at least one detector
4. Created a Policy Control tied to the Policy Configuration with criteria for the App/Credentials you set

## Optional env vars

- `OLLAMA_MODEL` (default: `llama3.2:1b`)
- `OLLAMA_URL` (default: `http://127.0.0.1:11434`)
