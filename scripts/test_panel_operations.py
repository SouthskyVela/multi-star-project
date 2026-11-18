#!/usr/bin/env python3
"""Exercise the actual dashboard proxy operations used by the panel."""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(base: str, path: str, body=None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def wait_snapshot(base: str, predicate, timeout: float = 90.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, value = request(base, "/api/snapshot")
        if status == 200 and predicate(value):
            return value
        time.sleep(1)
    raise TimeoutError("snapshot condition not met")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:18082")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = []

    with urllib.request.urlopen(args.base + "/sample-events.csv", timeout=10) as response:
        sample = response.read().decode("utf-8-sig")
    events = list(csv.DictReader(io.StringIO(sample)))
    assert len(events) == 3
    checks.append({"name": "sample_csv_download", "events": len(events)})

    before = wait_snapshot(args.base, lambda d: bool(d["leader"]["id"]))
    status, _ = request(args.base, "/small-sat/fault", {"satellite_id": "small-sat-8"})
    assert status == 200
    degraded = wait_snapshot(args.base, lambda d: d["metrics"].get("healthy_small_satellites") == 8)
    assert degraded["metrics"]["baseline_count"] == 28
    assert degraded["plan_version"] > before["plan_version"]
    checks.append({"name": "small_fault", "healthy": 8, "baselines": 28})

    status, _ = request(args.base, "/small-sat/recover", {"satellite_id": "small-sat-8"})
    assert status == 200
    recovered = wait_snapshot(args.base, lambda d: d["metrics"].get("healthy_small_satellites") == 9)
    assert recovered["metrics"]["baseline_count"] == 36
    checks.append({"name": "small_recover", "healthy": 9, "baselines": 36})

    event_results = []
    for event in events:
        for key in ("frequency_hz", "flux_jy", "confidence", "spectral_index", "expiry_s"):
            event[key] = float(event[key])
        status, response = request(args.base, "/events", event)
        assert status == 202, (status, response, event)
        event_results.append({"event_id": event["event_id"], "accepted": response.get("accepted"), "duplicate": response.get("duplicate")})
    checks.append({"name": "file_event_injection", "results": event_results})

    for mode in ("CALIBRATION", "SURVEY"):
        status, response = request(args.base, "/mode", {"mode": mode})
        assert status == 200
        state = wait_snapshot(args.base, lambda d: d["mode"] == mode)
        checks.append({"name": "mode_" + mode.lower(), "plan_version": state["plan_version"]})

    old = wait_snapshot(args.base, lambda d: bool(d["leader"]["id"]))["leader"]
    status, _ = request(args.base, "/test/suspend", {"seconds": 22})
    assert status == 200
    switched = wait_snapshot(args.base, lambda d: d["leader"]["id"] not in ("", old["id"]), 120)
    assert switched["leader"]["epoch"] > old["epoch"]
    time.sleep(8)
    stable = wait_snapshot(args.base, lambda d: d["leader"]["id"] == switched["leader"]["id"])
    checks.append({"name": "main_suspend", "old": old["id"], "new": stable["leader"]["id"], "epoch": stable["leader"]["epoch"]})

    result = {"passed": True, "checks": checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
