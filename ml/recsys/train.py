"""Two-Tower v3 training: genome features, in-batch + explicit negatives, τ=0.07."""
import argparse
import asyncio
import os
import random
from collections import defaultdict
from typing import Any

import asyncpg
import mlflow
import mlflow.pytorch
import numpy as np
import pytorch_lightning as pl
import torch
from dotenv import load_dotenv
from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint
from torch.utils.data import DataLoader, Dataset

from model import TwoTowerModel

load_dotenv()

N_GENRES = 19
ITEM_FEATURE_DIM = N_GENRES + 3
USER_FEATURE_DIM = N_GENRES + 3
NLP_DIM = 384
GENOME_DIM = 1128
NEG_SAMPLES = 20
HISTORY_TOP_N = 20  # how many recent rated movies to use in BoW user history

# Implicit-feedback treatment: treat ratings ≥ threshold as positives for training.
# Users outside [MIN..MAX] positives are dropped (core-pruning).
POSITIVE_THRESHOLD = 4.0
MIN_USER_POSITIVES = 10
MAX_USER_POSITIVES = 500


def parse_vector(raw: Any, dim: int) -> np.ndarray:
    if raw is None:
        return np.zeros(dim, dtype=np.float32)
    if isinstance(raw, str):
        raw = [float(x) for x in raw.strip("[]{}").split(",") if x.strip()]
    return np.asarray(raw, dtype=np.float32)


