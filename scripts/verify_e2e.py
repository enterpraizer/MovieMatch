from __future__ import annotations

import argparse
import time

import requests


def fail(msg: str) -> None:
    raise SystemExit(f"E2E failed: {msg}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end recommendation check via gateway API")
    parser.add_argument("--gateway-url", default="http://localhost:8000")
    parser.add_argument("--email", default="ml_user_1@moviematch.local")
    parser.add_argument("--password", default="moviematch")
    args = parser.parse_args()

    base = args.gateway_url.rstrip("/")

    login_resp = requests.post(
        f"{base}/auth/login",
        json={"email": args.email, "password": args.password},
        timeout=10,
    )
    if login_resp.status_code != 200:
        fail(f"login status {login_resp.status_code}: {login_resp.text}")

    payload = login_resp.json()
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not access_token or not refresh_token:
        fail("missing access_token or refresh_token in login response")

    refresh_resp = requests.post(
        f"{base}/auth/refresh",
        json={"refresh_token": refresh_token},
        timeout=10,
    )
    if refresh_resp.status_code != 200:
        fail(f"refresh status {refresh_resp.status_code}: {refresh_resp.text}")

    headers = {"Authorization": f"Bearer {access_token}"}
    modes = [
        ("collaborative", {"top_k": 5}),
        ("nlp", {"query": "space", "top_k": 5}),
        ("mood", {"query": "happy", "top_k": 5}),
    ]

    for mode, body in modes:
        resp = requests.post(f"{base}/recommendations/{mode}", json=body, headers=headers, timeout=15)
        if resp.status_code not in (200, 202):
            fail(f"{mode} status {resp.status_code}: {resp.text}")
        submit = resp.json()
        job_id = submit.get("job_id")
        if not job_id:
            fail(f"{mode} missing job_id in response")

        deadline = time.time() + 60
        while time.time() < deadline:
            job_resp = requests.get(f"{base}/recommendations/jobs/{job_id}", headers=headers, timeout=15)
            if job_resp.status_code != 200:
                fail(f"{mode} status poll {job_resp.status_code}: {job_resp.text}")
            job = job_resp.json()
            if job.get("status") == "completed":
                recommendations = (job.get("result") or {}).get("recommendations", [])
                if not recommendations:
                    fail(f"{mode} completed without recommendations")
                print(f"{mode}: ok ({len(recommendations)} recommendations)")
                break
            if job.get("status") == "failed":
                fail(f"{mode} failed: {job.get('error')}")
            time.sleep(1)
        else:
            fail(f"{mode} timed out")

    print("E2E passed")


if __name__ == "__main__":
    main()
