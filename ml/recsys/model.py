import pytorch_lightning as pl
import torch
import torch.nn as nn
import torch.nn.functional as F


class ResidualBlock(nn.Module):
    def __init__(self, dim: int, dropout: float) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, dim),
            nn.LayerNorm(dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.net(x)


class Tower(nn.Module):
    def __init__(
        self, input_dim: int, hidden_dim: int, out_dim: int, dropout: float, n_blocks: int = 2
    ) -> None:
        super().__init__()
        self.project = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.blocks = nn.Sequential(
            *[ResidualBlock(hidden_dim, dropout) for _ in range(n_blocks)]
        )
        self.head = nn.Linear(hidden_dim, out_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.project(x)
        h = self.blocks(h)
        return F.normalize(self.head(h), dim=-1)


class GenomeEncoder(nn.Module):
    def __init__(self, in_dim: int = 1128, out_dim: int = 64, dropout: float = 0.2) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 256),
            nn.LayerNorm(256),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, out_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class TwoTowerModel(pl.LightningModule):
    def __init__(
        self,
        n_users: int,
        n_items: int,
        item_feature_dim: int = 22,
        user_feature_dim: int = 22,
        nlp_emb_dim: int = 384,
        nlp_proj_dim: int = 64,
        genome_dim: int = 1128,
        genome_proj_dim: int = 64,
        emb_dim: int = 256,
        hidden_dim: int = 512,
        out_dim: int = 256,
        dropout: float = 0.2,
        n_blocks: int = 2,
        lr: float = 3e-4,
        weight_decay: float = 1e-4,
        label_smoothing: float = 0.1,
        temperature: float = 0.07,
    ) -> None:
        super().__init__()
        self.save_hyperparameters()

        self.user_embedding = nn.Embedding(n_users + 1, emb_dim, padding_idx=0)
        self.item_embedding = nn.Embedding(n_items + 1, emb_dim, padding_idx=0)
        nn.init.xavier_normal_(self.user_embedding.weight[1:])
        nn.init.xavier_normal_(self.item_embedding.weight[1:])

        self.nlp_proj = nn.Sequential(
            nn.Linear(nlp_emb_dim, nlp_proj_dim),
            nn.LayerNorm(nlp_proj_dim),
            nn.GELU(),
        )
        self.genome_encoder = GenomeEncoder(genome_dim, genome_proj_dim, dropout)

        user_input_dim = emb_dim + user_feature_dim
        item_input_dim = emb_dim + item_feature_dim + nlp_proj_dim + genome_proj_dim

        self.user_tower = Tower(user_input_dim, hidden_dim, out_dim, dropout, n_blocks)
        self.item_tower = Tower(item_input_dim, hidden_dim, out_dim, dropout, n_blocks)

        self.register_buffer("temperature_t", torch.tensor(temperature))
        self.label_smoothing = label_smoothing

    @property
    def temperature(self) -> torch.Tensor:
        return self.temperature_t

    def encode_user(self, user_ids: torch.Tensor, user_feats: torch.Tensor) -> torch.Tensor:
        emb = self.user_embedding(user_ids)
        return self.user_tower(torch.cat([emb, user_feats], dim=-1))

    def encode_item(
        self,
        item_ids: torch.Tensor,
        item_feats: torch.Tensor,
        nlp_emb: torch.Tensor,
        genome: torch.Tensor,
    ) -> torch.Tensor:
        emb = self.item_embedding(item_ids)
        nlp = self.nlp_proj(nlp_emb)
        gn = self.genome_encoder(genome)
        return self.item_tower(torch.cat([emb, item_feats, nlp, gn], dim=-1))

    def _infonce_loss(
        self, user_emb: torch.Tensor, pos_emb: torch.Tensor
    ) -> torch.Tensor:
        B = user_emb.shape[0]
        in_batch_scores = (user_emb @ pos_emb.T) / self.temperature
        in_batch_scores = in_batch_scores.clamp(-50.0, 50.0)
        labels = torch.arange(B, device=self.device)
        return F.cross_entropy(in_batch_scores, labels, label_smoothing=self.label_smoothing)

    def _step(self, batch: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        u = self.encode_user(batch["user_ids"], batch["user_feats"])
        p = self.encode_item(
            batch["pos_ids"], batch["pos_feats"], batch["pos_nlp"], batch["pos_genome"]
        )
        return u, p

    def training_step(self, batch: dict[str, torch.Tensor], _: int) -> torch.Tensor:
        u, p = self._step(batch)
        loss = self._infonce_loss(u, p)
        self.log("train_loss", loss, prog_bar=True)
        return loss

    def validation_step(self, batch: dict[str, torch.Tensor], _: int) -> None:
        u, p = self._step(batch)
        loss = self._infonce_loss(u, p)

        scores = u @ p.T
        ranks = (scores >= scores.diag().unsqueeze(-1)).sum(dim=-1).float()

        self.log("val_loss", loss, prog_bar=True, sync_dist=True)
        self.log("val_hr_at_10", (ranks <= 10).float().mean(), prog_bar=True, sync_dist=True)
        self.log("val_ndcg_at_10", (1.0 / torch.log2(ranks + 1)).clamp(max=1.0).mean(), sync_dist=True)
        self.log("val_mrr", (1.0 / ranks).mean(), sync_dist=True)

    def configure_optimizers(self) -> dict:
        opt = torch.optim.AdamW(
            self.parameters(),
            lr=self.hparams.lr,
            weight_decay=self.hparams.weight_decay,
        )
        sched = torch.optim.lr_scheduler.OneCycleLR(
            opt,
            max_lr=self.hparams.lr,
            total_steps=self.trainer.estimated_stepping_batches,
            pct_start=0.05,
            anneal_strategy="cos",
        )
        return {
            "optimizer": opt,
            "lr_scheduler": {"scheduler": sched, "interval": "step"},
        }
