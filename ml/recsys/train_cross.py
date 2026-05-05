"""Train Cross-Encoder re-ranker using frozen Two-Tower embeddings.

Usage:
    POSTGRES_URL=postgresql://... \\
      uv run python train_cross.py \\
        --two-tower-checkpoint lightning_logs/version_X/checkpoints/best-*.ckpt \\
        --epochs 10
"""

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg
import mlflow
import mlflow.pytorch
import numpy as np
import pytorch_lightning as pl
import torch
from dotenv import load_dotenv
from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint
from torch.utils.data import DataLoader, Dataset

from cross_encoder import CrossEncoderModel
from model import TwoTowerModel
from train import (
    ITEM_FEATURE_DIM, NLP_DIM, GENOME_DIM, HISTORY_TOP_N,
    build_user_features, build_user_history_nlp, build_user_sequence_ids,
    load_training_data,
)

load_dotenv()


class PairDataset(Dataset):
    """Returns (user_emb, item_emb, target) precomputed from frozen Two-Tower."""

    def __init__(
        self,
        ratings: list[dict],
        user_embs: dict[str, np.ndarray],
        item_embs: dict[int, np.ndarray],
    ) -> None:
        # Filter to ratings where both embeddings exist
        self.data = [
            (str(r["user_id"]), r["movie_id"], float(r["score"]))
            for r in ratings
            if str(r["user_id"]) in user_embs and r["movie_id"] in item_embs
        ]
        self.user_embs = user_embs
        self.item_embs = item_embs

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        uid, mid, score = self.data[idx]
        return {
            "user_emb": torch.tensor(self.user_embs[uid], dtype=torch.float32),
            "item_emb": torch.tensor(self.item_embs[mid], dtype=torch.float32),
            "target": torch.tensor(score, dtype=torch.float32),
        }


async def _load(url: str) -> dict:
    pool = await asyncpg.create_pool(url, min_size=2, max_size=5)
    try:
        return await load_training_data(pool)
    finally:
        await pool.close()


def precompute_embeddings(
    model: TwoTowerModel,
    data: dict,
    ratings: list[dict],
    device: torch.device,
) -> tuple[dict[str, np.ndarray], dict[int, np.ndarray]]:
    """Run frozen Two-Tower once over all users and items, cache embeddings."""
    item_features = data["item_features"]
    nlp_embeddings = data["nlp_embeddings"]
    genomes = data["genomes"]
    movie_genres = data["movie_genres"]
    user_map = data["user_map"]
    movie_map = data["movie_map"]
    genre_to_idx = data["genre_to_idx"]

    print("Computing item catalog embeddings...")
    all_mids = sorted(movie_map.keys())
    item_embs_arr: list[np.ndarray] = []
    batch_size = 1024
    for i in range(0, len(all_mids), batch_size):
        chunk = all_mids[i : i + batch_size]
        with torch.no_grad():
            ids_t = torch.tensor([movie_map[m] for m in chunk], dtype=torch.long, device=device)
            feats_t = torch.tensor(
                np.array([item_features.get(m, np.zeros(ITEM_FEATURE_DIM)) for m in chunk]),
                dtype=torch.float32, device=device,
            )
            nlp_t = torch.tensor(
                np.array([nlp_embeddings.get(m, np.zeros(NLP_DIM)) for m in chunk]),
                dtype=torch.float32, device=device,
            )
            gen_t = torch.tensor(
                np.array([genomes.get(m, np.zeros(GENOME_DIM)) for m in chunk]),
                dtype=torch.float32, device=device,
            )
            emb = model.encode_item(ids_t, feats_t, nlp_t, gen_t).cpu().numpy().astype(np.float32)
        item_embs_arr.append(emb)
    item_embs_arr = np.concatenate(item_embs_arr, axis=0)
    item_embs = {mid: item_embs_arr[i] for i, mid in enumerate(all_mids)}
    print(f"  {len(item_embs)} item embeddings cached")

    print("Computing user embeddings...")
    user_features = build_user_features(ratings, movie_genres, genre_to_idx)
    hist_nlp = build_user_history_nlp(ratings, nlp_embeddings) if getattr(model, "use_history", False) else {}
    seq_ids_map = build_user_sequence_ids(ratings, movie_map) if getattr(model, "use_sequence", False) else {}

    uid_to_idx = {str(k): v for k, v in user_map.items()}
    all_uids = list(user_features.keys())
    user_embs_arr: list[np.ndarray] = []
    for i in range(0, len(all_uids), batch_size):
        chunk = all_uids[i : i + batch_size]
        with torch.no_grad():
            uids_t = torch.tensor([uid_to_idx.get(u, 0) for u in chunk], dtype=torch.long, device=device)
            feats_t = torch.tensor(
                np.array([user_features[u] for u in chunk]), dtype=torch.float32, device=device
            )
            hist_t = None
            if getattr(model, "use_history", False):
                hist_t = torch.tensor(
                    np.array([hist_nlp.get(u, np.zeros(NLP_DIM, dtype=np.float32)) for u in chunk]),
                    dtype=torch.float32, device=device,
                )
            seq_t = None
            if getattr(model, "use_sequence", False):
                seq_t = torch.tensor(
                    np.array([seq_ids_map.get(u, np.zeros(HISTORY_TOP_N, dtype=np.int64)) for u in chunk]),
                    dtype=torch.long, device=device,
                )
            try:
                emb = model.encode_user(uids_t, feats_t, hist_t, seq_t).cpu().numpy().astype(np.float32)
            except TypeError:
                emb = model.encode_user(uids_t, feats_t).cpu().numpy().astype(np.float32)
        user_embs_arr.append(emb)
    user_embs_arr = np.concatenate(user_embs_arr, axis=0)
    user_embs = {uid: user_embs_arr[i] for i, uid in enumerate(all_uids)}
    print(f"  {len(user_embs)} user embeddings cached")

    return user_embs, item_embs


