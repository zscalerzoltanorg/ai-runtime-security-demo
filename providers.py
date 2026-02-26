import os
from typing import Any
import ast

from urllib import error, request
import json


DEFAULT_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DEFAULT_BEDROCK_INVOKE_MODEL = os.getenv("BEDROCK_INVOKE_MODEL", "amazon.nova-lite-v1:0")
DEFAULT_PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar")
DEFAULT_XAI_MODEL = os.getenv("XAI_MODEL", "grok-2-latest")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
DEFAULT_LITELLM_MODEL = os.getenv("LITELLM_MODEL", "claude-3-haiku-20240307")
DEFAULT_VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
DEFAULT_VERTEX_MODEL = os.getenv("VERTEX_MODEL", "gemini-1.5-flash")
DEFAULT_AZURE_AI_FOUNDRY_MODEL = os.getenv("AZURE_AI_FOUNDRY_MODEL", "gpt-4o-mini")
DEFAULT_ZS_PROXY_BASE_URL = os.getenv("ZS_PROXY_BASE_URL", "https://proxy.zseclipse.net")
DEFAULT_ZS_PROXY_API_KEY_HEADER_NAME = os.getenv("ZS_PROXY_API_KEY_HEADER_NAME", "X-ApiKey")
DEMO_USER_HEADER_NAME = "X-Demo-User"


def _proxy_guardrails_block_from_error(
    *,
    status_code: int | None,
    response_body: Any = None,
    details_text: str | None = None,
) -> dict[str, Any] | None:
    if int(status_code or 0) != 403:
        return None

    body: Any = response_body
    if body is None and details_text:
        txt = str(details_text)
        if " - " in txt:
            _, suffix = txt.split(" - ", 1)
            suffix = suffix.strip()
            if suffix.startswith("{") and suffix.endswith("}"):
                try:
                    body = ast.literal_eval(suffix)
                except Exception:
                    body = None
        if body is None and txt.strip().startswith("{") and txt.strip().endswith("}"):
            try:
                body = ast.literal_eval(txt.strip())
            except Exception:
                body = None

    if not isinstance(body, dict):
        return None

    reason = str(body.get("reason") or "")
    if "Zscaler AI Guard" not in reason and not any(k in body for k in ("policyName", "inputDetections", "outputDetections")):
        return None

    input_detections = body.get("inputDetections")
    output_detections = body.get("outputDetections")
    stage = "IN" if input_detections else ("OUT" if output_detections else "UNKNOWN")
    return {
        "reason": reason or "Your request was blocked by Zscaler AI Guard",
        "policyName": body.get("policyName"),
        "inputDetections": input_detections if isinstance(input_detections, list) else [],
        "outputDetections": output_detections if isinstance(output_detections, list) else [],
        "stage": stage,
        "raw": body,
        "status_code": 403,
    }


