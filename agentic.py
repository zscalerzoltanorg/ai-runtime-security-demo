import base64
import getpass
import hashlib
import ipaddress
import json
import os
import platform
import re
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib import error, parse, request
from zoneinfo import ZoneInfo

from mcp_client import mcp_client_from_env


def _int_env(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


BRAVE_SEARCH_BASE_URL = os.getenv("BRAVE_SEARCH_BASE_URL", "https://api.search.brave.com")
BRAVE_SEARCH_MAX_RESULTS = _int_env("BRAVE_SEARCH_MAX_RESULTS", 5)
AGENTIC_MAX_STEPS = _int_env("AGENTIC_MAX_STEPS", 3)
ALLOW_PRIVATE_TOOL_NETWORK = str(os.getenv("ALLOW_PRIVATE_TOOL_NETWORK", "")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
LOCAL_TASKS_BASE_DIR = str(os.getenv("LOCAL_TASKS_BASE_DIR", "demo_local_workspace")).strip() or "demo_local_workspace"
LOCAL_TASKS_MAX_ENTRIES = max(1, _int_env("LOCAL_TASKS_MAX_ENTRIES", 200))
LOCAL_TASKS_MAX_BYTES = max(1024, _int_env("LOCAL_TASKS_MAX_BYTES", 500_000))


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
    "current_time": {
        "description": "Get current date/time in a timezone (IANA tz, e.g., America/Chicago).",
        "input_schema": {"timezone": "string (optional)"},
    },
    "dns_lookup": {
        "description": "Resolve a hostname to IP addresses.",
        "input_schema": {"host": "string"},
    },
    "http_head": {
        "description": "Fetch HTTP headers/status for a URL (HEAD request).",
        "input_schema": {"url": "string"},
    },
    "hash_text": {
        "description": "Hash text using md5/sha1/sha256/sha512.",
        "input_schema": {"text": "string", "algorithm": "string (optional)"},
    },
    "url_codec": {
        "description": "URL-encode or URL-decode text.",
        "input_schema": {"mode": "encode|decode", "text": "string"},
    },
    "text_stats": {
        "description": "Get simple text statistics (chars/words/lines).",
        "input_schema": {"text": "string"},
    },
    "uuid_generate": {
        "description": "Generate UUIDv4 values (1-10).",
        "input_schema": {"count": "integer (optional)"},
    },
    "base64_codec": {
        "description": "Base64 encode or decode text.",
        "input_schema": {"mode": "encode|decode", "text": "string"},
    },
    "local_whoami": {
        "description": "Return the current local OS user and host/platform info.",
        "input_schema": {},
    },
    "local_pwd": {
        "description": "Return the current working directory and allowed local tasks base directory.",
        "input_schema": {},
    },
    "local_ls": {
        "description": "List files/directories under a path inside the local tasks base directory.",
        "input_schema": {"path": "string (optional)", "recursive": "boolean (optional)", "max_entries": "integer (optional)"},
    },
    "local_file_sizes": {
        "description": "Summarize file sizes under a path inside the local tasks base directory.",
        "input_schema": {"path": "string (optional)", "top_n": "integer (optional)"},
    },
    "local_curl": {
        "description": "Make a curl-like HTTP request (GET/HEAD/POST), returning status, headers, and a body preview.",
        "input_schema": {
            "url": "string",
            "method": "GET|HEAD|POST (optional)",
            "headers": "object (optional)",
            "params": "object (optional)",
            "body": "string (optional)",
            "timeout_seconds": "number (optional)",
        },
    },
}

LOCAL_TASK_TOOL_NAMES = {
    "local_whoami",
    "local_pwd",
    "local_ls",
    "local_file_sizes",
    "local_curl",
}

TOOL_NAME_ALIASES = {
    "curl": "local_curl",
    "http_get": "local_curl",
    "http_fetch": "local_curl",
    "ls": "local_ls",
    "dir": "local_ls",
    "list_files": "local_ls",
    "pwd": "local_pwd",
    "whoami": "local_whoami",
    "du": "local_file_sizes",
    "file_sizes": "local_file_sizes",
    "filesizes": "local_file_sizes",
}


def _canonical_tool_name(name: str) -> str:
    key = str(name or "").strip().lower()
    return TOOL_NAME_ALIASES.get(key, key)


def _resolve_local_tasks_base_dir() -> Path:
    candidate = Path(LOCAL_TASKS_BASE_DIR).expanduser()
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parent.joinpath(candidate)
    return candidate.resolve()


def _safe_local_relpath(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base))
    except Exception:
        return str(path)


