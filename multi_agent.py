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
MULTI_AGENT_MAX_SPECIALISTS = max(1, min(_int_env("MULTI_AGENT_MAX_SPECIALISTS", 3), 4))


SPECIALIST_ROLE_SPECS: dict[str, dict[str, str]] = {
    "researcher": {
        "label": "Researcher",
        "summary": "Gather facts and use tools/MCP when useful and allowed.",
        "system": (
            "You are a Researcher specialist in a bounded multi-agent demo.\n"
            "Answer only the assigned task. Use concrete findings, cite tool output when present, "
            "and call out unknowns instead of guessing."
        ),
    },
    "tool_auditor": {
        "label": "Tool Auditor",
        "summary": "Decide whether tools are needed and whether tool results are sufficient.",
        "system": (
            "You are a Tool Auditor specialist in a bounded multi-agent demo.\n"
            "Review the request and available context for tool-use needs, tool risks, and missing evidence. "
            "Do not invent tool results."
        ),
    },
    "security_reviewer": {
        "label": "Security Reviewer",
        "summary": "Check for data handling, policy, and safety concerns.",
        "system": (
            "You are a Security Reviewer specialist in a bounded multi-agent demo.\n"
            "Identify security, privacy, policy, and data-handling risks relevant to the request. "
            "Keep the review practical and concise."
        ),
    },
    "domain_analyst": {
        "label": "Domain Analyst",
        "summary": "Analyze the user goal and convert findings into useful guidance.",
        "system": (
            "You are a Domain Analyst specialist in a bounded multi-agent demo.\n"
            "Analyze the user request and prior context, separate facts from assumptions, and provide "
            "decision-ready guidance."
        ),
    },
}


def _allowed_specialist_roles() -> list[str]:
    return list(SPECIALIST_ROLE_SPECS.keys())


def _specialist_label(role: str) -> str:
    return SPECIALIST_ROLE_SPECS.get(role, {}).get("label") or role.replace("_", " ").title()


def _specialist_system_prompt(role: str) -> str:
    return SPECIALIST_ROLE_SPECS.get(role, {}).get("system") or SPECIALIST_ROLE_SPECS["domain_analyst"]["system"]


def _clean_text(value: object, fallback: str = "", limit: int = 800) -> str:
    text = str(value or fallback or "").strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "..."
    return text


def _normalize_specialist_plan(plan: object, latest_user: str) -> dict:
    if not isinstance(plan, dict):
        plan = {}
    allowed = set(_allowed_specialist_roles())
    specialists: list[dict] = []
    raw_specialists = plan.get("specialists")
    if isinstance(raw_specialists, list):
        for item in raw_specialists:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower().replace("-", "_")
            if role not in allowed:
                continue
            task = _clean_text(item.get("task"), latest_user)
            specialists.append(
                {
                    "role": role,
                    "label": _specialist_label(role),
                    "task": task or latest_user,
                    "tools_allowed": bool(item.get("tools_allowed")),
                }
            )
            if len(specialists) >= MULTI_AGENT_MAX_SPECIALISTS:
                break

    # Backward-compatible fallback for older/simple planner outputs.
    if not specialists:
        needs_tools = bool(plan.get("needs_tools"))
        research_focus = _clean_text(plan.get("research_focus"), latest_user)
        analysis_focus = _clean_text(plan.get("analysis_focus"), "Analyze the request and produce useful guidance.")
        specialists.append(
            {
                "role": "researcher" if needs_tools else "domain_analyst",
                "label": _specialist_label("researcher" if needs_tools else "domain_analyst"),
                "task": research_focus or analysis_focus or latest_user,
                "tools_allowed": needs_tools,
            }
        )
        if analysis_focus and needs_tools and len(specialists) < MULTI_AGENT_MAX_SPECIALISTS:
            specialists.append(
                {
                    "role": "domain_analyst",
                    "label": _specialist_label("domain_analyst"),
                    "task": analysis_focus,
                    "tools_allowed": False,
                }
            )

    return {
        "goal": _clean_text(plan.get("goal"), latest_user),
        "specialists": specialists[:MULTI_AGENT_MAX_SPECIALISTS],
        "review_required": True,
        "final_style": _clean_text(
            plan.get("final_style"),
            "Clear, concise answer with bullets when helpful.",
            limit=240,
        ),
    }