async def load_training_data(pool: asyncpg.Pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        ratings = [
            dict(r)
            for r in await conn.fetch(
                "SELECT user_id, movie_id, score FROM ratings ORDER BY created_at"
            )
        ]
        movies = [
            dict(r)
            for r in await conn.fetch(
                """
                SELECT m.id, m.year, m.avg_rating, m.popularity_score,
                       m.embedding, m.genome_scores,
                       ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.slug), NULL) AS genres
                FROM movies m
                LEFT JOIN movie_genres mg ON mg.movie_id = m.id
                LEFT JOIN genres g ON g.id = mg.genre_id
                GROUP BY m.id
                """
            )
        ]
        genre_list = [
            r["slug"]
            for r in await conn.fetch("SELECT slug FROM genres ORDER BY id")
        ]

    genre_to_idx = {g: i for i, g in enumerate(genre_list)}
    item_features: dict[int, np.ndarray] = {}
    nlp_embeddings: dict[int, np.ndarray] = {}
    genomes: dict[int, np.ndarray] = {}
    movie_genres: dict[int, list[str]] = {}

    for m in movies:
        feat = np.zeros(ITEM_FEATURE_DIM, dtype=np.float32)
        genres = []
        for g in m.get("genres") or []:
            if g in genre_to_idx and genre_to_idx[g] < N_GENRES:
                feat[genre_to_idx[g]] = 1.0
                genres.append(g)
        if m.get("year"):
            feat[N_GENRES] = (m["year"] - 1900) / 130.0
        if m.get("avg_rating"):
            feat[N_GENRES + 1] = float(m["avg_rating"]) / 5.0
        if m.get("popularity_score"):
            feat[N_GENRES + 2] = min(float(m["popularity_score"]) / 50.0, 1.0)
        item_features[m["id"]] = feat
        movie_genres[m["id"]] = genres
        nlp_embeddings[m["id"]] = parse_vector(m.get("embedding"), NLP_DIM)
        genomes[m["id"]] = parse_vector(m.get("genome_scores"), GENOME_DIM)

    all_users = sorted({r["user_id"] for r in ratings})
    all_movies = sorted(item_features.keys())
    user_map = {uid: i + 1 for i, uid in enumerate(all_users)}
    movie_map = {mid: i + 1 for i, mid in enumerate(all_movies)}

    return {
        "ratings": ratings,
        "item_features": item_features,
        "nlp_embeddings": nlp_embeddings,
        "genomes": genomes,
        "movie_genres": movie_genres,
        "user_map": user_map,
        "movie_map": movie_map,
        "genre_to_idx": genre_to_idx,
    }


def build_user_history_nlp(
    ratings: list[dict[str, Any]],
    nlp_embeddings: dict[int, np.ndarray],
    top_n: int = HISTORY_TOP_N,
) -> dict[str, np.ndarray]:
    """Build a weighted average NLP embedding from each user's rating history.

    Weighted by (score/5.0) to emphasize well-rated movies. Only takes the
    most recent top_n ratings per user (MovieLens data is already sorted by time).
    Returns: user_id_str → 384-dim vector, L2-normalized.
    """
    user_ratings: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for r in ratings:
        user_ratings[str(r["user_id"])].append((r["movie_id"], float(r["score"])))

    out: dict[str, np.ndarray] = {}
    for uid, urs in user_ratings.items():
        urs = urs[-top_n:]  # last N ratings
        vecs = []
        weights = []
        for mid, score in urs:
            nlp = nlp_embeddings.get(mid)
            if nlp is None or not nlp.any():
                continue
            vecs.append(nlp)
            weights.append(max(score / 5.0, 0.1))
        if not vecs:
            out[uid] = np.zeros(NLP_DIM, dtype=np.float32)
            continue
        arr = np.asarray(vecs, dtype=np.float32)
        w = np.asarray(weights, dtype=np.float32)
        w = w / w.sum()
        avg = (arr * w[:, None]).sum(axis=0)
        norm = np.linalg.norm(avg)
        if norm > 1e-8:
            avg = avg / norm
        out[uid] = avg.astype(np.float32)
    return out


def build_user_sequence_ids(
    ratings: list[dict[str, Any]],
    movie_map: dict[int, int],
    seq_len: int = HISTORY_TOP_N,
) -> dict[str, np.ndarray]:
    """For each user, return a fixed-length vector of their LAST `seq_len`
    internal movie indices (padded with 0)."""
    user_ratings: dict[str, list[int]] = defaultdict(list)
    for r in ratings:
        mid = r["movie_id"]
        idx = movie_map.get(mid)
        if idx is not None:
            user_ratings[str(r["user_id"])].append(idx)

    out: dict[str, np.ndarray] = {}
    for uid, ids in user_ratings.items():
        tail = ids[-seq_len:]
        buf = np.zeros(seq_len, dtype=np.int64)
        if tail:
            buf[: len(tail)] = tail
        out[uid] = buf
    return out


def compute_item_popularity(
    ratings: list[dict[str, Any]],
    movie_map: dict[int, int],
) -> np.ndarray:
    """Empirical popularity vector for LogQ correction.
    Returns (n_items + 1,) with probability of sampling each item.
    Index 0 is padding — set to small value.
    """
    n = len(movie_map) + 1
    counts = np.zeros(n, dtype=np.float64)
    for r in ratings:
        idx = movie_map.get(r["movie_id"])
        if idx is not None:
            counts[idx] += 1.0
    total = counts.sum()
    if total <= 0:
        # uniform fallback
        counts[:] = 1.0
        total = float(n)
    prob = counts / total
    # padding slot gets tiny probability (not zero to avoid log issues)
    prob[0] = max(prob[0], 1e-10)
    return prob.astype(np.float32)


def build_user_features(
    ratings: list[dict[str, Any]],
    movie_genres: dict[int, list[str]],
    genre_to_idx: dict[str, int],
) -> dict[str, np.ndarray]:
    user_ratings: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for r in ratings:
        user_ratings[str(r["user_id"])].append((r["movie_id"], float(r["score"])))

    user_features: dict[str, np.ndarray] = {}
    for uid, urs in user_ratings.items():
        feat = np.zeros(USER_FEATURE_DIM, dtype=np.float32)
        scores = [s for _, s in urs]
        genre_counts = np.zeros(N_GENRES, dtype=np.float32)
        for mid, _ in urs:
            for g in movie_genres.get(mid, []):
                if g in genre_to_idx and genre_to_idx[g] < N_GENRES:
                    genre_counts[genre_to_idx[g]] += 1
        total = genre_counts.sum()
        if total > 0:
            feat[:N_GENRES] = genre_counts / total
        feat[N_GENRES] = np.mean(scores) / 5.0
        # log(n_ratings+1) normalized by log(500+1) — matches engagement scale
        feat[N_GENRES + 1] = float(np.log1p(len(scores)) / np.log1p(500.0))
        feat[N_GENRES + 2] = np.std(scores) / 2.5 if len(scores) > 1 else 0.0
        user_features[uid] = feat
    return user_features


class MovieLensDataset(Dataset):
    def __init__(
        self,
        ratings: list[dict[str, Any]],
        item_features: dict[int, np.ndarray],
        nlp_embeddings: dict[int, np.ndarray],
        genomes: dict[int, np.ndarray],
        user_features: dict[str, np.ndarray],
        user_map: dict[int, int],
        movie_map: dict[int, int],
        user_history: dict[str, set[int]],
        user_history_nlp: dict[str, np.ndarray] | None = None,
        user_sequence_ids: dict[str, np.ndarray] | None = None,
        neg_samples: int = NEG_SAMPLES,
    ) -> None:
        self.ratings = ratings
        self.item_features = item_features
        self.nlp_embeddings = nlp_embeddings
        self.genomes = genomes
        self.user_features = user_features
        self.user_map = user_map
        self.movie_map = movie_map
        self.user_history = user_history
        self.user_history_nlp = user_history_nlp
        self.user_sequence_ids = user_sequence_ids
        self.neg_samples = neg_samples
        self.all_movie_ids = list(movie_map.keys())
        self._zero_seq = np.zeros(HISTORY_TOP_N, dtype=np.int64)
        self._zero_item = np.zeros(ITEM_FEATURE_DIM, dtype=np.float32)
        self._zero_nlp = np.zeros(NLP_DIM, dtype=np.float32)
        self._zero_genome = np.zeros(GENOME_DIM, dtype=np.float32)
        self._zero_user = np.zeros(USER_FEATURE_DIM, dtype=np.float32)

    def __len__(self) -> int:
        return len(self.ratings)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        r = self.ratings[idx]
        uid_str = str(r["user_id"])
        uid = self.user_map.get(r["user_id"], 0)
        mid = r["movie_id"]
        pos_idx = self.movie_map.get(mid, 0)

        seen = self.user_history.get(uid_str, set())
        neg_ids: list[int] = []
        neg_feats: list[np.ndarray] = []
        neg_nlps: list[np.ndarray] = []
        neg_genomes: list[np.ndarray] = []

        attempts = 0
        while len(neg_ids) < self.neg_samples and attempts < self.neg_samples * 4:
            neg_mid = random.choice(self.all_movie_ids)
            attempts += 1
            if neg_mid in seen:
                continue
            neg_ids.append(self.movie_map.get(neg_mid, 0))
            neg_feats.append(self.item_features.get(neg_mid, self._zero_item))
            neg_nlps.append(self.nlp_embeddings.get(neg_mid, self._zero_nlp))
            neg_genomes.append(self.genomes.get(neg_mid, self._zero_genome))
        while len(neg_ids) < self.neg_samples:
            neg_mid = random.choice(self.all_movie_ids)
            neg_ids.append(self.movie_map.get(neg_mid, 0))
            neg_feats.append(self.item_features.get(neg_mid, self._zero_item))
            neg_nlps.append(self.nlp_embeddings.get(neg_mid, self._zero_nlp))
            neg_genomes.append(self.genomes.get(neg_mid, self._zero_genome))

        out: dict[str, torch.Tensor] = {
            "user_ids": torch.tensor(uid, dtype=torch.long),
            "user_feats": torch.tensor(
                self.user_features.get(uid_str, self._zero_user), dtype=torch.float32
            ),
            "pos_ids": torch.tensor(pos_idx, dtype=torch.long),
            "pos_feats": torch.tensor(
                self.item_features.get(mid, self._zero_item), dtype=torch.float32
            ),
            "pos_nlp": torch.tensor(
                self.nlp_embeddings.get(mid, self._zero_nlp), dtype=torch.float32
            ),
            "pos_genome": torch.tensor(
                self.genomes.get(mid, self._zero_genome), dtype=torch.float32
            ),
            "neg_ids": torch.tensor(neg_ids, dtype=torch.long),
            "neg_feats": torch.tensor(np.array(neg_feats), dtype=torch.float32),
            "neg_nlp": torch.tensor(np.array(neg_nlps), dtype=torch.float32),
            "neg_genome": torch.tensor(np.array(neg_genomes), dtype=torch.float32),
        }
        if self.user_history_nlp is not None:
            out["user_history_nlp"] = torch.tensor(
                self.user_history_nlp.get(uid_str, self._zero_nlp),
                dtype=torch.float32,
            )
        if self.user_sequence_ids is not None:
            out["user_sequence_ids"] = torch.tensor(
                self.user_sequence_ids.get(uid_str, self._zero_seq),
                dtype=torch.long,
            )
        return out


async def _load_data(url: str) -> dict[str, Any]:
    pool = await asyncpg.create_pool(url, min_size=2, max_size=5)
    try:
        return await load_training_data(pool)
    finally:
        await pool.close()


def train(
    epochs: int = 20,
    batch_size: int = 2048,
    lr: float = 3e-4,
    dropout: float = 0.2,
    temperature: float = 0.07,
    label_smoothing: float = 0.1,
    patience: int = 5,
    use_logq_correction: bool = False,
    use_history: bool = False,
    use_sequence: bool = False,
) -> None:
    url = os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://")
    data = asyncio.run(_load_data(url))

    ratings = data["ratings"]
    item_features = data["item_features"]
    nlp_embeddings = data["nlp_embeddings"]
    genomes = data["genomes"]
    movie_genres = data["movie_genres"]
    user_map = data["user_map"]
    movie_map = data["movie_map"]
    genre_to_idx = data["genre_to_idx"]

    print(
        f"Loaded {len(ratings)} ratings, {len(movie_map)} movies, {len(user_map)} users"
    )
    g_count = sum(1 for v in genomes.values() if v.any())
    print(f"Genome coverage: {g_count}/{len(genomes)} movies")

    # --- Core-pruning + positive-threshold filtering (implicit feedback) ---
    # Count positives (rating ≥ 4.0) per user; keep users with 10..500 positives.
    from collections import Counter
    user_pos_count: Counter = Counter()
    for r in ratings:
        if float(r["score"]) >= POSITIVE_THRESHOLD:
            user_pos_count[r["user_id"]] += 1
    eligible_users = {
        uid for uid, cnt in user_pos_count.items()
        if MIN_USER_POSITIVES <= cnt <= MAX_USER_POSITIVES
    }
    print(
        f"Core-pruning: {len(eligible_users)}/{len(user_pos_count)} users "
        f"have {MIN_USER_POSITIVES}-{MAX_USER_POSITIVES} positives (score ≥ {POSITIVE_THRESHOLD})"
    )

    # Keep ALL context ratings (score < 4) for user history/features, but the
    # Dataset iterates only over positives.
    context_ratings = [r for r in ratings if r["user_id"] in eligible_users]
    positive_ratings = [
        r for r in context_ratings if float(r["score"]) >= POSITIVE_THRESHOLD
    ]
    print(
        f"After filtering: {len(context_ratings):,} context ratings, "
        f"{len(positive_ratings):,} positives"
    )

    # Temporal split on POSITIVES (targets)
    split_idx = int(len(positive_ratings) * 0.9)
    train_ratings = positive_ratings[:split_idx]
    val_ratings = positive_ratings[split_idx:]

    # Context for user features: all train-time interactions (even low-rated)
    # of eligible users, sorted by time (same order as DB).
    split_time_cutoff_idx = 0
    if train_ratings:
        # Find the cutoff in context_ratings that corresponds to train_ratings end.
        # Use the last train positive's index among context_ratings.
        last_train_pos_id = id(train_ratings[-1])
        for i, r in enumerate(context_ratings):
            if id(r) == last_train_pos_id:
                split_time_cutoff_idx = i + 1
                break
    train_context = context_ratings[:split_time_cutoff_idx] if split_time_cutoff_idx else train_ratings

    print("Building user features from TRAIN CONTEXT (all ratings ≤ train cutoff)...")
    # IMPORTANT: ALL user-derived features must be built from train context only.
    # User's genre profile / activity stats use their FULL train history
    # (including ratings <4), while targets in the Dataset are only positives.
    train_user_features = build_user_features(train_context, movie_genres, genre_to_idx)

    # user_history blocks ALL seen items (even low-rated) from negative sampling
    user_history: dict[str, set[int]] = defaultdict(set)
    for r in train_context:
        user_history[str(r["user_id"])].add(r["movie_id"])

    train_history_nlp = None
    if use_history:
        print("Building user BoW history vectors (positives only, weighted by score)...")
        train_history_nlp = build_user_history_nlp(train_ratings, nlp_embeddings)

    train_sequence_ids = None
    if use_sequence:
        print("Building user sequence IDs (last N positives in TRAIN)...")
        train_sequence_ids = build_user_sequence_ids(train_ratings, movie_map)

    item_popularity = None
    if use_logq_correction:
        print("Computing item popularity for LogQ correction (positives only)...")
        item_popularity = compute_item_popularity(train_ratings, movie_map)
        nonzero = int(np.count_nonzero(item_popularity > 1e-10))
        print(f"  popularity computed for {nonzero}/{len(item_popularity)} items")

    train_ds = MovieLensDataset(
        train_ratings, item_features, nlp_embeddings, genomes, train_user_features,
        user_map, movie_map, user_history,
        user_history_nlp=train_history_nlp,
        user_sequence_ids=train_sequence_ids,
    )
    # val uses TRAIN-derived user features — model must predict val from train context only.
    val_ds = MovieLensDataset(
        val_ratings, item_features, nlp_embeddings, genomes, train_user_features,
        user_map, movie_map, user_history,
        user_history_nlp=train_history_nlp,
        user_sequence_ids=train_sequence_ids,
    )

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, num_workers=0, drop_last=True
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, num_workers=0, drop_last=True
    )

    model = TwoTowerModel(
        n_users=len(user_map),
        n_items=len(movie_map),
        item_feature_dim=ITEM_FEATURE_DIM,
        user_feature_dim=USER_FEATURE_DIM,
        nlp_emb_dim=NLP_DIM,
        nlp_proj_dim=64,
        genome_dim=GENOME_DIM,
        genome_proj_dim=64,
        emb_dim=256,
        user_emb_dim=64,
        hidden_dim=512,
        out_dim=256,
        dropout=dropout,
        n_blocks=2,
        lr=lr,
        weight_decay=1e-4,
        label_smoothing=label_smoothing,
        temperature=temperature,
        use_logq_correction=use_logq_correction,
        history_nlp_dim=NLP_DIM if use_history else 0,
        history_proj_dim=64,
        use_sequence=use_sequence,
        sequence_len=HISTORY_TOP_N,
        sequence_dim=64,
    )

    if item_popularity is not None:
        model.set_item_popularity(torch.tensor(item_popularity))

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "./mlruns"))
    mlflow.set_experiment("two_tower_recsys_v3")

    early_stop = EarlyStopping(
        monitor="val_hr_at_10", patience=patience, mode="max", verbose=True
    )
    checkpoint = ModelCheckpoint(
        monitor="val_hr_at_10", mode="max", save_top_k=1,
        filename="best-{epoch}-{val_hr_at_10:.4f}",
    )

    with mlflow.start_run() as run:
        mlflow.log_params({
            "version": "v3",
            "n_users": len(user_map),
            "n_items": len(movie_map),
            "n_train": len(train_ratings),
            "n_val": len(val_ratings),
            "batch_size": batch_size,
            "epochs": epochs,
            "lr": lr,
            "dropout": dropout,
            "temperature": temperature,
            "label_smoothing": label_smoothing,
            "genome_dim": GENOME_DIM,
            "emb_dim": 256,
            "hidden_dim": 512,
            "out_dim": 256,
        })

        trainer = pl.Trainer(
            max_epochs=epochs,
            accelerator="auto",
            enable_progress_bar=True,
            log_every_n_steps=50,
            callbacks=[early_stop, checkpoint],
            gradient_clip_val=1.0,
        )
        trainer.fit(model, train_loader, val_loader)

        best_score = checkpoint.best_model_score
        if best_score is not None:
            mlflow.log_metric("best_val_hr_at_10", best_score.item())
            print(f"\nBest val HR@10: {best_score.item():.4f}")

        if checkpoint.best_model_path:
            model = TwoTowerModel.load_from_checkpoint(checkpoint.best_model_path)
            print(f"Loaded: {checkpoint.best_model_path}")

        mlflow.pytorch.log_model(model, "model")
        model_uri = f"runs:/{run.info.run_id}/model"
        mlflow.register_model(model_uri, "two_tower_recsys")
        print(f"Run: {run.info.run_id}\nURI: {model_uri}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--temperature", type=float, default=0.07)
    parser.add_argument("--label-smoothing", type=float, default=0.1)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--use-logq", action="store_true", help="Enable LogQ correction")
    parser.add_argument("--use-history", action="store_true", help="Enable BoW user history")
    parser.add_argument("--use-sequence", action="store_true", help="Enable attention over recent items")
    args = parser.parse_args()
    train(
        epochs=args.epochs, batch_size=args.batch_size, lr=args.lr,
        dropout=args.dropout, temperature=args.temperature,
        label_smoothing=args.label_smoothing, patience=args.patience,
        use_logq_correction=args.use_logq,
        use_history=args.use_history,
        use_sequence=args.use_sequence,
    )
