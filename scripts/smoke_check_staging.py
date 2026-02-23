from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc


def get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke check for staging deployment")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", default="staging-smoke@moviematch.local")
    parser.add_argument("--password", default="moviematch")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    status, _ = get(f"{base_url}/health")
    if status != 200:
        raise RuntimeError("gateway health check failed")

    status, _ = get(f"{base_url}/metrics")
    if status != 200:
        raise RuntimeError("gateway metrics check failed")

    login_status, login_payload = post_json(
        f"{base_url}/auth/login",
        {"email": args.email, "password": args.password},
    )
    if login_status != 200:
        raise RuntimeError("login failed")

    token = login_payload.get("access_token")
    if not token:
        raise RuntimeError("access_token missing in login response")

    modes = [
        ("collaborative", {"top_k": 3}),
        ("nlp", {"query": "space", "top_k": 3}),
        ("mood", {"query": "happy", "top_k": 3}),
    ]
    headers = {"Authorization": f"Bearer {token}"}

    for mode, payload in modes:
        status_code, response_payload = post_json(
            f"{base_url}/recommendations/{mode}",
            payload,
            headers=headers,
        )
        if status_code != 200:
            raise RuntimeError(f"{mode} request failed")
        if "recommendations" not in response_payload:
            raise RuntimeError(f"{mode} response missing recommendations")

    print("Staging smoke check passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Smoke check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
