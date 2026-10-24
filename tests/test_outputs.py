from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path


ENTRY = os.environ.get("OSCILLATOR_ENTRY", "/app/identify.py")

SAFE_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
}


def _run(payload: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-S", "-P", "-B", ENTRY, str(payload), str(output)],
        text=True,
        capture_output=True,
        env=SAFE_ENV,
        timeout=30,
        check=False,
    )


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _response(parameters: dict[str, float], time: float) -> float:
    return parameters["offset"] + parameters["amplitude"] * math.exp(
        -parameters["damping_rate"] * time
    ) * math.cos(parameters["omega"] * time + parameters["phase"])


def _first_parameters() -> dict[str, float]:
    return {
        "amplitude": 2.4,
        "damping_rate": 0.18,
        "omega": 1.25,
        "phase": 0.4,
        "offset": 0.35,
    }


def _second_parameters() -> dict[str, float]:
    return {
        "amplitude": 1.7,
        "damping_rate": 0.07,
        "omega": 1.85,
        "phase": -1.1,
        "offset": -0.2,
    }


def _trace_payload() -> dict[str, object]:
    parameters = _first_parameters()
    times = sorted(
        set(
            round(0.13 * index + 0.29 * math.sin(0.7 * index) + 0.07 * (index % 3), 6)
            for index in range(24)
        )
    )
    while len(times) < 24:
        index = len(times)
        times.append(round(times[-1] + 0.23 + 0.03 * (index % 4), 6))
    return {
        "schema": "damped-trace-v1",
        "samples": [
            {"t": time, "x": round(_response(parameters, time), 9)}
            for time in times
        ],
        "queries": [0.0, 1.4, 5.1, 9.7, 17.2],
        "noise_floor": 0.000001,
    }


def _second_payload() -> dict[str, object]:
    parameters = _second_parameters()
    times = sorted(
        set(
            round(0.31 * index + 0.18 * math.sin(1.1 * index) + 0.04 * (index % 5), 6)
            for index in range(20)
        )
    )
    while len(times) < 20:
        index = len(times)
        times.append(round(times[-1] + 0.36 + 0.02 * (index % 4), 6))
    return {
        "schema": "damped-trace-v1",
        "samples": [
            {"t": time, "x": round(_response(parameters, time), 9)}
            for time in times
        ],
        "queries": [0.25, 2.5, 7.75, 14.0],
        "noise_floor": 0.000001,
    }


def _parameter_payload(
    parameters: dict[str, float],
    *,
    sample_count: int = 32,
    end_time: float = 18.0,
    noise_floor: float = 0.000000001,
) -> dict[str, object]:
    times = [
        round(end_time * index / (sample_count - 1), 9)
        for index in range(sample_count)
    ]
    return {
        "schema": "damped-trace-v1",
        "samples": [
            {"t": time, "x": round(_response(parameters, time), 12)}
            for time in times
        ],
        "queries": [0.0, round(end_time / 3.0, 6), round(end_time, 6)],
        "noise_floor": noise_floor,
    }


def test_gate_model_is_physical_and_fits_samples(tmp_path: Path) -> None:
    # case_id: OS-GATE-01 OS-MODEL-01 OS-INPUT-01 OS-MODEL-02 OS-INPUT-02
    """题面：
    「振动台在一次夹具碰撞后只留下了零散位移采样，设备的激振频率、阻尼和静平衡位置都没有」
    「`"ok"`；`model` 恰好有 `amplitude`、`damping_rate`、`omega`、`phase`、`offset`；」
    """

    source = tmp_path / "trace.json"
    output = tmp_path / "trace.out.json"
    _write(source, _trace_payload())
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert result["status"] == "ok"
    assert result["rms"] <= 0.000001
    assert result["model"]["damping_rate"] > 0
    assert set(result["model"]) == {
        "amplitude",
        "damping_rate",
        "omega",
        "phase",
        "offset",
    }


