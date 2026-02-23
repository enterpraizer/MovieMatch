from __future__ import annotations

from collections.abc import Generator
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

from apps.common.auth import hash_password
from apps.common.cache import _memory_cache
from apps.common.db.base import Base
from apps.common.db.models import Movie, User, UserRating
from apps.common.db.session import get_db
from apps.gateway.main import app as gateway_app
from apps.orchestrator.main import app as orchestrator_app


@pytest.fixture()
def session_local(tmp_path) -> sessionmaker:
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        _seed_data(db)

    yield SessionLocal

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def clear_memory_cache() -> Generator[None, None, None]:
    _memory_cache.clear()
    yield
    _memory_cache.clear()


@pytest.fixture()
def db_session(session_local: sessionmaker) -> Generator[Session, None, None]:
    db = session_local()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def orchestrator_client(session_local: sessionmaker) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    orchestrator_app.dependency_overrides[get_db] = override_get_db
    with TestClient(orchestrator_app) as client:
        yield client
    orchestrator_app.dependency_overrides.clear()


@pytest.fixture()
def gateway_client(session_local: sessionmaker) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    gateway_app.dependency_overrides[get_db] = override_get_db
    with TestClient(gateway_app) as client:
        yield client
    gateway_app.dependency_overrides.clear()


def _seed_data(db: Session) -> None:
    users = [
        User(id=1, email="ml_user_1@moviematch.local", password_hash=hash_password("moviematch")),
        User(id=2, email="ml_user_2@moviematch.local", password_hash=hash_password("moviematch")),
    ]
    db.add_all(users)

    movies = [
        Movie(id=1, title="The Matrix", year=1999, genres="Action, Sci-Fi", overview="A hacker discovers reality."),
        Movie(id=2, title="Titanic", year=1997, genres="Drama, Romance", overview="Epic romance and tragedy."),
        Movie(id=3, title="Space Odyssey", year=1968, genres="Sci-Fi, Adventure", overview="Journey through space."),
        Movie(id=4, title="Funny Journey", year=2010, genres="Comedy, Adventure", overview="Light comedy trip."),
    ]
    db.add_all(movies)

    ratings = [
        UserRating(user_id=1, movie_id=1, rating=5.0),
        UserRating(user_id=1, movie_id=2, rating=4.0),
        UserRating(user_id=2, movie_id=1, rating=4.0),
        UserRating(user_id=2, movie_id=3, rating=5.0),
        UserRating(user_id=2, movie_id=4, rating=3.5),
    ]
    db.add_all(ratings)

    db.commit()