def _resolve_local_path(user_path: str | None) -> tuple[Path | None, Path, str | None]:
    base = _resolve_local_tasks_base_dir()
    if not base.exists():
        return None, base, f"Local tasks base directory does not exist: {base}"
    raw = str(user_path or "").strip().strip("\"' ")
    normalized = raw.replace("\\", "/").strip()
    normalized_lower = normalized.lower().strip("/ ")
    base_name = base.name.lower()
    base_aliases = {
        base_name,
        "demo_local_workspace",
        "local demo workspace",
        "local demo workspace folder",
        "demo workspace",
        "workspace",
        "local workspace",
        "base",
        "base dir",
        "base directory",
        ".",
        "./",
    }
    if normalized_lower in base_aliases:
        normalized = ""
    elif normalized_lower.startswith(f"{base_name}/"):
        normalized = normalized[len(base_name) + 1 :]
    elif normalized_lower.startswith(f"./{base_name}/"):
        normalized = normalized[len(base_name) + 3 :]
    target = (
        base
        if not normalized
        else (base.joinpath(normalized).resolve() if not Path(normalized).is_absolute() else Path(normalized).resolve())
    )
    try:
        target.relative_to(base)
    except Exception:
        return None, base, f"Path `{raw}` escapes allowed base directory."
    return target, base, None


def _tool_catalog_text(extra_tools: list[dict] | None = None, *, local_tasks_enabled: bool = False) -> str:
    rows = []
    for name, meta in TOOLS.items():
        if name in LOCAL_TASK_TOOL_NAMES and not local_tasks_enabled:
            continue
        rows.append(f"- {name}: {meta['description']} input={json.dumps(meta['input_schema'])}")
    for tool in extra_tools or []:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or "").strip()
        if name in LOCAL_TASK_TOOL_NAMES and not local_tasks_enabled:
            continue
        if not name or name in TOOLS:
            continue
        desc = str(tool.get("description") or "MCP tool")
        input_schema = tool.get("inputSchema")
        rows.append(f"- {name}: {desc} input={json.dumps(input_schema if input_schema is not None else {})}")
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


