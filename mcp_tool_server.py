import json
import sys
from typing import Any

import agentic


PROTOCOL_VERSION = "2024-11-05"


def _send(msg: dict[str, Any]) -> None:
    raw = json.dumps(msg).encode("utf-8")
    frame = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
    sys.stdout.buffer.write(frame)
    sys.stdout.buffer.flush()


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("utf-8", errors="replace").strip()
        if ":" not in text:
            continue
        k, v = text.split(":", 1)
        headers[k.strip().lower()] = v.strip()

    if "content-length" not in headers:
        return None
    try:
        n = int(headers["content-length"])
    except ValueError:
        return None
    body = sys.stdin.buffer.read(n)
    if not body:
        return None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _tools_list() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name, meta in agentic.TOOLS.items():
        if not isinstance(meta, dict):
            continue
        tools.append(
            {
                "name": name,
                "description": str(meta.get("description") or ""),
                "inputSchema": meta.get("input_schema") or {},
            }
        )
    return tools


def _handle_request(req: dict[str, Any]) -> None:
    req_id = req.get("id")
    method = str(req.get("method") or "")
    params = req.get("params") if isinstance(req.get("params"), dict) else {}

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "local-llm-demo-mcp-tools", "version": "1.0"},
        }
        if req_id is not None:
            _send({"jsonrpc": "2.0", "id": req_id, "result": result})
        return

    if method == "notifications/initialized":
        return

    if method == "tools/list":
        if req_id is not None:
            _send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": _tools_list()}})
        return

    if method == "tools/call":
        tool_name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        output_text, tool_meta = agentic.run_tool(tool_name, arguments, mcp_client=None)
        is_error = str(output_text).startswith("Error:")
        result = {
            "content": [{"type": "text", "text": str(output_text)}],
            "isError": is_error,
            "meta": tool_meta,
        }
        if req_id is not None:
            _send({"jsonrpc": "2.0", "id": req_id, "result": result})
        return

    if req_id is not None:
        _send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )


def main() -> None:
    while True:
        msg = _read_message()
        if msg is None:
            break
        _handle_request(msg)


if __name__ == "__main__":
    main()
