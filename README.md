# Local LLM Demo (Ollama Local / Anthropic + Optional Zscaler AI Guard)

Very small demo app for local testing and live demos.

## What this demo shows

- Local web chat UI (`python app.py`)
- Multi-provider LLM selector (`Ollama (Local)` default, plus `Anthropic`)
- Single-turn / Multi-turn chat mode toggle (provider-agnostic)
- Optional Zscaler AI Guard checks with a UI toggle (`Guardrails` ON/OFF)
- HTTP trace sidebar showing request/response payloads (including upstream calls)
- Code Path Viewer (before/after guardrails, auto follows toggle/provider)

## Quick start

1. Start Ollama:
   - `ollama serve`
2. Pull a small model (once):
   - `ollama pull llama3.2:1b`
3. Run app:
   - `python app.py`
4. Open:
   - `http://127.0.0.1:5000`

## Optional Anthropic Provider (SDK)

The app supports `Anthropic` as a selectable LLM provider in the UI.

Requirements:

- Install the SDK in your environment:
  - `pip install anthropic`
- Set your API key:
  - `export ANTHROPIC_API_KEY='your_key_here'`

Optional:

- `export ANTHROPIC_MODEL='claude-sonnet-4-5-20250929'`

Notes:

- `Ollama (Local)` remains the default provider
- If Anthropic SDK or API key is missing and you select `Anthropic`, the app returns a clear error and shows the provider trace in `HTTP Trace`

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
- `Clear`: clears prompt, response, status, HTTP trace, and code path viewer state (but keeps the selected LLM provider)
- `LLM` dropdown: choose `Ollama (Local)` or `Anthropic`
- `Multi-turn Chat` toggle:
  - OFF (default): single-turn prompt/response
  - ON: chat transcript mode with conversation history sent to the selected provider
- `Zscaler AI Guard` toggle (default OFF): enables/disables Zscaler AI Guard flow per request
- `HTTP Trace` panel:
  - Client request to `/chat`
  - Client response from the app
  - Upstream calls (selected provider and, when enabled, Zscaler AI Guard IN/OUT checks)
- `Code Path Viewer`:
  - Shows provider-aware before/after code paths
  - Auto mode follows selected provider, chat mode, and Zscaler AI Guard toggle state

## App Name (optional)

You can customize the browser/app title shown in the UI with an env var:

- `export APP_DEMO_NAME='My AI Demo App'`

If not set, the app defaults to:

- `AI App Demo`

## Optional Zscaler AI Guardrails (toggleable in UI)

The app includes a `Zscaler AI Guard` toggle (default: OFF). When enabled, each chat request uses this flow:

1. Zscaler AI Guard `IN` check (prompt)
2. Selected LLM provider generation (`Ollama (Local)` or `Anthropic`)
3. Zscaler AI Guard `OUT` check (response)

If Zscaler blocks the prompt or response, the app returns a blocked message.

In multi-turn mode, the guardrails flow remains the same but is applied per turn:

1. `IN` check on the latest user message
2. Selected provider is called with conversation history (`messages`)
3. `OUT` check on the generated assistant response

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
- `ANTHROPIC_API_KEY` (required only when `Anthropic` provider is selected)
- `ANTHROPIC_MODEL` (default: `claude-sonnet-4-5-20250929`)
- `APP_DEMO_NAME` (default: `AI App Demo`)
