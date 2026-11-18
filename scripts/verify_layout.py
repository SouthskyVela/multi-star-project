#!/usr/bin/env python3
"""Fail when runtime storage escapes the project directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def contained(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve(value: str, root: Path) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "config" / "runtime.json").read_text(encoding="utf-8"))
    errors: list[str] = []

    project_root = resolve(config["project"].get("root", "."), root)
    if project_root.resolve() != root:
        errors.append(f"项目根目录不符：{root} != {project_root}")

    runtime = resolve(config["runtime"]["root"], root)
    if not contained(runtime, root):
        errors.append(f"runtime 越出项目目录：{runtime}")

    wsl_root = resolve(config["runtime"].get("wsl_root", "runtime/wsl"), root)
    if not contained(wsl_root, root):
        errors.append(f"WSL 磁盘目录越出项目目录：{wsl_root}")

    required = ["wsl", "downloads", "tmp", "cache", "results", "shared"]
    for name in required:
        path = runtime / name
        if not path.is_dir():
            errors.append(f"缺少运行目录：{path}")
        elif path.is_symlink() and not contained(path, root):
            errors.append(f"运行目录通过符号链接越出项目：{path}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"OK: 项目根目录 {root}")
    print(f"OK: 运行数据根目录 {runtime}")
    print("OK: wsl/downloads/tmp/cache/results/shared 均位于项目内")
    print("INFO: Docker 镜像与容器写层须位于专用 WSL 虚拟磁盘内，创建集群前另行核验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
