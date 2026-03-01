import ast
import json
import os
import re
from dataclasses import dataclass
from hashlib import sha1
from typing import Any
from urllib import error, request

from tooling import ToolDef


def _env_or_default(name: str, default: str) -> str:
    raw = str(os.getenv(name, "")).strip()
    return raw or default


DEFAULT_ANTHROPIC_MODEL = _env_or_default("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
DEFAULT_OPENAI_MODEL = _env_or_default("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_AWS_REGION = _env_or_default("AWS_REGION", "us-east-1")
DEFAULT_BEDROCK_INVOKE_MODEL = _env_or_default("BEDROCK_INVOKE_MODEL", "amazon.nova-lite-v1:0")
DEFAULT_PERPLEXITY_MODEL = _env_or_default("PERPLEXITY_MODEL", "sonar")
DEFAULT_XAI_MODEL = _env_or_default("XAI_MODEL", "grok-4")
DEFAULT_GEMINI_MODEL = _env_or_default("GEMINI_MODEL", "gemini-1.5-flash")
DEFAULT_LITELLM_MODEL = _env_or_default("LITELLM_MODEL", "claude-3-haiku-20240307")
DEFAULT_KONG_MODEL = _env_or_default("KONG_MODEL", "")
DEFAULT_VERTEX_LOCATION = _env_or_default("VERTEX_LOCATION", "us-central1")
DEFAULT_VERTEX_MODEL = _env_or_default("VERTEX_MODEL", "gemini-1.5-flash")
DEFAULT_AZURE_AI_FOUNDRY_MODEL = _env_or_default("AZURE_AI_FOUNDRY_MODEL", "gpt-4o-mini")
DEFAULT_ZS_PROXY_BASE_URL = _env_or_default("ZS_PROXY_BASE_URL", "https://proxy.zseclipse.net")
DEFAULT_ZS_PROXY_API_KEY_HEADER_NAME = _env_or_default("ZS_PROXY_API_KEY_HEADER_NAME", "X-ApiKey")
DEMO_USER_HEADER_NAME = "X-Demo-User"
DEFAULT_INCLUDE_TOOLS_IN_LLM_REQUEST = False
DEFAULT_MAX_TOOLS_IN_REQUEST = 20
DEFAULT_TOOL_INCLUDE_MODE = "all"
DEFAULT_TOOL_NAME_PREFIX_STRATEGY = "serverPrefix"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _csv_env(name: str) -> set[str]:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


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

    if isinstance(body, dict) and "Error" in body and isinstance(body.get("Error"), dict):
        err_obj = body.get("Error") or {}
        err_code = str(err_obj.get("Code") or "").strip()
        nested_msg = err_obj.get("Message")
        if isinstance(nested_msg, str) and nested_msg.strip():
            msg = nested_msg.strip()
            parsed_nested: Any = None
            if msg.startswith("{") and msg.endswith("}"):
                try:
                    parsed_nested = json.loads(msg)
                except Exception:
                    try:
                        parsed_nested = ast.literal_eval(msg)
                    except Exception:
                        parsed_nested = None
            if isinstance(parsed_nested, dict):
                body = parsed_nested
            else:
                body = {"reason": msg}
        elif err_code == "403":
            return {
                "reason": "Request was rejected by Zscaler AI Guard proxy (HTTP 403)",
                "policyName": None,
                "inputDetections": [],
                "outputDetections": [],
                "stage": "UNKNOWN",
                "raw": body,
                "status_code": 403,
            }

    if not isinstance(body, dict):
        return {
            "reason": "Request was rejected by Zscaler AI Guard proxy (HTTP 403)",
            "policyName": None,
            "inputDetections": [],
            "outputDetections": [],
            "stage": "UNKNOWN",
            "raw": body if body is not None else details_text,
            "status_code": 403,
        }

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
        {"id": "kong", "label": "Kong Gateway"},
        {"id": "azure_foundry", "label": "Azure AI Foundry"},
    ]


@dataclass
class ProviderToolingContext:
    include_tools: bool
    include_mode: str
    max_tools: int
    name_strategy: str
    available_count: int
    included_count: int
    dropped_count: int
    supported: bool
    reason: str
    provider_tool_map: dict[str, dict[str, Any]]
    provider_tools_payload: list[dict[str, Any]]


class ProviderAdapter:
    provider_id = "base"

    def build_request(
        self,
        *,
        messages: list[dict],
        model: str,
        tool_defs: list[ToolDef] | None,
        settings: ProviderToolingContext,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def parse_response(self, provider_response: Any) -> dict[str, Any]:
        raise NotImplementedError

    def tool_call_to_mcp(self, tool_call: dict[str, Any], settings: ProviderToolingContext) -> dict[str, Any] | None:
        raise NotImplementedError


def _sanitize_provider_tool_name(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw or "tool"))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:64] or "tool"


