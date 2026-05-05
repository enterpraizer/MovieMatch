"""Cross-Encoder re-ranker for multi-stage recommendation.

Two-Tower retrieves top-K candidates fast.  Cross-Encoder takes the same user
and each candidate, processes them jointly through a deep MLP and scores each
pair.  This stage is slow per-pair but only runs on K=200 candidates, so total
latency is bounded.

Input per pair: concat(user_emb, item_emb, user_emb * item_emb, abs diff)
Output: scalar score.  Trained pointwise on rating scores (0.5..5.0).
"""

from typing import Any

import pytorch_lightning as pl
import torch
import torch.nn as nn
import torch.nn.functional as F


class CrossEncoderModel(pl.LightningModule):
    def __init__(
        self,
        emb_dim: int = 256,
        hidden_dim: int = 512,
        dropout: float = 0.2,
        lr: float = 1e-3,
        weight_decay: float = 1e-4,
    ) -> None:
        super().__init__()
        self.save_hyperparameters()

        # Interaction features: user_emb + item_emb + element-wise product + abs diff
        input_dim = emb_dim * 4

        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, user_emb: torch.Tensor, item_emb: torch.Tensor) -> torch.Tensor:
        # user_emb, item_emb: (N, emb_dim)
        mul = user_emb * item_emb
        diff = (user_emb - item_emb).abs()
        x = torch.cat([user_emb, item_emb, mul, diff], dim=-1)
        return self.net(x).squeeze(-1)  # (N,)

    def training_step(self, batch: dict[str, torch.Tensor], _: int) -> torch.Tensor:
        # batch["user_emb"]: (B, emb), batch["item_emb"]: (B, emb), batch["target"]: (B,)
        pred = self(batch["user_emb"], batch["item_emb"])
        target = batch["target"]
        loss = F.mse_loss(pred, target)
        self.log("train_mse", loss, prog_bar=True)
        return loss

    def validation_step(self, batch: dict[str, torch.Tensor], _: int) -> None:
        pred = self(batch["user_emb"], batch["item_emb"])
        target = batch["target"]
        mse = F.mse_loss(pred, target)
        mae = (pred - target).abs().mean()
        self.log("val_mse", mse, prog_bar=True, sync_dist=True)
        self.log("val_mae", mae, prog_bar=True, sync_dist=True)

    def configure_optimizers(self) -> dict[str, Any]:
        opt = torch.optim.AdamW(
            self.parameters(),
            lr=self.hparams.lr,
            weight_decay=self.hparams.weight_decay,
        )
        return {"optimizer": opt}
