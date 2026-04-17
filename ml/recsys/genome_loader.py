"""Import genome-scores.csv into movies.genome_scores column.

Usage:
    POSTGRES_URL=postgresql://... uv run python genome_loader.py
"""
import asyncio
import csv
import os
from collections import defaultdict
from pathlib import Path

import asyncpg

GENOME_SIZE = 1128
DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "raw" / "ml-25m" / "genome-scores.csv"


async def main() -> None:
    assert DATA_FILE.exists(), f"Missing {DATA_FILE}"

    print(f"Reading {DATA_FILE}...")
    scores: dict[int, list[float]] = defaultdict(lambda: [0.0] * GENOME_SIZE)
    row_count = 0
    with open(DATA_FILE) as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = int(row["movieId"])
            tid = int(row["tagId"]) - 1  # tagId is 1-indexed
            if 0 <= tid < GENOME_SIZE:
                scores[mid][tid] = float(row["relevance"])
            row_count += 1
            if row_count % 1_000_000 == 0:
                print(f"  {row_count:,} rows, {len(scores):,} movies")
    print(f"Done reading. {row_count:,} rows total, {len(scores):,} movies with genome.")

    dsn = os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=4)
    try:
        async with pool.acquire() as conn:
            movie_rows = await conn.fetch(
                "SELECT id, title, year FROM movies WHERE genome_scores IS NULL"
            )

        print(f"Looking up MovieLens IDs for {len(movie_rows)} movies...")
        movies_csv = DATA_FILE.parent / "movies.csv"
        ml_id_by_title: dict[tuple[str, int | None], int] = {}
        with open(movies_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw = row["title"].strip()
                year = None
                title = raw
                if raw.endswith(")") and "(" in raw:
                    try:
                        year = int(raw[raw.rfind("(") + 1 : -1])
                        title = raw[: raw.rfind("(")].strip()
                    except ValueError:
                        pass
                ml_id_by_title[(title, year)] = int(row["movieId"])

        updates: list[tuple[list[float], int]] = []
        missed = 0
        for r in movie_rows:
            ml_id = ml_id_by_title.get((r["title"], r["year"]))
            if ml_id is None or ml_id not in scores:
                missed += 1
                continue
            updates.append((scores[ml_id], r["id"]))

        print(f"Matched {len(updates)} movies; {missed} without genome data")

        batch = 500
        async with pool.acquire() as conn:
            for i in range(0, len(updates), batch):
                await conn.executemany(
                    "UPDATE movies SET genome_scores = $1 WHERE id = $2",
                    updates[i : i + batch],
                )
                print(f"  {min(i + batch, len(updates))}/{len(updates)}")
        print("Done.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