def available_providers() -> list[dict[str, str]]:
    return [
        {"id": "ollama", "label": "Ollama (Local)"},
        {"id": "anthropic", "label": "Anthropic"},
        {"id": "openai", "label": "OpenAI"},
        {"id": "bedrock_invoke", "label": "AWS Bedrock"},
        {"id": "bedrock_agent", "label": "AWS Bedrock Agent"},
        {"id": "perplexity", "label": "Perplexity"},
        {"id": "xai", "label": "xAI (Grok)"},
        {"id": "gemini", "label": "Google Gemini"},
        {"id": "vertex", "label": "Google Vertex"},
        {"id": "litellm", "label": "LiteLLM"},
        {"id": "azure_foundry", "label": "Azure AI Foundry"},
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
    demo_user: str | None = None,
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
    if demo_user:
        headers[DEMO_USER_HEADER_NAME] = str(demo_user)
    return proxy_key or None, base_url, api_key_header_name, headers, proxy_key_source


def _openai_proxy_base_url(base_url: str) -> str:
    cleaned = (base_url or "").rstrip("/")
    if cleaned.lower().endswith("/v1"):
        return cleaned
    return f"{cleaned}/v1"


def _openai_compatible_chat_messages(
    *,
    provider_name: str,
    api_key_env: str,
    model: str,
    default_base_url: str,
    base_url_env: str,
    messages: list[dict],
    conversation_id: str | None = None,
    demo_user: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv(api_key_env, "").strip()
    base_url = os.getenv(base_url_env, "").strip() or default_base_url
    normalized = _normalize_messages(messages)
    request_payload = {
        "model": model,
        "messages": normalized,
        "temperature": 0.2,
    }
    trace_request = {
        "method": "SDK",
        "url": f"{base_url.rstrip('/')}/chat/completions ({provider_name} via OpenAI-compatible SDK)",
        "headers": {
            "Authorization": "Bearer ***redacted***" if api_key else "***missing***",
            **(
                {os.getenv("ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME", "").strip(): conversation_id}
                if os.getenv("ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME", "").strip() and conversation_id
                else {}
            ),
            **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {}),
        },
        "payload": request_payload,
    }

    if not api_key:
        return None, {
            "error": f"{api_key_env} is not set.",
            "status_code": 500,
            "trace_step": {
                "name": provider_name,
                "request": trace_request,
                "response": {"status": 500, "body": {"error": f"Missing {api_key_env}"}},
            },
        }

    try:
        from openai import OpenAI
    except Exception as exc:
        return None, {
            "error": "OpenAI-compatible SDK is not installed.",
            "status_code": 500,
            "details": str(exc),
            "trace_step": {
                "name": provider_name,
                "request": trace_request,
                "response": {"status": 500, "body": {"error": "Install with `pip install openai`", "details": str(exc)}},
            },
        }

    default_headers = {}
    conv_header_name = os.getenv("ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME", "").strip()
    if conv_header_name and conversation_id:
        default_headers[conv_header_name] = str(conversation_id)
    if demo_user:
        default_headers[DEMO_USER_HEADER_NAME] = str(demo_user)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers or None)
        resp = client.chat.completions.create(**request_payload)
        choice0 = (getattr(resp, "choices", None) or [None])[0]
        message_obj = getattr(choice0, "message", None)
        text = str(getattr(message_obj, "content", "") or "").strip()
        usage_obj = getattr(resp, "usage", None)
        response_body: dict[str, Any] = {
            "id": getattr(resp, "id", None),
            "model": getattr(resp, "model", model),
            "object": getattr(resp, "object", None),
            "choices": [
                {
                    "index": getattr(choice0, "index", 0),
                    "finish_reason": getattr(choice0, "finish_reason", None),
                    "message": {"role": getattr(message_obj, "role", None), "content": text},
                }
            ] if choice0 is not None else [],
            "usage": usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else None,
        }
        return text, {
            "trace_step": {
                "name": provider_name,
                "request": trace_request,
                "response": {"status": 200, "body": response_body},
            }
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
            "error": f"{provider_name} request failed.",
            "status_code": int(err_status or 502),
            "details": str(exc),
            "trace_step": {
                "name": provider_name,
                "request": trace_request,
                "response": {
                    "status": int(err_status or 502),
                    "body": {"error": str(exc), "status_code": err_status, "response_body": err_body},
                },
            },
        }