def _planner_system_prompt() -> str:
    role_lines = "\n".join(
        f"- {role}: {spec['summary']}" for role, spec in SPECIALIST_ROLE_SPECS.items()
    )
    return (
        "You are the Orchestrator agent for a multi-agent learning demo.\n"
        "Decide which bounded specialist agents should be spawned for the user's request.\n"
        f"Choose 1-{MULTI_AGENT_MAX_SPECIALISTS} specialists from this allowed list:\n"
        f"{role_lines}\n"
        "Use researcher only when external facts, local workspace inspection, or tools/MCP would help.\n"
        "Set tools_allowed=true only for specialists that should be allowed to call tools.\n"
        "Return ONLY JSON with this shape:\n"
        '{"goal":"...","specialists":[{"role":"researcher|tool_auditor|security_reviewer|domain_analyst",'
        '"task":"...","tools_allowed":true|false}],"final_style":"..."}'
    )


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
    local_tasks_enabled: bool = False,
    tool_permission_profile: str = "standard",
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

    planner_prompt = _planner_system_prompt()
    agent_trace.append(
        {
            "kind": "multi_agent",
            "event": "pipeline_start",
            "agent": "orchestrator",
            "agents": ["orchestrator", "specialists", "reviewer", "finalizer"],
            "allowed_specialists": _allowed_specialist_roles(),
            "max_specialists": MULTI_AGENT_MAX_SPECIALISTS,
            "tools_enabled": bool(tools_enabled),
            "local_tasks_enabled": bool(local_tasks_enabled),
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
                **(
                    {"proxy_guardrails_block": planner_meta.get("proxy_guardrails_block")}
                    if isinstance(planner_meta.get("proxy_guardrails_block"), dict)
                    else {}
                ),
                "agent_trace": agent_trace,
                "trace": {"steps": [planner_meta.get("trace_step", {})]},
                "multi_agent": {"enabled": True, "implemented": True},
            },
            int(planner_meta.get("status_code", 502)),
        )

    plan = _normalize_specialist_plan(agentic._extract_json(planner_text), latest_user)  # noqa: SLF001
    specialists = plan["specialists"]
    final_style = str(plan.get("final_style") or "Clear, concise answer with bullets when helpful.")

    specialist_outputs: list[dict] = []
    specialist_agent_trace: list[dict] = []
    for index, specialist in enumerate(specialists, start=1):
        role = str(specialist.get("role") or "domain_analyst")
        label = str(specialist.get("label") or _specialist_label(role))
        task = str(specialist.get("task") or latest_user)
        specialist_id = f"{role}_{index}"
        use_tools = bool(tools_enabled and specialist.get("tools_allowed"))
        agent_trace.append(
            {
                "kind": "multi_agent",
                "event": "spawn_agent",
                "agent": "orchestrator",
                "to_agent": role,
                "agent_id": specialist_id,
                "label": label,
                "task": task,
                "tools_allowed": bool(specialist.get("tools_allowed")),
                "tools_enabled_for_agent": use_tools,
            }
        )

        if role == "researcher" and use_tools:
            outputs: list[str] = []
            for round_idx in range(1, max(1, MULTI_AGENT_MAX_SPECIALIST_ROUNDS) + 1):
                research_task = (
                    f"{label} task round {round_idx}: {task}\n"
                    "Use tools when helpful and available. Return concise findings for the next agent."
                )
                research_messages = list(conversation_messages) + [{"role": "user", "content": research_task}]
                research_payload, research_status = agentic.run_agentic_turn(
                    conversation_messages=research_messages,
                    provider_messages_call=provider_messages_call,
                    tools_enabled=use_tools,
                    local_tasks_enabled=local_tasks_enabled,
                    tool_permission_profile=tool_permission_profile,
                )
                round_trace = list(research_payload.get("agent_trace", []) or [])
                for item in round_trace:
                    if isinstance(item, dict):
                        item.setdefault("agent", role)
                        item["agent_id"] = specialist_id
                        item["agent_round"] = round_idx
                specialist_agent_trace.extend(round_trace)
                if research_status != 200:
                    return (
                        {
                            "error": research_payload.get("error", f"{label} failed."),
                            "details": research_payload.get("details"),
                            "agent_trace": agent_trace + specialist_agent_trace,
                            "trace": research_payload.get("trace", {"steps": []}),
                            "multi_agent": {
                                "enabled": True,
                                "implemented": True,
                                "failed_agent": role,
                                "spawned_agents": specialists,
                            },
                        },
                        research_status,
                    )
                outputs.append(str(research_payload.get("response") or "").strip())
                if outputs[-1]:
                    break
            output = outputs[-1] if outputs else ""
        else:
            specialist_task = (
                f"Assigned specialist role: {label}\n"
                f"Assigned task:\n{task}\n\n"
                "Return a concise specialist report. Include assumptions or gaps if relevant."
            )
            text, meta, trace_item = _llm_agent_step(
                provider_messages_call=provider_messages_call,
                agent_name=role,
                system_prompt=_specialist_system_prompt(role),
                user_prompt=specialist_task,
                context_messages=conversation_messages,
            )
            if trace_item:
                trace_item["agent_id"] = specialist_id
                specialist_agent_trace.append(trace_item)
            if text is None:
                return (
                    {
                        "error": meta.get("error", f"{label} failed."),
                        "details": meta.get("details"),
                        **(
                            {"proxy_guardrails_block": meta.get("proxy_guardrails_block")}
                            if isinstance(meta.get("proxy_guardrails_block"), dict)
                            else {}
                        ),
                        "agent_trace": agent_trace + specialist_agent_trace,
                        "trace": {"steps": [meta.get("trace_step", {})]},
                        "multi_agent": {
                            "enabled": True,
                            "implemented": True,
                            "failed_agent": role,
                            "spawned_agents": specialists,
                        },
                    },
                    int(meta.get("status_code", 502)),
                )
            output = str(text or "").strip()

        specialist_outputs.append({"role": role, "label": label, "task": task, "output": output})
        agent_trace.append(
            {
                "kind": "multi_agent",
                "event": "agent_complete",
                "agent": role,
                "agent_id": specialist_id,
                "label": label,
                "task": task,
                "output_chars": len(output),
                "output_preview": _clean_text(output)[:700],
                "used_tools": bool(role == "researcher" and use_tools),
            }
        )

    agent_trace.extend(specialist_agent_trace)
    specialist_report = "\n\n".join(
        f"{item['label']} ({item['role']})\nTask: {item['task']}\nOutput:\n{item['output'] or '(No output)'}"
        for item in specialist_outputs
    ) or "(No specialist output)"

    reviewer_prompt = (
        "You are the Reviewer agent.\n"
        "Review the specialist outputs for accuracy risks, gaps, tool-use issues, and clarity.\n"
        "Return ONLY JSON with this shape:\n"
        '{"strengths":["..."],"risks":["..."],"fixes":["..."],"approved_summary":"..."}'
    )
    reviewer_task = (
        f"Original user request:\n{latest_user}\n\n"
        f"Orchestrator goal:\n{plan.get('goal')}\n\n"
        f"Specialist outputs:\n{specialist_report}"
    )
    agent_trace.append(
        {
            "kind": "multi_agent",
            "event": "handoff",
            "agent": "specialists",
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
                **(
                    {"proxy_guardrails_block": reviewer_meta.get("proxy_guardrails_block")}
                    if isinstance(reviewer_meta.get("proxy_guardrails_block"), dict)
                    else {}
                ),
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
        f"Specialist outputs:\n{specialist_report}\n\n"
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
                **(
                    {"proxy_guardrails_block": final_meta.get("proxy_guardrails_block")}
                    if isinstance(final_meta.get("proxy_guardrails_block"), dict)
                    else {}
                ),
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
                "agents": ["orchestrator", "specialists", "reviewer", "finalizer"],
                "spawned_agents": specialists,
                "tools_enabled": bool(tools_enabled),
                "research_used_tools": any((i or {}).get("kind") == "tool" for i in specialist_agent_trace),
                "needs_tools_plan": any(bool(i.get("tools_allowed")) for i in specialists),
            },
            "trace": {"steps": []},
        },
        200,
    )