def _normalize_agent_decision(
    decision: dict | None, known_tools: set[str]
) -> dict | None:
    if not isinstance(decision, dict):
        return None

    dtype = str(decision.get("type") or "").strip().lower()
    tool_name = _canonical_tool_name(
        str(
            decision.get("tool")
            or decision.get("tool_name")
            or decision.get("name")
            or decision.get("function")
            or decision.get("action")
            or ""
        ).strip()
    )
    response = (
        decision.get("response")
        or decision.get("output")
        or decision.get("final")
        or decision.get("answer")
        or decision.get("message")
        or decision.get("text")
    )
    tool_input = decision.get("input") if isinstance(decision.get("input"), dict) else {}
    if not tool_input and isinstance(decision.get("arguments"), dict):
        tool_input = dict(decision.get("arguments") or {})
    if not tool_input and isinstance(decision.get("args"), dict):
        tool_input = dict(decision.get("args") or {})
    inferred_args = {
        str(k): v
        for k, v in decision.items()
        if str(k) not in {
            "type",
            "tool",
            "tool_name",
            "name",
            "function",
            "action",
            "input",
            "arguments",
            "args",
            "response",
            "output",
            "final",
            "answer",
            "message",
            "text",
        }
    }
    known_canonical = {_canonical_tool_name(name) for name in (known_tools or set()) if str(name).strip()}

    # Happy path
    if dtype in {"final", "tool"}:
        normalized_response = response
        if dtype == "final" and (not isinstance(normalized_response, str) or not normalized_response.strip()):
            if "output" in decision:
                normalized_response = str(decision.get("output") or "")
            elif tool_name and tool_name in known_canonical:
                return {
                    "type": "tool",
                    "tool": tool_name,
                    "input": tool_input or inferred_args,
                    "response": None,
                }
        return {
            "type": dtype,
            "tool": tool_name,
            "input": tool_input,
            "response": normalized_response,
        }

    # Some smaller models return {"tool":"name","input":{...}} without type.
    if not dtype and tool_name and tool_name in known_canonical:
        return {
            "type": "tool",
            "tool": tool_name,
            "input": tool_input or inferred_args,
            "response": response,
        }

    # Some smaller models incorrectly put the tool name in "type".
    if _canonical_tool_name(dtype) in known_canonical:
        canonical_dtype = _canonical_tool_name(dtype)
        # If no usable input is provided but a response exists, degrade gracefully to final.
        if not tool_input and isinstance(response, str) and response.strip():
            return {
                "type": "final",
                "tool": "",
                "input": {},
                "response": response,
            }
        return {
            "type": "tool",
            "tool": canonical_dtype,
            "input": tool_input or inferred_args,
            "response": response,
        }

    # Graceful final fallback when response field exists.
    if isinstance(response, str) and response.strip():
        return {
            "type": "final",
            "tool": "",
            "input": {},
            "response": response,
        }

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


def _http_head(url: str, headers: dict | None = None, timeout: float = 15.0) -> tuple[int, dict]:
    req = request.Request(url, headers=headers or {}, method="HEAD")
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.status, dict(resp.headers.items())


