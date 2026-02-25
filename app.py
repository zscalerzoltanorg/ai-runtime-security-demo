import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib import error, request


HOST = "127.0.0.1"
PORT = 5000
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")


HTML = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Local LLM Demo</title>
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
        max-width: 1180px;
        margin: 48px auto;
        padding: 0 16px;
      }}
      .layout {{
        display: grid;
        grid-template-columns: 1.2fr 0.8fr;
        gap: 16px;
      }}
      .card {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
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
      }}
      .log-label {{
        font-size: 0.75rem;
        color: var(--muted);
        margin: 6px 0 4px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
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
      }}
    </style>
  </head>
  <body>
    <main class="wrap">
      <div class="layout">
        <section class="card">
          <h1>Local LLM Chat Demo</h1>
          <p class="sub">Model: <strong>{OLLAMA_MODEL}</strong> (via local Ollama)</p>

          <label for="prompt" class="sub">Prompt</label>
          <textarea id="prompt" placeholder="Type a prompt, then click Send..."></textarea>

          <div class="actions">
            <button id="sendBtn" type="button">Send</button>
            <button id="clearBtn" type="button">Clear</button>
            <label class="status" style="display:flex;align-items:center;gap:6px;">
              <input id="guardrailsToggle" type="checkbox" />
              Guardrails
            </label>
            <span id="status" class="status">Idle</span>
          </div>

          <div id="response" class="response">Response will appear here.</div>
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
    </main>

    <script>
      const sendBtn = document.getElementById("sendBtn");
      const promptEl = document.getElementById("prompt");
      const responseEl = document.getElementById("response");
      const statusEl = document.getElementById("status");
      const clearBtn = document.getElementById("clearBtn");
      const logListEl = document.getElementById("logList");
      const guardrailsToggleEl = document.getElementById("guardrailsToggle");

      let traceCount = 0;

      function pretty(obj) {{
        try {{
          return JSON.stringify(obj, null, 2);
        }} catch {{
          return String(obj);
        }}
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
          payload: {{ prompt: entry.prompt, guardrails_enabled: !!entry.guardrailsEnabled }}
        }};
        const clientRes = {{
          status: entry.status,
          body: entry.body
        }};
        const upstreamReq = entry.body && entry.body.trace ? entry.body.trace.upstream_request : null;
        const upstreamRes = entry.body && entry.body.trace ? entry.body.trace.upstream_response : null;
        const traceSteps = entry.body && entry.body.trace && Array.isArray(entry.body.trace.steps)
          ? entry.body.trace.steps
          : [];

        const traceStepsHtml = traceSteps.map((step, idx) => `
          <div class="log-label">Step ${{idx + 1}}: ${{step.name || "Upstream"}}</div>
          <pre>${{pretty(step.request || {{}})}}</pre>
          <div class="log-label">Step ${{idx + 1}} Response</div>
          <pre>${{pretty(step.response || {{}})}}</pre>
        `).join("");

        item.innerHTML = `
          <div class="log-title">#${{traceCount}} ${{now}}</div>
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
        resetTrace();
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
        responseEl.textContent = "Waiting for local model response...";

        try {{
          const res = await fetch("/chat", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              prompt,
              guardrails_enabled: guardrailsToggleEl.checked
            }})
          }});
          const data = await res.json();
          addTrace({{
            prompt,
            guardrailsEnabled: guardrailsToggleEl.checked,
            status: res.status,
            body: data
          }});
          if (!res.ok) {{
            throw new Error(data.error || "Request failed");
          }}
          responseEl.textContent = data.response || "(Empty response)";
          statusEl.textContent = "Done";
        }} catch (err) {{
          responseEl.textContent = err.message || String(err);
          responseEl.classList.add("error");
          statusEl.textContent = "Error";
        }} finally {{
          sendBtn.disabled = false;
        }}
      }}

      sendBtn.addEventListener("click", sendPrompt);
      clearBtn.addEventListener("click", clearViews);
      promptEl.addEventListener("keydown", (e) => {{
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {{
          sendPrompt();
        }}
      }});
    </script>
  </body>
</html>"""


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
            self._send_html(HTML)
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
        guardrails_enabled = bool(data.get("guardrails_enabled"))
        if not prompt:
            self._send_json({"error": "Prompt is required."}, status=400)
            return

        if guardrails_enabled:
            try:
                import guardrails

                payload, status = guardrails.guarded_ollama_chat(
                    prompt=prompt,
                    ollama_url=OLLAMA_URL,
                    ollama_model=OLLAMA_MODEL,
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

            self._send_json(payload, status=status)
            return

        ollama_request_json = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
        ollama_payload = json.dumps(ollama_request_json).encode("utf-8")
        req = request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=ollama_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=120) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self._send_json(
                {
                    "error": "Ollama request failed.",
                    "status_code": exc.code,
                    "details": detail,
                    "trace": {
                        "upstream_request": {
                            "method": "POST",
                            "url": f"{OLLAMA_URL}/api/generate",
                            "headers": {"Content-Type": "application/json"},
                            "payload": ollama_request_json,
                        },
                        "upstream_response": {
                            "status": exc.code,
                            "body": detail,
                        },
                    },
                },
                status=502,
            )
            return
        except Exception as exc:
            self._send_json(
                {
                    "error": "Could not reach local Ollama server.",
                    "details": str(exc),
                    "ollama_url": OLLAMA_URL,
                    "trace": {
                        "upstream_request": {
                            "method": "POST",
                            "url": f"{OLLAMA_URL}/api/generate",
                            "headers": {"Content-Type": "application/json"},
                            "payload": ollama_request_json,
                        }
                    },
                },
                status=502,
            )
            return

        self._send_json(
            {
                "response": (response_data.get("response") or "").strip(),
                "trace": {
                    "upstream_request": {
                        "method": "POST",
                        "url": f"{OLLAMA_URL}/api/generate",
                        "headers": {"Content-Type": "application/json"},
                        "payload": ollama_request_json,
                    },
                    "upstream_response": {
                        "status": 200,
                        "body": response_data,
                    },
                },
            }
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Serving demo app at http://{HOST}:{PORT}")
    print(f"Using Ollama model: {OLLAMA_MODEL}")
    print(f"Ollama base URL: {OLLAMA_URL}")
    print("Guardrails toggle default: OFF (per-request in UI)")
    server.serve_forever()


if __name__ == "__main__":
    main()
