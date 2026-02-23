from sqlalchemy.orm import Session

from apps.common.schemas import MovieRecommendation, RecommendationMode, RecommendationRequest
from apps.orchestrator.recommender import build_recommendations


class RecommendationWorker:
    """Worker abstraction for recommendation job execution."""

    def run(self, db: Session, mode: RecommendationMode, payload: RecommendationRequest) -> list[MovieRecommendation]:
        return build_recommendations(db=db, mode=mode, payload=payload)

