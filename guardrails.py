import json
import os
from urllib import error, request


DEFAULT_ZS_GUARDRAILS_URL = (
    "https://api.zseclipse.net/v1/detection/resolve-and-execute-policy"
)
DEMO_USER_HEADER_NAME = "X-Demo-User"


def _float_env(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _guardrails_config() -> tuple[str, str, float, str]:
    url = os.getenv("ZS_GUARDRAILS_URL", DEFAULT_ZS_GUARDRAILS_URL)
    api_key = os.getenv("ZS_GUARDRAILS_API_KEY", "")
    timeout = _float_env("ZS_GUARDRAILS_TIMEOUT_SECONDS", 15.0)
    conversation_id_header = os.getenv("ZS_GUARDRAILS_CONVERSATION_ID_HEADER_NAME", "").strip()
    return url, api_key, timeout, conversation_id_header


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
        f"This {stage} was blocked by AI Guard per Company Policy. "
        "If you believe this is incorrect or have an exception to make please contact "
        "helpdesk@mycompany.com or call our internal helpdesk at (555)555-5555.\n\n"
        "Block details:\n"
        f"- transactionId: {transaction_id}\n"
        f"- policyName: {policy_name}\n"
        f"- policyId: {policy_id_text}\n"
        f"- severity: {severity}\n"
        f"- maskedContent: {masked_content}\n"
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
) -> tuple[bool, dict]:
    zag_url, zag_key, zag_timeout, conversation_id_header = _guardrails_config()

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
                    "payload": {"direction": direction, "content": content or ""},
                },
                "response": {
                    "status": 500,
                    "body": {"error": "Missing ZS_GUARDRAILS_API_KEY"},
                },
            },
        }

    payload = {"direction": direction, "content": content or ""}
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
        return False, {
            "error": f"Zscaler AI Guard HTTP error on {direction} check.",
            "status_code": 502,
            "details": detail,
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

    return blocked, {
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
) -> tuple[dict, int]:
    trace_steps: list[dict] = []

    in_blocked, in_meta = _zag_check("IN", prompt, conversation_id=conversation_id, demo_user=demo_user)
    trace_steps.append(in_meta["trace_step"])
    if in_meta.get("error"):
        return (
            {
                "error": in_meta["error"],
                "details": in_meta.get("details"),
                "trace": {"steps": trace_steps},
            },
            int(in_meta.get("status_code", 502)),
        )
    if in_blocked:
        in_block_body = (in_meta.get("trace_step") or {}).get("response", {}).get("body")
        return (
            {
                "response": _block_message("Prompt", in_block_body),
                "guardrails": {"enabled": True, "blocked": True, "stage": "IN"},
                "trace": {"steps": trace_steps},
            },
            200,
        )

    llm_text, llm_meta = llm_call(prompt)
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

    out_blocked, out_meta = _zag_check("OUT", text, conversation_id=conversation_id, demo_user=demo_user)
    trace_steps.append(out_meta["trace_step"])
    if out_meta.get("error"):
        return (
            {
                "error": out_meta["error"],
                "details": out_meta.get("details"),
                "trace": {"steps": trace_steps},
            },
            int(out_meta.get("status_code", 502)),
        )
    if out_blocked:
        out_block_body = (out_meta.get("trace_step") or {}).get("response", {}).get("body")
        safe_trace_steps = _redact_trace_for_out_block(trace_steps)
        safe_block_body = _redact_block_body_for_client(out_block_body)
        return (
            {
                "response": _block_message("Response", safe_block_body),
                "guardrails": {"enabled": True, "blocked": True, "stage": "OUT"},
                "trace": {"steps": safe_trace_steps},
            },
            200,
        )

    return (
        {
            "response": text,
            "guardrails": {"enabled": True, "blocked": False},
            "trace": {"steps": trace_steps},
        },
        200,
    )
