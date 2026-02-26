import json
import os
from typing import Callable

import agentic


def _int_env(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


MULTI_AGENT_MAX_SPECIALIST_ROUNDS = _int_env("MULTI_AGENT_MAX_SPECIALIST_ROUNDS", 1)


def _latest_user_prompt(messages: list[dict]) -> str:
    for msg in reversed(messages or []):
        if str((msg or {}).get("role") or "").lower() == "user":
            return str((msg or {}).get("content") or "")
    return ""


def _conversation_summary(messages: list[dict], limit: int = 8) -> str:
    rows: list[str] = []
    for msg in (messages or [])[-limit:]:
        role = str((msg or {}).get("role") or "assistant").lower()
        content = str((msg or {}).get("content") or "").strip()
        if not content:
            continue
        label = "USER" if role == "user" else "ASSISTANT"
        rows.append(f"{label}: {content}")
    return "\n".join(rows)


def _llm_agent_step(
    *,
    provider_messages_call: Callable[[list[dict]], tuple[str | None, dict]],
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    context_messages: list[dict],
) -> tuple[str | None, dict, dict]:
    convo = _conversation_summary(context_messages)
    composed_user = user_prompt.strip()
    if convo:
        composed_user = (
            "Conversation context (most recent turns):\n"
            f"{convo}\n\n"
            "Current task:\n"
            f"{user_prompt.strip()}"
        )
    msgs = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": composed_user},
    ]
    text, meta = provider_messages_call(msgs)
    trace_item = {
        "kind": "llm",
        "agent": agent_name,
        "step": None,
        "trace_step": meta.get("trace_step"),
        "raw_output": text,
    }
    return text, meta, trace_item


