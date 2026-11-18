#!/usr/bin/env python3
"""Wait for small-satellite processes without clearing intentional business faults."""

from __future__ import annotations

import argparse
import json
import subprocess
import time


def running_pod_names(document: dict) -> list[str]:
    names = []
    for item in document.get("items", []):
        status = item.get("status", {})
        containers = status.get("containerStatuses", [])
        if status.get("phase") == "Running" and any(item.get("containerID") for item in containers):
            names.append(item["metadata"]["name"])
    return sorted(names)


def process_alive(namespace: str, pod: str) -> bool:
    code = (
        'import urllib.request; '
        'assert urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=2).status == 200'
    )
    result = subprocess.run(
        ["kubectl", "exec", "-n", namespace, pod, "--", "python", "-c", code],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="multi-star")
    parser.add_argument("--count", type=int, default=9)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    last_summary = None
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", args.namespace, "-l", "app=small-sat", "-o", "json"],
            check=True, capture_output=True, text=True,
        )
        names = running_pod_names(json.loads(result.stdout))
        if len(names) == args.count:
            alive = [name for name in names if process_alive(args.namespace, name)]
            if len(alive) == args.count:
                print(json.dumps({"small_satellite_processes_alive": len(alive), "business_faults_preserved": True}))
                return
            summary = f"running={len(names)}, process_alive={len(alive)}"
        else:
            summary = f"running={len(names)}, required={args.count}"
        if summary != last_summary:
            print(summary, flush=True)
            last_summary = summary
        time.sleep(2)
    raise TimeoutError("not all small-satellite processes became available")


if __name__ == "__main__":
    main()