def test_irregular_trace_recovers_five_parameters(tmp_path: Path) -> None:
    # case_id: OS-FIT-01 OS-CONTEXT-01 OS-BASELINE-01
    """题面：
    「`x(t) = offset + amplitude * exp(-damping_rate*t) * cos(omega*t + phase)`。」
    """

    source = tmp_path / "trace.json"
    output = tmp_path / "parameters.out.json"
    _write(source, _trace_payload())
    completed = _run(source, output)
    model = json.loads(output.read_text(encoding="utf-8"))["model"]
    assert completed.returncode == 0
    assert abs(model["amplitude"] - 2.4) < 0.00001
    assert abs(model["damping_rate"] - 0.18) < 0.00001
    assert abs(model["omega"] - 1.25) < 0.00001
    assert abs(model["phase"] - 0.4) < 0.00001
    assert abs(model["offset"] - 0.35) < 0.00001


def test_query_predictions_follow_fitted_decay(tmp_path: Path) -> None:
    # case_id: OS-PRED-01
    """题面：
    「`predictions` 按查询顺序给出对象，每项恰好有 `t` 与 `x`。所有浮点结果保留六位小数。」
    """

    source = tmp_path / "trace.json"
    output = tmp_path / "predictions.out.json"
    _write(source, _trace_payload())
    completed = _run(source, output)
    predicted = json.loads(output.read_text(encoding="utf-8"))["predictions"]
    assert completed.returncode == 0
    assert [item["t"] for item in predicted] == [0.0, 1.4, 5.1, 9.7, 17.2]
    assert abs(predicted[0]["x"] - 2.560546) < 0.000001
    assert abs(predicted[2]["x"] - 1.194773) < 0.000001
    assert abs(predicted[4]["x"] - 0.241899) < 0.000001


def test_energy_ratio_uses_one_period_dissipation(tmp_path: Path) -> None:
    # case_id: OS-ENERGY-01 OS-OUT-01 OS-OUT-02
    """题面：
    「辨识成功后，输出包含辨识状态、`model`、`predictions`、一周期 `energy_ratio` 和 `rms`。`status` 为」
    """

    source = tmp_path / "second.json"
    output = tmp_path / "energy.out.json"
    _write(source, _second_payload())
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert abs(result["energy_ratio"] - 0.621584) < 0.000001
    assert abs(result["model"]["phase"] + 1.1) < 0.00001
    assert abs(result["model"]["offset"] + 0.2) < 0.00001


def test_public_parameter_lower_bounds_are_accepted(tmp_path: Path) -> None:
    """题面：
    「`damping_rate` 位于 `[0, 1.5]`，`omega` 位于 `[0.1, 4.0]`」
    """

    # case_id: OS-BOUND-04
    parameters = {
        "amplitude": 1.5,
        "damping_rate": 0.0,
        "omega": 0.1,
        "phase": 0.25,
        "offset": 0.4,
    }
    source = tmp_path / "lower-bounds.json"
    output = tmp_path / "lower-bounds.out.json"
    _write(source, _parameter_payload(parameters, end_time=36.0))
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert abs(result["model"]["damping_rate"]) < 0.00001
    assert abs(result["model"]["omega"] - 0.1) < 0.00001
    assert abs(result["energy_ratio"] - 1.0) < 0.000001


def test_public_parameter_upper_bounds_are_accepted(tmp_path: Path) -> None:
    """题面：
    「`damping_rate` 位于 `[0, 1.5]`，`omega` 位于 `[0.1, 4.0]`」
    """

    # case_id: OS-BOUND-05
    parameters = {
        "amplitude": 2.0,
        "damping_rate": 1.5,
        "omega": 4.0,
        "phase": 0.3,
        "offset": -0.1,
    }
    source = tmp_path / "upper-bounds.json"
    output = tmp_path / "upper-bounds.out.json"
    _write(source, _parameter_payload(parameters, sample_count=48, end_time=6.0))
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert abs(result["model"]["damping_rate"] - 1.5) < 0.00001
    assert abs(result["model"]["omega"] - 4.0) < 0.00001


def test_parameters_outside_public_domain_are_refused(tmp_path: Path) -> None:
    """题面：
    「超过时说明采样不属于这条可接受模型，应拒绝而不应猜测参数」
    """

    # case_id: OS-BOUND-06 OS-BOUND-07 OS-BOUND-08 OS-BOUND-09 OS-RANGE-01 OS-RANGE-02
    cases = [
        ("negative-damping", -0.05, 1.2, 20.0),
        ("damping-above-cap", 1.6, 2.0, 8.0),
        ("omega-below-floor", 0.0, 0.05, 120.0),
        ("omega-above-cap", 0.05, 4.1, 10.0),
    ]
    for name, damping, omega, end_time in cases:
        parameters = {
            "amplitude": 1.8,
            "damping_rate": damping,
            "omega": omega,
            "phase": 0.2,
            "offset": 0.1,
        }
        source = tmp_path / f"{name}.json"
        output = tmp_path / f"{name}.out.json"
        _write(
            source,
            _parameter_payload(
                parameters,
                sample_count=48,
                end_time=end_time,
                noise_floor=0.0000000001,
            ),
        )
        completed = _run(source, output)
        assert completed.returncode == 2, name
        assert completed.stderr.startswith("REFUSED: "), name
        assert not output.exists(), name


