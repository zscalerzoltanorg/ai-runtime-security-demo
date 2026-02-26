import os
from typing import Any

from urllib import error, request
import json


DEFAULT_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_ZS_PROXY_BASE_URL = os.getenv("ZS_PROXY_BASE_URL", "https://proxy.zseclipse.net")
DEFAULT_ZS_PROXY_API_KEY_HEADER_NAME = os.getenv("ZS_PROXY_API_KEY_HEADER_NAME", "X-ApiKey")


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


def _zscaler_proxy_sdk_config(
    provider_family: str,
    conversation_id: str | None = None,
) -> tuple[str | None, str, str, dict[str, str], str]:
    provider_prefix = (provider_family or "").strip().upper()
    provider_key_envs = [
        f"{provider_prefix}_ZS_PROXY_API_KEY",
        f"{provider_prefix}_ZS_PROXY_KEY",
    ]
    proxy_key = ""
    proxy_key_source = ""
    for env_name in provider_key_envs + ["ZS_PROXY_API_KEY"]:
        candidate = os.getenv(env_name, "").strip()
        if candidate:
            proxy_key = candidate
            proxy_key_source = env_name
            break
    base_url = os.getenv("ZS_PROXY_BASE_URL", DEFAULT_ZS_PROXY_BASE_URL).strip() or DEFAULT_ZS_PROXY_BASE_URL
    api_key_header_name = (
        os.getenv("ZS_PROXY_API_KEY_HEADER_NAME", DEFAULT_ZS_PROXY_API_KEY_HEADER_NAME).strip()
        or DEFAULT_ZS_PROXY_API_KEY_HEADER_NAME
    )
    headers: dict[str, str] = {}
    if proxy_key:
        headers[api_key_header_name] = proxy_key
    conv_header_name = os.getenv("ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME", "").strip()
    if conv_header_name and conversation_id:
        headers[conv_header_name] = conversation_id
    return proxy_key or None, base_url, api_key_header_name, headers, proxy_key_source


def _openai_proxy_base_url(base_url: str) -> str:
    cleaned = (base_url or "").rstrip("/")
    if cleaned.lower().endswith("/v1"):
        return cleaned
    return f"{cleaned}/v1"


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


