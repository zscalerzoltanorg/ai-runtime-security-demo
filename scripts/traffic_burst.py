#!/usr/bin/env python3
"""
Convenience wrapper for a high-volume AI Guard demo traffic run.

This preserves the tested "fill the logs" recipe while keeping the main
traffic_generator.py script fully configurable. Extra arguments passed to this
wrapper are appended last, so they can override these defaults.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    generator = script_dir / "traffic_generator.py"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if "--stop-file" not in sys.argv[1:]:
        Path("/tmp/ai-runtime-security-demo-traffic.stop").unlink(missing_ok=True)
    default_args = [
        sys.executable,
        str(generator),
        "--duration-hours",
        "1",
        "--parallel",
        "5",
        "--min-delay",
        "3",
        "--max-delay",
        "12",
        "--pause-every",
        "40",
        "--pause-min",
        "20",
        "--pause-max",
        "60",
        "--detector-rate",
        "0.95",
        "--response-detector-rate",
        "0.6",
        "--attachment-rate",
        "0.35",
        "--coverage-mode",
        "balanced",
        "--multi-turn-rate",
        "0.15",
        "--agentic-rate",
        "0.15",
        "--multi-agent-rate",
        "0.03",
        "--tools-rate",
        "0.6",
        "--provider-weights",
        "ollama=10,openai=5,bedrock_invoke=3,gemini=2,anthropic=1",
        "--jsonl",
        f"traffic-burst-{timestamp}.jsonl",
    ]
    os.execv(sys.executable, default_args + sys.argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
