#!/usr/bin/env python3
"""Bounded readiness wait for explicit CI/local service addresses; no port scanning."""

import argparse
import socket
import time


def wait(host, port, timeout):
    if not 1 <= port <= 65535 or not 1 <= timeout <= 300:
        raise ValueError("Invalid port or readiness timeout")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(
                (host, port), timeout=min(2, max(0.1, deadline - time.monotonic()))
            ):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError("Service did not open its configured port before the deadline")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    wait(args.host, args.port, args.timeout)
    print("Configured service port is accepting connections")