def _anthropic_tool_name(tool: ToolDef, strategy: str) -> str:
    base = _sanitize_provider_tool_name(tool.name)
    if strategy == "none":
        return base
    if strategy == "hash":
        digest = sha1(tool.id.encode("utf-8")).hexdigest()[:12]
        return f"t_{digest}"
    server = _sanitize_provider_tool_name(tool.source_server)[:18] or "mcp"
    suffix = sha1(tool.id.encode("utf-8")).hexdigest()[:6]
    combined = f"{server}_{base}"
    if len(combined) > 56:
        combined = combined[:56]
    return f"{combined}_{suffix}"


def _select_tool_defs(tool_defs: list[ToolDef], include_mode: str, max_tools: int) -> tuple[list[ToolDef], str]:
    selected = list(tool_defs or [])
    mode = (include_mode or DEFAULT_TOOL_INCLUDE_MODE).strip().lower()
    if mode not in {"all", "allowlist", "progressive"}:
        mode = DEFAULT_TOOL_INCLUDE_MODE
    reason = f"mode={mode}"
    if mode == "allowlist":
        allowlist = _csv_env("TOOL_ALLOWLIST")
        if allowlist:
            selected = [t for t in selected if t.name in allowlist or t.id in allowlist]
        else:
            selected = []
        reason = f"{reason},allowlist={len(allowlist)}"
    elif mode == "progressive":
        progressive_count = _int_env("TOOL_PROGRESSIVE_COUNT", min(5, max_tools))
        selected = selected[: max(0, progressive_count)]
        reason = f"{reason},progressive_count={progressive_count}"
    return selected[: max(0, max_tools)], reason


def _build_anthropic_tool_payload(
    tool_defs: list[ToolDef] | None,
) -> ProviderToolingContext:
    include_tools = _bool_env("INCLUDE_TOOLS_IN_LLM_REQUEST", DEFAULT_INCLUDE_TOOLS_IN_LLM_REQUEST)
    include_mode = str(os.getenv("TOOL_INCLUDE_MODE", DEFAULT_TOOL_INCLUDE_MODE)).strip() or DEFAULT_TOOL_INCLUDE_MODE
    max_tools = max(0, _int_env("MAX_TOOLS_IN_REQUEST", DEFAULT_MAX_TOOLS_IN_REQUEST))
    name_strategy = (
        str(os.getenv("TOOL_NAME_PREFIX_STRATEGY", DEFAULT_TOOL_NAME_PREFIX_STRATEGY)).strip()
        or DEFAULT_TOOL_NAME_PREFIX_STRATEGY
    )
    available = list(tool_defs or [])
    if not include_tools:
        return ProviderToolingContext(
            include_tools=False,
            include_mode=include_mode,
            max_tools=max_tools,
            name_strategy=name_strategy,
            available_count=len(available),
            included_count=0,
            dropped_count=len(available),
            supported=True,
            reason="INCLUDE_TOOLS_IN_LLM_REQUEST=false",
            provider_tool_map={},
            provider_tools_payload=[],
        )

    selected, reason = _select_tool_defs(available, include_mode, max_tools)
    provider_tools: list[dict[str, Any]] = []
    provider_tool_map: dict[str, dict[str, Any]] = {}
    used_names: set[str] = set()
    for idx, tool in enumerate(selected):
        provider_name = _anthropic_tool_name(tool, name_strategy)
        if provider_name in used_names:
            provider_name = f"{provider_name[:52]}_{idx:02d}"
        used_names.add(provider_name)
        provider_tools.append(
            {
                "name": provider_name,
                "description": tool.description,
                "input_schema": tool.input_schema or {"type": "object", "properties": {}},
            }
        )
        provider_tool_map[provider_name] = {
            "mcp_tool_id": tool.id,
            "mcp_tool_name": tool.name,
            "source_server": tool.source_server,
        }
    return ProviderToolingContext(
        include_tools=True,
        include_mode=include_mode,
        max_tools=max_tools,
        name_strategy=name_strategy,
        available_count=len(available),
        included_count=len(provider_tools),
        dropped_count=max(0, len(available) - len(provider_tools)),
        supported=True,
        reason=reason,
        provider_tool_map=provider_tool_map,
        provider_tools_payload=provider_tools,
    )


class AnthropicAdapter(ProviderAdapter):
    provider_id = "anthropic"

    def build_request(
        self,
        *,
        messages: list[dict],
        model: str,
        tool_defs: list[ToolDef] | None,
        settings: ProviderToolingContext,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "max_tokens": 400,
            "temperature": 0.2,
            "messages": messages,
        }
        if settings.provider_tools_payload:
            payload["tools"] = settings.provider_tools_payload
        return payload

    def parse_response(self, provider_response: Any) -> dict[str, Any]:
        text = "".join(
            block.text
            for block in getattr(provider_response, "content", [])
            if getattr(block, "type", None) == "text"
        ).strip()
        tool_calls: list[dict[str, Any]] = []
        for block in getattr(provider_response, "content", []):
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_calls.append(
                {
                    "id": getattr(block, "id", None),
                    "name": getattr(block, "name", None),
                    "args": getattr(block, "input", {}) or {},
                }
            )
        return {"assistant_text": text, "tool_calls": tool_calls}

    def tool_call_to_mcp(self, tool_call: dict[str, Any], settings: ProviderToolingContext) -> dict[str, Any] | None:
        provider_name = str(tool_call.get("name") or "").strip()
        mapped = settings.provider_tool_map.get(provider_name)
        if not mapped:
            return None
        return {
            "mcp_server": mapped.get("source_server"),
            "tool_name": mapped.get("mcp_tool_name"),
            "args": tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {},
        }