def _ollama_generate(
    prompt: str, ollama_url: str, ollama_model: str, demo_user: str | None = None
) -> tuple[str | None, dict]:
    payload = {"model": ollama_model, "prompt": prompt, "stream": False}
    url = f"{ollama_url}/api/generate"
    headers = {"Content-Type": "application/json", **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {})}

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
    messages: list[dict], ollama_url: str, ollama_model: str, demo_user: str | None = None
) -> tuple[str | None, dict]:
    payload = {"model": ollama_model, "messages": _normalize_messages(messages), "stream": False}
    url = f"{ollama_url}/api/chat"
    headers = {"Content-Type": "application/json", **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {})}

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
    demo_user: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, proxy_key_source = _zscaler_proxy_sdk_config(
        "ANTHROPIC",
        conversation_id,
        demo_user,
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
    if demo_user:
        trace_headers[DEMO_USER_HEADER_NAME] = str(demo_user)
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
            client = Anthropic(
                api_key=effective_api_key,
                default_headers=({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else None),
            )
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
        proxy_block = (
            _proxy_guardrails_block_from_error(
                status_code=int(err_status or 0) if err_status else None,
                response_body=err_body,
                details_text=str(exc),
            )
            if proxy_mode
            else None
        )
        return None, {
            "error": "Anthropic request failed.",
            "status_code": int(err_status or 502),
            "details": str(exc),
            **({"proxy_guardrails_block": proxy_block} if proxy_block else {}),
            "trace_step": {
                "name": "Anthropic",
                "request": trace_request,
                "response": {
                    "status": int(err_status or 502),
                    "body": {
                        "error": str(exc),
                        **({"status_code": err_status} if err_status is not None else {}),
                        **({"response_body": err_body} if err_body is not None else {}),
                    },
                },
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
    demo_user: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, proxy_key_source = _zscaler_proxy_sdk_config(
        "ANTHROPIC",
        conversation_id,
        demo_user,
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
    if demo_user:
        trace_headers[DEMO_USER_HEADER_NAME] = str(demo_user)
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
            client = Anthropic(
                api_key=effective_api_key,
                default_headers=({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else None),
            )
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
        proxy_block = (
            _proxy_guardrails_block_from_error(
                status_code=int(err_status or 0) if err_status else None,
                response_body=err_body,
                details_text=str(exc),
            )
            if proxy_mode
            else None
        )
        return None, {
            "error": "Anthropic request failed.",
            "status_code": int(err_status or 502),
            "details": str(exc),
            **({"proxy_guardrails_block": proxy_block} if proxy_block else {}),
            "trace_step": {
                "name": "Anthropic",
                "request": trace_request,
                "response": {
                    "status": int(err_status or 502),
                    "body": {
                        "error": str(exc),
                        **({"status_code": err_status} if err_status is not None else {}),
                        **({"response_body": err_body} if err_body is not None else {}),
                    },
                },
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
    demo_user: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, proxy_key_source = _zscaler_proxy_sdk_config(
        "OPENAI",
        conversation_id,
        demo_user,
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
    if demo_user:
        trace_headers[DEMO_USER_HEADER_NAME] = str(demo_user)
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
            client = OpenAI(
                api_key=effective_api_key,
                default_headers=({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else None),
            )
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
        proxy_block = (
            _proxy_guardrails_block_from_error(
                status_code=int(err_status or 0) if err_status else None,
                response_body=err_body,
                details_text=str(exc),
            )
            if proxy_mode
            else None
        )
        return None, {
            "error": "OpenAI request failed.",
            "status_code": int(err_status or 502),
            "details": str(exc),
            **({"proxy_guardrails_block": proxy_block} if proxy_block else {}),
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


def _bedrock_invoke_chat_messages(
    messages: list[dict],
    model_id: str,
    *,
    region: str,
) -> tuple[str | None, dict]:
    normalized = _normalize_messages(messages)
    system_blocks = [m["content"] for m in normalized if m["role"] == "system" and m["content"].strip()]
    request_payload = {
        "modelId": model_id,
        "messages": [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in normalized
            if m["role"] in {"user", "assistant"}
        ],
        "inferenceConfig": {"maxTokens": 400, "temperature": 0.2},
    }
    if system_blocks:
        request_payload["system"] = [{"text": "\n\n".join(system_blocks)}]
    trace_request = {
        "method": "SDK",
        "url": f"AWS Bedrock Runtime (converse) [{region}]",
        "headers": {"Authorization": "AWS SigV4 (ambient credentials)"},
        "payload": request_payload,
    }
    try:
        import boto3
    except Exception as exc:
        return None, {
            "error": "boto3 is not installed.",
            "status_code": 500,
            "details": str(exc),
            "trace_step": {"name": "AWS Bedrock (Nova Lite)", "request": trace_request, "response": {"status": 500, "body": {"error": "Install with `pip install boto3`", "details": str(exc)}}},
        }
    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        resp = client.converse(**request_payload)
        text = "".join(
            part.get("text", "")
            for part in (((resp.get("output") or {}).get("message") or {}).get("content") or [])
            if isinstance(part, dict) and "text" in part
        ).strip()
        return text, {
            "trace_step": {
                "name": "AWS Bedrock (Nova Lite)",
                "request": trace_request,
                "response": {"status": 200, "body": {
                    "modelId": model_id,
                    "text": text,
                    "usage": resp.get("usage"),
                    "stopReason": resp.get("stopReason"),
                }},
            }
        }
    except Exception as exc:
        return None, {
            "error": "Bedrock invoke request failed.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {"name": "AWS Bedrock (Nova Lite)", "request": trace_request, "response": {"status": 502, "body": {"error": str(exc)}}},
        }


def _bedrock_agent_chat_messages(
    messages: list[dict],
    *,
    region: str,
    conversation_id: str | None = None,
) -> tuple[str | None, dict]:
    agent_id = os.getenv("BEDROCK_AGENT_ID", "").strip()
    alias_id = os.getenv("BEDROCK_AGENT_ALIAS_ID", "").strip()
    normalized = _normalize_messages(messages)
    latest_user = ""
    for m in reversed(normalized):
        if m.get("role") == "user":
            latest_user = str(m.get("content") or "")
            break
    if not latest_user:
        latest_user = str((normalized[-1].get("content") if normalized else "") or "")
    session_id = (conversation_id or os.getenv("BEDROCK_AGENT_SESSION_ID") or "local-llm-demo-session").strip()
    request_payload = {
        "agentId": agent_id,
        "agentAliasId": alias_id,
        "sessionId": session_id,
        "inputText": latest_user,
    }
    trace_request = {
        "method": "SDK",
        "url": f"AWS Bedrock Agent Runtime (invoke_agent) [{region}]",
        "headers": {"Authorization": "AWS SigV4 (ambient credentials)"},
        "payload": request_payload,
    }
    if not agent_id or not alias_id:
        return None, {
            "error": "BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS_ID are required.",
            "status_code": 500,
            "trace_step": {"name": "AWS Bedrock Agent", "request": trace_request, "response": {"status": 500, "body": {"error": "Missing BEDROCK_AGENT_ID/BEDROCK_AGENT_ALIAS_ID"}}},
        }
    try:
        import boto3
    except Exception as exc:
        return None, {
            "error": "boto3 is not installed.",
            "status_code": 500,
            "details": str(exc),
            "trace_step": {"name": "AWS Bedrock Agent", "request": trace_request, "response": {"status": 500, "body": {"error": "Install with `pip install boto3`", "details": str(exc)}}},
        }
    try:
        client = boto3.client("bedrock-agent-runtime", region_name=region)
        resp = client.invoke_agent(**request_payload)
        chunks: list[str] = []
        completion = resp.get("completion")
        if completion is not None:
            for event in completion:
                if not isinstance(event, dict):
                    continue
                chunk = event.get("chunk")
                if isinstance(chunk, dict):
                    b = chunk.get("bytes")
                    if isinstance(b, (bytes, bytearray)):
                        chunks.append(b.decode("utf-8", errors="replace"))
                    elif isinstance(b, str):
                        chunks.append(b)
        text = "".join(chunks).strip()
        return text, {
            "trace_step": {
                "name": "AWS Bedrock Agent",
                "request": trace_request,
                "response": {"status": 200, "body": {"sessionId": session_id, "text": text}},
            }
        }
    except Exception as exc:
        return None, {
            "error": "Bedrock agent request failed.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {"name": "AWS Bedrock Agent", "request": trace_request, "response": {"status": 502, "body": {"error": str(exc)}}},
        }


def _gemini_chat_messages(
    messages: list[dict],
    model: str,
    demo_user: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
    normalized = _normalize_messages(messages)
    contents = []
    system_parts = []
    for m in normalized:
        role = m.get("role")
        content = str(m.get("content") or "")
        if role == "system":
            if content.strip():
                system_parts.append(content)
            continue
        gem_role = "user" if role == "user" else "model"
        contents.append({"role": gem_role, "parts": [{"text": content}]})
    payload: dict[str, Any] = {"contents": contents}
    if system_parts:
        payload["system_instruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key if api_key else '***missing***'}"
    trace_request = {
        "method": "POST",
        "url": f"{base_url}/v1beta/models/{model}:generateContent",
        "headers": {
            "x-goog-api-key": "***redacted***" if api_key else "***missing***",
            "Content-Type": "application/json",
            **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {}),
        },
        "payload": payload,
    }
    if not api_key:
        return None, {
            "error": "GEMINI_API_KEY is not set.",
            "status_code": 500,
            "trace_step": {"name": "Google Gemini", "request": trace_request, "response": {"status": 500, "body": {"error": "Missing GEMINI_API_KEY"}}},
        }
    try:
        status, body = _post_json(
            f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}",
            payload=payload,
            headers={"Content-Type": "application/json", **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {})},
            timeout=120,
        )
        text = ""
        if isinstance(body, dict):
            for cand in body.get("candidates") or []:
                content = cand.get("content") or {}
                for part in content.get("parts") or []:
                    if isinstance(part, dict) and "text" in part:
                        text += str(part.get("text") or "")
        return text.strip(), {
            "trace_step": {"name": "Google Gemini", "request": trace_request, "response": {"status": status, "body": body}}
        }
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(detail)
        except Exception:
            parsed = detail
        return None, {
            "error": "Gemini request failed.",
            "status_code": 502,
            "details": detail,
            "trace_step": {"name": "Google Gemini", "request": trace_request, "response": {"status": exc.code, "body": parsed}},
        }
    except Exception as exc:
        return None, {
            "error": "Gemini request failed.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {"name": "Google Gemini", "request": trace_request, "response": {"status": 502, "body": {"error": str(exc)}}},
        }


def _vertex_chat_messages(
    messages: list[dict],
    model: str,
    *,
    project_id: str,
    location: str,
    demo_user: str | None = None,
) -> tuple[str | None, dict]:
    normalized = _normalize_messages(messages)
    contents = []
    system_parts = []
    for m in normalized:
        role = m.get("role")
        content = str(m.get("content") or "")
        if role == "system":
            if content.strip():
                system_parts.append(content)
            continue
        vertex_role = "user" if role == "user" else "model"
        contents.append({"role": vertex_role, "parts": [{"text": content}]})
    payload: dict[str, Any] = {"contents": contents}
    if system_parts:
        payload["system_instruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    endpoint = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}"
        f"/publishers/google/models/{model}:generateContent"
    )
    trace_request = {
        "method": "POST",
        "url": endpoint,
        "headers": {
            "Authorization": "Bearer ***redacted***",
            "Content-Type": "application/json",
            **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {}),
        },
        "payload": payload,
    }
    if not project_id:
        return None, {
            "error": "VERTEX_PROJECT_ID is not set.",
            "status_code": 500,
            "trace_step": {"name": "Google Vertex", "request": trace_request, "response": {"status": 500, "body": {"error": "Missing VERTEX_PROJECT_ID"}}},
        }
    try:
        import google.auth  # type: ignore
        from google.auth.transport.requests import Request as GoogleAuthRequest  # type: ignore
    except Exception as exc:
        return None, {
            "error": "google-auth is not installed.",
            "status_code": 500,
            "details": str(exc),
            "trace_step": {"name": "Google Vertex", "request": trace_request, "response": {"status": 500, "body": {"error": "Install with `pip install google-auth requests`", "details": str(exc)}}},
        }
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not credentials.valid:
            credentials.refresh(GoogleAuthRequest())
        token = credentials.token
        status, body = _post_json(
            endpoint,
            payload=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {}),
            },
            timeout=120,
        )
        text = ""
        if isinstance(body, dict):
            for cand in body.get("candidates") or []:
                content = cand.get("content") or {}
                for part in content.get("parts") or []:
                    if isinstance(part, dict) and "text" in part:
                        text += str(part.get("text") or "")
        return text.strip(), {
            "trace_step": {"name": "Google Vertex", "request": trace_request, "response": {"status": status, "body": body}}
        }
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
        except Exception:
            parsed = detail
        return None, {
            "error": "Google Vertex request failed.",
            "status_code": 502,
            "details": detail,
            "trace_step": {"name": "Google Vertex", "request": trace_request, "response": {"status": exc.code, "body": parsed}},
        }
    except Exception as exc:
        return None, {
            "error": "Google Vertex request failed.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {"name": "Google Vertex", "request": trace_request, "response": {"status": 502, "body": {"error": str(exc)}}},
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
    demo_user: str | None = None,
) -> tuple[str | None, dict]:
    provider = (provider_id or "ollama").strip().lower()
    aws_region = os.getenv("AWS_REGION", DEFAULT_AWS_REGION).strip() or DEFAULT_AWS_REGION
    if zscaler_proxy_mode and provider not in {"anthropic", "openai"}:
        return None, {
            "error": "Zscaler Proxy Mode is currently supported only for Anthropic and OpenAI in this demo. Use DAS/API mode for the selected provider.",
            "status_code": 400,
            "trace_step": {
                "name": "Provider Selection",
                "request": {"provider": provider_id, "zscaler_proxy_mode": True},
                "response": {"status": 400, "body": {"error": "Unsupported provider for proxy mode"}},
            },
        }
    if provider == "anthropic":
        return _anthropic_chat_messages(
            messages,
            anthropic_model or DEFAULT_ANTHROPIC_MODEL,
            proxy_mode=zscaler_proxy_mode,
            conversation_id=conversation_id,
            demo_user=demo_user,
        )
    if provider == "openai":
        return _openai_chat_messages(
            messages,
            openai_model or DEFAULT_OPENAI_MODEL,
            proxy_mode=zscaler_proxy_mode,
            conversation_id=conversation_id,
            demo_user=demo_user,
        )
    if provider == "bedrock_invoke":
        return _bedrock_invoke_chat_messages(
            messages,
            os.getenv("BEDROCK_INVOKE_MODEL", DEFAULT_BEDROCK_INVOKE_MODEL).strip() or DEFAULT_BEDROCK_INVOKE_MODEL,
            region=aws_region,
        )
    if provider == "bedrock_agent":
        return _bedrock_agent_chat_messages(
            messages,
            region=aws_region,
            conversation_id=conversation_id,
        )
    if provider == "perplexity":
        return _openai_compatible_chat_messages(
            provider_name="Perplexity",
            api_key_env="PERPLEXITY_API_KEY",
            model=os.getenv("PERPLEXITY_MODEL", DEFAULT_PERPLEXITY_MODEL).strip() or DEFAULT_PERPLEXITY_MODEL,
            default_base_url=os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai").strip() or "https://api.perplexity.ai",
            base_url_env="PERPLEXITY_BASE_URL",
            messages=messages,
            conversation_id=conversation_id,
            demo_user=demo_user,
        )
    if provider == "xai":
        return _openai_compatible_chat_messages(
            provider_name="xAI (Grok)",
            api_key_env="XAI_API_KEY",
            model=os.getenv("XAI_MODEL", DEFAULT_XAI_MODEL).strip() or DEFAULT_XAI_MODEL,
            default_base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").strip() or "https://api.x.ai/v1",
            base_url_env="XAI_BASE_URL",
            messages=messages,
            conversation_id=conversation_id,
            demo_user=demo_user,
        )
    if provider == "gemini":
        return _gemini_chat_messages(
            messages,
            os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL,
            demo_user=demo_user,
        )
    if provider == "vertex":
        return _vertex_chat_messages(
            messages,
            os.getenv("VERTEX_MODEL", DEFAULT_VERTEX_MODEL).strip() or DEFAULT_VERTEX_MODEL,
            project_id=os.getenv("VERTEX_PROJECT_ID", "").strip(),
            location=os.getenv("VERTEX_LOCATION", DEFAULT_VERTEX_LOCATION).strip() or DEFAULT_VERTEX_LOCATION,
            demo_user=demo_user,
        )
    if provider == "litellm":
        return _openai_compatible_chat_messages(
            provider_name="LiteLLM",
            api_key_env="LITELLM_API_KEY",
            model=os.getenv("LITELLM_MODEL", DEFAULT_LITELLM_MODEL).strip() or DEFAULT_LITELLM_MODEL,
            default_base_url=os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1").strip() or "http://127.0.0.1:4000/v1",
            base_url_env="LITELLM_BASE_URL",
            messages=messages,
            conversation_id=conversation_id,
            demo_user=demo_user,
        )
    if provider == "azure_foundry":
        return _openai_compatible_chat_messages(
            provider_name="Azure AI Foundry",
            api_key_env="AZURE_AI_FOUNDRY_API_KEY",
            model=os.getenv("AZURE_AI_FOUNDRY_MODEL", DEFAULT_AZURE_AI_FOUNDRY_MODEL).strip() or DEFAULT_AZURE_AI_FOUNDRY_MODEL,
            default_base_url=os.getenv("AZURE_AI_FOUNDRY_BASE_URL", "").strip() or "https://example.inference.ai.azure.com/v1",
            base_url_env="AZURE_AI_FOUNDRY_BASE_URL",
            messages=messages,
            conversation_id=conversation_id,
            demo_user=demo_user,
        )
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
    return _ollama_chat_messages(
        messages, ollama_url=ollama_url, ollama_model=ollama_model, demo_user=demo_user
    )


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
    demo_user: str | None = None,
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
        demo_user=demo_user,
    )
