import json
import os
import select
import shlex
import subprocess
import sys
import time
from typing import Any


DEFAULT_MCP_PROTOCOL_VERSION = os.getenv("MCP_PROTOCOL_VERSION", "2024-11-05")


class MCPError(Exception):
    pass


class MCPClient:
    def __init__(self, command: list[str], timeout_seconds: float = 15.0):
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.proc: subprocess.Popen | None = None
        self._next_id = 1
        self.server_info: dict[str, Any] | None = None
        self.capabilities: dict[str, Any] | None = None

    def __enter__(self) -> "MCPClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self.proc is not None:
            return
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        result = self.request(
            "initialize",
            {
                "protocolVersion": DEFAULT_MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "local-llm-demo", "version": "1.0"},
            },
        )
        self.server_info = result.get("serverInfo") if isinstance(result, dict) else None
        self.capabilities = result.get("capabilities") if isinstance(result, dict) else None
        self.notify("notifications/initialized", {})

    def close(self) -> None:
        proc = self.proc
        self.proc = None
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _stdout_fd(self) -> int:
        if not self.proc or not self.proc.stdout:
            raise MCPError("MCP process is not started.")
        return self.proc.stdout.fileno()

    def _wait_readable(self, timeout_seconds: float) -> None:
        fd = self._stdout_fd()
        ready, _, _ = select.select([fd], [], [], timeout_seconds)
        if not ready:
            raise MCPError("MCP read timeout.")

    def _readline(self, deadline: float) -> bytes:
        fd = self._stdout_fd()
        buf = bytearray()
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise MCPError("MCP read timeout while waiting for header line.")
            self._wait_readable(remaining)
            chunk = os.read(fd, 1)
            if not chunk:
                raise MCPError("MCP server closed stdout.")
            buf.extend(chunk)
            if chunk == b"\n":
                return bytes(buf)

    def _readexact(self, nbytes: int, deadline: float) -> bytes:
        fd = self._stdout_fd()
        buf = bytearray()
        while len(buf) < nbytes:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise MCPError("MCP read timeout while waiting for payload.")
            self._wait_readable(remaining)
            chunk = os.read(fd, nbytes - len(buf))
            if not chunk:
                raise MCPError("MCP server closed stdout.")
            buf.extend(chunk)
        return bytes(buf)

    def _read_message(self, timeout_seconds: float | None = None) -> dict[str, Any]:
        deadline = time.time() + (timeout_seconds or self.timeout_seconds)
        headers: dict[str, str] = {}
        while True:
            line = self._readline(deadline)
            if line in (b"\r\n", b"\n"):
                break
            text = line.decode("utf-8", errors="replace").strip()
            if ":" not in text:
                continue
            key, value = text.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        if "content-length" not in headers:
            raise MCPError("MCP message missing Content-Length header.")
        try:
            content_length = int(headers["content-length"])
        except ValueError as exc:
            raise MCPError("Invalid MCP Content-Length header.") from exc
        raw = self._readexact(content_length, deadline)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MCPError("Invalid JSON from MCP server.") from exc
        if not isinstance(parsed, dict):
            raise MCPError("Unexpected MCP message shape.")
        return parsed

    def _send_message(self, payload: dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise MCPError("MCP process is not started.")
        raw = json.dumps(payload).encode("utf-8")
        frame = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
        try:
            self.proc.stdin.write(frame)
            self.proc.stdin.flush()
        except Exception as exc:
            raise MCPError(f"Failed writing to MCP server: {exc}") from exc

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send_message(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
        )

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        self._send_message(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            }
        )
        while True:
            msg = self._read_message()
            if "id" in msg and msg.get("id") == req_id:
                if "error" in msg:
                    raise MCPError(f"MCP {method} error: {msg.get('error')}")
                result = msg.get("result")
                if not isinstance(result, dict):
                    return {"value": result}
                return result
            # Ignore notifications and other request/response traffic for this minimal client.

    def tools_list(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {})
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []

    def tools_call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})


def mcp_client_from_env() -> MCPClient | None:
    cmd_str = os.getenv("MCP_SERVER_COMMAND", "").strip()
    if not cmd_str:
        # Default to the bundled local MCP stdio tool server for easy demos.
        local_server = os.path.join(os.path.dirname(__file__), "mcp_tool_server.py")
        if os.path.exists(local_server):
            cmd_str = f"{shlex.quote(sys.executable)} {shlex.quote(local_server)}"
        else:
            return None
    timeout = float(os.getenv("MCP_TIMEOUT_SECONDS", "15"))
    command = shlex.split(cmd_str)
    if not command:
        return None
    return MCPClient(command=command, timeout_seconds=timeout)
