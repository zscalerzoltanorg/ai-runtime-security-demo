# Release Notes

Historical release notes for AI Runtime Security Demo. The README keeps only the latest three versions; older entries move here.

## Historical Releases

- `v1.5.27`
  - Expanded Traffic Automation prompt breadth beyond code-heavy tests, with more legal, finance, prompt-injection/jailbreak, PII, secrets, brand, multilingual, off-topic, URL, and response-detector scenarios. Added synthetic text-file attachment attempts so generated traffic can exercise prompts plus uploaded support tickets, contracts, CSVs, logs, and policy snippets.

- `v1.5.26`
  - Clarified Traffic Automation in the UI and release notes. Traffic Automation is the local background smoke-test/log-filler that sends synthetic `/chat` conversations through configured providers, users, AI Guard Proxy/API-DAS modes, agent/MCP/tool options, and detector-oriented prompts so demos can generate realistic AI Guard activity on demand.

- `v1.5.25`
  - Moved Traffic Automation out of the main chat path into a collapsed section below the composer so it stays available without being front and center.

- `v1.5.23`
  - Added local web UI controls to start, stop, and configure the background traffic automation, defaulting to the high-volume burst recipe.

- `v1.5.22`
  - Added low-weight Anthropic traffic to the high-volume burst wrapper.

- `v1.5.21`
  - Added a high-volume `scripts/traffic_burst.py` wrapper for the tested AI Guard log-filler traffic mix, while still allowing extra command-line overrides.

- `v1.5.20`
  - Improved background traffic generation with balanced detector-family coverage, response-detector prompts that can pass IN checks but trip OUT checks, duration-based runs, and randomized longer pauses for more natural traffic waves.

- `v1.5.19`
  - Expanded background traffic prompts across AI Guard detector families and added optional parallel conversation execution with unique conversation IDs.

- `v1.5.18`
  - Made the background traffic generator infer configured providers from the running app settings by default, including direct and proxy keys, while keeping Anthropic opt-in.

- `v1.5.17`
  - Improved the background traffic generator with clearer proxy/API-DAS labels, balanced Resolve/Execute defaults, tunable guard-mode weights, named demo-user rotation, and an end-of-run mix summary.

- `v1.5.16`
  - Added a standalone background traffic generator for randomized AI Guard demo traffic across providers, DAS/API vs proxy, response modes, agentic/tool settings, and multi-turn prompts.

- `v1.5.15`
  - Fixed Zscaler AI Guard DAS/API request payloads to send the live API's accepted direction values (`IN`/`OUT`) for both Resolve and Execute modes.

- `v1.5.14`
  - Aligned Zscaler AI Guard DAS/API direction payloads with current docs and added clearer 401 guidance for DAS/API key mismatches.
  - Updated proxy-mode OpenAI, Anthropic, and Gemini calls to use documented direct AI Guard proxy HTTP endpoints so prompt/response content is visible to AI Guard inspection.

- `v1.5.13`
  - Marked Google Gemini as validated end-to-end in this demo environment after successful testing.

- `v1.5.12`
  - Added a first-time Setup Wizard that explains common provider keys, Zscaler AI Guard modes, local Ollama setup, and MCP/tool configuration before users start demos.
  - Added capability-aware response mode controls with visible JSON, NDJSON stream (`/chat/stream`), SSE (`/chat/sse`), WebSocket, protobuf/gRPC, and protocol-trace demos; unsupported modes are disabled by provider and active runtime settings.
  - Fixed Stream/SSE browser parsing so streaming responses render incrementally without freezing the UI.

- `v1.5.11`
  - Added six realistic agent demo recipes to the Demo Wizard: enterprise workflow, developer assistant, security analyst, IT helpdesk, research/planning, and MCP-enabled chatbot.

- `v1.5.10`
  - Added a Demo Wizard with guided recipes for baseline chat, AI Guard API/DAS, AI Guard Proxy, agentic tools, multi-agent research, and local workspace tasks.
  - Expanded the bundled MCP demo toolset with no-key DuckDuckGo search, Wikipedia lookup, arXiv search, and simulated calendar creation, plus clearer agent role summaries.

- `v1.5.9`
  - Fixed Docker deployment behavior so Local Settings persist through a mounted `.env.local` file and usage data is stored in a persistent Docker volume.
  - Clarified Docker upgrade behavior: in-app update is disabled in containers, and Docker users should update with `git pull` followed by `docker compose up -d --build`.

- `v1.5.8`
  - Added configurable request timeout settings for both the app chat flow and Zscaler AI Guard DAS/API checks to help avoid false timeout failures on slower local runs.
  - Improved local Ollama model selection with installed/not-installed validation plus clearer setup guidance when switching to a model that has not been pulled yet.

- `v1.5.7`
  - Fixed Zscaler AI Guard Proxy-mode blocked requests so the app now returns the same formatted assistant block message as DAS/API mode instead of falling through to a generic `Failed to fetch` error.

- `v1.5.6`
  - Improved Flow Graph clarity with persistent label legend and edge hover tooltips explaining request/return branch labels (`2a/2b/2c`, `r2a/r2b/r2c`).
  - Polished Settings UX with collapsible provider sections by default, clearer secret visibility controls, and improved save/restart feedback behavior.
  - Added stability fixes for provider model handling and guardrail-related UI behavior.

- `v1.5.5`
  - Fixed model-setting hardening so invalid boolean-like values (for example `yes`/`no`/`true`/`false`) no longer become active provider model IDs and now safely fall back to valid defaults.
  - Fixed version badge/update display behavior so the app consistently shows a version-style identifier (tag or tag+sha) instead of only a build label when running non-exact-tag commits.
  - Fixed updater git sync to fetch tags during update checks/applies so release badge/tag visibility stays consistent after in-app updates.

- `v1.5.2`
  - Zscaler AI Guard API/DAS mode now supports two policy endpoints directly in the chat UI:
    - `Resolve`: automatically resolves and executes the matching configured policy.
    - `Execute`: sends checks to `execute-policy` for the exact `Policy ID` entered.

- `v1.5.1`
  - Added a new latency analysis workflow across Flow Graph and Latency Bench, including per-hop timing labels, an in-graph end-to-end summary (total/app/provider/AI Guard), clearer fixed-order mode comparisons (Baseline, Proxy, API/DAS), explicit Zscaler-vs-baseline deltas, and cleaner handling of unsupported proxy modes with transparent `unknown` attribution when exact timing cannot be measured.

- `v1.5`
  - App now checks GitHub for updates and supports in-app one-click update (with local-settings preservation).
  - Added dynamic provider model catalog (startup + cached refresh) and manual `Refresh Models` in Settings.
  - Improved model selection UX with editable suggested-model picklists and better provider config guidance.
  - Enhanced Usage Dashboard with estimated cost + utilization visibility and additional UI/UX polish.

- `v1.1.1`
  - Expanded adversarial Prompt Presets with attachable samples and auto multi-turn attack sequences.
  - Added multimodal attack examples (benign vs adversarial image samples) using provider-compatible attachments.
  - Added a persistent Usage Dashboard for requests, tokens, estimated cost, and provider-level trends.
  - Applied security hardening and repo hygiene updates (local-only sample loading controls, runtime DB ignored from git).