# Stub adapter notes for extension:
# - OpenAI-style tools use `tools=[{\"type\":\"function\",\"function\":{...}}]` and tool calls
#   appear in `choices[0].message.tool_calls[*].function`.
# - Bedrock tool formats vary by API (Converse vs Agent Runtime), with provider-specific schema
#   wrappers and different tool-call response shapes.


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
            item: dict[str, Any] = {"role": role, "content": content}
            raw_attachments = msg.get("attachments")
            if isinstance(raw_attachments, list):
                cleaned = []
                for raw in raw_attachments[:4]:
                    if not isinstance(raw, dict):
                        continue
                    kind = str(raw.get("kind") or "").strip().lower()
                    name = str(raw.get("name") or "attachment").strip()[:120]
                    mime = str(raw.get("mime") or "").strip()[:120]
                    if kind == "image":
                        data_url = str(raw.get("data_url") or "")
                        if data_url.startswith("data:image/") and len(data_url) <= 2_500_000:
                            cleaned.append({"kind": "image", "name": name, "mime": mime, "data_url": data_url})
                    elif kind == "text":
                        text = str(raw.get("text") or "")
                        cleaned.append(
                            {
                                "kind": "text",
                                "name": name,
                                "mime": mime or "text/plain",
                                "text": text[:16_000],
                                "truncated": bool(raw.get("truncated")) or len(text) > 16_000,
                            }
                        )
                if cleaned:
                    item["attachments"] = cleaned
            normalized.append(item)
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
    for env_name in provider_key_envs:
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


def _attachment_text_suffix(msg: dict[str, Any]) -> str:
    attachments = msg.get("attachments")
    if not isinstance(attachments, list):
        return ""
    rows: list[str] = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        if str(att.get("kind") or "").strip().lower() != "text":
            continue
        name = str(att.get("name") or "attachment").strip()
        text = str(att.get("text") or "")
        if not text:
            continue
        rows.append(f"[Attachment: {name}]\n{text}")
    return ("\n\n" + "\n\n".join(rows)) if rows else ""


def _parse_image_data_url(data_url: str) -> tuple[str | None, str | None]:
    raw = str(data_url or "")
    m = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", raw, re.DOTALL)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _openai_messages_with_attachments(normalized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in normalized:
        role = str(msg.get("role") or "user")
        text = str(msg.get("content") or "") + _attachment_text_suffix(msg)
        attachments = msg.get("attachments")
        if role == "system" or not isinstance(attachments, list):
            out.append({"role": role, "content": text})
            continue
        image_parts = []
        for att in attachments:
            if not isinstance(att, dict):
                continue
            if str(att.get("kind") or "").strip().lower() != "image":
                continue
            data_url = str(att.get("data_url") or "")
            media_type, data_b64 = _parse_image_data_url(data_url)
            if not media_type or not data_b64:
                continue
            image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
        if image_parts:
            parts = [{"type": "text", "text": text or "(image attachment)"}] + image_parts
            out.append({"role": role, "content": parts})
        else:
            out.append({"role": role, "content": text})
    return out


def _anthropic_messages_with_attachments(normalized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in normalized:
        role = str(msg.get("role") or "user")
        text = str(msg.get("content") or "") + _attachment_text_suffix(msg)
        attachments = msg.get("attachments")
        if role == "system" or not isinstance(attachments, list):
            out.append({"role": role, "content": text})
            continue
        content_blocks: list[dict[str, Any]] = []
        if text:
            content_blocks.append({"type": "text", "text": text})
        if role == "user":
            for att in attachments:
                if not isinstance(att, dict):
                    continue
                if str(att.get("kind") or "").strip().lower() != "image":
                    continue
                media_type, data_b64 = _parse_image_data_url(str(att.get("data_url") or ""))
                if not media_type or not data_b64:
                    continue
                content_blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data_b64,
                        },
                    }
                )
        out.append({"role": role, "content": content_blocks if content_blocks else text})
    return out


