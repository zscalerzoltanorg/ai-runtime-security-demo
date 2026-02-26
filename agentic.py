import json
import os
import re
from typing import Callable
from urllib import error, parse, request


BRAVE_SEARCH_BASE_URL = os.getenv("BRAVE_SEARCH_BASE_URL", "https://api.search.brave.com")
BRAVE_SEARCH_MAX_RESULTS = int(os.getenv("BRAVE_SEARCH_MAX_RESULTS", "5"))
AGENTIC_MAX_STEPS = int(os.getenv("AGENTIC_MAX_STEPS", "3"))


TOOLS = {
    "calculator": {
        "description": "Evaluate a simple arithmetic expression (numbers, + - * / parentheses).",
        "input_schema": {"expression": "string"},
    },
    "weather": {
        "description": "Get current weather and short forecast for a location.",
        "input_schema": {"location": "string"},
    },
    "web_fetch": {
        "description": "Fetch the text content of a specific URL.",
        "input_schema": {"url": "string"},
    },
    "brave_search": {
        "description": "Search the web via Brave Search API and return top results (requires BRAVE_SEARCH_API_KEY).",
        "input_schema": {"query": "string"},
    },
}


def _tool_catalog_text() -> str:
    rows = []
    for name, meta in TOOLS.items():
        rows.append(f"- {name}: {meta['description']} input={json.dumps(meta['input_schema'])}")
    return "\n".join(rows)


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _safe_eval_expr(expr: str) -> str:
    expr = (expr or "").strip()
    if not expr:
        return "Error: expression is required."
    if not re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s]+", expr):
        return "Error: only basic arithmetic is allowed."
    try:
        result = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 - constrained input regex
    except Exception as exc:
        return f"Error: {exc}"
    return str(result)


def _http_get(url: str, headers: dict | None = None, timeout: float = 15.0) -> tuple[int, str]:
    req = request.Request(url, headers=headers or {}, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body


def _tool_weather(args: dict) -> tuple[str, dict]:
    location = str((args or {}).get("location") or "").strip()
    if not location:
        return "Error: weather tool requires `location`.", {"tool": "weather", "input": args, "error": "missing location"}

    encoded = parse.quote(location)
    url = f"https://wttr.in/{encoded}?format=j1"
    try:
        status, body = _http_get(url)
        data = json.loads(body)
    except Exception as exc:
        return f"Error: weather lookup failed: {exc}", {"tool": "weather", "input": args, "error": str(exc)}

    current = (data.get("current_condition") or [{}])[0]
    weather_days = data.get("weather") or []
    today = weather_days[0] if weather_days else {}
    summary = {
        "location": location,
        "tempC": current.get("temp_C"),
        "tempF": current.get("temp_F"),
        "condition": ((current.get("weatherDesc") or [{}])[0]).get("value"),
        "humidity": current.get("humidity"),
        "windspeedKmph": current.get("windspeedKmph"),
        "todayMaxC": today.get("maxtempC"),
        "todayMinC": today.get("mintempC"),
    }
    return json.dumps(summary), {
        "tool": "weather",
        "input": args,
        "request": {"method": "GET", "url": url},
        "response": {"status": status, "body": summary},
    }


def _tool_web_fetch(args: dict) -> tuple[str, dict]:
    url = str((args or {}).get("url") or "").strip()
    if not url:
        return "Error: web_fetch tool requires `url`.", {"tool": "web_fetch", "input": args, "error": "missing url"}
    if not url.startswith(("http://", "https://")):
        return "Error: web_fetch only supports http/https URLs.", {"tool": "web_fetch", "input": args, "error": "invalid scheme"}

    try:
        status, body = _http_get(url, headers={"User-Agent": "LocalLLMDemo/1.0"}, timeout=20.0)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"Error: web_fetch HTTP {exc.code}", {
            "tool": "web_fetch",
            "input": args,
            "request": {"method": "GET", "url": url},
            "response": {"status": exc.code, "body": detail[:1000]},
        }
    except Exception as exc:
        return f"Error: web_fetch failed: {exc}", {
            "tool": "web_fetch",
            "input": args,
            "request": {"method": "GET", "url": url},
            "error": str(exc),
        }

    text = re.sub(r"<script[\s\S]*?</script>", " ", body, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    snippet = text[:4000]
    return snippet or "(empty body)", {
        "tool": "web_fetch",
        "input": args,
        "request": {"method": "GET", "url": url},
        "response": {"status": status, "body_preview": snippet[:800]},
    }


def _tool_brave_search(args: dict) -> tuple[str, dict]:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    query = str((args or {}).get("query") or "").strip()
    if not query:
        return "Error: brave_search tool requires `query`.", {"tool": "brave_search", "input": args, "error": "missing query"}
    if not api_key:
        return "Error: BRAVE_SEARCH_API_KEY is not set.", {"tool": "brave_search", "input": args, "error": "missing BRAVE_SEARCH_API_KEY"}

    url = (
        f"{BRAVE_SEARCH_BASE_URL}/res/v1/web/search?"
        f"q={parse.quote(query)}&count={BRAVE_SEARCH_MAX_RESULTS}"
    )
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    try:
        status, body = _http_get(url, headers=headers, timeout=15.0)
        data = json.loads(body)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"Error: Brave Search HTTP {exc.code}", {
            "tool": "brave_search",
            "input": args,
            "request": {"method": "GET", "url": url, "headers": {"X-Subscription-Token": "***redacted***"}},
            "response": {"status": exc.code, "body": detail[:1000]},
        }
    except Exception as exc:
        return f"Error: Brave Search failed: {exc}", {
            "tool": "brave_search",
            "input": args,
            "request": {"method": "GET", "url": url, "headers": {"X-Subscription-Token": "***redacted***"}},
            "error": str(exc),
        }

    results = []
    for item in (((data or {}).get("web") or {}).get("results") or [])[:BRAVE_SEARCH_MAX_RESULTS]:
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "description": item.get("description"),
            }
        )
    payload = {"query": query, "results": results}
    return json.dumps(payload), {
        "tool": "brave_search",
        "input": args,
        "request": {"method": "GET", "url": url, "headers": {"X-Subscription-Token": "***redacted***"}},
        "response": {"status": status, "body": payload},
    }


