"""Restart the native Windows app after its current process releases files."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102


def _log(handle, message: str) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    handle.write(f"[{timestamp}] {message}\n")
    handle.flush()


def _wait_for_parent(parent_pid: int, timeout_ms: int = 60_000) -> bool:
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(parent_pid))
    if not handle:
        return True
    try:
        result = kernel32.WaitForSingleObject(handle, int(timeout_ms))
        return result == WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--install-deps", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8", buffering=1) as log_handle:
        _log(log_handle, f"Windows restart helper started for parent PID {args.parent_pid}.")
        args.ready_file.write_text("ready\n", encoding="utf-8")
        if not _wait_for_parent(args.parent_pid):
            _log(log_handle, "Timed out waiting for the previous app process to exit.")
            return 1

        if args.install_deps:
            _log(log_handle, "Installing updated Python requirements after process shutdown.")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                    cwd=args.cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    timeout=300,
                    check=False,
                )
                if result.returncode != 0:
                    _log(log_handle, f"Dependency installation failed with exit code {result.returncode}; attempting app restart anyway.")
            except Exception as exc:
                _log(log_handle, f"Dependency installation failed: {exc}; attempting app restart anyway.")

        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            child = subprocess.Popen(
                [sys.executable, str(args.app)],
                cwd=args.cwd,
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                close_fds=True,
                creationflags=creation_flags,
            )
        except Exception as exc:
            _log(log_handle, f"Unable to launch updated app: {exc}")
            return 1
        _log(log_handle, f"Updated app launched as PID {child.pid}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