def _ollama_messages_with_attachments(normalized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in normalized:
        role = str(msg.get("role") or "user")
        text = str(msg.get("content") or "") + _attachment_text_suffix(msg)
        item: dict[str, Any] = {"role": role, "content": text}
        attachments = msg.get("attachments")
        if role == "user" and isinstance(attachments, list):
            images: list[str] = []
            for att in attachments:
                if not isinstance(att, dict):
                    continue
                if str(att.get("kind") or "").strip().lower() != "image":
                    continue
                _media_type, data_b64 = _parse_image_data_url(str(att.get("data_url") or ""))
                if data_b64:
                    images.append(data_b64)
            if images:
                item["images"] = images
        out.append(item)
    return out


def _gemini_parts_from_message(msg: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    text = str(msg.get("content") or "") + _attachment_text_suffix(msg)
    if text:
        parts.append({"text": text})
    attachments = msg.get("attachments")
    if isinstance(attachments, list):
        for att in attachments:
            if not isinstance(att, dict):
                continue
            if str(att.get("kind") or "").strip().lower() != "image":
                continue
            media_type, data_b64 = _parse_image_data_url(str(att.get("data_url") or ""))
            if not media_type or not data_b64:
                continue
            parts.append({"inline_data": {"mime_type": media_type, "data": data_b64}})
    return parts or [{"text": ""}]


def _bedrock_client_auth_kwargs() -> tuple[dict[str, str], str]:
    access_key_id = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    session_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
    if access_key_id and secret_access_key:
        kwargs = {
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
        }
        if session_token:
            kwargs["aws_session_token"] = session_token
            return kwargs, "env_keys+session_token"
        return kwargs, "env_keys"
    return {}, "ambient"


def _bedrock_botocore_config(*, proxy_mode: bool, unsigned: bool = False) -> Any:
    from botocore import UNSIGNED
    from botocore.config import Config as BotocoreConfig

    connect_default = 5 if proxy_mode else 10
    read_default = 12 if proxy_mode else 30
    connect_timeout = _int_env("BEDROCK_CONNECT_TIMEOUT_SECONDS", connect_default)
    read_timeout = _int_env("BEDROCK_READ_TIMEOUT_SECONDS", read_default)
    default_attempts = 1 if proxy_mode else 3
    max_attempts = _int_env("BEDROCK_MAX_ATTEMPTS", default_attempts)
    kwargs: dict[str, Any] = {
        "connect_timeout": max(1, connect_timeout),
        "read_timeout": max(1, read_timeout),
        "retries": {"max_attempts": max(1, max_attempts), "mode": "standard"},
    }
    if unsigned:
        kwargs["signature_version"] = UNSIGNED
    return BotocoreConfig(**kwargs)


def aws_auth_status(*, region: str | None = None) -> dict[str, Any]:
    auth_kwargs, auth_source = _bedrock_client_auth_kwargs()
    if auth_kwargs:
        key_id = str(auth_kwargs.get("aws_access_key_id") or "")
        return {
            "ok": True,
            "source": auth_source,
            "label": "Env Keys",
            "details": f"AWS_ACCESS_KEY_ID set ({'***' + key_id[-4:] if key_id else 'hidden'})",
        }
    try:
        import boto3
    except Exception as exc:
        return {
            "ok": False,
            "source": "unavailable",
            "label": "Unavailable",
            "details": f"boto3 not installed: {exc}",
        }
    try:
        session = boto3.Session(region_name=region or None)
        creds = session.get_credentials()
        frozen = creds.get_frozen_credentials() if creds else None
        if not frozen:
            return {
                "ok": False,
                "source": "none",
                "label": "Not Configured",
                "details": "No ambient AWS credentials detected. Configure env keys or local AWS profile/SSO.",
            }
        method = str(getattr(creds, "method", "") or "unknown")
        access_key = str(getattr(frozen, "access_key", "") or "")
        if "role" in method:
            label = "Role"
        elif "sso" in method:
            label = "SSO"
        elif method == "env":
            label = "Env (Ambient)"
        elif "shared" in method or "config" in method:
            label = "Profile"
        else:
            label = "Ambient"
        return {
            "ok": True,
            "source": f"ambient:{method}",
            "label": label,
            "details": f"Credential source `{method}` ({'***' + access_key[-4:] if access_key else 'hidden'})",
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": "error",
            "label": "Unavailable",
            "details": str(exc),
        }


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
    proxy_mode: bool = False,
    proxy_provider_family: str | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv(api_key_env, "").strip()
    base_url = os.getenv(base_url_env, "").strip() or default_base_url
    proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, _proxy_key_source = _zscaler_proxy_sdk_config(
        proxy_provider_family or provider_name,
        conversation_id,
        demo_user,
    )
    effective_api_key = proxy_key if proxy_mode else api_key
    effective_base_url = _openai_proxy_base_url(proxy_base_url) if proxy_mode else base_url
    normalized = _normalize_messages(messages)
    request_payload = {
        "model": model,
        "messages": _openai_messages_with_attachments(normalized),
        "temperature": 0.2,
    }
    if not str(model or "").strip():
        return None, {
            "error": f"{provider_name} model is not set.",
            "status_code": 500,
            "trace_step": {
                "name": provider_name,
                "request": {"method": "SDK", "url": "(not sent)", "headers": {}, "payload": request_payload},
                "response": {"status": 500, "body": {"error": "Missing model setting"}},
            },
        }
    if not proxy_mode and not str(base_url or "").strip():
        return None, {
            "error": f"{provider_name} base URL is not set.",
            "status_code": 500,
            "trace_step": {
                "name": provider_name,
                "request": {"method": "SDK", "url": "(not sent)", "headers": {}, "payload": request_payload},
                "response": {"status": 500, "body": {"error": "Missing base URL setting"}},
            },
        }
    trace_request = {
        "method": "SDK",
        "url": (
            f"{effective_base_url}/chat/completions (Zscaler Proxy -> {provider_name} via OpenAI-compatible SDK)"
            if proxy_mode
            else f"{base_url.rstrip('/')}/chat/completions ({provider_name} via OpenAI-compatible SDK)"
        ),
        "headers": {
            "Authorization": "Bearer ***redacted***" if effective_api_key else "***missing***",
            **(
                {
                    k: ("***redacted***" if k.lower() == proxy_api_key_header_name.lower() else v)
                    for k, v in proxy_headers.items()
                }
                if proxy_mode
                else {}
            ),
            **(
                {os.getenv("ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME", "").strip(): conversation_id}
                if os.getenv("ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME", "").strip() and conversation_id
                else {}
            ),
            **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {}),
        },
        "payload": request_payload,
    }

    if not effective_api_key:
        return None, {
            "error": (
                f"{proxy_provider_family or provider_name} proxy key is not set. "
                f"Set {(proxy_provider_family or provider_name).upper()}_ZS_PROXY_API_KEY "
                f"(or {(proxy_provider_family or provider_name).upper()}_ZS_PROXY_KEY)."
                if proxy_mode
                else f"{api_key_env} is not set."
            ),
            "status_code": 500,
            "trace_step": {
                "name": provider_name,
                "request": trace_request,
                "response": {
                    "status": 500,
                    "body": {
                        "error": (
                            "Missing provider-specific ZS proxy key"
                            if proxy_mode
                            else f"Missing {api_key_env}"
                        ),
                    },
                },
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
        client = OpenAI(
            api_key=effective_api_key,
            base_url=effective_base_url,
            default_headers=(proxy_headers if proxy_mode else (default_headers or None)),
        )
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
            "error": f"{provider_name} request failed.",
            "status_code": int(err_status or 502),
            "details": str(exc),
            **({"proxy_guardrails_block": proxy_block} if proxy_block else {}),
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
    payload = {"model": ollama_model, "messages": _ollama_messages_with_attachments(_normalize_messages(messages)), "stream": False}
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
    tool_defs: list[ToolDef] | None = None,
) -> tuple[str | None, dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, proxy_key_source = _zscaler_proxy_sdk_config(
        "ANTHROPIC",
        conversation_id,
        demo_user,
    )
    effective_api_key = proxy_key if proxy_mode else api_key
    tooling_ctx = _build_anthropic_tool_payload(tool_defs)
    adapter = AnthropicAdapter()
    request_payload = adapter.build_request(
        messages=[{"role": "user", "content": prompt}],
        model=anthropic_model,
        tool_defs=tool_defs,
        settings=tooling_ctx,
    )
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
        "tooling": {
            "available_tools": tooling_ctx.available_count,
            "included_tools": tooling_ctx.included_count,
            "dropped_tools": tooling_ctx.dropped_count,
            "include_mode": tooling_ctx.include_mode,
            "include_tools": tooling_ctx.include_tools,
            "tool_name_prefix_strategy": tooling_ctx.name_strategy,
            "reason": tooling_ctx.reason,
        },
    }
    if _bool_env("TOOLSET_DEBUG_LOGS", False):
        print(
            "[toolset.debug] provider_call=anthropic "
            f"tools_available={tooling_ctx.available_count} tools_included={tooling_ctx.included_count} "
            f"include_mode={tooling_ctx.include_mode} include_flag={tooling_ctx.include_tools}"
        )

    if not effective_api_key:
        return None, {
            "error": (
                "Anthropic proxy key is not set. Set ANTHROPIC_ZS_PROXY_API_KEY (or ANTHROPIC_ZS_PROXY_KEY)."
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
                        "error": "Missing provider-specific ZS proxy key" if proxy_mode else "Missing ANTHROPIC_API_KEY"
                        ,
                        "proxy_key_envs_checked": (
                            ["ANTHROPIC_ZS_PROXY_API_KEY", "ANTHROPIC_ZS_PROXY_KEY"]
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
        parsed = adapter.parse_response(resp)
        text = str(parsed.get("assistant_text") or "").strip()
        response_body: dict[str, Any] = {
            "id": getattr(resp, "id", None),
            "model": getattr(resp, "model", anthropic_model),
            "role": getattr(resp, "role", None),
            "stop_reason": getattr(resp, "stop_reason", None),
            "usage": getattr(resp, "usage", None).model_dump()
            if hasattr(getattr(resp, "usage", None), "model_dump")
            else None,
            "text": text,
            "tool_calls": parsed.get("tool_calls", []),
            "tool_name_map": tooling_ctx.provider_tool_map,
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
    tool_defs: list[ToolDef] | None = None,
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
    tooling_ctx = _build_anthropic_tool_payload(tool_defs)
    adapter = AnthropicAdapter()
    request_payload = adapter.build_request(
        messages=_anthropic_messages_with_attachments([m for m in normalized if m["role"] in {"user", "assistant"}]),
        model=anthropic_model,
        tool_defs=tool_defs,
        settings=tooling_ctx,
    )
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
        "tooling": {
            "available_tools": tooling_ctx.available_count,
            "included_tools": tooling_ctx.included_count,
            "dropped_tools": tooling_ctx.dropped_count,
            "include_mode": tooling_ctx.include_mode,
            "include_tools": tooling_ctx.include_tools,
            "tool_name_prefix_strategy": tooling_ctx.name_strategy,
            "reason": tooling_ctx.reason,
        },
    }
    if _bool_env("TOOLSET_DEBUG_LOGS", False):
        print(
            "[toolset.debug] provider_call=anthropic "
            f"tools_available={tooling_ctx.available_count} tools_included={tooling_ctx.included_count} "
            f"include_mode={tooling_ctx.include_mode} include_flag={tooling_ctx.include_tools}"
        )

    if not effective_api_key:
        return None, {
            "error": (
                "Anthropic proxy key is not set. Set ANTHROPIC_ZS_PROXY_API_KEY (or ANTHROPIC_ZS_PROXY_KEY)."
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
                        "error": "Missing provider-specific ZS proxy key" if proxy_mode else "Missing ANTHROPIC_API_KEY"
                        ,
                        "proxy_key_envs_checked": (
                            ["ANTHROPIC_ZS_PROXY_API_KEY", "ANTHROPIC_ZS_PROXY_KEY"]
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
        parsed = adapter.parse_response(resp)
        text = str(parsed.get("assistant_text") or "").strip()
        response_body: dict[str, Any] = {
            "id": getattr(resp, "id", None),
            "model": getattr(resp, "model", anthropic_model),
            "role": getattr(resp, "role", None),
            "stop_reason": getattr(resp, "stop_reason", None),
            "usage": getattr(resp, "usage", None).model_dump()
            if hasattr(getattr(resp, "usage", None), "model_dump")
            else None,
            "text": text,
            "tool_calls": parsed.get("tool_calls", []),
            "tool_name_map": tooling_ctx.provider_tool_map,
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
        "messages": _openai_messages_with_attachments(normalized),
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
                "OpenAI proxy key is not set. Set OPENAI_ZS_PROXY_API_KEY (or OPENAI_ZS_PROXY_KEY)."
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
                        "error": "Missing provider-specific ZS proxy key" if proxy_mode else "Missing OPENAI_API_KEY",
                        "proxy_key_envs_checked": (
                            ["OPENAI_ZS_PROXY_API_KEY", "OPENAI_ZS_PROXY_KEY"]
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
    proxy_mode: bool = False,
    conversation_id: str | None = None,
    demo_user: str | None = None,
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
    trace_headers: dict[str, str] = {
        "Authorization": "AWS SigV4 (AWS env keys or ambient credentials)"
    }
    client_kwargs: dict[str, Any] = {"region_name": region}
    auth_kwargs, auth_source = _bedrock_client_auth_kwargs()
    if auth_kwargs:
        client_kwargs.update(auth_kwargs)
    if proxy_mode:
        proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, _ = _zscaler_proxy_sdk_config(
            "BEDROCK_INVOKE",
            conversation_id,
            demo_user,
        )
        if not proxy_key:
            return None, {
                "error": "Bedrock proxy key is not set. Set BEDROCK_INVOKE_ZS_PROXY_API_KEY (or BEDROCK_INVOKE_ZS_PROXY_KEY).",
                "status_code": 500,
                "trace_step": {
                    "name": "AWS Bedrock (Nova Lite)",
                    "request": {
                        "method": "SDK",
                        "url": f"AWS Bedrock Runtime (converse) [{region}] via proxy",
                        "headers": trace_headers,
                        "payload": request_payload,
                    },
                    "response": {"status": 500, "body": {"error": "Missing provider-specific ZS proxy key"}},
                },
            }
        try:
            config_obj = _bedrock_botocore_config(proxy_mode=True, unsigned=True)
        except Exception as exc:
            return None, {
                "error": "botocore proxy support unavailable.",
                "status_code": 500,
                "details": str(exc),
            }
        client_kwargs["endpoint_url"] = proxy_base_url
        client_kwargs["config"] = config_obj
        auth_source = f"{auth_source}+proxy_unsigned"
        trace_headers["Authorization"] = "AWS Unsigned via proxy"
        trace_headers.update(
            {
                k: ("***redacted***" if k.lower() == proxy_api_key_header_name.lower() else v)
                for k, v in proxy_headers.items()
            }
        )
    else:
        try:
            client_kwargs["config"] = _bedrock_botocore_config(proxy_mode=False, unsigned=False)
        except Exception:
            pass
    trace_request = {
        "method": "SDK",
        "url": (
            f"AWS Bedrock Runtime (converse) [{region}] via proxy"
            if proxy_mode
            else f"AWS Bedrock Runtime (converse) [{region}]"
        ),
        "headers": trace_headers,
        "payload": request_payload,
        "auth_source": auth_source,
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
        client = boto3.client("bedrock-runtime", **client_kwargs)
        if proxy_mode:
            for k, v in proxy_headers.items():
                client.meta.events.register(
                    "request-created.bedrock-runtime.Converse",
                    lambda request, _k=k, _v=v, **kwargs: request.headers.__setitem__(_k, _v),
                )
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
        err_status: int | None = None
        err_body: Any = None
        if hasattr(exc, "response") and isinstance(getattr(exc, "response", None), dict):
            err_body = getattr(exc, "response")
            try:
                err_status = int(((err_body.get("ResponseMetadata") or {}).get("HTTPStatusCode")))
            except Exception:
                err_status = None
        proxy_block = (
            _proxy_guardrails_block_from_error(
                status_code=err_status,
                response_body=err_body,
                details_text=str(exc),
            )
            if proxy_mode
            else None
        )
        return None, {
            "error": "Bedrock invoke request failed.",
            "status_code": int(err_status or 502),
            "details": str(exc),
            **({"proxy_guardrails_block": proxy_block} if proxy_block else {}),
            "trace_step": {
                "name": "AWS Bedrock (Nova Lite)",
                "request": trace_request,
                "response": {
                    "status": int(err_status or 502),
                    "body": {"error": str(exc), **({"response_body": err_body} if err_body is not None else {})},
                },
            },
        }


def _bedrock_agent_chat_messages(
    messages: list[dict],
    *,
    region: str,
    proxy_mode: bool = False,
    conversation_id: str | None = None,
    demo_user: str | None = None,
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
    trace_headers: dict[str, str] = {
        "Authorization": "AWS SigV4 (AWS env keys or ambient credentials)"
    }
    client_kwargs: dict[str, Any] = {"region_name": region}
    auth_kwargs, auth_source = _bedrock_client_auth_kwargs()
    if auth_kwargs:
        client_kwargs.update(auth_kwargs)
    if proxy_mode:
        proxy_key, proxy_base_url, proxy_api_key_header_name, proxy_headers, _ = _zscaler_proxy_sdk_config(
            "BEDROCK_AGENT",
            conversation_id,
            demo_user,
        )
        if not proxy_key:
            return None, {
                "error": "Bedrock Agent proxy key is not set. Set BEDROCK_AGENT_ZS_PROXY_API_KEY (or BEDROCK_AGENT_ZS_PROXY_KEY).",
                "status_code": 500,
                "trace_step": {
                    "name": "AWS Bedrock Agent",
                    "request": {
                        "method": "SDK",
                        "url": f"AWS Bedrock Agent Runtime (invoke_agent) [{region}] via proxy",
                        "headers": trace_headers,
                        "payload": request_payload,
                    },
                    "response": {"status": 500, "body": {"error": "Missing provider-specific ZS proxy key"}},
                },
            }
        try:
            config_obj = _bedrock_botocore_config(proxy_mode=True, unsigned=True)
        except Exception as exc:
            return None, {
                "error": "botocore proxy support unavailable.",
                "status_code": 500,
                "details": str(exc),
            }
        client_kwargs["endpoint_url"] = proxy_base_url
        client_kwargs["config"] = config_obj
        auth_source = f"{auth_source}+proxy_unsigned"
        trace_headers["Authorization"] = "AWS Unsigned via proxy"
        trace_headers.update(
            {
                k: ("***redacted***" if k.lower() == proxy_api_key_header_name.lower() else v)
                for k, v in proxy_headers.items()
            }
        )
    else:
        try:
            client_kwargs["config"] = _bedrock_botocore_config(proxy_mode=False, unsigned=False)
        except Exception:
            pass
    trace_request = {
        "method": "SDK",
        "url": (
            f"AWS Bedrock Agent Runtime (invoke_agent) [{region}] via proxy"
            if proxy_mode
            else f"AWS Bedrock Agent Runtime (invoke_agent) [{region}]"
        ),
        "headers": trace_headers,
        "payload": request_payload,
        "auth_source": auth_source,
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
        client = boto3.client("bedrock-agent-runtime", **client_kwargs)
        if proxy_mode:
            for k, v in proxy_headers.items():
                client.meta.events.register(
                    "request-created.bedrock-agent-runtime.InvokeAgent",
                    lambda request, _k=k, _v=v, **kwargs: request.headers.__setitem__(_k, _v),
                )
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
        err_status: int | None = None
        err_body: Any = None
        if hasattr(exc, "response") and isinstance(getattr(exc, "response", None), dict):
            err_body = getattr(exc, "response")
            try:
                err_status = int(((err_body.get("ResponseMetadata") or {}).get("HTTPStatusCode")))
            except Exception:
                err_status = None
        proxy_block = (
            _proxy_guardrails_block_from_error(
                status_code=err_status,
                response_body=err_body,
                details_text=str(exc),
            )
            if proxy_mode
            else None
        )
        return None, {
            "error": "Bedrock agent request failed.",
            "status_code": int(err_status or 502),
            "details": str(exc),
            **({"proxy_guardrails_block": proxy_block} if proxy_block else {}),
            "trace_step": {
                "name": "AWS Bedrock Agent",
                "request": trace_request,
                "response": {
                    "status": int(err_status or 502),
                    "body": {"error": str(exc), **({"response_body": err_body} if err_body is not None else {})},
                },
            },
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
        contents.append({"role": gem_role, "parts": _gemini_parts_from_message(m)})
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
        contents.append({"role": vertex_role, "parts": _gemini_parts_from_message(m)})
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
    tool_defs: list[ToolDef] | None = None,
) -> tuple[str | None, dict]:
    provider = (provider_id or "ollama").strip().lower()
    if _bool_env("TOOLSET_DEBUG_LOGS", False):
        include_flag = _bool_env("INCLUDE_TOOLS_IN_LLM_REQUEST", DEFAULT_INCLUDE_TOOLS_IN_LLM_REQUEST)
        print(
            "[toolset.debug] llm_call "
            f"provider={provider} mcp_tools_available={len(tool_defs or [])} "
            f"include_tools_flag={include_flag} provider_supports_tools={provider == 'anthropic'}"
        )
    aws_region = os.getenv("AWS_REGION", DEFAULT_AWS_REGION).strip() or DEFAULT_AWS_REGION
    if zscaler_proxy_mode:
        if provider in {"ollama", "litellm"}:
            return None, {
                "error": "Zscaler Proxy Mode is disabled for Ollama and LiteLLM in this demo. Choose API/DAS mode or another provider.",
                "status_code": 400,
                "trace_step": {
                    "name": "Provider Selection",
                    "request": {"provider": provider_id, "zscaler_proxy_mode": True},
                    "response": {"status": 400, "body": {"error": "Unsupported provider for proxy mode"}},
                },
            }
        proxy_wired = {
            "anthropic",
            "openai",
            "bedrock_invoke",
            "bedrock_agent",
            "perplexity",
            "xai",
            "azure_foundry",
            "kong",
        }
        if provider not in proxy_wired:
            return None, {
                "error": f"Zscaler Proxy Mode is not wired yet for provider `{provider}` in backend calls. Choose API/DAS mode for this provider.",
                "status_code": 400,
                "trace_step": {
                    "name": "Provider Selection",
                    "request": {"provider": provider_id, "zscaler_proxy_mode": True},
                    "response": {"status": 400, "body": {"error": "Proxy mode backend not wired for provider"}},
                },
            }
    if provider == "anthropic":
        return _anthropic_chat_messages(
            messages,
            anthropic_model or DEFAULT_ANTHROPIC_MODEL,
            proxy_mode=zscaler_proxy_mode,
            conversation_id=conversation_id,
            demo_user=demo_user,
            tool_defs=tool_defs,
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
            proxy_mode=zscaler_proxy_mode,
            conversation_id=conversation_id,
            demo_user=demo_user,
        )
    if provider == "bedrock_agent":
        return _bedrock_agent_chat_messages(
            messages,
            region=aws_region,
            proxy_mode=zscaler_proxy_mode,
            conversation_id=conversation_id,
            demo_user=demo_user,
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
            proxy_mode=zscaler_proxy_mode,
            proxy_provider_family="PERPLEXITY",
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
            proxy_mode=zscaler_proxy_mode,
            proxy_provider_family="XAI",
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
    if provider == "kong":
        return _openai_compatible_chat_messages(
            provider_name="Kong Gateway",
            api_key_env="KONG_API_KEY",
            model=os.getenv("KONG_MODEL", DEFAULT_KONG_MODEL).strip(),
            default_base_url=os.getenv("KONG_BASE_URL", "").strip(),
            base_url_env="KONG_BASE_URL",
            messages=messages,
            conversation_id=conversation_id,
            demo_user=demo_user,
            proxy_mode=zscaler_proxy_mode,
            proxy_provider_family="KONG",
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
            proxy_mode=zscaler_proxy_mode,
            proxy_provider_family="AZURE_FOUNDRY",
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
    tool_defs: list[ToolDef] | None = None,
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
        tool_defs=tool_defs,
    )