def _tool_calculator(args: dict) -> tuple[str, dict]:
    expr = str((args or {}).get("expression") or "")
    result = _safe_eval_expr(expr)
    return result, {"tool": "calculator", "input": args, "response": {"result": result}}


def run_tool(tool_name: str, tool_input: dict) -> tuple[str, dict]:
    tool = (tool_name or "").strip()
    if tool == "calculator":
        return _tool_calculator(tool_input)
    if tool == "weather":
        return _tool_weather(tool_input)
    if tool == "web_fetch":
        return _tool_web_fetch(tool_input)
    if tool == "brave_search":
        return _tool_brave_search(tool_input)
    return (
        f"Error: unknown tool `{tool}`",
        {"tool": tool, "input": tool_input, "error": "unknown tool"},
    )


def run_agentic_turn(
    *,
    conversation_messages: list[dict],
    provider_messages_call: Callable[[list[dict]], tuple[str | None, dict]],
    tools_enabled: bool,
) -> tuple[dict, int]:
    agent_trace: list[dict] = []
    work_messages = list(conversation_messages)

    system_prompt = (
        "You are a helpful agent. "
        "When tools are enabled and useful, decide whether to call a tool.\n"
        "Return ONLY JSON in one of these shapes:\n"
        '{"type":"final","response":"..."}\n'
        '{"type":"tool","tool":"calculator","input":{"expression":"2+2"}}\n'
        "Available tools:\n"
        + _tool_catalog_text()
        + "\nIf tools are disabled, always return type=final."
    )

    llm_messages = [{"role": "system", "content": system_prompt}, *work_messages]

    for step in range(1, AGENTIC_MAX_STEPS + 1):
        llm_text, llm_meta = provider_messages_call(llm_messages)
        agent_trace.append(
            {
                "kind": "llm",
                "step": step,
                "trace_step": llm_meta.get("trace_step"),
                "raw_output": llm_text,
            }
        )

        if llm_text is None:
            return (
                {
                    "error": llm_meta.get("error", "Agent LLM call failed."),
                    "details": llm_meta.get("details"),
                    "agent_trace": agent_trace,
                    "trace": {"steps": [llm_meta.get("trace_step", {})]},
                },
                int(llm_meta.get("status_code", 502)),
            )

        decision = _extract_json(llm_text)
        if not isinstance(decision, dict):
            # Fallback: treat raw model text as final response.
            return (
                {
                    "response": llm_text.strip(),
                    "agent_trace": agent_trace,
                    "agentic": {"enabled": True, "tool_calls": 0, "final_mode": "raw_text_fallback"},
                    "trace": {"steps": [llm_meta["trace_step"]]},
                },
                200,
            )

        dtype = str(decision.get("type") or "").strip().lower()
        if dtype == "final":
            final_text = str(decision.get("response") or "").strip() or "(Empty response)"
            return (
                {
                    "response": final_text,
                    "agent_trace": agent_trace,
                    "agentic": {
                        "enabled": True,
                        "tool_calls": sum(1 for e in agent_trace if e.get("kind") == "tool"),
                        "final_mode": "json_final",
                    },
                    "trace": {"steps": [llm_meta["trace_step"]]},
                },
                200,
            )

        if dtype == "tool":
            tool_name = str(decision.get("tool") or "").strip()
            tool_input = decision.get("input") if isinstance(decision.get("input"), dict) else {}
            if not tools_enabled:
                return (
                    {
                        "response": "Agent requested a tool, but Tools (MCP) is disabled. Enable it to allow tool execution.",
                        "agent_trace": agent_trace,
                        "agentic": {"enabled": True, "tool_calls": 0, "blocked_reason": "tools_disabled"},
                        "trace": {"steps": [llm_meta["trace_step"]]},
                    },
                    200,
                )

            tool_output, tool_meta = run_tool(tool_name, tool_input)
            agent_trace.append(
                {
                    "kind": "tool",
                    "step": step,
                    "tool": tool_name,
                    "input": tool_input,
                    "output": tool_output,
                    "tool_trace": tool_meta,
                }
            )
            llm_messages.extend(
                [
                    {"role": "assistant", "content": llm_text},
                    {
                        "role": "user",
                        "content": (
                            "TOOL_RESULT\n"
                            + json.dumps(
                                {
                                    "tool": tool_name,
                                    "input": tool_input,
                                    "output": tool_output,
                                }
                            )
                        ),
                    },
                ]
            )
            continue

        return (
            {
                "response": "Agent produced an unsupported decision type. Returning raw model output.",
                "agent_trace": agent_trace,
                "trace": {"steps": [llm_meta["trace_step"]]},
            },
            200,
        )

    return (
        {
            "response": "Agent reached the max number of steps without producing a final answer.",
            "agent_trace": agent_trace,
            "agentic": {"enabled": True, "max_steps": AGENTIC_MAX_STEPS, "timed_out": True},
        },
        200,
    )
