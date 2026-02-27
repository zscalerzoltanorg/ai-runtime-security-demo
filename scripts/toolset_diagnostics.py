#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import providers
import tooling


def _pretty(obj):
    return json.dumps(obj, indent=2, ensure_ascii=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP toolset + Anthropic payload diagnostics")
    parser.add_argument("--prompt", default="Hello world")
    parser.add_argument("--model", default=os.getenv("ANTHROPIC_MODEL", providers.DEFAULT_ANTHROPIC_MODEL))
    parser.add_argument(
        "--include-tools",
        choices=["true", "false"],
        default="true",
        help="Override INCLUDE_TOOLS_IN_LLM_REQUEST for this diagnostic run",
    )
    args = parser.parse_args()

    os.environ["INCLUDE_TOOLS_IN_LLM_REQUEST"] = args.include_tools

    trace_id = uuid4().hex
    tool_defs, servers, startup_snapshot = tooling.discover_mcp_toolset(trace_id=trace_id)
    print("=== Step 1: MCP servers connected ===")
    print(_pretty(servers))
    print("=== Step 2: MCP tools discovered ===")
    print(_pretty([{"id": t.id, "name": t.name, "source_server": t.source_server, "description": t.description, "input_schema": t.input_schema} for t in tool_defs]))
    print("=== Step 3: toolset.snapshot (chat_start) ===")
    print(_pretty(startup_snapshot))

    pre_llm_snapshot = tooling.make_toolset_snapshot_event(
        trace_id=trace_id,
        servers=servers,
        tools=tool_defs,
        stage="before_llm_call_1",
    )
    print("=== Step 4: toolset.snapshot (before_llm_call_1) ===")
    print(_pretty(pre_llm_snapshot))

    text, meta = providers.call_provider_messages(
        "anthropic",
        [{"role": "user", "content": args.prompt}],
        ollama_url="http://127.0.0.1:11434",
        ollama_model="llama3.2:1b",
        anthropic_model=args.model,
        tool_defs=tool_defs,
    )

    trace_step = (meta or {}).get("trace_step") or {}
    request_payload = ((trace_step.get("request") or {}).get("payload") or {})
    attached_tools = request_payload.get("tools") if isinstance(request_payload, dict) else None
    attached_count = len(attached_tools) if isinstance(attached_tools, list) else 0

    print("=== Step 5: Anthropic request payload (redacted trace copy) ===")
    print(_pretty((trace_step.get("request") or {})))
    print("=== Step 6: Confirmation ===")
    print(f"tools field present: {bool(isinstance(attached_tools, list))}")
    print(f"tools attached count: {attached_count}")
    print(f"provider call success: {text is not None}")
    if text is None:
        print(f"provider call error: {meta.get('error')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
