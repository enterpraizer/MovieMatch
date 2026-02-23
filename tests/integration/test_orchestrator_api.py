from sqlalchemy import func, select

from apps.common.db.models import RecommendationRequest as RecommendationRequestModel
from apps.common.db.models import RecommendationResult


def test_orchestrator_auth_and_protected_recommendations(orchestrator_client, session_local):
    login_resp = orchestrator_client.post(
        "/auth/login",
        json={"email": "ml_user_1@moviematch.local", "password": "moviematch"},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    unauth_resp = orchestrator_client.post("/recommendations/collaborative", json={"top_k": 3})
    assert unauth_resp.status_code == 401

    auth_resp = orchestrator_client.post(
        "/recommendations/collaborative",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"top_k": 3},
    )
    assert auth_resp.status_code == 200
    body = auth_resp.json()
    assert body["mode"] == "collaborative"
    assert len(body["recommendations"]) > 0

    with session_local() as db:
        req_count = db.scalar(select(func.count(RecommendationRequestModel.id)))
        res_count = db.scalar(select(func.count(RecommendationResult.id)))

    assert req_count and req_count > 0
    assert res_count and res_count > 0
