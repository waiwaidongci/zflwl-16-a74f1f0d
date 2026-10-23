#!/usr/bin/env python3
"""Starter oscillator identifier that assumes undamped unit motion."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("REFUSED: expected input and output paths", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("REFUSED: unreadable input", file=sys.stderr)
        return 2

    queries = payload["queries"]
    result = {
        "energy_ratio": 1.0,
        "model": {
            "amplitude": 1.0,
            "damping_rate": 0.0,
            "offset": 0.0,
            "omega": 1.0,
            "phase": 0.0,
        },
        "predictions": [
            {"t": time, "x": round(math.cos(time), 6)} for time in queries
        ],
        "rms": 0.0,
        "status": "ok",
    }
    target.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