def test_noise_above_floor_is_refused_without_output(tmp_path: Path) -> None:
    # case_id: OS-NOISE-01 OS-FAIL-01
    """题面：
    「模型在全部样本上的均方根残差不能超过」
    """

    payload = _trace_payload()
    payload["noise_floor"] = 0
    for index, sample in enumerate(payload["samples"]):
        sample["x"] += 0.04 * math.sin(index * 1.7)
    source = tmp_path / "noise.json"
    output = tmp_path / "noise.out.json"
    _write(source, payload)
    completed = _run(source, output)
    assert completed.returncode == 2
    assert completed.stderr.startswith("REFUSED: ")
    assert not output.exists()


def test_twelve_samples_at_public_lower_bound_are_accepted(tmp_path: Path) -> None:
    # case_id: OS-LIMIT-01
    """题面：
    「`samples` 保存 12 到 64 条采样；每条仅由 `t` 与 `x` 两个字段组成。时间与位移都是有限数值，」
    """

    payload = _trace_payload()
    payload["samples"] = payload["samples"][:12]
    source = tmp_path / "twelve.json"
    output = tmp_path / "twelve.out.json"
    _write(source, payload)
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert result["status"] == "ok"
    assert abs(result["model"]["omega"] - 1.25) < 0.00001


def test_eleven_samples_are_refused(tmp_path: Path) -> None:
    # case_id: OS-LIMIT-02
    """题面：
    「`samples` 保存 12 到 64 条采样；」
    """

    payload = _trace_payload()
    payload["samples"] = payload["samples"][:11]
    source = tmp_path / "eleven.json"
    output = tmp_path / "eleven.out.json"
    _write(source, payload)
    completed = _run(source, output)
    assert completed.returncode == 2
    assert completed.stderr.startswith("REFUSED: ")
    assert not output.exists()


def test_duplicate_sample_time_is_refused(tmp_path: Path) -> None:
    # case_id: OS-DUP-01
    """题面：
    「时间落在 0 到 120 的时间坐标并严格递增」
    """

    payload = _trace_payload()
    payload["samples"][3]["t"] = payload["samples"][2]["t"]
    source = tmp_path / "duplicate.json"
    output = tmp_path / "duplicate.out.json"
    _write(source, payload)
    completed = _run(source, output)
    assert completed.returncode == 2
    assert completed.stderr.startswith("REFUSED: ")
    assert not output.exists()


def test_equal_damping_and_omega_is_refused_without_output(tmp_path: Path) -> None:
    # case_id: OS-BOUND-03
    """题面：
    「且必须满足 `damping_rate < omega`」
    """

    times = [round(0.7 * index, 6) for index in range(32)]
    payload = {
        "schema": "damped-trace-v1",
        "samples": [
            {
                "t": time,
                "x": round(0.2 + 1.8 * math.exp(-time) * math.cos(time + 0.3), 12),
            }
            for time in times
        ],
        "queries": [0.5, 3.5, 8.5, 15.0],
        "noise_floor": 0.000000001,
    }
    source = tmp_path / "equal-damping.json"
    output = tmp_path / "equal-damping.out.json"
    _write(source, payload)
    completed = _run(source, output)
    assert completed.returncode == 2
    assert completed.stderr.startswith("REFUSED: ")
    assert not output.exists()


def test_success_output_is_canonical_and_silent(tmp_path: Path) -> None:
    # case_id: OS-SER-01 OS-SER-02
    """题面：
    「无额外空格的 JSON，末字符为换行。」
    """

    source = tmp_path / "trace.json"
    output = tmp_path / "canonical.json"
    _write(source, _trace_payload())
    completed = _run(source, output)
    raw = output.read_bytes()
    parsed = json.loads(raw)
    canonical = (
        json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert raw == canonical
