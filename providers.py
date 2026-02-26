import os
from typing import Any

from urllib import error, request
import json


DEFAULT_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def available_providers() -> list[dict[str, str]]:
    return [
        {"id": "ollama", "label": "Ollama (Local)"},
        {"id": "anthropic", "label": "Anthropic"},
        {"id": "openai", "label": "OpenAI"},
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


def _normalize_messages(messages: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        content = str(msg.get("content") or "")
        if role in {"user", "assistant", "system"}:
            normalized.append({"role": role, "content": content})
    return normalized


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


def _ollama_chat_messages(
    messages: list[dict], ollama_url: str, ollama_model: str
) -> tuple[str | None, dict]:
    payload = {"model": ollama_model, "messages": _normalize_messages(messages), "stream": False}
    url = f"{ollama_url}/api/chat"
    headers = {"Content-Type": "application/json"}

    try:
        status, body = _post_json(url, payload=payload, headers=headers, timeout=120)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return None, {
            "error": "Ollama chat request failed.",
            "status_code": 502,
            "details": detail,
            "trace_step": {
                "name": "Ollama (Local)",
                "request": {"method": "POST", "url": url, "headers": headers, "payload": payload},
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
                "request": {"method": "POST", "url": url, "headers": headers, "payload": payload},
                "response": {"status": 502, "body": {"error": str(exc)}},
            },
        }

    if not isinstance(body, dict):
        return None, {
            "error": "Unexpected Ollama chat response format.",
            "status_code": 502,
            "details": str(body),
            "trace_step": {
                "name": "Ollama (Local)",
                "request": {"method": "POST", "url": url, "headers": headers, "payload": payload},
                "response": {"status": status, "body": body},
            },
        }

    message_obj = body.get("message") or {}
    text = str(message_obj.get("content") or "").strip()
    return text, {
        "trace_step": {
            "name": "Ollama (Local)",
            "request": {"method": "POST", "url": url, "headers": headers, "payload": payload},
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


def _anthropic_chat_messages(messages: list[dict], anthropic_model: str) -> tuple[str | None, dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    normalized = _normalize_messages(messages)
    system_blocks = [m["content"] for m in normalized if m["role"] == "system" and m["content"].strip()]
    request_payload = {
        "model": anthropic_model,
        "max_tokens": 400,
        "temperature": 0.2,
        "messages": [m for m in normalized if m["role"] in {"user", "assistant"}],
    }
    if system_blocks:
        request_payload["system"] = "\n\n".join(system_blocks)
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


def _openai_chat_messages(messages: list[dict], openai_model: str) -> tuple[str | None, dict]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    normalized = _normalize_messages(messages)
    request_payload = {
        "model": openai_model,
        "messages": normalized,
        "temperature": 0.2,
    }
    trace_request = {
        "method": "SDK",
        "url": "OpenAI SDK (chat.completions.create)",
        "headers": {"Authorization": "Bearer ***redacted***" if api_key else "***missing***"},
        "payload": request_payload,
    }

    if not api_key:
        return None, {
            "error": "OPENAI_API_KEY is not set.",
            "status_code": 500,
            "trace_step": {
                "name": "OpenAI",
                "request": trace_request,
                "response": {"status": 500, "body": {"error": "Missing OPENAI_API_KEY"}},
            },
        }

    try:
        from openai import OpenAI
    except Exception as exc:
        return None, {
            "error": "OpenAI SDK is not installed.",
            "status_code": 500,
            "details": str(exc),
            "trace_step": {
                "name": "OpenAI",
                "request": trace_request,
                "response": {
                    "status": 500,
                    "body": {"error": "Install with `pip install openai`", "details": str(exc)},
                },
            },
        }

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(**request_payload)
        choice0 = (getattr(resp, "choices", None) or [None])[0]
        message_obj = getattr(choice0, "message", None)
        text = str(getattr(message_obj, "content", "") or "").strip()
        usage_obj = getattr(resp, "usage", None)
        response_body: dict[str, Any] = {
            "id": getattr(resp, "id", None),
            "model": getattr(resp, "model", openai_model),
            "object": getattr(resp, "object", None),
            "choices": [
                {
                    "index": getattr(choice0, "index", 0),
                    "finish_reason": getattr(choice0, "finish_reason", None),
                    "message": {
                        "role": getattr(message_obj, "role", None),
                        "content": text,
                    },
                }
            ]
            if choice0 is not None
            else [],
            "usage": usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else None,
        }
    except Exception as exc:
        return None, {
            "error": "OpenAI request failed.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {
                "name": "OpenAI",
                "request": trace_request,
                "response": {"status": 502, "body": {"error": str(exc)}},
            },
        }

    return text, {
        "trace_step": {
            "name": "OpenAI",
            "request": trace_request,
            "response": {"status": 200, "body": response_body},
        }
    }


def call_provider_messages(
    provider_id: str,
    messages: list[dict],
    *,
    ollama_url: str,
    ollama_model: str,
    anthropic_model: str | None = None,
    openai_model: str | None = None,
) -> tuple[str | None, dict]:
    provider = (provider_id or "ollama").strip().lower()
    if provider == "anthropic":
        return _anthropic_chat_messages(messages, anthropic_model or DEFAULT_ANTHROPIC_MODEL)
    if provider == "openai":
        return _openai_chat_messages(messages, openai_model or DEFAULT_OPENAI_MODEL)
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
    return _ollama_chat_messages(messages, ollama_url=ollama_url, ollama_model=ollama_model)


def call_provider(
    provider_id: str,
    prompt: str,
    *,
    ollama_url: str,
    ollama_model: str,
    anthropic_model: str | None = None,
    openai_model: str | None = None,
) -> tuple[str | None, dict]:
    return call_provider_messages(
        provider_id,
        [{"role": "user", "content": prompt}],
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        anthropic_model=anthropic_model,
        openai_model=openai_model,
    )
