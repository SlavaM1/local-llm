#!/usr/bin/env python3
"""Small authenticated smoke test for the private HTTP service."""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


def request(opener, base_url, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        f"{base_url}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    started = time.perf_counter()
    try:
        with opener.open(req, timeout=660) as response:
            body = response.read().decode()
            return response.status, json.loads(body) if body else {}, time.perf_counter() - started
    except HTTPError as error:
        body = error.read().decode()
        return error.code, json.loads(body) if body else {}, time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:3000")
    parser.add_argument("--username", default=os.getenv("PRIVATE_SERVICE_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("PRIVATE_SERVICE_PASSWORD"))
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--prompt", default="Ответь одним коротким предложением: сервис доступен.")
    args = parser.parse_args()
    if not args.password:
        parser.error("set PRIVATE_SERVICE_PASSWORD or pass --password")

    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    status, _, _ = request(opener, args.url, "POST", "/api/auth/login", {
        "username": args.username, "password": args.password,
    })
    if status != 200:
        raise SystemExit(f"login failed: HTTP {status}")

    def generate(index):
        create_status, chat, _ = request(opener, args.url, "POST", "/api/chats", {})
        if create_status != 201:
            return create_status, 0.0
        response_status, _, elapsed = request(opener, args.url, "POST", f"/api/chats/{chat['id']}/messages", {
            "content": f"{args.prompt} #{index}", "profile": "optimized",
        })
        return response_status, elapsed

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        results = list(executor.map(generate, range(args.requests)))
    for index, (status, elapsed) in enumerate(results, 1):
        print(f"request {index}: HTTP {status}, {elapsed:.2f}s")
    logout_status, _, _ = request(opener, args.url, "POST", "/api/auth/logout", {})
    print(f"logout: HTTP {logout_status}")
    if logout_status != 204 or any(status < 200 or status >= 300 for status, _ in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