def _is_public_ip(ip_raw: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(str(ip_raw).strip())
    except ValueError:
        return False
    if ip_obj.is_loopback or ip_obj.is_private:
        return False
    if ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_unspecified:
        return False
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.is_site_local:
        return False
    return True


def _validate_public_tool_url(url: str) -> str | None:
    parsed = parse.urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return "only http/https URLs are allowed."
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        return "URL host is required."
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return "localhost/local domains are blocked."
    if ALLOW_PRIVATE_TOOL_NETWORK:
        return None
    try:
        infos = socket.getaddrinfo(host, parsed.port or None, type=socket.SOCK_STREAM)
    except Exception as exc:
        return f"could not resolve host: {exc}"
    ips = {info[4][0] for info in infos if info and len(info) > 4 and info[4]}
    if not ips:
        return "could not resolve host to an IP."
    blocked = [ip for ip in ips if not _is_public_ip(ip)]
    if blocked:
        return f"host resolves to blocked private/local IPs: {', '.join(sorted(blocked))}"
    return None


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
    url_err = _validate_public_tool_url(url)
    if url_err:
        return f"Error: web_fetch blocked: {url_err}", {
            "tool": "web_fetch",
            "input": args,
            "request": {"method": "GET", "url": url},
            "error": url_err,
        }

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


def _tool_current_time(args: dict) -> tuple[str, dict]:
    tz_name = str((args or {}).get("timezone") or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz_name = "UTC"
        tz = timezone.utc
    now = datetime.now(tz)
    payload = {
        "timezone": tz_name,
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
    }
    return json.dumps(payload), {"tool": "current_time", "input": args, "response": payload}


def _tool_dns_lookup(args: dict) -> tuple[str, dict]:
    host = str((args or {}).get("host") or "").strip()
    if not host:
        return "Error: dns_lookup requires `host`.", {"tool": "dns_lookup", "input": args, "error": "missing host"}
    try:
        infos = socket.getaddrinfo(host, None)
        addrs = sorted({info[4][0] for info in infos if info and len(info) > 4 and info[4]})
    except Exception as exc:
        return f"Error: dns lookup failed: {exc}", {"tool": "dns_lookup", "input": args, "error": str(exc)}
    payload = {"host": host, "addresses": addrs}
    return json.dumps(payload), {"tool": "dns_lookup", "input": args, "response": payload}


def _tool_http_head(args: dict) -> tuple[str, dict]:
    url = str((args or {}).get("url") or "").strip()
    if not url:
        return "Error: http_head requires `url`.", {"tool": "http_head", "input": args, "error": "missing url"}
    if not url.startswith(("http://", "https://")):
        return "Error: http_head only supports http/https URLs.", {"tool": "http_head", "input": args, "error": "invalid scheme"}
    url_err = _validate_public_tool_url(url)
    if url_err:
        return f"Error: http_head blocked: {url_err}", {
            "tool": "http_head",
            "input": args,
            "request": {"method": "HEAD", "url": url},
            "error": url_err,
        }
    req_headers = {"User-Agent": "LocalLLMDemo/1.0"}
    try:
        status, headers = _http_head(url, headers=req_headers, timeout=15.0)
    except error.HTTPError as exc:
        return f"Error: http_head HTTP {exc.code}", {
            "tool": "http_head",
            "input": args,
            "request": {"method": "HEAD", "url": url},
            "response": {"status": exc.code, "headers": dict(exc.headers.items()) if exc.headers else {}},
        }
    except Exception as exc:
        return f"Error: http_head failed: {exc}", {
            "tool": "http_head",
            "input": args,
            "request": {"method": "HEAD", "url": url},
            "error": str(exc),
        }
    payload = {"url": url, "status": status, "headers": headers}
    return json.dumps(payload), {
        "tool": "http_head",
        "input": args,
        "request": {"method": "HEAD", "url": url},
        "response": {"status": status, "headers": headers},
    }


def _tool_hash_text(args: dict) -> tuple[str, dict]:
    text = str((args or {}).get("text") or "")
    algorithm = str((args or {}).get("algorithm") or "sha256").strip().lower()
    allowed = {"md5", "sha1", "sha256", "sha512"}
    if algorithm not in allowed:
        return (
            f"Error: unsupported algorithm `{algorithm}`. Use one of: {', '.join(sorted(allowed))}",
            {"tool": "hash_text", "input": args, "error": "unsupported algorithm"},
        )
    h = hashlib.new(algorithm)
    h.update(text.encode("utf-8"))
    payload = {"algorithm": algorithm, "hex": h.hexdigest(), "length": len(text)}
    return json.dumps(payload), {"tool": "hash_text", "input": args, "response": payload}


def _tool_url_codec(args: dict) -> tuple[str, dict]:
    mode = str((args or {}).get("mode") or "encode").strip().lower()
    text = str((args or {}).get("text") or "")
    if mode == "encode":
        out = parse.quote(text)
    elif mode == "decode":
        out = parse.unquote(text)
    else:
        return "Error: url_codec mode must be `encode` or `decode`.", {
            "tool": "url_codec",
            "input": args,
            "error": "invalid mode",
        }
    payload = {"mode": mode, "input": text, "output": out}
    return json.dumps(payload), {"tool": "url_codec", "input": args, "response": payload}


def _tool_text_stats(args: dict) -> tuple[str, dict]:
    text = str((args or {}).get("text") or "")
    lines = text.splitlines() or ([text] if text else [])
    words = [w for w in re.split(r"\s+", text.strip()) if w] if text.strip() else []
    payload = {
        "chars": len(text),
        "chars_no_spaces": len(re.sub(r"\s+", "", text)),
        "words": len(words),
        "lines": len(lines),
    }
    return json.dumps(payload), {"tool": "text_stats", "input": args, "response": payload}


def _tool_uuid_generate(args: dict) -> tuple[str, dict]:
    count_raw = (args or {}).get("count")
    try:
        count = max(1, min(int(count_raw if count_raw is not None else 1), 10))
    except Exception:
        count = 1
    values = [str(uuid.uuid4()) for _ in range(count)]
    payload = {"version": 4, "count": count, "uuids": values}
    return json.dumps(payload), {"tool": "uuid_generate", "input": args, "response": payload}


def _tool_base64_codec(args: dict) -> tuple[str, dict]:
    mode = str((args or {}).get("mode") or "encode").strip().lower()
    text = str((args or {}).get("text") or "")
    try:
        if mode == "encode":
            out = base64.b64encode(text.encode("utf-8")).decode("ascii")
        elif mode == "decode":
            out = base64.b64decode(text.encode("ascii"), validate=True).decode("utf-8", errors="replace")
        else:
            return "Error: base64_codec mode must be `encode` or `decode`.", {
                "tool": "base64_codec",
                "input": args,
                "error": "invalid mode",
            }
    except Exception as exc:
        return f"Error: base64_codec failed: {exc}", {"tool": "base64_codec", "input": args, "error": str(exc)}
    payload = {"mode": mode, "input": text, "output": out}
    return json.dumps(payload), {"tool": "base64_codec", "input": args, "response": payload}


def _tool_local_whoami(args: dict) -> tuple[str, dict]:
    payload = {
        "user": getpass.getuser(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    return json.dumps(payload), {"tool": "local_whoami", "input": args, "response": payload}


def _tool_local_pwd(args: dict) -> tuple[str, dict]:
    base = _resolve_local_tasks_base_dir()
    cwd = Path.cwd().resolve()
    payload = {"cwd": str(cwd), "local_tasks_base_dir": str(base)}
    return json.dumps(payload), {"tool": "local_pwd", "input": args, "response": payload}


def _tool_local_ls(args: dict) -> tuple[str, dict]:
    target, base, err = _resolve_local_path((args or {}).get("path"))
    if err:
        return f"Error: local_ls blocked: {err}", {"tool": "local_ls", "input": args, "error": err}
    assert target is not None
    if not target.exists():
        return "Error: local_ls target path does not exist.", {"tool": "local_ls", "input": args, "error": "path missing"}
    recursive = bool((args or {}).get("recursive"))
    try:
        max_entries = max(1, min(int((args or {}).get("max_entries", LOCAL_TASKS_MAX_ENTRIES)), LOCAL_TASKS_MAX_ENTRIES))
    except Exception:
        max_entries = LOCAL_TASKS_MAX_ENTRIES
    rows: list[dict] = []
    iterator = target.rglob("*") if recursive and target.is_dir() else target.iterdir() if target.is_dir() else [target]
    for idx, item in enumerate(iterator):
        if idx >= max_entries:
            break
        try:
            stat = item.stat()
            rows.append(
                {
                    "path": _safe_local_relpath(item, base),
                    "type": "dir" if item.is_dir() else "file",
                    "size_bytes": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
        except Exception as exc:
            rows.append({"path": _safe_local_relpath(item, base), "error": str(exc)})
    payload = {
        "base_dir": str(base),
        "target": _safe_local_relpath(target, base),
        "recursive": recursive,
        "count": len(rows),
        "entries": rows,
    }
    return json.dumps(payload), {"tool": "local_ls", "input": args, "response": payload}


def _tool_local_file_sizes(args: dict) -> tuple[str, dict]:
    target, base, err = _resolve_local_path((args or {}).get("path"))
    if err:
        return f"Error: local_file_sizes blocked: {err}", {"tool": "local_file_sizes", "input": args, "error": err}
    assert target is not None
    if not target.exists():
        return "Error: local_file_sizes target path does not exist.", {
            "tool": "local_file_sizes",
            "input": args,
            "error": "path missing",
        }
    try:
        top_n = max(1, min(int((args or {}).get("top_n", 20)), 100))
    except Exception:
        top_n = 20
    files: list[tuple[int, Path]] = []
    total_size = 0
    if target.is_file():
        st = target.stat()
        files.append((st.st_size, target))
        total_size = st.st_size
    else:
        for item in target.rglob("*"):
            if not item.is_file():
                continue
            try:
                size = item.stat().st_size
                total_size += size
                files.append((size, item))
            except Exception:
                continue
    files.sort(key=lambda x: x[0], reverse=True)
    largest = [{"path": _safe_local_relpath(p, base), "size_bytes": s} for s, p in files[:top_n]]
    payload = {
        "base_dir": str(base),
        "target": _safe_local_relpath(target, base),
        "file_count": len(files),
        "total_size_bytes": total_size,
        "largest_files": largest,
    }
    return json.dumps(payload), {"tool": "local_file_sizes", "input": args, "response": payload}


def _tool_local_curl(args: dict) -> tuple[str, dict]:
    url = str((args or {}).get("url") or "").strip()
    if not url:
        return "Error: local_curl requires `url`.", {"tool": "local_curl", "input": args, "error": "missing url"}
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "Error: local_curl only supports http/https URLs.", {"tool": "local_curl", "input": args, "error": "invalid scheme"}
    method = str((args or {}).get("method") or "GET").strip().upper()
    if method not in {"GET", "HEAD", "POST"}:
        return "Error: local_curl method must be GET, HEAD, or POST.", {"tool": "local_curl", "input": args, "error": "invalid method"}
    timeout_raw = (args or {}).get("timeout_seconds")
    try:
        timeout_seconds = float(timeout_raw) if timeout_raw is not None else 20.0
    except Exception:
        timeout_seconds = 20.0
    timeout_seconds = min(max(timeout_seconds, 1.0), 60.0)
    params = (args or {}).get("params")
    if isinstance(params, dict) and params:
        query = parse.parse_qsl(parsed.query, keep_blank_values=True)
        for k, v in params.items():
            query.append((str(k), str(v)))
        url = parse.urlunparse(parsed._replace(query=parse.urlencode(query)))
    body = (args or {}).get("body")
    raw_body = str(body).encode("utf-8") if body is not None and method == "POST" else None
    headers_in = (args or {}).get("headers") if isinstance((args or {}).get("headers"), dict) else {}
    headers = {str(k): str(v) for k, v in headers_in.items()}
    req = request.Request(url, headers=headers, data=raw_body, method=method)

    def _redacted_headers(src: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in src.items():
            out[k] = "***redacted***" if k.lower() in {"authorization", "x-api-key", "proxy-authorization"} else v
        return out

    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            data = resp.read(LOCAL_TASKS_MAX_BYTES)
            text = data.decode("utf-8", errors="replace")
            payload = {
                "url": url,
                "method": method,
                "status": resp.status,
                "headers": dict(resp.headers.items()),
                "body_preview": text[:4000],
                "body_bytes": len(data),
                "body_truncated": len(data) >= LOCAL_TASKS_MAX_BYTES,
            }
            return json.dumps(payload), {
                "tool": "local_curl",
                "input": args,
                "request": {"method": method, "url": url, "headers": _redacted_headers(headers), "timeout_seconds": timeout_seconds},
                "response": {"status": resp.status, "headers": dict(resp.headers.items()), "body_preview": text[:800]},
            }
    except error.HTTPError as exc:
        detail = exc.read(LOCAL_TASKS_MAX_BYTES).decode("utf-8", errors="replace")
        return f"Error: local_curl HTTP {exc.code}", {
            "tool": "local_curl",
            "input": args,
            "request": {"method": method, "url": url, "headers": _redacted_headers(headers), "timeout_seconds": timeout_seconds},
            "response": {"status": exc.code, "headers": dict(exc.headers.items()) if exc.headers else {}, "body_preview": detail[:800]},
        }
    except Exception as exc:
        return f"Error: local_curl failed: {exc}", {
            "tool": "local_curl",
            "input": args,
            "request": {"method": method, "url": url, "headers": _redacted_headers(headers), "timeout_seconds": timeout_seconds},
            "error": str(exc),
        }


def _tool_mcp_call(tool_name: str, tool_input: dict, mcp_client) -> tuple[str, dict]:
    try:
        result = mcp_client.tools_call(tool_name, tool_input or {})
    except Exception as exc:
        return f"Error: MCP tool `{tool_name}` failed: {exc}", {
            "tool": tool_name,
            "input": tool_input,
            "source": "mcp",
            "error": str(exc),
        }

    content = result.get("content")
    is_error = bool(result.get("isError"))
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(json.dumps(item))
    elif content is not None:
        parts.append(json.dumps(content) if not isinstance(content, str) else content)
    else:
        parts.append(json.dumps(result))
    text = "\n".join([p for p in parts if p]).strip() or "(empty MCP tool result)"
    if is_error:
        text = f"Error: MCP tool `{tool_name}` returned isError=true. {text}"
    return text, {
        "tool": tool_name,
        "input": tool_input,
        "source": "mcp",
        "request": {"method": "tools/call", "params": {"name": tool_name, "arguments": tool_input or {}}},
        "response": result,
    }


def run_tool(
    tool_name: str,
    tool_input: dict,
    mcp_client=None,
    *,
    local_tasks_enabled: bool = False,
) -> tuple[str, dict]:
    tool = _canonical_tool_name((tool_name or "").strip())
    if tool in LOCAL_TASK_TOOL_NAMES and not local_tasks_enabled:
        return (
            f"Error: local task tool `{tool}` is disabled for this request.",
            {"tool": tool, "input": tool_input, "error": "local_tasks_disabled"},
        )
    if tool == "calculator":
        return _tool_calculator(tool_input)
    if tool == "weather":
        return _tool_weather(tool_input)
    if tool == "web_fetch":
        return _tool_web_fetch(tool_input)
    if tool == "brave_search":
        return _tool_brave_search(tool_input)
    if tool == "current_time":
        return _tool_current_time(tool_input)
    if tool == "dns_lookup":
        return _tool_dns_lookup(tool_input)
    if tool == "http_head":
        return _tool_http_head(tool_input)
    if tool == "hash_text":
        return _tool_hash_text(tool_input)
    if tool == "url_codec":
        return _tool_url_codec(tool_input)
    if tool == "text_stats":
        return _tool_text_stats(tool_input)
    if tool == "uuid_generate":
        return _tool_uuid_generate(tool_input)
    if tool == "base64_codec":
        return _tool_base64_codec(tool_input)
    if tool == "local_whoami":
        return _tool_local_whoami(tool_input)
    if tool == "local_pwd":
        return _tool_local_pwd(tool_input)
    if tool == "local_ls":
        return _tool_local_ls(tool_input)
    if tool == "local_file_sizes":
        return _tool_local_file_sizes(tool_input)
    if tool == "local_curl":
        return _tool_local_curl(tool_input)
    if mcp_client is not None:
        return _tool_mcp_call(tool, tool_input, mcp_client)
    return (
        f"Error: unknown tool `{tool}`",
        {"tool": tool, "input": tool_input, "error": "unknown tool"},
    )


def run_agentic_turn(
    *,
    conversation_messages: list[dict],
    provider_messages_call: Callable[[list[dict]], tuple[str | None, dict]],
    tools_enabled: bool,
    local_tasks_enabled: bool = False,
) -> tuple[dict, int]:
    agent_trace: list[dict] = []
    work_messages = list(conversation_messages)
    seen_tool_signatures: set[str] = set()
    tool_outputs_by_signature: dict[str, str] = {}
    mcp_client = None
    mcp_tools: list[dict] = []

    if tools_enabled:
        mcp_client = mcp_client_from_env()
        if mcp_client is not None:
            try:
                mcp_client.start()
                mcp_tools = mcp_client.tools_list()
                if not local_tasks_enabled:
                    mcp_tools = [
                        t
                        for t in mcp_tools
                        if isinstance(t, dict)
                        and str(t.get("name") or "").strip() not in LOCAL_TASK_TOOL_NAMES
                    ]
                agent_trace.append(
                    {
                        "kind": "mcp",
                        "step": 0,
                        "event": "tools_list",
                        "tool_count": len(mcp_tools),
                        "server_info": getattr(mcp_client, "server_info", None),
                        "tools": [
                            {
                                "name": t.get("name"),
                                "description": t.get("description"),
                            }
                            for t in mcp_tools
                            if isinstance(t, dict)
                        ],
                    }
                )
            except Exception as exc:
                agent_trace.append(
                    {
                        "kind": "mcp",
                        "step": 0,
                        "event": "startup_error",
                        "error": str(exc),
                    }
                )
                try:
                    mcp_client.close()
                except Exception:
                    pass
                mcp_client = None

    system_prompt = (
        "You are a helpful agent. "
        "When tools are enabled and useful, decide whether to call a tool.\n"
        f"TOOLS_ENABLED={str(bool(tools_enabled)).lower()} | LOCAL_TASKS_ENABLED={str(bool(local_tasks_enabled)).lower()}\n"
        "Return ONLY JSON in one of these shapes:\n"
        '{"type":"final","response":"..."}\n'
        '{"type":"tool","tool":"calculator","input":{"expression":"2+2"}}\n'
        'IMPORTANT: "type" must be exactly "final" or "tool". Put the tool name in the "tool" field, not in "type".\n'
        'IMPORTANT: If choosing a local network request, use tool name "local_curl" (not "curl").\n'
        "Available tools:\n"
        + _tool_catalog_text(mcp_tools, local_tasks_enabled=local_tasks_enabled)
        + "\nIf tools are disabled, always return type=final."
    )

    llm_messages = [{"role": "system", "content": system_prompt}, *work_messages]

    try:
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
                        **(
                            {"proxy_guardrails_block": llm_meta.get("proxy_guardrails_block")}
                            if isinstance(llm_meta.get("proxy_guardrails_block"), dict)
                            else {}
                        ),
                        "agent_trace": agent_trace,
                        "trace": {"steps": [llm_meta.get("trace_step", {})]},
                    },
                    int(llm_meta.get("status_code", 502)),
                )

            decision = _normalize_agent_decision(
                _extract_json(llm_text),
                known_tools=(
                    {
                        name
                        for name in TOOLS.keys()
                        if local_tasks_enabled or name not in LOCAL_TASK_TOOL_NAMES
                    }
                    | {str((t or {}).get("name") or "").strip() for t in mcp_tools if isinstance(t, dict)}
                ),
            )
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

                tool_signature = json.dumps(
                    {"tool": tool_name, "input": tool_input}, sort_keys=True
                )
                if tool_signature in seen_tool_signatures:
                    prior_output = tool_outputs_by_signature.get(tool_signature, "")
                    return (
                        {
                            "response": (
                                "Agent repeated the same tool call. Returning the previous tool result to avoid a loop.\n\n"
                                + (prior_output or json.dumps({"tool": tool_name, "input": tool_input}))
                            ),
                            "agent_trace": agent_trace,
                            "agentic": {
                                "enabled": True,
                                "tool_calls": sum(1 for e in agent_trace if e.get("kind") == "tool"),
                                "final_mode": "repeated_tool_loop_break",
                            },
                            "trace": {"steps": [llm_meta["trace_step"]]},
                        },
                        200,
                    )

                tool_output, tool_meta = run_tool(
                    tool_name,
                    tool_input,
                    mcp_client=mcp_client,
                    local_tasks_enabled=local_tasks_enabled,
                )
                seen_tool_signatures.add(tool_signature)
                tool_outputs_by_signature[tool_signature] = str(tool_output)
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
    finally:
        if mcp_client is not None:
            try:
                mcp_client.close()
            except Exception:
                pass
