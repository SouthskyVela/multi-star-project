#!/usr/bin/env python3
"""In-cluster end-to-end acceptance driver using only the standard library."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable

MAIN = "http://dashboard.multi-star.svc.cluster.local:8082"
SMALL_8 = "http://small-sat-8.small-sat.multi-star.svc.cluster.local:8080"
SMALL_7 = "http://small-sat-7.small-sat.multi-star.svc.cluster.local:8080"


def request(base: str, path: str, body: dict[str, Any] | None = None, timeout: float = 5.0) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            payload = json.load(exc)
        except Exception:
            payload = {"error": str(exc)}
        return exc.code, payload


def wait_for(predicate: Callable[[], Any], timeout_s: float = 90.0, interval_s: float = 1.0) -> Any:
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:
            last_error = exc
        time.sleep(interval_s)
    raise TimeoutError(f"condition not met within {timeout_s}s; last_error={last_error}")


def snapshot() -> dict[str, Any]:
    status, payload = request(MAIN, "/api/snapshot")
    if status != 200:
        raise RuntimeError(f"snapshot HTTP {status}: {payload}")
    return payload


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_acceptance() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    started = time.time()

    def record(name: str, detail: Any) -> None:
        checks.append({"name": name, "passed": True, "detail": detail})
        print(json.dumps({"check": name, "detail": detail}), file=sys.stderr, flush=True)

    initial = wait_for(lambda: snapshot() if snapshot().get("leader", {}).get("id") else None)
    check(len(initial["small_satellites"]) == 9, "expected nine small satellites")
    status, _ = request(MAIN, "/mode", {"mode": "SURVEY"})
    check(status == 200, "failed to enter SURVEY baseline")
    baseline = wait_for(lambda: snapshot() if snapshot()["mode"] == "SURVEY" else None)
    record("baseline_survey", {"plan_version": baseline["plan_version"], "baselines": baseline["metrics"].get("baseline_count")})

    old = snapshot()
    old_id = old["leader"]["id"]
    old_epoch = int(old["leader"]["epoch"])
    suspend_started = time.monotonic()
    status, payload = request(MAIN, "/test/suspend", {"seconds": 22})
    check(status == 200, f"suspend old leader failed: {payload}")
    switched = wait_for(lambda: snapshot() if snapshot().get("leader", {}).get("id") not in ("", old_id) else None, 120)
    switch_seconds = time.monotonic() - suspend_started
    new_id = switched["leader"]["id"]
    new_epoch = int(switched["leader"]["epoch"])
    check(new_id != old_id, "leader identity did not change")
    check(new_epoch > old_epoch, "epoch did not increase")
    check(int(switched["plan_version"]) >= int(old["plan_version"]), "plan version regressed")
    time.sleep(max(0.0, 23.0 - (time.monotonic() - suspend_started)))
    stable = snapshot()
    check(stable["leader"]["id"] == new_id, "old leader reclaimed control after resuming")
    record("main_failover", {"old": old_id, "new": new_id, "epoch_before": old_epoch, "epoch_after": new_epoch, "switch_seconds": switch_seconds})

    def new_epoch_reached_executor() -> bool:
        status, payload = request(SMALL_7, "/status")
        return status == 200 and int(payload.get("highest_epoch", -1)) >= new_epoch

    wait_for(new_epoch_reached_executor)
    stale_command = {
        "command_id": f"stale-{old_epoch}-{int(time.time())}",
        "satellite_id": "small-sat-7",
        "epoch": old_epoch,
        "plan_version": 0,
        "kind": "observation",
        "not_before": 0,
        "expires_at": 1_000_000_000,
        "duration_s": 0,
        "data_bytes": 1,
    }
    _, stale_response = request(SMALL_7, "/commands", stale_command)
    receipt = stale_response.get("receipt", {})
    check(receipt.get("accepted") is False and "stale" in receipt.get("reason", ""), f"stale command was not fenced: {receipt}")
    record("stale_epoch_fencing", receipt)

    before_fault = snapshot()
    status, _ = request(SMALL_8, "/fault", {})
    check(status == 200, "failed to inject small-sat-8 fault")
    degraded = wait_for(lambda: snapshot() if snapshot()["metrics"].get("healthy_small_satellites") == 8 else None)
    failed_view = next(item for item in degraded["small_satellites"] if item["id"] == "small-sat-8")
    check(failed_view["health"] == "failed", "failed satellite is not marked failed")
    check(degraded["metrics"].get("baseline_count") == 28, f"expected 28 baselines after one loss: {degraded['metrics']}")
    check(int(degraded["plan_version"]) > int(before_fault["plan_version"]), "fault did not trigger a new plan")
    record("small_satellite_fault_replan", {"healthy": 8, "baselines": 28, "plan_before": before_fault["plan_version"], "plan_after": degraded["plan_version"]})

    status, response = request(SMALL_8, "/recover", {})
    check(status == 200, f"explicit recovery failed: {response}")
    recovered = wait_for(lambda: snapshot() if snapshot()["metrics"].get("healthy_small_satellites") == 9 else None)
    check(recovered["metrics"].get("baseline_count") == 36, "recovered array does not have 36 baselines")
    record("small_satellite_recovery", {"healthy": 9, "baselines": 36})

    event_id = f"synthetic-event-{int(time.time())}"
    before_event = snapshot()
    event = {
        "event_id": event_id,
        "target_id": "synthetic-deep-space-target",
        "frequency_hz": 140_000_000,
        "flux_jy": 25.0,
        "confidence": 0.97,
        "spectral_index": -0.7,
        "expiry_s": 600,
    }
    status, response = request(MAIN, "/events", event)
    check(status == 202 and response.get("accepted") is True, f"event rejected: {response}")
    event_state = wait_for(lambda: snapshot() if snapshot()["mode"] == "FIXED_SOURCE" else None)
    check(int(event_state["plan_version"]) > int(before_event["plan_version"]), "event did not create a plan")
    check(event_state["metrics"].get("frequency_hz") == 140_000_000.0, "event frequency not propagated")
    check(any(event_id in item.get("message", "") for item in event_state["events"]), "event missing from audit log")
    duplicate_status, duplicate = request(MAIN, "/events", event)
    check(duplicate_status == 202 and duplicate.get("duplicate") is True, f"duplicate event not deduplicated: {duplicate}")
    check(int(duplicate["plan_version"]) == int(event_state["plan_version"]), "duplicate event incremented plan")
    record("event_trigger_and_dedup", {"event_id": event_id, "mode": "FIXED_SOURCE", "plan_version": event_state["plan_version"], "frequency_hz": 140_000_000})

    for mode in ("CALIBRATION", "SURVEY"):
        before = snapshot()
        status, response = request(MAIN, "/mode", {"mode": mode})
        check(status == 200, f"mode {mode} rejected: {response}")
        after = wait_for(lambda: snapshot() if snapshot()["mode"] == mode else None)
        check(int(after["plan_version"]) > int(before["plan_version"]), f"mode {mode} did not increment plan")
        record(f"mode_{mode.lower()}", {"plan_version": after["plan_version"]})

    final = snapshot()
    return {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "elapsed_seconds": time.time() - started,
        "final": {
            "leader": final["leader"],
            "mode": final["mode"],
            "plan_version": final["plan_version"],
            "healthy_small_satellites": final["metrics"].get("healthy_small_satellites"),
            "baseline_count": final["metrics"].get("baseline_count"),
        },
    }


def main() -> None:
    try:
        report = run_acceptance()
        code = 0 if report["passed"] else 1
    except Exception as exc:
        report = {"passed": False, "fatal_error": f"{type(exc).__name__}: {exc}"}
        code = 1
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
