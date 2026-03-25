from apps.common.schemas import RecommendationMode
from apps.workers.service_base import create_worker_app

app = create_worker_app(service_name="mood-worker", fixed_mode=RecommendationMode.mood)
