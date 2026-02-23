import httpx
from urllib.parse import urlparse


def test_gateway_to_orchestrator_e2e(gateway_client, orchestrator_client, monkeypatch):
    async def fake_post(self, url, json=None, headers=None, **kwargs):
        endpoint = urlparse(url).path
        upstream = orchestrator_client.post(endpoint, json=json, headers=headers or {})
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=upstream.status_code,
            content=upstream.content,
            headers=dict(upstream.headers),
            request=request,
        )

    async def fake_get(self, url, headers=None, **kwargs):
        endpoint = urlparse(url).path
        upstream = orchestrator_client.get(endpoint, headers=headers or {})
        request = httpx.Request("GET", url)
        return httpx.Response(
            status_code=upstream.status_code,
            content=upstream.content,
            headers=dict(upstream.headers),
            request=request,
        )

    monkeypatch.setattr("apps.gateway.main.httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("apps.gateway.main.httpx.AsyncClient.get", fake_get)

    login_resp = gateway_client.post(
        "/auth/login",
        json={"email": "ml_user_1@moviematch.local", "password": "moviematch"},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}

    for mode, payload in [
        ("collaborative", {"top_k": 3}),
        ("nlp", {"query": "space", "top_k": 3}),
        ("mood", {"query": "happy", "top_k": 3}),
    ]:
        resp = gateway_client.post(f"/recommendations/{mode}", json=payload, headers=headers)
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_id"]
        job = gateway_client.get(f"/recommendations/jobs/{data['job_id']}", headers=headers)
        assert job.status_code == 200
        assert job.json()["status"] == "completed"
        assert job.json()["result"]["recommendations"]
