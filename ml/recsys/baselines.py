"""Baseline models with full-catalog evaluation.

Usage:
    POSTGRES_URL=postgresql://... uv run python baselines.py popularity
    POSTGRES_URL=postgresql://... uv run python baselines.py als
"""
import argparse
import asyncio
import os
import sys
from collections import defaultdict
from typing import Any

import asyncpg
import numpy as np


POSITIVE_THRESHOLD = 4.0
MIN_USER_POSITIVES = 10
MAX_USER_POSITIVES = 500


async def load_split() -> tuple[
    list[tuple[str, int]], list[tuple[str, int]], dict[int, int]
]:
    """Same filter+split as evaluate.py: core-pruning + per-user leave-last-10%.

    Returns train/val as (user_id_str, movie_id) pairs of POSITIVES only
    (score ≥ 4.0). Users with <10 or >500 positives are dropped.
    """
    dsn = os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT user_id::text AS user_id, movie_id, score "
            "FROM ratings ORDER BY created_at"
        )
        movies = await conn.fetch("SELECT id FROM movies ORDER BY id")
    finally:
        await conn.close()

    mid_to_idx = {r["id"]: i for i, r in enumerate(movies)}

    pos_count: dict[str, int] = defaultdict(int)
    for r in rows:
        if float(r["score"]) >= POSITIVE_THRESHOLD:
            pos_count[r["user_id"]] += 1
    eligible = {
        u for u, c in pos_count.items()
        if MIN_USER_POSITIVES <= c <= MAX_USER_POSITIVES
    }
    print(f"Eligible users: {len(eligible)} / {len(pos_count)}")

    user_positives: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r["user_id"] not in eligible:
            continue
        if float(r["score"]) >= POSITIVE_THRESHOLD:
            user_positives[r["user_id"]].append(r["movie_id"])

    train: list[tuple[str, int]] = []
    val: list[tuple[str, int]] = []
    for uid, mids in user_positives.items():
        n_val = max(1, int(len(mids) * 0.1))
        for m in mids[:-n_val]:
            train.append((uid, m))
        for m in mids[-n_val:]:
            val.append((uid, m))
    return train, val, mid_to_idx


def eval_rankings(
    scores_per_user: dict[str, np.ndarray],
    val: list[tuple[str, int]],
    train_history: dict[str, set[int]],
    mid_to_idx: dict[int, int],
) -> dict[str, float]:
    ks = [10, 50, 100]
    hit = {k: 0 for k in ks}
    ndcg = {k: 0.0 for k in ks}
    mrr = 0.0
    total = 0

    val_by_user: dict[str, list[int]] = defaultdict(list)
    for u, m in val:
        val_by_user[u].append(m)

    for uid, positives in val_by_user.items():
        if uid not in scores_per_user:
            continue
        scores = scores_per_user[uid].copy()
        for seen in train_history.get(uid, set()):
            if seen in mid_to_idx:
                scores[mid_to_idx[seen]] = -np.inf

        rank_of = np.empty(len(scores), dtype=np.int64)
        rank_of[np.argsort(-scores)] = np.arange(len(scores))

        for pos_mid in positives:
            if pos_mid not in mid_to_idx or pos_mid in train_history.get(uid, set()):
                continue
            total += 1
            rank = int(rank_of[mid_to_idx[pos_mid]]) + 1
            for k in ks:
                if rank <= k:
                    hit[k] += 1
                    ndcg[k] += 1.0 / np.log2(rank + 1)
            mrr += 1.0 / rank

    out: dict[str, float] = {}
    for k in ks:
        out[f"HR@{k}"] = hit[k] / total if total else 0.0
        out[f"NDCG@{k}"] = ndcg[k] / total if total else 0.0
    out["MRR"] = mrr / total if total else 0.0
    out["total_positives"] = total
    return out


def print_metrics(name: str, m: dict[str, float]) -> None:
    print(f"\n=== {name} ===")
    print(f"Positives: {int(m['total_positives'])}")
    for k in [10, 50, 100]:
        print(f"  HR@{k:<3}    = {m[f'HR@{k}']:.4f}")
    for k in [10, 50, 100]:
        print(f"  NDCG@{k:<3}  = {m[f'NDCG@{k}']:.4f}")
    print(f"  MRR       = {m['MRR']:.4f}")


def run_popularity(
    train: list[tuple[str, int]],
    val: list[tuple[str, int]],
    mid_to_idx: dict[int, int],
) -> None:
    popularity = np.zeros(len(mid_to_idx), dtype=np.float32)
    for _, mid in train:
        if mid in mid_to_idx:
            popularity[mid_to_idx[mid]] += 1.0

    train_history: dict[str, set[int]] = defaultdict(set)
    for u, m in train:
        train_history[u].add(m)

    val_users = {u for u, _ in val}
    scores_per_user = {u: popularity for u in val_users}

    metrics = eval_rankings(scores_per_user, val, train_history, mid_to_idx)
    print_metrics("Popularity baseline", metrics)


def run_als(
    train: list[tuple[str, int]],
    val: list[tuple[str, int]],
    mid_to_idx: dict[int, int],
    factors: int = 128,
    iterations: int = 15,
) -> None:
    import implicit
    from scipy.sparse import csr_matrix

    uid_to_idx: dict[str, int] = {}
    rows, cols, data = [], [], []
    for u, m in train:
        if u not in uid_to_idx:
            uid_to_idx[u] = len(uid_to_idx)
        if m not in mid_to_idx:
            continue
        rows.append(uid_to_idx[u])
        cols.append(mid_to_idx[m])
        data.append(1.0)

    n_users = len(uid_to_idx)
    n_items = len(mid_to_idx)
    ui_matrix = csr_matrix((data, (rows, cols)), shape=(n_users, n_items))

    print(f"ALS training: {n_users} users, {n_items} items, {len(data)} interactions")
    model = implicit.als.AlternatingLeastSquares(
        factors=factors, iterations=iterations, regularization=0.01, use_gpu=False
    )
    model.fit(ui_matrix)

    train_history: dict[str, set[int]] = defaultdict(set)
    for u, m in train:
        train_history[u].add(m)

    val_users = {u for u, _ in val if u in uid_to_idx}
    scores_per_user: dict[str, np.ndarray] = {}
    user_factors = model.user_factors
    item_factors = model.item_factors
    for u in val_users:
        scores_per_user[u] = user_factors[uid_to_idx[u]] @ item_factors.T

    metrics = eval_rankings(scores_per_user, val, train_history, mid_to_idx)
    print_metrics("ALS baseline", metrics)


def main(which: str) -> None:
    print("Loading data...")
    train, val, mid_to_idx = asyncio.run(load_split())
    print(f"Train: {len(train)}  Val: {len(val)}  Items: {len(mid_to_idx)}")

    if which == "popularity":
        run_popularity(train, val, mid_to_idx)
    elif which == "als":
        run_als(train, val, mid_to_idx)
    else:
        print(f"Unknown baseline: {which}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("which", choices=["popularity", "als"])
    args = parser.parse_args()
    main(args.which)