def train(checkpoint: str, epochs: int = 10, batch_size: int = 4096, lr: float = 1e-3) -> None:
    url = os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://")
    data = asyncio.run(_load(url))
    ratings = data["ratings"]

    split_idx = int(len(ratings) * 0.9)
    train_ratings = ratings[:split_idx]
    val_ratings = ratings[split_idx:]

    print(f"Loading Two-Tower: {checkpoint}")
    two_tower = TwoTowerModel.load_from_checkpoint(checkpoint, map_location="cpu")
    two_tower.eval()
    for p in two_tower.parameters():
        p.requires_grad = False

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    two_tower = two_tower.to(device)

    user_embs, item_embs = precompute_embeddings(two_tower, data, ratings, device)

    train_ds = PairDataset(train_ratings, user_embs, item_embs)
    val_ds = PairDataset(val_ratings, user_embs, item_embs)
    print(f"Pairs: {len(train_ds)} train, {len(val_ds)} val")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    emb_dim = next(iter(item_embs.values())).shape[0]
    model = CrossEncoderModel(emb_dim=emb_dim, hidden_dim=512, dropout=0.2, lr=lr)

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "./mlruns"))
    mlflow.set_experiment("cross_encoder")

    early = EarlyStopping(monitor="val_mse", patience=3, mode="min", verbose=True)
    ckpt = ModelCheckpoint(monitor="val_mse", mode="min", save_top_k=1, filename="best-{epoch}-{val_mse:.4f}")

    with mlflow.start_run() as run:
        mlflow.log_params({
            "two_tower_checkpoint": checkpoint,
            "emb_dim": emb_dim,
            "batch_size": batch_size,
            "lr": lr,
            "epochs": epochs,
            "n_train": len(train_ds),
            "n_val": len(val_ds),
        })

        trainer = pl.Trainer(
            max_epochs=epochs, accelerator="auto",
            callbacks=[early, ckpt],
            log_every_n_steps=50,
        )
        trainer.fit(model, train_loader, val_loader)

        best = ckpt.best_model_score
        if best is not None:
            mlflow.log_metric("best_val_mse", best.item())
            print(f"Best val MSE: {best.item():.4f}")

        if ckpt.best_model_path:
            model = CrossEncoderModel.load_from_checkpoint(ckpt.best_model_path)
        mlflow.pytorch.log_model(model, "model")
        mlflow.register_model(f"runs:/{run.info.run_id}/model", "cross_encoder")
        print(f"Run: {run.info.run_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--two-tower-checkpoint", type=str, required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()
    train(args.two_tower_checkpoint, args.epochs, args.batch_size, args.lr)
