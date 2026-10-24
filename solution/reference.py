#!/usr/bin/env python3
"""Reference nonlinear system identification for a damped oscillator."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any


INPUT_KEYS = {"schema", "samples", "queries", "noise_floor"}
DAMPING_MIN = 0.0
DAMPING_MAX = 1.5
OMEGA_MIN = 0.1
OMEGA_MAX = 4.0


class Refused(ValueError):
    pass


def _number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Refused(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise Refused(f"{label} is outside its allowed range")
    return number


def parse_input(path: Path) -> tuple[list[float], list[float], list[float], float]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Refused("input cannot be read") from exc
    except json.JSONDecodeError as exc:
        raise Refused("input is not valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != INPUT_KEYS:
        raise Refused("top-level keys do not match damped-trace-v1")
    if payload.get("schema") != "damped-trace-v1":
        raise Refused("unsupported schema")

    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, list) or not 12 <= len(raw_samples) <= 64:
        raise Refused("samples must contain twelve to sixty-four entries")
    times: list[float] = []
    values: list[float] = []
    previous = -1.0
    for index, item in enumerate(raw_samples):
        if not isinstance(item, dict) or set(item) != {"t", "x"}:
            raise Refused(f"sample {index} has an invalid key set")
        time = _number(item.get("t"), f"sample {index} t", 0.0, 120.0)
        value = _number(item.get("x"), f"sample {index} x", -1e12, 1e12)
        if time <= previous:
            raise Refused("sample times must strictly increase")
        previous = time
        times.append(time)
        values.append(value)

    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list) or not 1 <= len(raw_queries) <= 24:
        raise Refused("queries must contain one to twenty-four times")
    queries: list[float] = []
    previous = -1.0
    for index, value in enumerate(raw_queries):
        time = _number(value, f"query {index}", 0.0, 120.0)
        if time <= previous:
            raise Refused("query times must strictly increase")
        previous = time
        queries.append(time)
    noise_floor = _number(payload.get("noise_floor"), "noise_floor", 0.0, 0.05)
    return times, values, queries, noise_floor


def _solve_three(matrix: list[list[float]], vector: list[float]) -> list[float]:
    work = [list(row) + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) < 1e-14:
            raise Refused("sample geometry does not determine the oscillator")
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        for item in range(column, 4):
            work[column][item] /= divisor
        for row in range(3):
            if row == column:
                continue
            factor = work[row][column]
            for item in range(column, 4):
                work[row][item] -= factor * work[column][item]
    return [work[row][3] for row in range(3)]


def _linear_fit(
    times: list[float],
    values: list[float],
    damping: float,
    omega: float,
) -> tuple[float, tuple[float, float, float]]:
    rows: list[tuple[float, float, float]] = []
    for time in times:
        envelope = math.exp(-damping * time)
        rows.append(
            (
                envelope * math.cos(omega * time),
                envelope * math.sin(omega * time),
                1.0,
            )
        )
    matrix = [
        [math.fsum(row[left] * row[right] for row in rows) for right in range(3)]
        for left in range(3)
    ]
    vector = [
        math.fsum(value * row[column] for value, row in zip(values, rows))
        for column in range(3)
    ]
    coefficients = _solve_three(matrix, vector)
    sse = math.fsum(
        (
            value
            - coefficients[0] * row[0]
            - coefficients[1] * row[1]
            - coefficients[2]
        )
        ** 2
        for value, row in zip(values, rows)
    )
    return sse, (coefficients[0], coefficients[1], coefficients[2])


def recover(
    times: list[float],
    values: list[float],
    queries: list[float],
    noise_floor: float,
) -> dict[str, Any]:
    best: tuple[float, float, float, tuple[float, float, float]] | None = None
    for alpha_index in range(61):
        damping = DAMPING_MIN + (DAMPING_MAX - DAMPING_MIN) * alpha_index / 60
        for omega_index in range(391):
            omega = OMEGA_MIN + (OMEGA_MAX - OMEGA_MIN) * omega_index / 390
            if damping >= omega:
                continue
            sse, coefficients = _linear_fit(times, values, damping, omega)
            if best is None or sse < best[0] - 1e-14:
                best = (sse, damping, omega, coefficients)
    if best is None:
        raise Refused("no admissible oscillator model was found")

    step_damping = 0.005
    step_omega = 0.005
    for _ in range(9):
        center_damping = best[1]
        center_omega = best[2]
        for damping_index in range(-4, 5):
            damping = min(
                DAMPING_MAX,
                max(DAMPING_MIN, center_damping + damping_index * step_damping),
            )
            for omega_index in range(-4, 5):
                omega = min(
                    OMEGA_MAX,
                    max(OMEGA_MIN, center_omega + omega_index * step_omega),
                )
                if damping >= omega:
                    continue
                sse, coefficients = _linear_fit(times, values, damping, omega)
                if sse < best[0] - 1e-14:
                    best = (sse, damping, omega, coefficients)
        step_damping *= 0.42
        step_omega *= 0.42

    sse, damping, omega, (cosine, sine, offset) = best
    amplitude = math.hypot(cosine, sine)
    if amplitude <= 0.0:
        raise Refused("fitted amplitude must be positive")
    phase = math.atan2(-sine, cosine)
    if phase <= -math.pi:
        phase += 2 * math.pi
    rms = math.sqrt(sse / len(times))
    if rms > noise_floor + 1e-9:
        raise Refused("sample residual exceeds noise_floor")

    predictions = [
        {
            "t": time,
            "x": round(
                offset
                + amplitude
                * math.exp(-damping * time)
                * math.cos(omega * time + phase),
                6,
            ),
        }
        for time in queries
    ]
    return {
        "energy_ratio": round(math.exp(-4 * math.pi * damping / omega), 6),
        "model": {
            "amplitude": round(amplitude, 6),
            "damping_rate": round(damping, 6),
            "offset": round(offset, 6),
            "omega": round(omega, 6),
            "phase": round(phase, 6),
        },
        "predictions": predictions,
        "rms": round(rms, 6),
        "status": "ok",
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("REFUSED: expected input and output paths", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    try:
        times, values, queries, noise_floor = parse_input(source)
        result = recover(times, values, queries, noise_floor)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    target.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
