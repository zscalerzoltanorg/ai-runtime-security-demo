import json
import os
from urllib import error, request


DEFAULT_ZS_GUARDRAILS_URL = "https://api.zseclipse.net/v1/detection/resolve-and-execute-policy"
DEFAULT_ZS_GUARDRAILS_EXECUTE_URL = "https://api.zseclipse.net/v1/detection/execute-policy"
DEMO_USER_HEADER_NAME = "X-Demo-User"
DEFAULT_APPLY_MASKED_CONTENT = True
DEFAULT_AI_GUARD_BLOCK_CONTACT_TEXT = (
    "If you believe this is incorrect or have an exception to make please contact "
    "helpdesk@mycompany.com or call our internal helpdesk at (555)555-5555."
)


def _float_env(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _normalize_das_mode(raw: str | None) -> str:
    mode = str(raw or "").strip().lower().replace("-", "_")
    if mode in {"execute", "execute_policy"}:
        return "execute"
    return "resolve"


def _parse_policy_id(raw: object) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except Exception:
        return None
    return value if value > 0 else None


def _api_direction(stage: str) -> str:
    normalized = str(stage or "").strip().lower()
    if normalized in {"in", "input", "prompt", "request"}:
        return "IN"
    if normalized in {"out", "output", "completion", "response"}:
        return "OUT"
    return normalized.upper() or "IN"


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def redaction_enabled(override: object = None) -> bool:
    """Whether AI Guard entity redaction should be applied to provider traffic.

    Only meaningful in API/DAS mode: the app holds the detection response and
    builds the provider request itself. In Proxy mode the rewrite (if any)
    happens inside the proxy, so there is nothing for the app to apply.
    """
    if override is not None:
        return bool(override)
    return _bool_env("ZS_GUARDRAILS_APPLY_MASKED_CONTENT", DEFAULT_APPLY_MASKED_CONTENT)


def _detected_entity_spans(body: object) -> list[dict]:
    """Flatten per-detector detectedEntities into offset spans.

    Offsets are relative to the exact string that was submitted as `content`.
    """
    if not isinstance(body, dict):
        return []
    detector_responses = body.get("detectorResponses")
    if not isinstance(detector_responses, dict):
        return []

    spans: list[dict] = []
    for detector_name, details in detector_responses.items():
        if not isinstance(details, dict):
            continue
        inner = details.get("details")
        if not isinstance(inner, dict):
            continue
        entities = inner.get("detectedEntities")
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            try:
                start = int(entity.get("start"))
                end = int(entity.get("end"))
            except (TypeError, ValueError):
                continue
            if start < 0 or end <= start:
                continue
            entity_type = str(entity.get("type") or "").strip() or str(detector_name)
            replacement = str(entity.get("anonymizedEntityText") or "").strip()
            if not replacement:
                replacement = f"[{entity_type}]"
            spans.append(
                {
                    "detector": str(detector_name),
                    "type": entity_type,
                    "start": start,
                    "end": end,
                    "replacement": replacement,
                }
            )
    spans.sort(key=lambda span: (span["start"], span["end"]))
    return spans


def apply_entity_redaction(
    content: str,
    body: object,
    *,
    max_offset: int | None = None,
) -> tuple[str, list[dict], list[dict]]:
    """Replace detected entity spans in `content` with AI Guard's anonymized text.

    `max_offset` bounds application to a prefix of the submitted content. The
    demo submits `prompt + attachment text` for inspection but only the prompt
    is the user message, so spans past the prompt are reported as deferred
    instead of being applied at the wrong offsets.

    Overlapping detections are resolved in favour of the widest span, so a
    narrower match can never mask part of an entity and leave the rest exposed.

    Returns (redacted_text, applied_spans, deferred_spans). Span metadata never
    carries the matched text itself, only its length, so traces stay clean.
    """
    text = str(content or "")
    spans = _detected_entity_spans(body)
    if not text or not spans:
        return text, [], []

    limit = len(text) if max_offset is None else max(0, min(int(max_offset), len(text)))

    def _meta(span: dict, **extra: object) -> dict:
        return {
            "detector": span["detector"],
            "type": span["type"],
            "start": span["start"],
            "end": span["end"],
            "replacement": span["replacement"],
            "original_length": max(0, span["end"] - span["start"]),
            **extra,
        }

    in_range: list[dict] = []
    deferred: list[dict] = []
    for span in spans:
        if span["end"] > limit:
            deferred.append(_meta(span, reason="outside_redactable_range"))
        else:
            in_range.append(span)

    # Widest span wins, so no detection masks only part of an entity.
    accepted: list[dict] = []
    for span in sorted(in_range, key=lambda item: (-(item["end"] - item["start"]), item["start"])):
        if any(span["start"] < kept["end"] and kept["start"] < span["end"] for kept in accepted):
            deferred.append(_meta(span, reason="overlapping_span"))
            continue
        accepted.append(span)

    # Right-to-left so that offsets not yet applied stay valid.
    for span in sorted(accepted, key=lambda item: item["start"], reverse=True):
        text = f"{text[:span['start']]}{span['replacement']}{text[span['end']:]}"

    applied = [_meta(span) for span in sorted(accepted, key=lambda item: item["start"])]
    deferred.sort(key=lambda item: (item["start"], item["end"]))
    return text, applied, deferred


def redact_content(
    content: str,
    body: object,
    *,
    max_offset: int | None = None,
    submitted_length: int | None = None,
) -> tuple[str, dict]:
    """Apply AI Guard redaction to `content`, preferring precise entity offsets.

    Falls back to the response-level `maskedContent` only when no usable offsets
    were returned AND the inspected string was exactly `content`. `maskedContent`
    covers prompt plus attachment text as a single blob, so using it when the
    submitted string was longer would splice attachment text into the prompt.
    Pass `submitted_length` (the length of the string sent as `content` to AI
    Guard) whenever that differs from `content`.

    Returns (text, info) where info["method"] is one of entity_offsets,
    masked_content, or none.
    """
    original = str(content or "")
    text, applied, deferred = apply_entity_redaction(original, body, max_offset=max_offset)
    if applied:
        return text, {
            "method": "entity_offsets",
            "applied": applied,
            "deferred": deferred,
            "entity_count": len(applied),
        }

    masked = body.get("maskedContent") if isinstance(body, dict) else None
    inspected_exactly = submitted_length is None or int(submitted_length) == len(original)
    if isinstance(masked, str) and masked and masked != original and inspected_exactly:
        return masked, {
            "method": "masked_content",
            "applied": [],
            "deferred": deferred,
            "entity_count": 0,
        }

    return original, {
        "method": "none",
        "applied": [],
        "deferred": deferred,
        "entity_count": 0,
    }


def _redaction_type_counts(spans: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for span in spans or []:
        key = str(span.get("type") or "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1
    return counts


def redaction_summary_entry(info: dict) -> dict:
    """Compact per-direction redaction summary for the response payload."""
    applied = info.get("applied") if isinstance(info.get("applied"), list) else []
    deferred = info.get("deferred") if isinstance(info.get("deferred"), list) else []
    return {
        "method": str(info.get("method") or "none"),
        "entities": len(applied),
        "deferred": len(deferred),
        "types": _redaction_type_counts(applied),
    }


def redaction_trace_step(
    stage: str,
    info: dict,
    *,
    before_length: int,
    after_length: int,
    attachment_entities: int = 0,
) -> dict:
    """Trace step making the substitution visible in the demo UI."""
    direction = _api_direction(stage)
    applied = info.get("applied") if isinstance(info.get("applied"), list) else []
    deferred = info.get("deferred") if isinstance(info.get("deferred"), list) else []
    method = str(info.get("method") or "none")
    target = "provider request" if direction == "IN" else "user-visible response"
    notes: list[str] = []
    if method == "masked_content":
        notes.append(
            "No usable entity offsets were returned; applied the response-level "
            "maskedContent string instead."
        )
    if attachment_entities:
        notes.append(
            f"{attachment_entities} detection(s) inside text attachments were "
            "redacted in the attachment body sent to the provider."
        )
    remaining = max(0, len(deferred) - int(attachment_entities))
    if remaining:
        notes.append(
            f"{remaining} detection(s) fell outside the redactable range "
            "(non-text attachment content or overlapping spans) and were left unchanged."
        )
    return {
        # Name must start with "Zscaler" (so the UI does not mistake it for the
        # provider step) but not "Zscaler AI Guard" (so it is not counted as a
        # policy check in trace summaries).
        "name": f"Zscaler Redaction ({direction})",
        "request": {
            "method": "LOCAL",
            "url": "app://guardrails/apply-redaction",
            "payload": {
                "direction": direction,
                "method": method,
                "target": target,
                "entities_applied": len(applied),
                "entities_deferred": len(deferred),
                "attachment_entities_applied": int(attachment_entities),
                "entity_types": _redaction_type_counts(applied),
            },
        },
        "response": {
            "status": 200,
            "body": {
                "applied": method != "none" or bool(attachment_entities),
                "method": method,
                "content_length_before": int(before_length),
                "content_length_after": int(after_length),
                "entities": [
                    {
                        "detector": span.get("detector"),
                        "type": span.get("type"),
                        "start": span.get("start"),
                        "end": span.get("end"),
                        "replacement": span.get("replacement"),
                        "original_length": span.get("original_length"),
                    }
                    for span in applied
                ],
                **({"notes": notes} if notes else {}),
            },
        },
    }


def _block_contact_text() -> str:
    text = str(os.getenv("AI_GUARD_BLOCK_CONTACT_TEXT", DEFAULT_AI_GUARD_BLOCK_CONTACT_TEXT) or "").strip()
    return text or DEFAULT_AI_GUARD_BLOCK_CONTACT_TEXT


def _resolve_guardrails_url(base_url: str, das_mode: str) -> str:
    url = str(base_url or DEFAULT_ZS_GUARDRAILS_URL).strip()
    if not url:
        url = DEFAULT_ZS_GUARDRAILS_URL
    suffix = "execute-policy" if das_mode == "execute" else "resolve-and-execute-policy"
    if url.endswith("/resolve-and-execute-policy") or url.endswith("/execute-policy"):
        return f"{url.rsplit('/', 1)[0]}/{suffix}"
    if das_mode == "execute" and url == DEFAULT_ZS_GUARDRAILS_URL:
        return DEFAULT_ZS_GUARDRAILS_EXECUTE_URL
    return url


def _guardrails_config() -> tuple[str, str, float, str, str, int | None]:
    url = os.getenv("ZS_GUARDRAILS_URL", DEFAULT_ZS_GUARDRAILS_URL).strip()
    api_key = os.getenv("ZS_GUARDRAILS_API_KEY", "")
    timeout = _float_env("ZS_GUARDRAILS_TIMEOUT_SECONDS", 15.0)
    conversation_id_header = os.getenv("ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME", "").strip()
    das_mode = _normalize_das_mode(os.getenv("ZS_GUARDRAILS_DAS_MODE", "resolve"))
    policy_id = _parse_policy_id(os.getenv("ZS_GUARDRAILS_POLICY_ID", ""))
    return url, api_key, timeout, conversation_id_header, das_mode, policy_id


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


def _triggered_detectors(block_body: dict) -> list[str]:
    detectors = []
    detector_responses = block_body.get("detectorResponses") or {}
    if not isinstance(detector_responses, dict):
        return detectors

    for name, details in detector_responses.items():
        if not isinstance(details, dict):
            continue
        triggered = details.get("triggered") is True
        action = str(details.get("action", "")).upper()
        if triggered or action == "BLOCK":
            label = name
            secret_types = (
                (details.get("details") or {}).get("detectedSecretTypes")
                if isinstance(details.get("details"), dict)
                else None
            )
            if isinstance(secret_types, dict) and secret_types:
                label = f"{name} ({', '.join(secret_types.keys())})"
            detectors.append(label)
    return detectors


def _is_blocked_guardrails_body(body: object) -> bool:
    if not isinstance(body, dict):
        return False

    # Primary top-level indicators
    for key in ("action", "decision", "verdict", "policyAction"):
        value = str(body.get(key, "")).strip().upper()
        if value == "BLOCK":
            return True
    if body.get("blocked") is True:
        return True

    # Fallback: detector-level block actions
    detector_responses = body.get("detectorResponses")
    if isinstance(detector_responses, dict):
        for details in detector_responses.values():
            if not isinstance(details, dict):
                continue
            detector_action = str(details.get("action", "")).strip().upper()
            if detector_action == "BLOCK":
                return True
    return False


def _guardrails_notice_from_body(
    body: object,
    *,
    stage: str,
    das_mode: str,
    policy_id: int | None,
) -> dict | None:
    if not isinstance(body, dict):
        return None
    status_code_raw = body.get("statusCode")
    try:
        status_code = int(status_code_raw) if status_code_raw is not None else None
    except Exception:
        status_code = None
    error_msg = str(body.get("errorMsg") or "").strip()
    if (status_code is None or status_code < 400) and not error_msg:
        return None
    return {
        "stage": str(stage or "").upper(),
        "das_mode": das_mode,
        "policy_id": policy_id,
        "status_code": status_code,
        "error": error_msg or "AI Guard returned a non-success policy status.",
    }


def _block_message(stage: str, block_body: object) -> str:
    if not isinstance(block_body, dict):
        return f"Blocked by AI Guard ({stage.lower()})."

    transaction_id = block_body.get("transactionId") or "n/a"
    policy_name = block_body.get("policyName") or "n/a"
    policy_id = block_body.get("policyId")
    severity = block_body.get("severity") or "n/a"
    masked_content = "[redacted]"
    detectors = _triggered_detectors(block_body)
    detectors_text = ", ".join(detectors) if detectors else "n/a"
    policy_id_text = str(policy_id) if policy_id is not None else "n/a"

    return (
        f"This {stage} was blocked by AI Guard per Company Policy.\n"
        f"{_block_contact_text()}\n\n"
        "Block details:\n"
        f"- transactionId: {transaction_id}\n"
        f"- policyName: {policy_name}\n"
        f"- policyId: {policy_id_text}\n"
        f"- severity: {severity}\n"
        f"- maskedContent: {masked_content}\n"
        f"- triggeredDetectors: {detectors_text}"
    )


def proxy_block_message(stage: str, block_body: object) -> str:
    if not isinstance(block_body, dict):
        return (
            f"This {stage} was blocked by AI Guard per Company Policy.\n"
            f"{_block_contact_text()}"
        )

    policy_name = block_body.get("policyName") or "n/a"
    reason = block_body.get("reason") or "Your request was blocked by Zscaler AI Guard"
    detections: list[str] = []
    if isinstance(block_body.get("inputDetections"), list):
        detections.extend([str(x) for x in block_body.get("inputDetections") or []])
    if isinstance(block_body.get("outputDetections"), list):
        detections.extend([str(x) for x in block_body.get("outputDetections") or []])
    detectors_text = ", ".join(detections) if detections else "n/a"
    return (
        f"This {stage} was blocked by AI Guard per Company Policy.\n"
        f"{_block_contact_text()}\n\n"
        "Block details:\n"
        f"- policyName: {policy_name}\n"
        f"- reason: {reason}\n"
        f"- triggeredDetectors: {detectors_text}"
    )


def _redact_block_body_for_client(block_body: object) -> object:
    if not isinstance(block_body, dict):
        return block_body
    redacted = dict(block_body)
    if "maskedContent" in redacted:
        redacted["maskedContent"] = "[redacted]"
    return redacted


def _redact_trace_for_out_block(trace_steps: list[dict]) -> list[dict]:
    safe_steps: list[dict] = []
    for step in trace_steps:
        if not isinstance(step, dict):
            safe_steps.append(step)
            continue
        step_copy = dict(step)
        req = step_copy.get("request")
        res = step_copy.get("response")
        if isinstance(req, dict):
            req_copy = dict(req)
            payload = req_copy.get("payload")
            if isinstance(payload, dict) and str(payload.get("direction", "")).upper() == "OUT":
                req_payload = dict(payload)
                req_payload["content"] = "[redacted]"
                req_copy["payload"] = req_payload
            step_copy["request"] = req_copy
        if isinstance(res, dict):
            res_copy = dict(res)
            body = res_copy.get("body")
            if isinstance(body, dict):
                body_copy = dict(body)
                body_copy = _redact_block_body_for_client(body_copy)
                # Strip common raw provider text fields from trace payloads.
                for field in ("text", "response", "output", "content", "assistant_text"):
                    if field in body_copy and isinstance(body_copy[field], str):
                        body_copy[field] = "[redacted]"
                res_copy["body"] = body_copy
            step_copy["response"] = res_copy
        safe_steps.append(step_copy)
    return safe_steps


def _zag_check(
    direction: str,
    content: str,
    conversation_id: str | None = None,
    demo_user: str | None = None,
    zscaler_das_mode: str | None = None,
    zscaler_policy_id: int | str | None = None,
) -> tuple[bool, dict]:
    (
        zag_base_url,
        zag_key,
        zag_timeout,
        conversation_id_header,
        cfg_das_mode,
        cfg_policy_id,
    ) = _guardrails_config()
    das_mode = _normalize_das_mode(zscaler_das_mode or cfg_das_mode)
    policy_id = _parse_policy_id(zscaler_policy_id) if zscaler_policy_id is not None else cfg_policy_id
    zag_url = _resolve_guardrails_url(zag_base_url, das_mode)
    api_direction = _api_direction(direction)

    if not zag_key:
        return False, {
            "error": "ZS_GUARDRAILS_API_KEY is not set.",
            "status_code": 500,
            "trace_step": {
                "name": f"Zscaler AI Guard ({direction})",
                "request": {
                    "method": "POST",
                    "url": zag_url,
                    "headers": {
                        "Authorization": "Bearer ***missing***",
                        "Content-Type": "application/json",
                        **(
                            {conversation_id_header: str(conversation_id)}
                            if conversation_id_header and conversation_id
                            else {}
                        ),
                        **({DEMO_USER_HEADER_NAME: str(demo_user)} if demo_user else {}),
                    },
                    "payload": {
                        "direction": api_direction,
                        "content": content or "",
                        **({"policyId": policy_id} if das_mode == "execute" and policy_id else {}),
                    },
                },
                "response": {
                    "status": 500,
                    "body": {"error": "Missing ZS_GUARDRAILS_API_KEY"},
                },
            },
        }

    if das_mode == "execute" and not policy_id:
        payload = {
            "direction": api_direction,
            "content": content or "",
        }
        return False, {
            "error": "ZS_GUARDRAILS_POLICY_ID is required in Execute Policy mode.",
            "status_code": 400,
            "trace_step": {
                "name": f"Zscaler AI Guard ({direction})",
                "request": {
                    "method": "POST",
                    "url": zag_url,
                    "headers": {
                        "Authorization": "Bearer ***redacted***",
                        "Content-Type": "application/json",
                    },
                    "payload": payload,
                },
                "response": {"status": 400, "body": {"error": "Missing policyId"}},
            },
            "das_mode": das_mode,
            "policy_id": None,
        }

    payload = {"direction": api_direction, "content": content or ""}
    if das_mode == "execute" and policy_id:
        payload["policyId"] = policy_id
    headers = {
        "Authorization": f"Bearer {zag_key}",
        "Content-Type": "application/json",
    }
    if conversation_id_header and conversation_id:
        headers[conversation_id_header] = str(conversation_id)
    if demo_user:
        headers[DEMO_USER_HEADER_NAME] = str(demo_user)
    redacted_headers = {
        "Authorization": "Bearer ***redacted***",
        "Content-Type": "application/json",
    }
    if conversation_id_header and conversation_id:
        redacted_headers[conversation_id_header] = str(conversation_id)
    if demo_user:
        redacted_headers[DEMO_USER_HEADER_NAME] = str(demo_user)

    try:
        status, body = _post_json(
            zag_url,
            payload=payload,
            headers=headers,
            timeout=zag_timeout,
        )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        hint = ""
        if int(getattr(exc, "code", 0) or 0) == 401:
            hint = (
                "DAS/API mode expects a Zscaler AI Guard DAS/API key in "
                "ZS_GUARDRAILS_API_KEY and sends it as Authorization: Bearer "
                "to api.zseclipse.net. A 401 usually means the key is missing, "
                "expired, disabled, or is a proxy-mode application key instead "
                "of a DAS/API key."
            )
        return False, {
            "error": f"Zscaler AI Guard HTTP error on {direction} check.",
            "status_code": 502,
            "details": detail,
            **({"hint": hint} if hint else {}),
            "trace_step": {
                "name": f"Zscaler AI Guard ({direction})",
                "request": {
                    "method": "POST",
                    "url": zag_url,
                    "headers": redacted_headers,
                    "payload": payload,
                },
                "response": {"status": exc.code, "body": detail},
            },
        }
    except Exception as exc:  # network/timeouts/etc.
        return False, {
            "error": f"Could not reach Zscaler AI Guard on {direction} check.",
            "status_code": 502,
            "details": str(exc),
            "trace_step": {
                "name": f"Zscaler AI Guard ({direction})",
                "request": {
                    "method": "POST",
                    "url": zag_url,
                    "headers": redacted_headers,
                    "payload": payload,
                },
                "response": {"status": 502, "body": {"error": str(exc)}},
            },
        }

    blocked = _is_blocked_guardrails_body(body)
    notice = _guardrails_notice_from_body(
        body,
        stage=direction,
        das_mode=das_mode,
        policy_id=policy_id,
    )

    return blocked, {
        "das_mode": das_mode,
        "policy_id": policy_id,
        **({"notice": notice} if isinstance(notice, dict) else {}),
        "trace_step": {
            "name": f"Zscaler AI Guard ({direction})",
            "request": {
                "method": "POST",
                "url": zag_url,
                "headers": redacted_headers,
                "payload": payload,
            },
            "response": {"status": status, "body": body},
        }
    }


def guarded_chat(
    prompt: str,
    llm_call,
    conversation_id: str | None = None,
    demo_user: str | None = None,
    zscaler_das_mode: str | None = None,
    zscaler_policy_id: int | str | None = None,
    redact_target: str | None = None,
    apply_redaction: object = None,
    attachment_redactor=None,
) -> tuple[dict, int]:
    trace_steps: list[dict] = []
    effective_mode = _normalize_das_mode(zscaler_das_mode or _guardrails_config()[4])
    effective_policy_id = _parse_policy_id(zscaler_policy_id) if zscaler_policy_id is not None else _guardrails_config()[5]

    warnings: list[dict] = []

    in_blocked, in_meta = _zag_check(
        "IN",
        prompt,
        conversation_id=conversation_id,
        demo_user=demo_user,
        zscaler_das_mode=effective_mode,
        zscaler_policy_id=effective_policy_id,
    )
    trace_steps.append(in_meta["trace_step"])
    if in_meta.get("error"):
        return (
            {
                "error": in_meta["error"],
                "details": in_meta.get("details"),
                **({"hint": in_meta.get("hint")} if in_meta.get("hint") else {}),
                "trace": {"steps": trace_steps},
            },
            int(in_meta.get("status_code", 502)),
        )
    if isinstance(in_meta.get("notice"), dict):
        warnings.append(in_meta["notice"])
    if in_blocked:
        in_block_body = (in_meta.get("trace_step") or {}).get("response", {}).get("body")
        return (
            {
                "response": _block_message("Prompt", in_block_body),
                "guardrails": {
                    "enabled": True,
                    "mode": "api_das",
                    "das_mode": effective_mode,
                    "policy_id": effective_policy_id,
                    **({"warnings": warnings} if warnings else {}),
                    "blocked": True,
                    "stage": "IN",
                },
                "trace": {"steps": trace_steps},
            },
            200,
        )

    # API/DAS mode: the app builds the provider request, so it is the only place
    # AI Guard's anonymized rewrite can actually be applied.
    redact_on = redaction_enabled(apply_redaction)
    redaction_report: dict = {}
    provider_prompt = prompt if redact_target is None else redact_target
    in_body = (in_meta.get("trace_step") or {}).get("response", {}).get("body")
    if redact_on:
        # Attachment bodies are inlined into the provider payload by the provider
        # adapters, so they are redacted before the trace step is built in order
        # to report a single accurate entity count.
        attachment_count = 0
        if attachment_redactor is not None:
            try:
                attachment_count = int(attachment_redactor(in_body) or 0)
            except Exception:
                attachment_count = 0
        redacted_prompt, in_redaction = redact_content(
            provider_prompt,
            in_body,
            max_offset=len(provider_prompt),
            submitted_length=len(prompt),
        )
        if in_redaction.get("method") != "none" or attachment_count:
            trace_steps.append(
                redaction_trace_step(
                    "IN",
                    in_redaction,
                    before_length=len(provider_prompt),
                    after_length=len(redacted_prompt),
                    attachment_entities=attachment_count,
                )
            )
            summary = redaction_summary_entry(in_redaction)
            if attachment_count:
                summary["attachment_entities"] = attachment_count
            redaction_report["IN"] = summary
            provider_prompt = redacted_prompt

    llm_text, llm_meta = llm_call(provider_prompt)
    trace_steps.append(llm_meta["trace_step"])
    if llm_text is None:
        return (
            {
                "error": llm_meta["error"],
                "details": llm_meta.get("details"),
                "trace": {"steps": trace_steps},
            },
            int(llm_meta.get("status_code", 502)),
        )

    text = (llm_text or "").strip()

    out_blocked, out_meta = _zag_check(
        "OUT",
        text,
        conversation_id=conversation_id,
        demo_user=demo_user,
        zscaler_das_mode=effective_mode,
        zscaler_policy_id=effective_policy_id,
    )
    trace_steps.append(out_meta["trace_step"])
    if out_meta.get("error"):
        return (
            {
                "error": out_meta["error"],
                "details": out_meta.get("details"),
                **({"hint": out_meta.get("hint")} if out_meta.get("hint") else {}),
                "trace": {"steps": trace_steps},
            },
            int(out_meta.get("status_code", 502)),
        )
    if isinstance(out_meta.get("notice"), dict):
        warnings.append(out_meta["notice"])
    if out_blocked:
        out_block_body = (out_meta.get("trace_step") or {}).get("response", {}).get("body")
        safe_trace_steps = _redact_trace_for_out_block(trace_steps)
        safe_block_body = _redact_block_body_for_client(out_block_body)
        return (
            {
                "response": _block_message("Response", safe_block_body),
                "guardrails": {
                    "enabled": True,
                    "mode": "api_das",
                    "das_mode": effective_mode,
                    "policy_id": effective_policy_id,
                    **({"warnings": warnings} if warnings else {}),
                    "blocked": True,
                    "stage": "OUT",
                },
                "trace": {"steps": safe_trace_steps},
            },
            200,
        )

    if redact_on:
        out_body = (out_meta.get("trace_step") or {}).get("response", {}).get("body")
        redacted_text, out_redaction = redact_content(
            text,
            out_body,
            max_offset=len(text),
            submitted_length=len(text),
        )
        if out_redaction.get("method") != "none":
            trace_steps.append(
                redaction_trace_step(
                    "OUT",
                    out_redaction,
                    before_length=len(text),
                    after_length=len(redacted_text),
                )
            )
            redaction_report["OUT"] = redaction_summary_entry(out_redaction)
            text = redacted_text

    return (
        {
            "response": text,
            "guardrails": {
                "enabled": True,
                "mode": "api_das",
                "das_mode": effective_mode,
                "policy_id": effective_policy_id,
                **({"warnings": warnings} if warnings else {}),
                "blocked": False,
                "redaction": {
                    "enabled": redact_on,
                    **({"applied": redaction_report} if redaction_report else {"applied": {}}),
                },
            },
            "trace": {"steps": trace_steps},
        },
        200,
    )
