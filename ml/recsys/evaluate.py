"""Full-catalog evaluation on all 10K movies.

Computes HR@K, NDCG@K, MRR against the entire movie catalog (not 20 random negs).
This gives the real production-quality metric.

Usage:
    POSTGRES_URL=postgresql://... uv run python evaluate.py
    POSTGRES_URL=postgresql://... uv run python evaluate.py --checkpoint path/to/best.ckpt
"""

import argparse
import asyncio
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np
import torch
from dotenv import load_dotenv

from model import TwoTowerModel
from train import (
    ITEM_FEATURE_DIM, NLP_DIM, USER_FEATURE_DIM,
    build_user_features, load_training_data,
)

load_dotenv()


def find_best_checkpoint() -> str | None:
    logs_dir = Path("lightning_logs")
    if not logs_dir.exists():
        return None
    best_path = None
    best_score = -1.0
    for version_dir in logs_dir.glob("version_*/checkpoints"):
        for ckpt in version_dir.glob("best-*.ckpt"):
            try:
                score = float(ckpt.stem.split("val_hr_at_10=")[1])
                if score > best_score:
                    best_score = score
                    best_path = str(ckpt)
            except (ValueError, IndexError):
                continue
    return best_path


async def _load_data(url: str) -> dict[str, Any]:
    pool = await asyncpg.create_pool(url, min_size=2, max_size=5)
    try:
        return await load_training_data(pool)
    finally:
        await pool.close()


def evaluate(checkpoint_path: str) -> dict[str, float]:
    url = os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://")
    data = asyncio.run(_load_data(url))

    ratings = data["ratings"]
    item_features = data["item_features"]
    nlp_embeddings = data["nlp_embeddings"]
    movie_genres = data["movie_genres"]
    user_map = data["user_map"]
    movie_map = data["movie_map"]
    genre_to_idx = data["genre_to_idx"]
    genomes = data["genomes"]

    print(f"Loaded {len(ratings)} ratings, {len(movie_map)} movies, {len(user_map)} users")

    split_idx = int(len(ratings) * 0.9)
    train_ratings = ratings[:split_idx]
    val_ratings = ratings[split_idx:]
    print(f"Split: {len(train_ratings)} train, {len(val_ratings)} val")

    all_user_features = build_user_features(ratings, movie_genres, genre_to_idx)

    user_train_history: dict[str, set[int]] = defaultdict(set)
    for r in train_ratings:
        user_train_history[str(r["user_id"])].add(r["movie_id"])

    print(f"\nLoading checkpoint: {checkpoint_path}")
    model = TwoTowerModel.load_from_checkpoint(checkpoint_path, map_location="cpu")
    model.eval()
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = model.to(device)
    print(f"Model on device: {device}")

    all_mids = sorted(movie_map.keys())
    mid_to_idx = {m: i for i, m in enumerate(all_mids)}

    print(f"\nComputing embeddings for all {len(all_mids)} movies...")
    with torch.no_grad():
        item_ids_t = torch.tensor([movie_map[m] for m in all_mids], device=device)
        item_feats_t = torch.tensor(
            np.array([item_features.get(m, np.zeros(ITEM_FEATURE_DIM)) for m in all_mids]),
            dtype=torch.float32, device=device,
        )
        item_nlp_t = torch.tensor(
            np.array([nlp_embeddings.get(m, np.zeros(NLP_DIM)) for m in all_mids]),
            dtype=torch.float32, device=device,
        )
        genome_t = torch.tensor(
            np.array([genomes.get(m, np.zeros(1128)) for m in all_mids]),
            dtype=torch.float32, device=device,
        )
        all_item_emb = model.encode_item(item_ids_t, item_feats_t, item_nlp_t, genome_t)
    print(f"Item catalog shape: {all_item_emb.shape}")

    val_by_user: dict[str, list[int]] = defaultdict(list)
    for r in val_ratings:
        uid_str = str(r["user_id"])
        val_by_user[uid_str].append(r["movie_id"])

    val_users = [u for u in val_by_user.keys() if u in all_user_features]
    print(f"\nEvaluating on {len(val_users)} val users ({len(val_ratings)} positives)...")

    ks = [1, 5, 10, 20, 50, 100]
    hit_counts = {k: 0 for k in ks}
    ndcg_sums = {k: 0.0 for k in ks}
    mrr_sum = 0.0
    total_positives = 0

    uid_str_to_idx = {str(k): v for k, v in user_map.items()}
    batch_size = 128

    for bstart in range(0, len(val_users), batch_size):
        batch_users = val_users[bstart : bstart + batch_size]
        uid_indices = [uid_str_to_idx[u] for u in batch_users]
        uf_list = [all_user_features[u] for u in batch_users]

        with torch.no_grad():
            u_ids = torch.tensor(uid_indices, device=device)
            u_feats = torch.tensor(np.array(uf_list), dtype=torch.float32, device=device)
            u_emb = model.encode_user(u_ids, u_feats)
            scores = u_emb @ all_item_emb.T

        for bi, uid_str in enumerate(batch_users):
            user_scores = scores[bi].clone()
            for seen_mid in user_train_history.get(uid_str, set()):
                if seen_mid in mid_to_idx:
                    user_scores[mid_to_idx[seen_mid]] = float("-inf")

            sorted_indices = torch.argsort(user_scores, descending=True).cpu().numpy()
            rank_of_item = np.empty(len(sorted_indices), dtype=np.int64)
            rank_of_item[sorted_indices] = np.arange(len(sorted_indices))

            for pos_mid in val_by_user[uid_str]:
                if pos_mid not in mid_to_idx:
                    continue
                if pos_mid in user_train_history.get(uid_str, set()):
                    continue

                total_positives += 1
                rank = int(rank_of_item[mid_to_idx[pos_mid]]) + 1

                for k in ks:
                    if rank <= k:
                        hit_counts[k] += 1
                        ndcg_sums[k] += 1.0 / np.log2(rank + 1)
                mrr_sum += 1.0 / rank

        if (bstart // batch_size) % 5 == 0:
            done = bstart + len(batch_users)
            print(f"  {done}/{len(val_users)} users, {total_positives} positives scored")

    metrics: dict[str, float] = {}
    for k in ks:
        metrics[f"HR@{k}"] = hit_counts[k] / total_positives
        metrics[f"NDCG@{k}"] = ndcg_sums[k] / total_positives
    metrics["MRR"] = mrr_sum / total_positives
    metrics["total_positives"] = total_positives
    metrics["catalog_size"] = len(all_mids)

    return metrics


def print_metrics(metrics: dict[str, float]) -> None:
    print("\n" + "=" * 50)
    print(f"FULL-CATALOG EVALUATION (vs {int(metrics['catalog_size'])} movies)")
    print(f"Evaluated on {int(metrics['total_positives'])} val positives")
    print("=" * 50)
    print(f"\n{'Metric':<12} {'Score':>8}")
    print("-" * 22)
    for k in [1, 5, 10, 20, 50, 100]:
        print(f"HR@{k:<9} {metrics[f'HR@{k}']:>8.4f}")
    print("-" * 22)
    for k in [10, 20, 50, 100]:
        print(f"NDCG@{k:<7} {metrics[f'NDCG@{k}']:>8.4f}")
    print("-" * 22)
    print(f"{'MRR':<12} {metrics['MRR']:>8.4f}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, default=None)
    args = parser.parse_args()

    ckpt = args.checkpoint or find_best_checkpoint()
    if ckpt is None:
        print("No checkpoint found. Train first.")
        raise SystemExit(1)

    metrics = evaluate(ckpt)
    print_metrics(metrics)
