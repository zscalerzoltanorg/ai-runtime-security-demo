import datetime as dt
import hashlib
import os
from dataclasses import dataclass
from typing import Any

from mcp_client import mcp_client_from_env


@dataclass(frozen=True)
class ToolDef:
    id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    source_server: str


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _safe_server_name(server_info: dict[str, Any] | None, fallback: str = "mcp") -> str:
    raw = str((server_info or {}).get("name") or "").strip()
    if not raw:
        return fallback
    cleaned = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in raw.lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or fallback


def _normalize_input_schema(tool_obj: dict[str, Any]) -> dict[str, Any]:
    schema = tool_obj.get("inputSchema")
    if not isinstance(schema, dict):
        schema = tool_obj.get("input_schema")
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    return schema


def _redacted_tool_for_debug(tool: ToolDef) -> dict[str, Any]:
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "source_server": tool.source_server,
    }


def make_toolset_snapshot_event(
    *,
    trace_id: str,
    servers: list[dict[str, Any]],
    tools: list[ToolDef],
    stage: str,
) -> dict[str, Any]:
    return {
        "kind": "mcp",
        "event": "toolset.snapshot",
        "type": "toolset.snapshot",
        "trace_id": trace_id,
        "tool_source": "mcp",
        "stage": stage,
        "servers": servers,
        "tools": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "source_server": t.source_server,
            }
            for t in tools
        ],
        "counts": {"servers": len(servers), "tools": len(tools)},
        "timestamp": _utc_now_iso(),
    }


def discover_mcp_toolset(*, trace_id: str) -> tuple[list[ToolDef], list[dict[str, Any]], dict[str, Any]]:
    debug = _bool_env("TOOLSET_DEBUG_LOGS", False)
    servers: list[dict[str, Any]] = []
    tools: list[ToolDef] = []

    client = mcp_client_from_env()
    if client is None:
        event = make_toolset_snapshot_event(trace_id=trace_id, servers=servers, tools=tools, stage="chat_start")
        event["error"] = "mcp_client_not_configured"
        return tools, servers, event

    try:
        client.start()
        server_info = getattr(client, "server_info", None)
        server_name = _safe_server_name(server_info, fallback="mcp")
        server_id = hashlib.sha1(f"{server_name}:{client.command}".encode("utf-8")).hexdigest()[:12]
        servers = [
            {
                "id": server_id,
                "name": str((server_info or {}).get("name") or server_name),
                "transport": "stdio",
                "version": str((server_info or {}).get("version") or ""),
            }
        ]

        for item in client.tools_list():
            if not isinstance(item, dict):
                continue
            raw_name = str(item.get("name") or "").strip()
            if not raw_name:
                continue
            full_name = f"{server_name}.{raw_name}"
            tools.append(
                ToolDef(
                    id=f"{server_id}:{raw_name}",
                    name=full_name,
                    description=str(item.get("description") or "MCP tool").strip() or "MCP tool",
                    input_schema=_normalize_input_schema(item),
                    source_server=server_name,
                )
            )

        if debug:
            print("[toolset.debug] MCP servers connected:")
            for srv in servers:
                print(
                    f"  - id={srv.get('id')} name={srv.get('name')} transport={srv.get('transport')}"
                )
            print(f"[toolset.debug] MCP available tools ({len(tools)}):")
            for t in tools:
                print("  - " + str(_redacted_tool_for_debug(t)))

        event = make_toolset_snapshot_event(trace_id=trace_id, servers=servers, tools=tools, stage="chat_start")
        return tools, servers, event
    except Exception as exc:
        event = make_toolset_snapshot_event(trace_id=trace_id, servers=servers, tools=tools, stage="chat_start")
        event["error"] = str(exc)
        return tools, servers, event
    finally:
        try:
            client.close()
        except Exception:
            pass
