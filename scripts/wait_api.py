#!/usr/bin/env python3
"""Wait for the local K3s HTTPS endpoint to return any HTTP response."""

from __future__ import annotations

import argparse
import http.client
import ssl
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6443)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()
    context = ssl._create_unverified_context()
    deadline = time.monotonic() + args.timeout
    last_error = None
    while time.monotonic() < deadline:
        connection = http.client.HTTPSConnection(args.host, args.port, timeout=5, context=context)
        try:
            connection.request("GET", "/readyz")
            response = connection.getresponse()
            response.read()
            if response.status in (200, 401, 403):
                print(f"API HTTP endpoint responded with status {response.status}")
                return
            message = f"HTTP {response.status}"
            if message != last_error:
                print(f"API not ready: {message}", flush=True)
                last_error = message
            time.sleep(2)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if message != last_error:
                print(f"API not ready: {message}", flush=True)
                last_error = message
            time.sleep(2)
        finally:
            connection.close()
    raise TimeoutError(f"API did not respond within {args.timeout}s; last_error={last_error}")


if __name__ == "__main__":
    main()