def run_multi_agent_turn(
    *,
    conversation_messages: list[dict],
    provider_messages_call: Callable[[list[dict]], tuple[str | None, dict]],
    tools_enabled: bool,
) -> tuple[dict, int]:
    agent_trace: list[dict] = []
    latest_user = _latest_user_prompt(conversation_messages).strip()
    if not latest_user:
        return (
            {
                "error": "Multi-agent mode requires a user prompt.",
                "agent_trace": [],
                "multi_agent": {"enabled": True, "implemented": True},
            },
            400,
        )

    planner_prompt = (
        "You are the Orchestrator agent for a multi-agent demo.\n"
        "Create a concise plan for specialist agents. Return ONLY JSON with this shape:\n"
        '{"goal":"...","needs_tools":true|false,"research_focus":"...","analysis_focus":"...","final_style":"..."}'
    )
    agent_trace.append(
        {
            "kind": "multi_agent",
            "event": "pipeline_start",
            "agent": "orchestrator",
            "agents": ["orchestrator", "researcher", "reviewer", "finalizer"],
            "tools_enabled": bool(tools_enabled),
        }
    )
    planner_text, planner_meta, planner_trace = _llm_agent_step(
        provider_messages_call=provider_messages_call,
        agent_name="orchestrator",
        system_prompt=planner_prompt,
        user_prompt=latest_user,
        context_messages=conversation_messages,
    )
    agent_trace.append(planner_trace)
    if planner_text is None:
        return (
            {
                "error": planner_meta.get("error", "Orchestrator agent failed."),
                "details": planner_meta.get("details"),
                "agent_trace": agent_trace,
                "trace": {"steps": [planner_meta.get("trace_step", {})]},
                "multi_agent": {"enabled": True, "implemented": True},
            },
            int(planner_meta.get("status_code", 502)),
        )

    plan = agentic._extract_json(planner_text) or {}  # noqa: SLF001
    needs_tools = bool(plan.get("needs_tools")) if isinstance(plan, dict) else False
    research_focus = str((plan or {}).get("research_focus") or latest_user)
    analysis_focus = str((plan or {}).get("analysis_focus") or "Extract key facts, risks, and recommendations.")
    final_style = str((plan or {}).get("final_style") or "Clear, concise answer with bullets when helpful.")

    research_outputs: list[str] = []
    research_agent_trace: list[dict] = []
    agent_trace.append(
        {
            "kind": "multi_agent",
            "event": "handoff",
            "agent": "orchestrator",
            "to_agent": "researcher",
            "needs_tools_plan": needs_tools,
            "research_focus": research_focus,
        }
    )
    for round_idx in range(1, max(1, MULTI_AGENT_MAX_SPECIALIST_ROUNDS) + 1):
        research_task = (
            f"Research task round {round_idx}: {research_focus}\n"
            "Use tools when helpful and available. Return a useful answer for the analyst."
        )
        research_messages = list(conversation_messages) + [{"role": "user", "content": research_task}]
        research_payload, research_status = agentic.run_agentic_turn(
            conversation_messages=research_messages,
            provider_messages_call=provider_messages_call,
            tools_enabled=tools_enabled and needs_tools,
        )
        round_trace = list(research_payload.get("agent_trace", []) or [])
        for item in round_trace:
            if isinstance(item, dict):
                item.setdefault("agent", "researcher")
                item["agent_round"] = round_idx
        research_agent_trace.extend(round_trace)
        if research_status != 200:
            payload = {
                "error": research_payload.get("error", "Research agent failed."),
                "details": research_payload.get("details"),
                "agent_trace": agent_trace + research_agent_trace,
                "trace": research_payload.get("trace", {"steps": []}),
                "multi_agent": {
                    "enabled": True,
                    "implemented": True,
                    "failed_agent": "researcher",
                },
            }
            return payload, research_status
        research_outputs.append(str(research_payload.get("response") or "").strip())
        if research_outputs[-1]:
            break

    agent_trace.extend(research_agent_trace)
    research_output = research_outputs[-1] if research_outputs else "(No research output)"

    reviewer_prompt = (
        "You are the Reviewer agent.\n"
        "Review the research output for accuracy risks, gaps, and clarity.\n"
        "Return ONLY JSON with this shape:\n"
        '{"strengths":["..."],"risks":["..."],"fixes":["..."],"approved_summary":"..."}'
    )
    reviewer_task = (
        f"Original user request:\n{latest_user}\n\n"
        f"Research output:\n{research_output}\n\n"
        f"Analysis focus:\n{analysis_focus}"
    )
    agent_trace.append(
        {
            "kind": "multi_agent",
            "event": "handoff",
            "agent": "researcher",
            "to_agent": "reviewer",
        }
    )
    reviewer_text, reviewer_meta, reviewer_trace = _llm_agent_step(
        provider_messages_call=provider_messages_call,
        agent_name="reviewer",
        system_prompt=reviewer_prompt,
        user_prompt=reviewer_task,
        context_messages=[],
    )
    agent_trace.append(reviewer_trace)
    if reviewer_text is None:
        return (
            {
                "error": reviewer_meta.get("error", "Reviewer agent failed."),
                "details": reviewer_meta.get("details"),
                "agent_trace": agent_trace,
                "trace": {"steps": [reviewer_meta.get("trace_step", {})]},
                "multi_agent": {"enabled": True, "implemented": True, "failed_agent": "reviewer"},
            },
            int(reviewer_meta.get("status_code", 502)),
        )
    reviewer_json = agentic._extract_json(reviewer_text) or {}  # noqa: SLF001

    finalizer_prompt = (
        "You are the Finalizer agent in a multi-agent app.\n"
        "Produce the final user-facing response using the orchestrator plan, research output, and reviewer notes.\n"
        "Do not mention hidden chain-of-thought. If tools were not used, be transparent.\n"
        f"Style guidance: {final_style}"
    )
    finalizer_task = (
        f"User request:\n{latest_user}\n\n"
        f"Orchestrator plan (raw):\n{planner_text}\n\n"
        f"Research output:\n{research_output}\n\n"
        f"Reviewer notes:\n{json.dumps(reviewer_json) if reviewer_json else reviewer_text}"
    )
    agent_trace.append(
        {
            "kind": "multi_agent",
            "event": "handoff",
            "agent": "reviewer",
            "to_agent": "finalizer",
        }
    )
    final_text, final_meta, final_trace = _llm_agent_step(
        provider_messages_call=provider_messages_call,
        agent_name="finalizer",
        system_prompt=finalizer_prompt,
        user_prompt=finalizer_task,
        context_messages=[],
    )
    agent_trace.append(final_trace)
    if final_text is None:
        return (
            {
                "error": final_meta.get("error", "Finalizer agent failed."),
                "details": final_meta.get("details"),
                "agent_trace": agent_trace,
                "trace": {"steps": [final_meta.get("trace_step", {})]},
                "multi_agent": {"enabled": True, "implemented": True, "failed_agent": "finalizer"},
            },
            int(final_meta.get("status_code", 502)),
        )

    return (
        {
            "response": final_text.strip() or "(Empty response)",
            "agent_trace": agent_trace,
            "multi_agent": {
                "enabled": True,
                "implemented": True,
                "agents": ["orchestrator", "researcher", "reviewer", "finalizer"],
                "tools_enabled": bool(tools_enabled),
                "research_used_tools": any((i or {}).get("kind") == "tool" for i in research_agent_trace),
                "needs_tools_plan": needs_tools,
            },
            "trace": {"steps": []},
        },
        200,
    )
