from apps.common.schemas import RecommendationMode, RecommendationRequest
from apps.orchestrator.recommender import build_recommendations


def test_collaborative_returns_ranked_movies_for_user(db_session):
    payload = RecommendationRequest(user_id=1, top_k=3)

    recommendations = build_recommendations(db=db_session, mode=RecommendationMode.collaborative, payload=payload)

    assert recommendations
    assert recommendations[0].movie_id == 3
    assert all(item.movie_id not in {1, 2} for item in recommendations)


def test_nlp_falls_back_to_collaborative_when_no_match(db_session):
    collab = build_recommendations(
        db=db_session,
        mode=RecommendationMode.collaborative,
        payload=RecommendationRequest(user_id=1, top_k=2),
    )
    nlp = build_recommendations(
        db=db_session,
        mode=RecommendationMode.nlp,
        payload=RecommendationRequest(user_id=1, query="zzzz-no-match", top_k=2),
    )

    assert nlp
    assert [m.movie_id for m in nlp] == [m.movie_id for m in collab]
