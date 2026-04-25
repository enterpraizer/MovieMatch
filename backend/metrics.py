import contextlib
import time
from collections.abc import Iterator

from prometheus_client import Counter, Gauge, Histogram

recommendations_total = Counter(
    "moviematch_recommendations_total",
    "Total recommendations served",
    ["recommendation_type", "cached", "model_version"],
)

recommendation_latency = Histogram(
    "moviematch_recommendation_duration_seconds",
    "Recommendation request duration",
    ["recommendation_type"],
    buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.0, 5.0],
)

ml_service_up = Gauge(
    "moviematch_ml_service_available",
    "ML service availability (1=up 0=down)",
    ["service"],
)

auth_events = Counter(
    "moviematch_auth_events_total",
    "Authentication events",
    ["event"],
)


@contextlib.contextmanager
def recommendation_timer(rec_type: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        recommendation_latency.labels(recommendation_type=rec_type).observe(
            time.perf_counter() - start
        )
