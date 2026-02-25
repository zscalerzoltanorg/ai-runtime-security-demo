import os
from typing import Any

from urllib import error, request
import json


DEFAULT_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")


def available_providers() -> list[dict[str, str]]:
    return [
        {"id": "ollama", "label": "Ollama (Local)"},
        {"id": "anthropic", "label": "Anthropic"},
    ]


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> tuple[int, object]:
    raw = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=raw, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        if not text:
            return resp.status, {}
        try:
            return resp.status, json.loads(text)
        except json.JSONDecodeError:
            return resp.status, text


def _ollama_generate(prompt: str, ollama_url: str, ollama_model: str) -> tuple[str | None, dict]:
    payload = {"model": ollama_model, "prompt": prompt, "stream": False}
    url = f"{ollama_url}/api/generate"
    headers = {"Content-Type": "application/json"}

    try:
        status, body = _post_json(url, payload=payload, headers=headers, timeout=120)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return None, {
            "error": "Ollama request failed.",
            "status_code": 502,
            "details": detail,
            "trace_step": {
                "name": "Ollama (Local)",
                "request": {
                    "method": "POST",
                    "url": url,
                    "headers": headers,
                    "payload": payload,
                },
                "response": {"status": exc.code, "body": detail},
            },
        }
    except Exception as exc:
        return None, {
            "error": "Could not reach local Ollama server.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {
                "name": "Ollama (Local)",
                "request": {
                    "method": "POST",
                    "url": url,
                    "headers": headers,
                    "payload": payload,
                },
                "response": {"status": 502, "body": {"error": str(exc)}},
            },
        }

    if not isinstance(body, dict):
        return None, {
            "error": "Unexpected Ollama response format.",
            "status_code": 502,
            "details": str(body),
            "trace_step": {
                "name": "Ollama (Local)",
                "request": {
                    "method": "POST",
                    "url": url,
                    "headers": headers,
                    "payload": payload,
                },
                "response": {"status": status, "body": body},
            },
        }

    text = (body.get("response") or "").strip()
    return text, {
        "trace_step": {
            "name": "Ollama (Local)",
            "request": {
                "method": "POST",
                "url": url,
                "headers": headers,
                "payload": payload,
            },
            "response": {"status": status, "body": body},
        }
    }


def _anthropic_generate(prompt: str, anthropic_model: str) -> tuple[str | None, dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    request_payload = {
        "model": anthropic_model,
        "max_tokens": 400,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    trace_request = {
        "method": "SDK",
        "url": "Anthropic SDK (messages.create)",
        "headers": {"x-api-key": "***redacted***" if api_key else "***missing***"},
        "payload": request_payload,
    }

    if not api_key:
        return None, {
            "error": "ANTHROPIC_API_KEY is not set.",
            "status_code": 500,
            "trace_step": {
                "name": "Anthropic",
                "request": trace_request,
                "response": {"status": 500, "body": {"error": "Missing ANTHROPIC_API_KEY"}},
            },
        }

    try:
        from anthropic import Anthropic
    except Exception as exc:
        return None, {
            "error": "Anthropic SDK is not installed.",
            "status_code": 500,
            "details": str(exc),
            "trace_step": {
                "name": "Anthropic",
                "request": trace_request,
                "response": {
                    "status": 500,
                    "body": {"error": "Install with `pip install anthropic`", "details": str(exc)},
                },
            },
        }

    try:
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(**request_payload)
        text = "".join(
            block.text
            for block in getattr(resp, "content", [])
            if getattr(block, "type", None) == "text"
        ).strip()
        response_body: dict[str, Any] = {
            "id": getattr(resp, "id", None),
            "model": getattr(resp, "model", anthropic_model),
            "role": getattr(resp, "role", None),
            "stop_reason": getattr(resp, "stop_reason", None),
            "usage": getattr(resp, "usage", None).model_dump()
            if hasattr(getattr(resp, "usage", None), "model_dump")
            else None,
            "text": text,
        }
    except Exception as exc:
        return None, {
            "error": "Anthropic request failed.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {
                "name": "Anthropic",
                "request": trace_request,
                "response": {"status": 502, "body": {"error": str(exc)}},
            },
        }

    return text, {
        "trace_step": {
            "name": "Anthropic",
            "request": trace_request,
            "response": {"status": 200, "body": response_body},
        }
    }


def call_provider(
    provider_id: str,
    prompt: str,
    *,
    ollama_url: str,
    ollama_model: str,
    anthropic_model: str | None = None,
) -> tuple[str | None, dict]:
    provider = (provider_id or "ollama").strip().lower()
    if provider == "anthropic":
        return _anthropic_generate(prompt, anthropic_model or DEFAULT_ANTHROPIC_MODEL)
    if provider != "ollama":
        return None, {
            "error": f"Unsupported provider: {provider_id}",
            "status_code": 400,
            "trace_step": {
                "name": "Provider Selection",
                "request": {"provider": provider_id},
                "response": {"status": 400, "body": {"error": "Unsupported provider"}},
            },
        }
    return _ollama_generate(prompt, ollama_url=ollama_url, ollama_model=ollama_model)