def _anthropic_generate(
    prompt: str,
    anthropic_model: str,
    *,
    proxy_mode: bool = False,
    conversation_id: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, proxy_key_source = _zscaler_proxy_sdk_config(
        "ANTHROPIC",
        conversation_id,
    )
    effective_api_key = proxy_key if proxy_mode else api_key
    request_payload = {
        "model": anthropic_model,
        "max_tokens": 400,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    trace_headers: dict[str, str] = {
        "x-api-key": "***redacted***" if effective_api_key else "***missing***"
    }
    if proxy_mode:
        trace_headers.update(
            {
                k: ("***redacted***" if k.lower() == proxy_api_key_header_name.lower() else v)
                for k, v in proxy_headers.items()
            }
        )
    trace_request = {
        "method": "SDK",
        "url": (
            f"{proxy_base_url} (Zscaler Proxy -> Anthropic SDK messages.create)"
            if proxy_mode
            else "Anthropic SDK (messages.create)"
        ),
        "headers": trace_headers,
        "payload": request_payload,
    }

    if not effective_api_key:
        return None, {
            "error": (
                "Anthropic proxy key is not set. Set ANTHROPIC_ZS_PROXY_API_KEY (or ANTHROPIC_ZS_PROXY_KEY), or fall back to ZS_PROXY_API_KEY."
                if proxy_mode
                else "ANTHROPIC_API_KEY is not set."
            ),
            "status_code": 500,
            "trace_step": {
                "name": "Anthropic",
                "request": trace_request,
                "response": {
                    "status": 500,
                    "body": {
                        "error": "Missing ZS_PROXY_API_KEY" if proxy_mode else "Missing ANTHROPIC_API_KEY"
                        ,
                        "proxy_key_envs_checked": (
                            ["ANTHROPIC_ZS_PROXY_API_KEY", "ANTHROPIC_ZS_PROXY_KEY", "ZS_PROXY_API_KEY"]
                            if proxy_mode
                            else None
                        ),
                    },
                },
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
        if proxy_mode:
            client = Anthropic(api_key=effective_api_key, base_url=proxy_base_url, default_headers=proxy_headers)
        else:
            client = Anthropic(api_key=effective_api_key)
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


def _anthropic_chat_messages(
    messages: list[dict],
    anthropic_model: str,
    *,
    proxy_mode: bool = False,
    conversation_id: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, proxy_key_source = _zscaler_proxy_sdk_config(
        "ANTHROPIC",
        conversation_id,
    )
    effective_api_key = proxy_key if proxy_mode else api_key
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
    trace_headers: dict[str, str] = {
        "x-api-key": "***redacted***" if effective_api_key else "***missing***"
    }
    if proxy_mode:
        trace_headers.update(
            {
                k: ("***redacted***" if k.lower() == proxy_api_key_header_name.lower() else v)
                for k, v in proxy_headers.items()
            }
        )
    trace_request = {
        "method": "SDK",
        "url": (
            f"{proxy_base_url} (Zscaler Proxy -> Anthropic SDK messages.create)"
            if proxy_mode
            else "Anthropic SDK (messages.create)"
        ),
        "headers": trace_headers,
        "payload": request_payload,
    }

    if not effective_api_key:
        return None, {
            "error": (
                "Anthropic proxy key is not set. Set ANTHROPIC_ZS_PROXY_API_KEY (or ANTHROPIC_ZS_PROXY_KEY), or fall back to ZS_PROXY_API_KEY."
                if proxy_mode
                else "ANTHROPIC_API_KEY is not set."
            ),
            "status_code": 500,
            "trace_step": {
                "name": "Anthropic",
                "request": trace_request,
                "response": {
                    "status": 500,
                    "body": {
                        "error": "Missing ZS_PROXY_API_KEY" if proxy_mode else "Missing ANTHROPIC_API_KEY"
                        ,
                        "proxy_key_envs_checked": (
                            ["ANTHROPIC_ZS_PROXY_API_KEY", "ANTHROPIC_ZS_PROXY_KEY", "ZS_PROXY_API_KEY"]
                            if proxy_mode
                            else None
                        ),
                    },
                },
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
        if proxy_mode:
            client = Anthropic(api_key=effective_api_key, base_url=proxy_base_url, default_headers=proxy_headers)
        else:
            client = Anthropic(api_key=effective_api_key)
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


def _openai_chat_messages(
    messages: list[dict],
    openai_model: str,
    *,
    proxy_mode: bool = False,
    conversation_id: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, proxy_key_source = _zscaler_proxy_sdk_config(
        "OPENAI",
        conversation_id,
    )
    effective_api_key = proxy_key if proxy_mode else api_key
    normalized = _normalize_messages(messages)
    request_payload = {
        "model": openai_model,
        "messages": normalized,
        "temperature": 0.2,
    }
    trace_headers: dict[str, str] = {
        "Authorization": "Bearer ***redacted***" if effective_api_key else "***missing***"
    }
    if proxy_mode:
        trace_headers.update(
            {
                k: ("***redacted***" if k.lower() == proxy_api_key_header_name.lower() else v)
                for k, v in proxy_headers.items()
            }
        )
    proxy_openai_base_url = _openai_proxy_base_url(proxy_base_url) if proxy_mode else proxy_base_url
    trace_request = {
        "method": "SDK",
        "url": (
            f"{proxy_openai_base_url}/chat/completions (Zscaler Proxy -> OpenAI SDK chat.completions.create)"
            if proxy_mode
            else "OpenAI SDK (chat.completions.create)"
        ),
        "headers": trace_headers,
        "payload": request_payload,
    }

    if not effective_api_key:
        return None, {
            "error": (
                "OpenAI proxy key is not set. Set OPENAI_ZS_PROXY_API_KEY (or OPENAI_ZS_PROXY_KEY), or fall back to ZS_PROXY_API_KEY."
                if proxy_mode
                else "OPENAI_API_KEY is not set."
            ),
            "status_code": 500,
            "trace_step": {
                "name": "OpenAI",
                "request": trace_request,
                "response": {
                    "status": 500,
                    "body": {
                        "error": "Missing ZS_PROXY_API_KEY" if proxy_mode else "Missing OPENAI_API_KEY",
                        "proxy_key_envs_checked": (
                            ["OPENAI_ZS_PROXY_API_KEY", "OPENAI_ZS_PROXY_KEY", "ZS_PROXY_API_KEY"]
                            if proxy_mode
                            else None
                        ),
                    },
                },
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
        if proxy_mode:
            client = OpenAI(
                api_key=effective_api_key,
                base_url=proxy_openai_base_url,
                default_headers=proxy_headers,
            )
        else:
            client = OpenAI(api_key=effective_api_key)
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
        err_status = getattr(exc, "status_code", None)
        err_response = getattr(exc, "response", None)
        err_body: Any = None
        if err_response is not None:
            try:
                if hasattr(err_response, "json"):
                    err_body = err_response.json()
            except Exception:
                err_body = None
            if err_body is None:
                err_body = getattr(err_response, "text", None)
        return None, {
            "error": "OpenAI request failed.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {
                "name": "OpenAI",
                "request": trace_request,
                "response": {
                    "status": int(err_status or 502),
                    "body": {
                        "error": str(exc),
                        "status_code": err_status,
                        "response_body": err_body,
                    },
                },
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
    zscaler_proxy_mode: bool = False,
    conversation_id: str | None = None,
) -> tuple[str | None, dict]:
    provider = (provider_id or "ollama").strip().lower()
    if provider == "anthropic":
        return _anthropic_chat_messages(
            messages,
            anthropic_model or DEFAULT_ANTHROPIC_MODEL,
            proxy_mode=zscaler_proxy_mode,
            conversation_id=conversation_id,
        )
    if provider == "openai":
        return _openai_chat_messages(
            messages,
            openai_model or DEFAULT_OPENAI_MODEL,
            proxy_mode=zscaler_proxy_mode,
            conversation_id=conversation_id,
        )
    if zscaler_proxy_mode and provider == "ollama":
        return None, {
            "error": "Zscaler Proxy Mode is not supported for Ollama (Local). Select a remote provider (Anthropic/OpenAI) or use DAS/API mode.",
            "status_code": 400,
            "trace_step": {
                "name": "Provider Selection",
                "request": {"provider": provider_id, "zscaler_proxy_mode": True},
                "response": {"status": 400, "body": {"error": "Unsupported provider for proxy mode"}},
            },
        }
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
    zscaler_proxy_mode: bool = False,
    conversation_id: str | None = None,
) -> tuple[str | None, dict]:
    return call_provider_messages(
        provider_id,
        [{"role": "user", "content": prompt}],
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        anthropic_model=anthropic_model,
        openai_model=openai_model,
        zscaler_proxy_mode=zscaler_proxy_mode,
        conversation_id=conversation_id,
    )
