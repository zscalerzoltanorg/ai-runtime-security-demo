import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import providers


HOST = "127.0.0.1"
PORT = 5000
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
APP_DEMO_NAME = os.getenv("APP_DEMO_NAME", "AI App Demo")


HTML = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{APP_DEMO_NAME}</title>
    <style>
      :root {{
        --bg: #f4f1ea;
        --panel: #fffdf8;
        --ink: #1f2937;
        --muted: #6b7280;
        --accent: #0f766e;
        --accent-2: #115e59;
        --border: #d6d3d1;
        --sidebar: #f8fafc;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, sans-serif;
        background:
          radial-gradient(circle at 10% 10%, #d1fae5 0%, transparent 45%),
          radial-gradient(circle at 90% 20%, #fde68a 0%, transparent 35%),
          var(--bg);
        color: var(--ink);
      }}
      .wrap {{
        width: min(96vw, 1680px);
        margin: 32px auto;
        padding: 0 12px;
      }}
      .layout {{
        display: grid;
        grid-template-columns: minmax(620px, 1fr) minmax(620px, 1fr);
        gap: 16px;
        align-items: start;
      }}
      .card {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
      }}
      .card + .card {{
        margin-top: 16px;
      }}
      .code-path-card {{
        margin-top: 26px;
      }}
      h1 {{ margin: 0 0 8px; font-size: 1.5rem; }}
      .sub {{ margin: 0 0 16px; color: var(--muted); font-size: 0.95rem; }}
      textarea {{
        width: 100%;
        min-height: 140px;
        resize: vertical;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px;
        font: inherit;
        background: #fff;
      }}
      .actions {{
        display: flex;
        gap: 10px;
        align-items: center;
        margin-top: 12px;
        flex-wrap: wrap;
      }}
      button {{
        border: none;
        background: var(--accent);
        color: white;
        padding: 10px 16px;
        border-radius: 10px;
        font-weight: 600;
        cursor: pointer;
      }}
      button:hover {{ background: var(--accent-2); }}
      button:disabled {{ opacity: 0.6; cursor: wait; }}
      .status {{ color: var(--muted); font-size: 0.9rem; }}
      .toggle-wrap {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: var(--muted);
        font-size: 0.9rem;
        user-select: none;
      }}
      .toggle-wrap input {{
        position: absolute;
        opacity: 0;
        width: 1px;
        height: 1px;
        pointer-events: none;
      }}
      .toggle-track {{
        width: 42px;
        height: 24px;
        border-radius: 999px;
        background: #d6d3d1;
        border: 1px solid #cbd5e1;
        position: relative;
        transition: background-color 160ms ease, border-color 160ms ease;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.08);
      }}
      .toggle-track::after {{
        content: "";
        position: absolute;
        top: 2px;
        left: 2px;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: #fff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.18);
        transition: transform 160ms ease;
      }}
      .toggle-wrap input:checked + .toggle-track {{
        background: #0f766e;
        border-color: #115e59;
      }}
      .toggle-wrap input:checked + .toggle-track::after {{
        transform: translateX(18px);
      }}
      .toggle-wrap input:focus-visible + .toggle-track {{
        outline: 2px solid #99f6e4;
        outline-offset: 2px;
      }}
      .toggle-label {{
        font-weight: 500;
      }}
      .response {{
        margin-top: 16px;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 14px;
        background: #fff;
        min-height: 120px;
        white-space: pre-wrap;
        line-height: 1.4;
      }}
      .conversation {{
        margin-top: 16px;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 14px;
        background: #fff;
        min-height: 120px;
        max-height: 420px;
        overflow: auto;
        display: none;
      }}
      .msg {{
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 10px 12px;
        margin-bottom: 10px;
        white-space: pre-wrap;
      }}
      .msg:last-child {{ margin-bottom: 0; }}
      .msg-user {{ background: #f0fdfa; border-color: #99f6e4; }}
      .msg-assistant {{ background: #f8fafc; border-color: #e5e7eb; }}
      .msg-role {{
        font-size: 0.75rem;
        font-weight: 700;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 6px;
      }}
      .error {{ color: #b91c1c; }}
      .sidebar {{
        background: var(--sidebar);
      }}
      .log-list {{
        display: grid;
        gap: 12px;
        max-height: 560px;
        overflow: auto;
      }}
      .log-item {{
        border: 1px solid var(--border);
        border-radius: 10px;
        background: #fff;
        padding: 10px;
      }}
      .log-title {{
        font-weight: 700;
        font-size: 0.9rem;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }}
      .badge-row {{
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }}
      .badge {{
        display: inline-block;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 0.7rem;
        font-weight: 700;
        border: 1px solid transparent;
      }}
      .badge-ai {{
        background: #ecfeff;
        color: #155e75;
        border-color: #a5f3fc;
      }}
      .badge-ollama {{
        background: #ecfdf5;
        color: #166534;
        border-color: #a7f3d0;
      }}
      .log-label {{
        font-size: 0.75rem;
        color: var(--muted);
        margin: 6px 0 4px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }}
      .code-toolbar {{
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
        margin-bottom: 10px;
      }}
      .code-toolbar button {{
        padding: 8px 12px;
      }}
      .code-toolbar button.secondary {{
        background: #e7e5e4;
        color: #1f2937;
      }}
      .code-toolbar button.secondary:hover {{
        background: #d6d3d1;
      }}
      .code-status {{
        color: var(--muted);
        font-size: 0.9rem;
      }}
      .code-panels {{
        display: grid;
        gap: 12px;
      }}
      .code-panel {{
        border: 1px solid var(--border);
        border-radius: 12px;
        background: #fff;
        overflow: hidden;
      }}
      .code-panel-head {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        padding: 10px 12px;
        border-bottom: 1px solid var(--border);
        background: #fafaf9;
      }}
      .code-panel-title {{
        font-weight: 700;
        font-size: 0.9rem;
      }}
      .code-panel-file {{
        color: var(--muted);
        font-size: 0.8rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }}
      .code-panel-body {{
        overflow: auto;
        max-height: 340px;
        background: #0b1220;
      }}
      .code-pre {{
        margin: 0;
        padding: 10px 0;
        background: #0b1220;
        color: #e5e7eb;
        font-size: 0.82rem;
        line-height: 1.45;
      }}
      .code-line {{
        display: grid;
        grid-template-columns: 48px 1fr;
        gap: 10px;
        padding: 0 12px;
        white-space: pre;
      }}
      .code-line:hover {{
        background: rgba(255, 255, 255, 0.04);
      }}
      .code-ln {{
        color: #64748b;
        text-align: right;
        user-select: none;
      }}
      .code-txt {{
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }}
      .code-empty {{
        color: #64748b;
      }}
      .code-note {{
        margin-top: 8px;
        color: var(--muted);
        font-size: 0.85rem;
      }}
      pre {{
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        background: #f8fafc;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 8px;
        font-size: 0.8rem;
        line-height: 1.35;
      }}
      @media (max-width: 900px) {{
        .layout {{
          grid-template-columns: 1fr;
        }}
        .wrap {{
          width: min(96vw, 900px);
          margin: 20px auto;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="wrap">
      <div class="layout">
        <section class="card">
          <h1>{APP_DEMO_NAME}</h1>
          <p class="sub">Local default: <strong>{OLLAMA_MODEL}</strong> (Ollama). Anthropic env model: <strong>{ANTHROPIC_MODEL}</strong></p>

          <label for="prompt" class="sub">Prompt</label>
          <textarea id="prompt" placeholder="Type a prompt, then click Send..."></textarea>

          <div class="actions">
            <button id="sendBtn" type="button">Send</button>
            <button id="clearBtn" type="button">Clear</button>
            <label class="status" for="providerSelect">LLM</label>
            <select id="providerSelect" style="border:1px solid var(--border);border-radius:10px;padding:8px 10px;background:#fff;font:inherit;">
              <option value="ollama">Ollama (Local)</option>
              <option value="anthropic">Anthropic</option>
            </select>
            <label class="toggle-wrap" for="multiTurnToggle">
              <input id="multiTurnToggle" type="checkbox" role="switch" aria-label="Toggle multi-turn chat mode" />
              <span class="toggle-track" aria-hidden="true"></span>
              <span class="toggle-label">Multi-turn Chat</span>
            </label>
            <label class="toggle-wrap" for="guardrailsToggle">
              <input id="guardrailsToggle" type="checkbox" role="switch" aria-label="Toggle Zscaler AI Guard" />
              <span class="toggle-track" aria-hidden="true"></span>
              <span class="toggle-label">Zscaler AI Guard</span>
            </label>
            <span id="status" class="status">Idle</span>
          </div>

          <div id="response" class="response">Response will appear here.</div>
          <div id="conversationView" class="conversation"></div>
        </section>

        <aside class="card sidebar">
          <h1>HTTP Trace</h1>
          <p class="sub">Shows each `/chat` request and response for demo visibility.</p>
          <div id="logList" class="log-list">
            <div class="log-item">
              <div class="log-title">No requests yet</div>
              <pre>Send a prompt to capture request/response details.</pre>
            </div>
          </div>
        </aside>
      </div>

      <section class="card code-path-card">
        <h1>Code Path Viewer</h1>
        <p class="sub">Visual snippets for the Python code paths used by this demo (before/after guardrails).</p>
        <div class="code-toolbar">
          <button id="codeAutoBtn" type="button">Auto (Follow Toggle)</button>
          <button id="codeBeforeBtn" class="secondary" type="button">Before: No Guardrails</button>
          <button id="codeAfterBtn" class="secondary" type="button">After: AI Guard</button>
          <span id="codeStatus" class="code-status">Auto mode: waiting...</span>
        </div>
        <div id="codePanels" class="code-panels"></div>
        <div class="code-note">Tip: In Auto mode, the viewer switches based on the Guardrails checkbox and the last sent request path.</div>
      </section>
    </main>

    <script>
      const codeSnippets = __CODE_SNIPPETS_JSON__;
      const sendBtn = document.getElementById("sendBtn");
      const promptEl = document.getElementById("prompt");
      const responseEl = document.getElementById("response");
      const conversationViewEl = document.getElementById("conversationView");
      const statusEl = document.getElementById("status");
      const clearBtn = document.getElementById("clearBtn");
      const logListEl = document.getElementById("logList");
      const guardrailsToggleEl = document.getElementById("guardrailsToggle");
      const providerSelectEl = document.getElementById("providerSelect");
      const multiTurnToggleEl = document.getElementById("multiTurnToggle");
      const codeAutoBtn = document.getElementById("codeAutoBtn");
      const codeBeforeBtn = document.getElementById("codeBeforeBtn");
      const codeAfterBtn = document.getElementById("codeAfterBtn");
      const codeStatusEl = document.getElementById("codeStatus");
      const codePanelsEl = document.getElementById("codePanels");

      let traceCount = 0;
      let codeViewMode = "auto";
      let lastSentGuardrailsEnabled = false;
      let lastSelectedProvider = "ollama";
      let lastChatMode = "single";
      let conversation = [];

      function pretty(obj) {{
        try {{
          return JSON.stringify(obj, null, 2);
        }} catch {{
          return String(obj);
        }}
      }}

      function providerWaitingText() {{
        const provider = (providerSelectEl.value || "ollama").toLowerCase();
        return provider === "ollama"
          ? "Waiting for local model response..."
          : "Waiting for remote model response...";
      }}

      function currentChatMode() {{
        return multiTurnToggleEl.checked ? "multi" : "single";
      }}

      function escapeHtml(value) {{
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;");
      }}

      function renderConversation() {{
        if (!conversation.length) {{
          conversationViewEl.innerHTML = '<div class="msg msg-assistant"><div class="msg-role">Conversation</div>No messages yet. Enable Multi-turn Chat and send a prompt.</div>';
          return;
        }}
        conversationViewEl.innerHTML = conversation.map((m) => {{
          const role = (m.role || "assistant").toLowerCase();
          const label = role === "user" ? "User" : "Assistant";
          const cls = role === "user" ? "msg-user" : "msg-assistant";
          return `<div class="msg ${{cls}}"><div class="msg-role">${{label}}</div>${{escapeHtml(m.content || "")}}</div>`;
        }}).join("");
        conversationViewEl.scrollTop = conversationViewEl.scrollHeight;
      }}

      function updateChatModeUI() {{
        const multi = currentChatMode() === "multi";
        responseEl.style.display = multi ? "none" : "block";
        conversationViewEl.style.display = multi ? "block" : "none";
        if (multi) {{
          renderConversation();
        }}
      }}

      function renderCodeBlock(section) {{
        const lines = String(section.code || "").replace(/\\n$/, "").split("\\n");
        const lineRows = lines.map((line, idx) => {{
          const safeLine = line.length ? escapeHtml(line) : '<span class="code-empty"> </span>';
          return `<div class="code-line"><span class="code-ln">${{idx + 1}}</span><span class="code-txt">${{safeLine}}</span></div>`;
        }}).join("");
        return `
          <div class="code-panel">
            <div class="code-panel-head">
              <div class="code-panel-title">${{escapeHtml(section.title || "Code Section")}}</div>
              <div class="code-panel-file">${{escapeHtml(section.file || "")}}</div>
            </div>
            <div class="code-panel-body">
              <pre class="code-pre">${{lineRows}}</pre>
            </div>
          </div>
        `;
      }}

      function effectiveCodeMode() {{
        const provider = providerSelectEl.value || lastSelectedProvider || "ollama";
        if (codeViewMode === "before" || codeViewMode === "after") {{
          return `${{codeViewMode}}_${{provider}}`;
        }}
        return `${{
          (guardrailsToggleEl.checked || lastSentGuardrailsEnabled) ? "after" : "before"
        }}_${{provider}}`;
      }}

      function renderCodeViewer() {{
        const mode = effectiveCodeMode();
        const spec = codeSnippets[mode];
        const chatModeSpec = (codeSnippets.chat_mode || {{}})[currentChatMode()] || {{ sections: [] }};
        if (!spec) {{
          codePanelsEl.innerHTML = "<div class='code-panel'><div class='code-panel-head'><div class='code-panel-title'>No code snippets available</div></div></div>";
          return;
        }}

        codeStatusEl.textContent = codeViewMode === "auto"
          ? `Auto mode: showing ${{
              mode.startsWith("after_") ? "AI Guard path" : "direct path"
            }} for ${{
              (providerSelectEl.value || "ollama") === "ollama" ? "Ollama (Local)" : "Anthropic"
            }} in ${{
              currentChatMode() === "multi" ? "Multi-turn Chat" : "Single-turn Chat"
            }} mode (Zscaler AI Guard toggle is ${{guardrailsToggleEl.checked ? "ON" : "OFF"}})`
          : `Manual mode: showing ${{
              mode.startsWith("after_") ? "AI Guard path" : "direct path"
            }} for ${{mode.endsWith("_anthropic") ? "Anthropic" : "Ollama (Local)"}} in ${{
              currentChatMode() === "multi" ? "Multi-turn Chat" : "Single-turn Chat"
            }} mode`;

        codeAutoBtn.classList.toggle("secondary", codeViewMode !== "auto");
        codeBeforeBtn.classList.toggle("secondary", codeViewMode !== "before");
        codeAfterBtn.classList.toggle("secondary", codeViewMode !== "after");

        const allSections = [...(spec.sections || []), ...(chatModeSpec.sections || [])];
        codePanelsEl.innerHTML = allSections.map(renderCodeBlock).join("");
      }}

      function addTrace(entry) {{
        traceCount += 1;
        if (traceCount === 1) {{
          logListEl.innerHTML = "";
        }}

        const item = document.createElement("div");
        item.className = "log-item";

        const now = new Date().toLocaleTimeString();
        const clientReq = {{
          method: "POST",
          url: `${{window.location.origin}}/chat`,
          headers: {{ "Content-Type": "application/json" }},
          payload: {{
            prompt: entry.prompt,
            provider: entry.provider || "ollama",
            chat_mode: entry.chatMode || "single",
            guardrails_enabled: !!entry.guardrailsEnabled
          }}
        }};
        if (entry.chatMode === "multi" && Array.isArray(entry.messages)) {{
          clientReq.payload.messages = entry.messages;
        }}
        const responseBodyForDisplay = entry.body && typeof entry.body === "object"
          ? JSON.parse(JSON.stringify(entry.body))
          : entry.body;
        if (responseBodyForDisplay && responseBodyForDisplay.trace && responseBodyForDisplay.trace.steps) {{
          responseBodyForDisplay.trace = {{
            ...responseBodyForDisplay.trace,
            steps: `See step-by-step trace sections below (${{
              responseBodyForDisplay.trace.steps.length
            }} step(s))`
          }};
        }}

        const clientRes = {{
          status: entry.status,
          body: responseBodyForDisplay
        }};
        const upstreamReq = entry.body && entry.body.trace ? entry.body.trace.upstream_request : null;
        const upstreamRes = entry.body && entry.body.trace ? entry.body.trace.upstream_response : null;
        const traceSteps = entry.body && entry.body.trace && Array.isArray(entry.body.trace.steps)
          ? entry.body.trace.steps
          : [];

        const traceStepsHtml = traceSteps.map((step, idx) => `
          <div class="log-title">
            <span>Step ${{idx + 1}}</span>
            <span class="badge-row">
              <span class="badge ${{
                (step.name || "").startsWith("Zscaler") ? "badge-ai" : "badge-ollama"
              }}">${{
                (step.name || "").startsWith("Zscaler")
                  ? (step.name || "AI Guard").replace("Zscaler ", "")
                  : (step.name || "Provider")
              }}</span>
            </span>
          </div>
          <div class="log-label">Step ${{idx + 1}}: ${{step.name || "Upstream"}}</div>
          <pre>${{pretty(step.request || {{}})}}</pre>
          <div class="log-label">Step ${{idx + 1}} Response</div>
          <pre>${{pretty(step.response || {{}})}}</pre>
        `).join("");

        item.innerHTML = `
          <div class="log-title">
            <span>#${{traceCount}} ${{now}}</span>
            <span class="badge-row">
              ${{traceSteps.map((step) => {{
                const isAIGuard = (step.name || "").startsWith("Zscaler");
                const label = isAIGuard
                  ? (step.name || "AI Guard").replace("Zscaler ", "")
                  : (step.name || "Provider");
                return `<span class="badge ${{isAIGuard ? "badge-ai" : "badge-ollama"}}">${{label}}</span>`;
              }}).join("")}}
            </span>
          </div>
          <div class="log-label">Request</div>
          <pre>${{pretty(clientReq)}}</pre>
          <div class="log-label">Response</div>
          <pre>${{pretty(clientRes)}}</pre>
          ${{upstreamReq ? `<div class="log-label">Upstream Request (Ollama)</div><pre>${{pretty(upstreamReq)}}</pre>` : ""}}
          ${{upstreamRes ? `<div class="log-label">Upstream Response (Ollama)</div><pre>${{pretty(upstreamRes)}}</pre>` : ""}}
          ${{traceStepsHtml}}
        `;

        logListEl.prepend(item);
      }}

      function resetTrace() {{
        traceCount = 0;
        logListEl.innerHTML = `
          <div class="log-item">
            <div class="log-title">No requests yet</div>
            <pre>Send a prompt to capture request/response details.</pre>
          </div>
        `;
      }}

      function clearViews() {{
        promptEl.value = "";
        responseEl.textContent = "Response will appear here.";
        responseEl.classList.remove("error");
        statusEl.textContent = "Idle";
        lastSentGuardrailsEnabled = guardrailsToggleEl.checked;
        lastSelectedProvider = providerSelectEl.value || "ollama";
        lastChatMode = currentChatMode();
        conversation = [];
        resetTrace();
        renderConversation();
        updateChatModeUI();
        renderCodeViewer();
      }}

      async function sendPrompt() {{
        const prompt = promptEl.value.trim();
        if (!prompt) {{
          responseEl.textContent = "Please enter a prompt.";
          responseEl.classList.add("error");
          return;
        }}

        sendBtn.disabled = true;
        statusEl.textContent = "Sending...";
        responseEl.classList.remove("error");
        responseEl.textContent = providerWaitingText();

        try {{
          lastSentGuardrailsEnabled = guardrailsToggleEl.checked;
          lastSelectedProvider = providerSelectEl.value || "ollama";
          lastChatMode = currentChatMode();
          renderCodeViewer();
          const multi = currentChatMode() === "multi";
          const pendingMessages = multi
            ? [...conversation, {{ role: "user", content: prompt }}]
            : null;
          if (multi) {{
            renderConversation();
          }}
          const res = await fetch("/chat", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              prompt,
              provider: providerSelectEl.value,
              chat_mode: currentChatMode(),
              messages: pendingMessages || undefined,
              guardrails_enabled: guardrailsToggleEl.checked
            }})
          }});
          const data = await res.json();
          addTrace({{
            prompt,
            provider: providerSelectEl.value,
            chatMode: currentChatMode(),
            messages: pendingMessages,
            guardrailsEnabled: guardrailsToggleEl.checked,
            status: res.status,
            body: data
          }});
          if (!res.ok) {{
            throw new Error(data.error || "Request failed");
          }}
          if (multi) {{
            if (Array.isArray(data.conversation)) {{
              conversation = data.conversation;
            }} else {{
              conversation = [...(pendingMessages || []), {{ role: "assistant", content: data.response || "(Empty response)" }}];
            }}
            promptEl.value = "";
            renderConversation();
          }} else {{
            responseEl.textContent = data.response || "(Empty response)";
          }}
          statusEl.textContent = "Done";
          updateChatModeUI();
          renderCodeViewer();
        }} catch (err) {{
          responseEl.textContent = err.message || String(err);
          responseEl.classList.add("error");
          statusEl.textContent = "Error";
          updateChatModeUI();
          renderCodeViewer();
        }} finally {{
          sendBtn.disabled = false;
        }}
      }}

      sendBtn.addEventListener("click", sendPrompt);
      clearBtn.addEventListener("click", clearViews);
      guardrailsToggleEl.addEventListener("change", () => {{
        if (codeViewMode === "auto") {{
          renderCodeViewer();
        }}
      }});
      providerSelectEl.addEventListener("change", () => {{
        lastSelectedProvider = providerSelectEl.value || "ollama";
        renderCodeViewer();
      }});
      multiTurnToggleEl.addEventListener("change", () => {{
        lastChatMode = currentChatMode();
        updateChatModeUI();
        renderCodeViewer();
      }});
      codeAutoBtn.addEventListener("click", () => {{
        codeViewMode = "auto";
        renderCodeViewer();
      }});
      codeBeforeBtn.addEventListener("click", () => {{
        codeViewMode = "before";
        renderCodeViewer();
      }});
      codeAfterBtn.addEventListener("click", () => {{
        codeViewMode = "after";
        renderCodeViewer();
      }});
      promptEl.addEventListener("keydown", (e) => {{
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {{
          sendPrompt();
        }}
      }});
      renderConversation();
      updateChatModeUI();
      renderCodeViewer();
    </script>
  </body>
</html>"""


CODE_SNIPPETS = {
    "before_ollama": {
        "sections": [
            {
                "title": "app.py: Provider Selection + Direct Path (Guardrails OFF)",
                "file": "app.py",
                "code": """provider_id = (data.get(\"provider\") or \"ollama\").strip().lower()
guardrails_enabled = bool(data.get(\"guardrails_enabled\"))

if guardrails_enabled:
    payload, status = guardrails.guarded_chat(prompt=prompt, llm_call=_provider_call)
    self._send_json(payload, status=status)
    return

text, meta = providers.call_provider(
    provider_id,
    prompt,
    ollama_url=OLLAMA_URL,
    ollama_model=OLLAMA_MODEL,
    anthropic_model=ANTHROPIC_MODEL,
)
self._send_json({\"response\": text, \"trace\": {\"steps\": [meta[\"trace_step\"]}}})""",
            },
            {
                "title": "providers.py: Ollama (Local) Provider",
                "file": "providers.py",
                "code": """def _ollama_generate(prompt, ollama_url, ollama_model):
    payload = {\"model\": ollama_model, \"prompt\": prompt, \"stream\": False}
    url = f\"{ollama_url}/api/generate\"
    status, body = _post_json(url, payload=payload, headers={\"Content-Type\": \"application/json\"}, timeout=120)
    text = (body.get(\"response\") or \"\").strip()
    return text, {
        \"trace_step\": {
            \"name\": \"Ollama (Local)\",
            \"request\": {\"method\": \"POST\", \"url\": url, \"payload\": payload},
            \"response\": {\"status\": status, \"body\": body},
        }
    }""",
            },
        ]
    },
    "before_anthropic": {
        "sections": [
            {
                "title": "app.py: Provider Selection + Direct Path (Guardrails OFF)",
                "file": "app.py",
                "code": """provider_id = (data.get(\"provider\") or \"ollama\").strip().lower()
text, meta = providers.call_provider(
    provider_id,
    prompt,
    ollama_url=OLLAMA_URL,
    ollama_model=OLLAMA_MODEL,
    anthropic_model=ANTHROPIC_MODEL,
)""",
            },
            {
                "title": "providers.py: Anthropic SDK Provider",
                "file": "providers.py",
                "code": """def _anthropic_generate(prompt, anthropic_model):
    from anthropic import Anthropic
    api_key = os.getenv(\"ANTHROPIC_API_KEY\", \"\")
    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=anthropic_model,
        max_tokens=400,
        temperature=0.2,
        messages=[{\"role\": \"user\", \"content\": prompt}],
    )
    text = \"\".join(block.text for block in resp.content if getattr(block, \"type\", None) == \"text\").strip()
    return text, {\"trace_step\": {\"name\": \"Anthropic\", \"request\": {\"method\": \"SDK\", \"url\": \"Anthropic SDK (messages.create)\"}}}""",
            },
        ]
    },
    "after_ollama": {
        "sections": [
            {
                "title": "app.py: Guarded Provider Call (Ollama selected)",
                "file": "app.py",
                "code": """payload, status = guardrails.guarded_chat(
    prompt=prompt,
    llm_call=lambda p: providers.call_provider(
        provider_id,
        p,
        ollama_url=OLLAMA_URL,
        ollama_model=OLLAMA_MODEL,
        anthropic_model=ANTHROPIC_MODEL,
    ),
)""",
            },
            {
                "title": "guardrails.py: Zscaler IN -> Provider -> Zscaler OUT",
                "file": "guardrails.py",
                "code": """def guarded_chat(prompt, llm_call):
    in_blocked, in_meta = _zag_check(\"IN\", prompt)
    if in_blocked:
        return {\"response\": _block_message(\"Prompt\", in_meta[\"trace_step\"][\"response\"][\"body\"])}, 200

    llm_text, llm_meta = llm_call(prompt)
    trace_steps.append(llm_meta[\"trace_step\"])

    out_blocked, out_meta = _zag_check(\"OUT\", llm_text)
    if out_blocked:
        return {\"response\": _block_message(\"Response\", out_meta[\"trace_step\"][\"response\"][\"body\"])}, 200""",
            },
            {
                "title": "providers.py: Ollama (Local) Upstream Step",
                "file": "providers.py",
                "code": """return text, {
    \"trace_step\": {
        \"name\": \"Ollama (Local)\",
        \"request\": {\"method\": \"POST\", \"url\": f\"{ollama_url}/api/generate\", \"payload\": payload},
        \"response\": {\"status\": status, \"body\": body},
    }
}""",
            },
        ]
    },
    "after_anthropic": {
        "sections": [
            {
                "title": "app.py: Guarded Provider Call (Anthropic selected)",
                "file": "app.py",
                "code": """payload, status = guardrails.guarded_chat(
    prompt=prompt,
    llm_call=lambda p: providers.call_provider(
        provider_id,  # \"anthropic\"
        p,
        ollama_url=OLLAMA_URL,
        ollama_model=OLLAMA_MODEL,
        anthropic_model=ANTHROPIC_MODEL,
    ),
)""",
            },
            {
                "title": "guardrails.py: Shared Zscaler Wrapper (Provider-Agnostic)",
                "file": "guardrails.py",
                "code": """# Same wrapper flow regardless of LLM provider:
# 1) _zag_check(\"IN\", prompt)
# 2) llm_call(prompt)   <- Ollama or Anthropic
# 3) _zag_check(\"OUT\", llm_text)
# 4) return response + trace.steps""",
            },
            {
                "title": "providers.py: Anthropic SDK Upstream Step",
                "file": "providers.py",
                "code": """trace_request = {
    \"method\": \"SDK\",
    \"url\": \"Anthropic SDK (messages.create)\",
    \"headers\": {\"x-api-key\": \"***redacted***\"},
    \"payload\": request_payload,
}
# Response trace stores normalized metadata + generated text""",
            },
        ]
    },
    "chat_mode": {
        "single": {
            "sections": [
                {
                    "title": "app.py: Single-turn Mode Request Shape",
                    "file": "app.py",
                    "code": """# Client sends one prompt per request
{
  \"prompt\": prompt,
  \"provider\": selectedProvider,
  \"chat_mode\": \"single\",
  \"guardrails_enabled\": toggleState
}

# Server builds one-message context:
messages_for_provider = [{\"role\": \"user\", \"content\": prompt}]""",
                }
            ]
        },
        "multi": {
            "sections": [
                {
                    "title": "app.py: Multi-turn Mode (Provider-Agnostic Conversation State)",
                    "file": "app.py",
                    "code": """# Browser keeps conversation state (in-memory UI state)
pendingMessages = [...conversation, {\"role\": \"user\", \"content\": prompt}]

# Request includes normalized message history
{
  \"prompt\": prompt,           # latest user turn (for guardrails IN)
  \"provider\": selectedProvider,
  \"chat_mode\": \"multi\",
  \"messages\": pendingMessages,
  \"guardrails_enabled\": toggleState
}""",
                },
                {
                    "title": "app.py / providers.py: Multi-turn Provider Dispatch",
                    "file": "app.py + providers.py",
                    "code": """# app.py routes by provider without provider-specific UI logic
text, meta = providers.call_provider_messages(provider_id, messages_for_provider, ...)

# providers.py implements per-provider message formatting:
# - Ollama (Local): /api/chat with messages[]
# - Anthropic SDK: messages.create(messages=[...])
# Future providers (Bedrock, LiteLLM proxy, etc.) can plug into the same interface.""",
                },
            ]
        },
    },
}


def _script_safe_json(value: object) -> str:
    return json.dumps(value).replace("</", "<\\/")


def _normalize_client_messages(messages: object) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if not isinstance(messages, list):
        return normalized
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        content = str(msg.get("content") or "")
        if role in {"user", "assistant"}:
            normalized.append({"role": role, "content": content})
    return normalized


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_html(
                HTML.replace("__CODE_SNIPPETS_JSON__", _script_safe_json(CODE_SNIPPETS))
            )
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/chat":
            self._send_json({"error": "Not found"}, status=404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        try:
            data = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, status=400)
            return

        prompt = (data.get("prompt") or "").strip()
        provider_id = (data.get("provider") or "ollama").strip().lower()
        chat_mode = "multi" if str(data.get("chat_mode") or "").lower() == "multi" else "single"
        guardrails_enabled = bool(data.get("guardrails_enabled"))
        if not prompt:
            self._send_json({"error": "Prompt is required."}, status=400)
            return

        if chat_mode == "multi":
            messages_for_provider = _normalize_client_messages(data.get("messages"))
            if (
                not messages_for_provider
                or messages_for_provider[-1].get("role") != "user"
                or messages_for_provider[-1].get("content") != prompt
            ):
                messages_for_provider.append({"role": "user", "content": prompt})
        else:
            messages_for_provider = [{"role": "user", "content": prompt}]

        if guardrails_enabled:
            try:
                import guardrails
                payload, status = guardrails.guarded_chat(
                    prompt=prompt,
                    llm_call=lambda p: providers.call_provider_messages(
                        provider_id,
                        messages_for_provider,
                        ollama_url=OLLAMA_URL,
                        ollama_model=OLLAMA_MODEL,
                        anthropic_model=ANTHROPIC_MODEL,
                    ),
                )
            except Exception as exc:
                self._send_json(
                    {
                        "error": "Guardrails module failed.",
                        "details": str(exc),
                    },
                    status=500,
                )
                return

            if chat_mode == "multi" and status == 200 and payload.get("response"):
                payload["conversation"] = messages_for_provider + [
                    {"role": "assistant", "content": str(payload.get("response") or "")}
                ]
            self._send_json(payload, status=status)
            return

        text, meta = providers.call_provider_messages(
            provider_id,
            messages_for_provider,
            ollama_url=OLLAMA_URL,
            ollama_model=OLLAMA_MODEL,
            anthropic_model=ANTHROPIC_MODEL,
        )
        if text is None:
            self._send_json(
                {
                    "error": meta.get("error", "Provider request failed."),
                    "details": meta.get("details"),
                    "trace": {"steps": [meta.get("trace_step", {})]},
                },
                status=int(meta.get("status_code", 502)),
            )
            return

        payload = {"response": text, "trace": {"steps": [meta["trace_step"]]}}
        if chat_mode == "multi":
            payload["conversation"] = messages_for_provider + [
                {"role": "assistant", "content": str(text or "")}
            ]
        self._send_json(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Serving demo app at http://{HOST}:{PORT}")
    print(f"Using Ollama model: {OLLAMA_MODEL}")
    print(f"Ollama base URL: {OLLAMA_URL}")
    print(f"Anthropic model (env default): {ANTHROPIC_MODEL}")
    print("Guardrails toggle default: OFF (per-request in UI)")
    server.serve_forever()


if __name__ == "__main__":
    main()
