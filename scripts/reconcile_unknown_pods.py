#!/usr/bin/env python3
"""Recreate only Unknown/NodeLost business pods after a WSL stop/start cycle."""

from __future__ import annotations

import argparse
import json
import subprocess


def unknown_pod_names(document: dict) -> list[str]:
    names = []
    for item in document.get("items", []):
        status = item.get("status", {})
        if status.get("phase") == "Unknown" or status.get("reason") == "NodeLost":
            names.append(item["metadata"]["name"])
    return sorted(names)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="multi-star")
    args = parser.parse_args()
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", args.namespace, "-o", "json"],
        check=True, capture_output=True, text=True,
    )
    names = unknown_pod_names(json.loads(result.stdout))
    for name in names:
        print(f"Recreating stale business pod: {name}")
        subprocess.run(
            ["kubectl", "delete", "pod", "-n", args.namespace, name, "--wait=false"],
            check=True,
        )
    print(f"Stale business pods requested for recreation: {len(names)}")


if __name__ == "__main__":
    main()
