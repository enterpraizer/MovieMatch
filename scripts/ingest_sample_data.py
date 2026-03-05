from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.common.auth import hash_password
from apps.common.db.models import Movie, User, UserRating
from apps.common.db.session import SessionLocal


def _parse_title_and_year(raw_title: str) -> tuple[str, int | None]:
    if not isinstance(raw_title, str):
        return "Unknown", None
    match = re.match(r"^(.*)\s\((\d{4})\)$", raw_title.strip())
    if not match:
        return raw_title.strip(), None
    return match.group(1).strip(), int(match.group(2))


def _load_movielens_sample(raw_dir: Path, ratings_limit: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    ml_dir = raw_dir / "ml-25m"
    movies_path = ml_dir / "movies.csv"
    ratings_path = ml_dir / "ratings.csv"

    if not movies_path.exists() or not ratings_path.exists():
        raise FileNotFoundError("MovieLens files not found in data/raw/ml-25m")

    ratings_df = pd.read_csv(ratings_path, nrows=ratings_limit)
    movies_df = pd.read_csv(movies_path)

    movie_ids = set(ratings_df["movieId"].astype(int).tolist())
    movies_df = movies_df[movies_df["movieId"].astype(int).isin(movie_ids)].copy()
    return movies_df, ratings_df


def _prepare_ml_movies(movies_df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, row in movies_df.iterrows():
        movie_id = int(row["movieId"])
        title, year = _parse_title_and_year(str(row["title"]))
        genres = str(row.get("genres", "")).replace("|", ", ")
        rows.append(
            {
                "id": movie_id,
                "title": title,
                "year": year,
                "genres": genres if genres != "(no genres listed)" else None,
                "overview": None,
            }
        )
    return rows


def _prepare_imdb_movies(raw_dir: Path, imdb_limit: int, existing_keys: set[tuple[str, int | None]], start_id: int) -> list[dict]:
    imdb_dir = raw_dir / "IMDb"
    basics_path = imdb_dir / "title.basics.tsv"
    ratings_path = imdb_dir / "title.ratings.tsv"

    if not basics_path.exists() or not ratings_path.exists() or imdb_limit <= 0:
        return []

    ratings_df = pd.read_csv(ratings_path, sep="\t", usecols=["tconst", "numVotes"])
    ratings_df["numVotes"] = pd.to_numeric(ratings_df["numVotes"], errors="coerce").fillna(0).astype(int)
    top_ids = set(ratings_df.sort_values("numVotes", ascending=False).head(imdb_limit * 8)["tconst"].tolist())

    results: list[dict] = []
    next_id = start_id
    needed = imdb_limit

    for chunk in pd.read_csv(
        basics_path,
        sep="\t",
        usecols=["tconst", "titleType", "primaryTitle", "startYear", "genres"],
        chunksize=100_000,
        low_memory=False,
    ):
        filtered = chunk[(chunk["titleType"] == "movie") & (chunk["tconst"].isin(top_ids))].copy()
        if filtered.empty:
            continue

        for _, row in filtered.iterrows():
            title = str(row["primaryTitle"]).strip()
            year_raw = str(row.get("startYear", ""))
            year = int(year_raw) if year_raw.isdigit() else None
            key = (title.lower(), year)
            if key in existing_keys:
                continue

            genres = str(row.get("genres", "")).replace(",", ", ")
            if genres == "\\N":
                genres = None

            results.append(
                {
                    "id": next_id,
                    "title": title,
                    "year": year,
                    "genres": genres,
                    "overview": None,
                }
            )
            existing_keys.add(key)
            next_id += 1
            needed -= 1
            if needed <= 0:
                return results

    return results


def ingest(raw_dir: Path, ratings_limit: int, imdb_limit: int) -> None:
    movies_df, ratings_df = _load_movielens_sample(raw_dir=raw_dir, ratings_limit=ratings_limit)
    ml_movies = _prepare_ml_movies(movies_df)

    with SessionLocal() as db:
        # Upsert MovieLens movies by primary key movieId.
        if ml_movies:
            stmt = insert(Movie).values(ml_movies)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Movie.id],
                set_={
                    "title": stmt.excluded.title,
                    "year": stmt.excluded.year,
                    "genres": stmt.excluded.genres,
                    "overview": stmt.excluded.overview,
                },
            )
            db.execute(stmt)

        max_movie_id = db.scalar(select(func.max(Movie.id))) or 0
        existing_keys = {
            (title.lower(), year)
            for title, year in db.execute(select(Movie.title, Movie.year)).all()
            if isinstance(title, str)
        }
        imdb_movies = _prepare_imdb_movies(
            raw_dir=raw_dir,
            imdb_limit=imdb_limit,
            existing_keys=existing_keys,
            start_id=max_movie_id + 1,
        )

        if imdb_movies:
            stmt = insert(Movie).values(imdb_movies)
            stmt = stmt.on_conflict_do_nothing(index_elements=[Movie.id])
            db.execute(stmt)

        # Create users for sampled MovieLens userIds.
        user_ids = sorted(set(ratings_df["userId"].astype(int).tolist()))
        user_emails = [f"ml_user_{uid}@moviematch.local" for uid in user_ids]
        existing_users = {
            email: user_id
            for user_id, email in db.execute(select(User.id, User.email).where(User.email.in_(user_emails))).all()
        }

        new_users = []
        for uid in user_ids:
            email = f"ml_user_{uid}@moviematch.local"
            if email in existing_users:
                continue
            new_users.append({"email": email, "password_hash": hash_password("moviematch")})

        if new_users:
            user_stmt = insert(User).values(new_users)
            user_stmt = user_stmt.on_conflict_do_nothing(index_elements=[User.email])
            db.execute(user_stmt)

        # Refresh map email -> id after inserts.
        user_map = {
            email: user_id
            for user_id, email in db.execute(select(User.id, User.email).where(User.email.in_(user_emails))).all()
        }

        rating_rows = []
        for _, row in ratings_df.iterrows():
            email = f"ml_user_{int(row['userId'])}@moviematch.local"
            user_id = user_map.get(email)
            if user_id is None:
                continue
            rating_rows.append(
                {
                    "user_id": user_id,
                    "movie_id": int(row["movieId"]),
                    "rating": float(row["rating"]),
                }
            )

        if rating_rows:
            rating_stmt = insert(UserRating).values(rating_rows)
            rating_stmt = rating_stmt.on_conflict_do_update(
                index_elements=[UserRating.user_id, UserRating.movie_id],
                set_={"rating": rating_stmt.excluded.rating},
            )
            db.execute(rating_stmt)

        db.commit()

        total_movies = db.scalar(select(func.count(Movie.id))) or 0
        total_users = db.scalar(select(func.count(User.id))) or 0
        total_ratings = db.scalar(select(func.count(UserRating.id))) or 0

    print("Ingestion complete")
    print(f"- MovieLens ratings imported: {len(ratings_df)}")
    print(f"- MovieLens movies imported: {len(ml_movies)}")
    print(f"- IMDb movies imported: {len(imdb_movies)}")
    print(f"- DB totals -> movies: {total_movies}, users: {total_users}, ratings: {total_ratings}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import sample MovieLens + IMDb data into PostgreSQL.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--ratings-limit", type=int, default=50_000)
    parser.add_argument("--imdb-limit", type=int, default=20_000)
    args = parser.parse_args()

    ingest(raw_dir=args.raw_dir, ratings_limit=args.ratings_limit, imdb_limit=args.imdb_limit)


if __name__ == "__main__":
    main()
