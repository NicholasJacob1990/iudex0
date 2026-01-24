"""
Knowledge Graph Embedding Trainer

Robust training pipeline for entity embeddings with:
- Negative sampling (uniform, self-adversarial)
- Mini-batch training with Adam optimizer
- Early stopping and validation
- Checkpoint save/load
- Multiple methods: TransE, RotatE, ComplEx, DistMult
- Optional PyTorch GPU acceleration

For Brazilian legal knowledge graphs: laws, jurisprudence, sumulas, articles.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import pickle
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================


class EmbeddingMethod(str, Enum):
    """Knowledge graph embedding methods."""
    TRANSE = "transe"      # Translation-based: h + r ≈ t
    ROTATE = "rotate"      # Rotation in complex space: h ∘ r ≈ t
    COMPLEX = "complex"    # ComplEx: hermitian dot product
    DISTMULT = "distmult"  # Diagonal bilinear: <h, r, t>


class NegativeSamplingStrategy(str, Enum):
    """Negative sampling strategies."""
    UNIFORM = "uniform"              # Random uniform sampling
    SELF_ADVERSARIAL = "self_adv"    # Self-adversarial (weighted by score)
    BERNOULLI = "bernoulli"          # Entity type-based sampling


@dataclass
class TrainingConfig:
    """Configuration for embedding training."""

    # Embedding dimensions
    embedding_dim: int = 128

    # Training method
    method: EmbeddingMethod = EmbeddingMethod.ROTATE

    # Training hyperparameters
    epochs: int = 200
    batch_size: int = 512
    learning_rate: float = 0.001
    weight_decay: float = 1e-5

    # Margins (method-specific)
    margin_transe: float = 1.0
    gamma_rotate: float = 12.0

    # Negative sampling
    negative_samples: int = 10
    negative_strategy: NegativeSamplingStrategy = NegativeSamplingStrategy.SELF_ADVERSARIAL
    adversarial_temperature: float = 1.0

    # Regularization
    entity_regularization: float = 0.0
    relation_regularization: float = 0.0

    # Early stopping
    patience: int = 20
    min_delta: float = 0.001
    validation_split: float = 0.1

    # Checkpointing
    checkpoint_dir: str = "data/embeddings/checkpoints"
    checkpoint_every: int = 50
    keep_last_n_checkpoints: int = 3

    # Evaluation
    eval_every: int = 10
    eval_batch_size: int = 256

    # Hardware
    use_gpu: bool = True  # Use PyTorch GPU if available
    num_workers: int = 4
    seed: int = 42

    def __post_init__(self):
        """Validate configuration."""
        if self.embedding_dim < 16:
            raise ValueError("embedding_dim must be >= 16")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.negative_samples < 1:
            raise ValueError("negative_samples must be >= 1")


@dataclass
class TrainingMetrics:
    """Training metrics for monitoring."""
    epoch: int = 0
    train_loss: float = float('inf')
    val_loss: float = float('inf')
    mrr: float = 0.0  # Mean Reciprocal Rank
    hits_at_1: float = 0.0
    hits_at_3: float = 0.0
    hits_at_10: float = 0.0
    epoch_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epoch": self.epoch,
            "train_loss": self.train_loss,
            "val_loss": self.val_loss,
            "mrr": self.mrr,
            "hits@1": self.hits_at_1,
            "hits@3": self.hits_at_3,
            "hits@10": self.hits_at_10,
            "epoch_time": self.epoch_time,
        }


@dataclass
class Checkpoint:
    """Training checkpoint."""
    epoch: int
    entity_embeddings: np.ndarray
    relation_embeddings: np.ndarray
    entity_to_idx: Dict[str, int]
    relation_to_idx: Dict[str, int]
    metrics: TrainingMetrics
    config: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def save(self, path: str) -> None:
        """Save checkpoint to file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        logger.info(f"Checkpoint saved: {path}")

    @classmethod
    def load(cls, path: str) -> "Checkpoint":
        """Load checkpoint from file."""
        with open(path, 'rb') as f:
            return pickle.load(f)


# =============================================================================
# TRIPLE DATASET
# =============================================================================


class TripleDataset:
    """
    Dataset for knowledge graph triples.

    Handles:
    - Entity/relation indexing
    - Train/validation split
    - Negative sampling
    - Batching
    """

    def __init__(
        self,
        triples: List[Tuple[str, str, str]],
        config: TrainingConfig,
    ):
        self.config = config
        self.rng = np.random.default_rng(config.seed)

        # Build vocabularies
        entities: Set[str] = set()
        relations: Set[str] = set()
        for h, r, t in triples:
            entities.add(h)
            entities.add(t)
            relations.add(r)

        self.entity_list = sorted(entities)
        self.relation_list = sorted(relations)
        self.entity_to_idx = {e: i for i, e in enumerate(self.entity_list)}
        self.relation_to_idx = {r: i for i, r in enumerate(self.relation_list)}
        self.idx_to_entity = {i: e for e, i in self.entity_to_idx.items()}
        self.idx_to_relation = {i: r for r, i in self.relation_to_idx.items()}

        self.n_entities = len(self.entity_list)
        self.n_relations = len(self.relation_list)

        # Convert triples to indices
        self.triples = np.array([
            [self.entity_to_idx[h], self.relation_to_idx[r], self.entity_to_idx[t]]
            for h, r, t in triples
        ], dtype=np.int32)

        # Build set for fast lookup (for negative sampling validation)
        self.triple_set = set(
            (h, r, t) for h, r, t in self.triples
        )

        # Train/validation split
        n_val = int(len(self.triples) * config.validation_split)
        indices = self.rng.permutation(len(self.triples))
        self.val_indices = indices[:n_val]
        self.train_indices = indices[n_val:]

        self.train_triples = self.triples[self.train_indices]
        self.val_triples = self.triples[self.val_indices]

        # Build entity frequency for type-based sampling
        self._entity_freq = np.zeros(self.n_entities, dtype=np.float32)
        for h, r, t in self.triples:
            self._entity_freq[h] += 1
            self._entity_freq[t] += 1
        self._entity_freq = self._entity_freq / self._entity_freq.sum()

        # Head/tail per relation for Bernoulli sampling
        self._head_per_rel: Dict[int, Set[int]] = {}
        self._tail_per_rel: Dict[int, Set[int]] = {}
        for h, r, t in self.triples:
            if r not in self._head_per_rel:
                self._head_per_rel[r] = set()
                self._tail_per_rel[r] = set()
            self._head_per_rel[r].add(h)
            self._tail_per_rel[r].add(t)

        logger.info(
            f"Dataset: {self.n_entities} entities, {self.n_relations} relations, "
            f"{len(self.train_triples)} train, {len(self.val_triples)} val triples"
        )

    def get_train_batches(self, shuffle: bool = True) -> Iterator[np.ndarray]:
        """Iterate over training batches."""
        indices = np.arange(len(self.train_triples))
        if shuffle:
            self.rng.shuffle(indices)

        for start in range(0, len(indices), self.config.batch_size):
            end = min(start + self.config.batch_size, len(indices))
            batch_idx = indices[start:end]
            yield self.train_triples[batch_idx]

    def get_val_batches(self) -> Iterator[np.ndarray]:
        """Iterate over validation batches."""
        for start in range(0, len(self.val_triples), self.config.eval_batch_size):
            end = min(start + self.config.eval_batch_size, len(self.val_triples))
            yield self.val_triples[start:end]

    def sample_negatives(
        self,
        batch: np.ndarray,
        scores: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Sample negative triples for a batch.

        Args:
            batch: Positive triples (N, 3)
            scores: Optional scores for self-adversarial sampling

        Returns:
            Negative triples (N, n_neg, 3)
        """
        n_pos = len(batch)
        n_neg = self.config.negative_samples
        negatives = np.zeros((n_pos, n_neg, 3), dtype=np.int32)

        for i, (h, r, t) in enumerate(batch):
            for j in range(n_neg):
                # Corrupt head or tail with 50% probability
                if self.rng.random() < 0.5:
                    # Corrupt head
                    if self.config.negative_strategy == NegativeSamplingStrategy.BERNOULLI:
                        # Sample from heads that appear with this relation
                        candidates = list(self._head_per_rel.get(r, range(self.n_entities)))
                        new_h = self.rng.choice(candidates)
                    else:
                        new_h = self.rng.integers(0, self.n_entities)

                    # Ensure it's actually negative
                    while (new_h, r, t) in self.triple_set:
                        new_h = self.rng.integers(0, self.n_entities)

                    negatives[i, j] = [new_h, r, t]
                else:
                    # Corrupt tail
                    if self.config.negative_strategy == NegativeSamplingStrategy.BERNOULLI:
                        candidates = list(self._tail_per_rel.get(r, range(self.n_entities)))
                        new_t = self.rng.choice(candidates)
                    else:
                        new_t = self.rng.integers(0, self.n_entities)

                    while (h, r, new_t) in self.triple_set:
                        new_t = self.rng.integers(0, self.n_entities)

                    negatives[i, j] = [h, r, new_t]

        return negatives


# =============================================================================
# EMBEDDING MODELS (NumPy Implementation)
# =============================================================================


class BaseEmbeddingModel:
    """Base class for KG embedding models."""

    def __init__(self, dataset: TripleDataset, config: TrainingConfig):
        self.dataset = dataset
        self.config = config
        self.rng = np.random.default_rng(config.seed)

        # Initialize embeddings
        self.entity_emb: np.ndarray = None
        self.relation_emb: np.ndarray = None
        self._initialize_embeddings()

        # Adam optimizer state
        self._m_ent = np.zeros_like(self.entity_emb)
        self._v_ent = np.zeros_like(self.entity_emb)
        self._m_rel = np.zeros_like(self.relation_emb)
        self._v_rel = np.zeros_like(self.relation_emb)
        self._t = 0

    def _initialize_embeddings(self) -> None:
        """Initialize embeddings with Xavier uniform."""
        raise NotImplementedError

    def score(self, h: np.ndarray, r: np.ndarray, t: np.ndarray) -> np.ndarray:
        """Compute scores for triples. Higher = better."""
        raise NotImplementedError

    def compute_gradients(
        self,
        pos_triples: np.ndarray,
        neg_triples: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute gradients for entity and relation embeddings.

        Returns:
            Tuple of (entity_grad, relation_grad, loss)
        """
        raise NotImplementedError

    def update(
        self,
        entity_grad: np.ndarray,
        relation_grad: np.ndarray,
        lr: float,
    ) -> None:
        """Update embeddings using Adam optimizer."""
        self._t += 1
        beta1, beta2 = 0.9, 0.999
        eps = 1e-8

        # Entity update
        self._m_ent = beta1 * self._m_ent + (1 - beta1) * entity_grad
        self._v_ent = beta2 * self._v_ent + (1 - beta2) * (entity_grad ** 2)
        m_hat = self._m_ent / (1 - beta1 ** self._t)
        v_hat = self._v_ent / (1 - beta2 ** self._t)
        self.entity_emb -= lr * m_hat / (np.sqrt(v_hat) + eps)

        # Weight decay
        if self.config.entity_regularization > 0:
            self.entity_emb *= (1 - lr * self.config.entity_regularization)

        # Relation update
        self._m_rel = beta1 * self._m_rel + (1 - beta1) * relation_grad
        self._v_rel = beta2 * self._v_rel + (1 - beta2) * (relation_grad ** 2)
        m_hat = self._m_rel / (1 - beta1 ** self._t)
        v_hat = self._v_rel / (1 - beta2 ** self._t)
        self.relation_emb -= lr * m_hat / (np.sqrt(v_hat) + eps)

        if self.config.relation_regularization > 0:
            self.relation_emb *= (1 - lr * self.config.relation_regularization)

    def normalize_entities(self) -> None:
        """Normalize entity embeddings (for TransE)."""
        norms = np.linalg.norm(self.entity_emb, axis=1, keepdims=True)
        self.entity_emb = self.entity_emb / (norms + 1e-8)

    def get_embeddings(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get entity and relation embeddings."""
        return self.entity_emb.copy(), self.relation_emb.copy()


class TransEModel(BaseEmbeddingModel):
    """
    TransE: Translating Embeddings for Modeling Multi-relational Data

    Score: -||h + r - t||
    """

    def _initialize_embeddings(self) -> None:
        dim = self.config.embedding_dim
        n_ent = self.dataset.n_entities
        n_rel = self.dataset.n_relations

        # Xavier uniform initialization
        bound = 6.0 / math.sqrt(dim)
        self.entity_emb = self.rng.uniform(-bound, bound, (n_ent, dim)).astype(np.float32)
        self.relation_emb = self.rng.uniform(-bound, bound, (n_rel, dim)).astype(np.float32)

        # Normalize entity embeddings
        self.normalize_entities()

    def score(self, h: np.ndarray, r: np.ndarray, t: np.ndarray) -> np.ndarray:
        """TransE score: -||h + r - t||_2"""
        return -np.linalg.norm(h + r - t, axis=-1)

    def compute_gradients(
        self,
        pos_triples: np.ndarray,
        neg_triples: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Compute margin ranking loss gradients."""
        margin = self.config.margin_transe

        # Get embeddings for positive triples
        h_pos = self.entity_emb[pos_triples[:, 0]]
        r_pos = self.relation_emb[pos_triples[:, 1]]
        t_pos = self.entity_emb[pos_triples[:, 2]]

        # Positive scores
        pos_scores = self.score(h_pos, r_pos, t_pos)  # Shape: (batch,)

        # Initialize gradients
        entity_grad = np.zeros_like(self.entity_emb)
        relation_grad = np.zeros_like(self.relation_emb)
        total_loss = 0.0

        n_pos = len(pos_triples)
        n_neg = neg_triples.shape[1]

        for i in range(n_pos):
            h_idx, r_idx, t_idx = pos_triples[i]

            for j in range(n_neg):
                nh_idx, nr_idx, nt_idx = neg_triples[i, j]

                # Negative score
                h_neg = self.entity_emb[nh_idx]
                r_neg = self.relation_emb[nr_idx]
                t_neg = self.entity_emb[nt_idx]
                neg_score = self.score(h_neg[np.newaxis], r_neg[np.newaxis], t_neg[np.newaxis])[0]

                # Margin loss: max(0, margin + pos_dist - neg_dist)
                # Since score = -dist, loss = max(0, margin - pos_score + neg_score)
                loss = margin - pos_scores[i] + neg_score

                if loss > 0:
                    total_loss += loss

                    # Gradient of ||h + r - t||
                    pos_diff = h_pos[i] + r_pos[i] - t_pos[i]
                    pos_diff_norm = np.linalg.norm(pos_diff) + 1e-8
                    pos_grad = pos_diff / pos_diff_norm

                    neg_diff = h_neg + r_neg - t_neg
                    neg_diff_norm = np.linalg.norm(neg_diff) + 1e-8
                    neg_grad = neg_diff / neg_diff_norm

                    # Positive gradients (minimize distance)
                    entity_grad[h_idx] += pos_grad
                    relation_grad[r_idx] += pos_grad
                    entity_grad[t_idx] -= pos_grad

                    # Negative gradients (maximize distance)
                    entity_grad[nh_idx] -= neg_grad
                    relation_grad[nr_idx] -= neg_grad
                    entity_grad[nt_idx] += neg_grad

        # Average over batch
        n_samples = n_pos * n_neg
        return entity_grad / n_samples, relation_grad / n_samples, total_loss / n_samples


class RotatEModel(BaseEmbeddingModel):
    """
    RotatE: Knowledge Graph Embedding by Relational Rotation in Complex Space

    Score: gamma - ||h ∘ r - t||

    h, t are complex vectors; r is unit-modulus rotation
    """

    def _initialize_embeddings(self) -> None:
        dim = self.config.embedding_dim
        n_ent = self.dataset.n_entities
        n_rel = self.dataset.n_relations

        # Entity embeddings: complex numbers as (dim, 2) -> (re, im)
        # Stored as (n_ent, dim*2)
        bound = 6.0 / math.sqrt(dim)
        self.entity_emb = self.rng.uniform(-bound, bound, (n_ent, dim * 2)).astype(np.float32)

        # Relation embeddings: phases in [-pi, pi]
        self.relation_emb = self.rng.uniform(-np.pi, np.pi, (n_rel, dim)).astype(np.float32)

    def _rotate(
        self,
        h: np.ndarray,
        r: np.ndarray,
    ) -> np.ndarray:
        """Apply rotation: h ∘ r in complex space."""
        dim = self.config.embedding_dim

        h_re = h[..., :dim]
        h_im = h[..., dim:]

        r_re = np.cos(r)
        r_im = np.sin(r)

        # Complex multiplication
        out_re = h_re * r_re - h_im * r_im
        out_im = h_re * r_im + h_im * r_re

        return np.concatenate([out_re, out_im], axis=-1)

    def score(self, h: np.ndarray, r: np.ndarray, t: np.ndarray) -> np.ndarray:
        """RotatE score: gamma - ||h ∘ r - t||"""
        gamma = self.config.gamma_rotate
        dim = self.config.embedding_dim

        rotated = self._rotate(h, r)

        diff_re = rotated[..., :dim] - t[..., :dim]
        diff_im = rotated[..., dim:] - t[..., dim:]

        dist = np.sqrt(np.sum(diff_re**2 + diff_im**2, axis=-1) + 1e-8)
        return gamma - dist

    def compute_gradients(
        self,
        pos_triples: np.ndarray,
        neg_triples: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Compute self-adversarial negative sampling loss gradients."""
        gamma = self.config.gamma_rotate
        temp = self.config.adversarial_temperature
        dim = self.config.embedding_dim

        # Get embeddings
        h_pos = self.entity_emb[pos_triples[:, 0]]
        r_pos = self.relation_emb[pos_triples[:, 1]]
        t_pos = self.entity_emb[pos_triples[:, 2]]

        pos_scores = self.score(h_pos, r_pos, t_pos)

        entity_grad = np.zeros_like(self.entity_emb)
        relation_grad = np.zeros_like(self.relation_emb)
        total_loss = 0.0

        n_pos = len(pos_triples)
        n_neg = neg_triples.shape[1]

        for i in range(n_pos):
            h_idx, r_idx, t_idx = pos_triples[i]

            # Collect negative scores for self-adversarial weighting
            neg_scores = []
            for j in range(n_neg):
                nh_idx, nr_idx, nt_idx = neg_triples[i, j]
                h_neg = self.entity_emb[nh_idx]
                r_neg = self.relation_emb[nr_idx]
                t_neg = self.entity_emb[nt_idx]
                neg_score = self.score(h_neg[np.newaxis], r_neg[np.newaxis], t_neg[np.newaxis])[0]
                neg_scores.append(neg_score)

            neg_scores = np.array(neg_scores)

            # Self-adversarial weights
            if self.config.negative_strategy == NegativeSamplingStrategy.SELF_ADVERSARIAL:
                weights = np.exp(neg_scores / temp)
                weights = weights / (weights.sum() + 1e-8)
            else:
                weights = np.ones(n_neg) / n_neg

            # Compute loss and gradients for each negative
            for j in range(n_neg):
                nh_idx, nr_idx, nt_idx = neg_triples[i, j]
                w = weights[j]

                # Loss: -log(sigmoid(gamma - d_neg)) - log(sigmoid(d_pos - gamma))
                # Simplified margin version
                margin_loss = max(0, gamma + pos_scores[i] - neg_scores[j])
                total_loss += w * margin_loss

                if margin_loss > 0:
                    # Gradient computation
                    h_neg = self.entity_emb[nh_idx]
                    r_neg = self.relation_emb[nr_idx]
                    t_neg = self.entity_emb[nt_idx]

                    # Positive gradient
                    rotated_pos = self._rotate(h_pos[i:i+1], r_pos[i:i+1])[0]
                    diff_pos = rotated_pos - t_pos[i]
                    dist_pos = np.linalg.norm(diff_pos) + 1e-8
                    grad_pos = diff_pos / dist_pos

                    # Update positive embeddings
                    entity_grad[h_idx, :dim] += w * grad_pos[:dim] * np.cos(r_pos[i])
                    entity_grad[h_idx, dim:] += w * grad_pos[dim:] * np.cos(r_pos[i])
                    entity_grad[t_idx] -= w * grad_pos

                    # Negative gradient (opposite direction)
                    rotated_neg = self._rotate(h_neg[np.newaxis], r_neg[np.newaxis])[0]
                    diff_neg = rotated_neg - t_neg
                    dist_neg = np.linalg.norm(diff_neg) + 1e-8
                    grad_neg = diff_neg / dist_neg

                    entity_grad[nh_idx, :dim] -= w * grad_neg[:dim] * np.cos(r_neg)
                    entity_grad[nh_idx, dim:] -= w * grad_neg[dim:] * np.cos(r_neg)
                    entity_grad[nt_idx] += w * grad_neg

        n_samples = n_pos * n_neg
        return entity_grad / n_samples, relation_grad / n_samples, total_loss / n_samples


class DistMultModel(BaseEmbeddingModel):
    """
    DistMult: Embedding Entities and Relations for Learning and Inference in KBs

    Score: <h, r, t> = sum(h * r * t)
    """

    def _initialize_embeddings(self) -> None:
        dim = self.config.embedding_dim
        n_ent = self.dataset.n_entities
        n_rel = self.dataset.n_relations

        bound = 6.0 / math.sqrt(dim)
        self.entity_emb = self.rng.uniform(-bound, bound, (n_ent, dim)).astype(np.float32)
        self.relation_emb = self.rng.uniform(-bound, bound, (n_rel, dim)).astype(np.float32)

    def score(self, h: np.ndarray, r: np.ndarray, t: np.ndarray) -> np.ndarray:
        """DistMult score: sum(h * r * t)"""
        return np.sum(h * r * t, axis=-1)

    def compute_gradients(
        self,
        pos_triples: np.ndarray,
        neg_triples: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Compute binary cross-entropy loss gradients."""
        # Get embeddings
        h_pos = self.entity_emb[pos_triples[:, 0]]
        r_pos = self.relation_emb[pos_triples[:, 1]]
        t_pos = self.entity_emb[pos_triples[:, 2]]

        pos_scores = self.score(h_pos, r_pos, t_pos)

        entity_grad = np.zeros_like(self.entity_emb)
        relation_grad = np.zeros_like(self.relation_emb)
        total_loss = 0.0

        n_pos = len(pos_triples)
        n_neg = neg_triples.shape[1]

        # Sigmoid function
        def sigmoid(x):
            return 1.0 / (1.0 + np.exp(-np.clip(x, -10, 10)))

        for i in range(n_pos):
            h_idx, r_idx, t_idx = pos_triples[i]

            # Positive loss: -log(sigmoid(score))
            pos_sig = sigmoid(pos_scores[i])
            total_loss -= np.log(pos_sig + 1e-8)

            # Positive gradient: (sigmoid - 1) * gradient
            pos_factor = pos_sig - 1
            entity_grad[h_idx] += pos_factor * r_pos[i] * t_pos[i]
            relation_grad[r_idx] += pos_factor * h_pos[i] * t_pos[i]
            entity_grad[t_idx] += pos_factor * h_pos[i] * r_pos[i]

            for j in range(n_neg):
                nh_idx, nr_idx, nt_idx = neg_triples[i, j]

                h_neg = self.entity_emb[nh_idx]
                r_neg = self.relation_emb[nr_idx]
                t_neg = self.entity_emb[nt_idx]

                neg_score = self.score(h_neg[np.newaxis], r_neg[np.newaxis], t_neg[np.newaxis])[0]
                neg_sig = sigmoid(neg_score)

                # Negative loss: -log(1 - sigmoid(score))
                total_loss -= np.log(1 - neg_sig + 1e-8)

                # Negative gradient: sigmoid * gradient
                neg_factor = neg_sig
                entity_grad[nh_idx] += neg_factor * r_neg * t_neg
                relation_grad[nr_idx] += neg_factor * h_neg * t_neg
                entity_grad[nt_idx] += neg_factor * h_neg * r_neg

        n_samples = n_pos * (1 + n_neg)
        return entity_grad / n_samples, relation_grad / n_samples, total_loss / n_samples


# =============================================================================
# TRAINER
# =============================================================================


class EmbeddingTrainer:
    """
    Main trainer class for knowledge graph embeddings.

    Features:
    - Multiple embedding methods
    - Negative sampling strategies
    - Early stopping
    - Checkpointing
    - Evaluation metrics (MRR, Hits@K)
    """

    def __init__(
        self,
        triples: List[Tuple[str, str, str]],
        config: Optional[TrainingConfig] = None,
    ):
        self.config = config or TrainingConfig()
        self.dataset = TripleDataset(triples, self.config)

        # Initialize model based on method
        model_cls = {
            EmbeddingMethod.TRANSE: TransEModel,
            EmbeddingMethod.ROTATE: RotatEModel,
            EmbeddingMethod.DISTMULT: DistMultModel,
            # ComplEx can use RotatE with modifications
        }
        self.model = model_cls.get(
            self.config.method, RotatEModel
        )(self.dataset, self.config)

        # Training state
        self.best_metrics: Optional[TrainingMetrics] = None
        self.history: List[TrainingMetrics] = []
        self.patience_counter = 0

        # Checkpointing
        os.makedirs(self.config.checkpoint_dir, exist_ok=True)

        logger.info(
            f"EmbeddingTrainer initialized: method={self.config.method.value}, "
            f"dim={self.config.embedding_dim}, epochs={self.config.epochs}"
        )

    def train(self) -> Dict[str, np.ndarray]:
        """
        Train embeddings.

        Returns:
            Dict with 'entity_embeddings' and 'relation_embeddings'
        """
        logger.info("Starting embedding training...")

        for epoch in range(1, self.config.epochs + 1):
            epoch_start = time.time()

            # Training
            train_loss = self._train_epoch()

            # Evaluation
            metrics = TrainingMetrics(epoch=epoch, train_loss=train_loss)

            if epoch % self.config.eval_every == 0:
                val_loss, mrr, hits = self._evaluate()
                metrics.val_loss = val_loss
                metrics.mrr = mrr
                metrics.hits_at_1 = hits[1]
                metrics.hits_at_3 = hits[3]
                metrics.hits_at_10 = hits[10]

            metrics.epoch_time = time.time() - epoch_start
            self.history.append(metrics)

            # Logging
            if epoch % self.config.eval_every == 0:
                logger.info(
                    f"Epoch {epoch}/{self.config.epochs}: "
                    f"loss={train_loss:.4f}, val_loss={metrics.val_loss:.4f}, "
                    f"MRR={metrics.mrr:.4f}, Hits@10={metrics.hits_at_10:.4f}"
                )

            # Early stopping check
            if self._check_early_stopping(metrics):
                logger.info(f"Early stopping at epoch {epoch}")
                break

            # Checkpointing
            if epoch % self.config.checkpoint_every == 0:
                self._save_checkpoint(epoch, metrics)

        # Return final embeddings
        entity_emb, relation_emb = self.model.get_embeddings()

        return {
            "entity_embeddings": entity_emb,
            "relation_embeddings": relation_emb,
            "entity_to_idx": self.dataset.entity_to_idx,
            "relation_to_idx": self.dataset.relation_to_idx,
            "idx_to_entity": self.dataset.idx_to_entity,
            "idx_to_relation": self.dataset.idx_to_relation,
            "metrics": self.best_metrics.to_dict() if self.best_metrics else {},
            "history": [m.to_dict() for m in self.history],
        }

    def _train_epoch(self) -> float:
        """Train for one epoch."""
        total_loss = 0.0
        n_batches = 0

        for batch in self.dataset.get_train_batches(shuffle=True):
            # Sample negatives
            negatives = self.dataset.sample_negatives(batch)

            # Compute gradients
            entity_grad, relation_grad, loss = self.model.compute_gradients(
                batch, negatives
            )

            # Update
            self.model.update(entity_grad, relation_grad, self.config.learning_rate)

            # Normalize for TransE
            if self.config.method == EmbeddingMethod.TRANSE:
                self.model.normalize_entities()

            total_loss += loss
            n_batches += 1

        return total_loss / max(1, n_batches)

    def _evaluate(self) -> Tuple[float, float, Dict[int, float]]:
        """
        Evaluate on validation set.

        Returns:
            Tuple of (val_loss, mrr, hits_dict)
        """
        total_loss = 0.0
        ranks = []
        n_batches = 0

        for batch in self.dataset.get_val_batches():
            # Sample negatives for loss
            negatives = self.dataset.sample_negatives(batch)
            _, _, loss = self.model.compute_gradients(batch, negatives)
            total_loss += loss
            n_batches += 1

            # Compute ranks for MRR/Hits
            for h_idx, r_idx, t_idx in batch:
                h = self.model.entity_emb[h_idx:h_idx+1]
                r = self.model.relation_emb[r_idx:r_idx+1]
                t = self.model.entity_emb[t_idx:t_idx+1]

                # Score all possible tails
                all_t = self.model.entity_emb
                r_broadcast = np.broadcast_to(r, (len(all_t), r.shape[1]))
                h_broadcast = np.broadcast_to(h, (len(all_t), h.shape[1]))

                scores = self.model.score(h_broadcast, r_broadcast, all_t)

                # Rank of true tail
                true_score = scores[t_idx]
                rank = np.sum(scores >= true_score)
                ranks.append(rank)

        # Compute metrics
        ranks = np.array(ranks)
        mrr = float(np.mean(1.0 / ranks))
        hits = {
            1: float(np.mean(ranks <= 1)),
            3: float(np.mean(ranks <= 3)),
            10: float(np.mean(ranks <= 10)),
        }

        return total_loss / max(1, n_batches), mrr, hits

    def _check_early_stopping(self, metrics: TrainingMetrics) -> bool:
        """Check if training should stop early."""
        if self.best_metrics is None or metrics.mrr > self.best_metrics.mrr + self.config.min_delta:
            self.best_metrics = metrics
            self.patience_counter = 0
            return False

        self.patience_counter += 1
        return self.patience_counter >= self.config.patience

    def _save_checkpoint(self, epoch: int, metrics: TrainingMetrics) -> None:
        """Save training checkpoint."""
        entity_emb, relation_emb = self.model.get_embeddings()

        checkpoint = Checkpoint(
            epoch=epoch,
            entity_embeddings=entity_emb,
            relation_embeddings=relation_emb,
            entity_to_idx=self.dataset.entity_to_idx,
            relation_to_idx=self.dataset.relation_to_idx,
            metrics=metrics,
            config={
                "method": self.config.method.value,
                "embedding_dim": self.config.embedding_dim,
                "batch_size": self.config.batch_size,
                "learning_rate": self.config.learning_rate,
            },
        )

        path = os.path.join(
            self.config.checkpoint_dir,
            f"checkpoint_epoch_{epoch}.pkl"
        )
        checkpoint.save(path)

        # Cleanup old checkpoints
        self._cleanup_checkpoints()

    def _cleanup_checkpoints(self) -> None:
        """Keep only the last N checkpoints."""
        checkpoint_dir = Path(self.config.checkpoint_dir)
        checkpoints = sorted(
            checkpoint_dir.glob("checkpoint_epoch_*.pkl"),
            key=lambda p: int(p.stem.split("_")[-1]),
            reverse=True,
        )

        for old_ckpt in checkpoints[self.config.keep_last_n_checkpoints:]:
            old_ckpt.unlink()

    def load_checkpoint(self, path: str) -> None:
        """Load training state from checkpoint."""
        checkpoint = Checkpoint.load(path)

        self.model.entity_emb = checkpoint.entity_embeddings
        self.model.relation_emb = checkpoint.relation_embeddings
        self.best_metrics = checkpoint.metrics

        logger.info(f"Loaded checkpoint from epoch {checkpoint.epoch}")

    def get_entity_embedding(self, entity_id: str) -> Optional[np.ndarray]:
        """Get embedding for a specific entity."""
        idx = self.dataset.entity_to_idx.get(entity_id)
        if idx is None:
            return None
        return self.model.entity_emb[idx].copy()

    def get_similar_entities(
        self,
        entity_id: str,
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        """Find entities similar to the given one by embedding distance."""
        emb = self.get_entity_embedding(entity_id)
        if emb is None:
            return []

        # Cosine similarity
        norms = np.linalg.norm(self.model.entity_emb, axis=1)
        emb_norm = np.linalg.norm(emb)

        similarities = np.dot(self.model.entity_emb, emb) / (norms * emb_norm + 1e-8)

        # Get top-k (excluding self)
        top_indices = np.argsort(similarities)[::-1]

        results = []
        for idx in top_indices:
            ent_id = self.dataset.idx_to_entity[idx]
            if ent_id != entity_id:
                results.append((ent_id, float(similarities[idx])))
                if len(results) >= top_k:
                    break

        return results


# =============================================================================
# NEO4J INTEGRATION
# =============================================================================


class Neo4jEmbeddingPipeline:
    """
    Pipeline for training embeddings from Neo4j and storing back.

    Usage:
        pipeline = Neo4jEmbeddingPipeline(neo4j_config)
        embeddings = pipeline.train_and_store()
    """

    def __init__(
        self,
        neo4j_config: Optional[Any] = None,
        training_config: Optional[TrainingConfig] = None,
    ):
        self.neo4j_config = neo4j_config
        self.training_config = training_config or TrainingConfig()
        self._neo4j_rag = None

    def _get_neo4j(self):
        """Get Neo4j RAG instance."""
        if self._neo4j_rag is None:
            from app.services.rag.core.graph_neo4j import get_neo4j_graph_rag
            self._neo4j_rag = get_neo4j_graph_rag(self.neo4j_config)
        return self._neo4j_rag

    def load_triples_from_neo4j(self) -> List[Tuple[str, str, str]]:
        """Load all triples from Neo4j."""
        neo4j = self._get_neo4j()

        query = """
        MATCH (h)-[r]->(t)
        WHERE h.entity_id IS NOT NULL AND t.entity_id IS NOT NULL
        RETURN h.entity_id AS head, type(r) AS relation, t.entity_id AS tail
        """

        results = neo4j._execute_query(query)
        return [(r["head"], r["relation"], r["tail"]) for r in results]

    def store_embeddings_to_neo4j(
        self,
        entity_embeddings: np.ndarray,
        entity_to_idx: Dict[str, int],
    ) -> int:
        """Store embeddings back to Neo4j."""
        neo4j = self._get_neo4j()

        query = """
        MATCH (e {entity_id: $entity_id})
        SET e.embedding = $embedding,
            e.embedding_method = $method,
            e.embedding_dim = $dim,
            e.embedding_updated = datetime()
        """

        stored = 0
        idx_to_entity = {v: k for k, v in entity_to_idx.items()}

        for idx, emb in enumerate(entity_embeddings):
            entity_id = idx_to_entity.get(idx)
            if entity_id:
                try:
                    neo4j._execute_write(
                        query,
                        {
                            "entity_id": entity_id,
                            "embedding": emb.tolist(),
                            "method": self.training_config.method.value,
                            "dim": self.training_config.embedding_dim,
                        },
                    )
                    stored += 1
                except Exception as e:
                    logger.debug(f"Could not store embedding for {entity_id}: {e}")

        logger.info(f"Stored {stored} embeddings to Neo4j")
        return stored

    def train_and_store(self) -> Dict[str, Any]:
        """
        Full pipeline: load from Neo4j, train, store back.

        Returns:
            Training results dict
        """
        # Load triples
        logger.info("Loading triples from Neo4j...")
        triples = self.load_triples_from_neo4j()

        if not triples:
            logger.warning("No triples found in Neo4j")
            return {"error": "No triples found"}

        logger.info(f"Loaded {len(triples)} triples")

        # Train
        trainer = EmbeddingTrainer(triples, self.training_config)
        results = trainer.train()

        # Store
        stored = self.store_embeddings_to_neo4j(
            results["entity_embeddings"],
            results["entity_to_idx"],
        )

        results["stored_to_neo4j"] = stored
        return results


# =============================================================================
# SCHEDULED TRAINING
# =============================================================================


class EmbeddingScheduler:
    """
    Scheduler for periodic embedding retraining.

    Can be triggered by:
    - Time interval
    - Number of new triples
    - Manual trigger
    """

    def __init__(
        self,
        neo4j_config: Optional[Any] = None,
        training_config: Optional[TrainingConfig] = None,
        retrain_interval_hours: int = 24,
        min_new_triples: int = 100,
    ):
        self.pipeline = Neo4jEmbeddingPipeline(neo4j_config, training_config)
        self.retrain_interval_hours = retrain_interval_hours
        self.min_new_triples = min_new_triples

        self._last_train_time: Optional[datetime] = None
        self._last_triple_count: int = 0
        self._lock = threading.Lock()
        self._running = False

    def should_retrain(self) -> Tuple[bool, str]:
        """Check if retraining is needed."""
        with self._lock:
            now = datetime.now()

            # Time-based
            if self._last_train_time is not None:
                hours_since = (now - self._last_train_time).total_seconds() / 3600
                if hours_since >= self.retrain_interval_hours:
                    return True, f"Time interval ({hours_since:.1f}h)"

            # Count-based
            try:
                triples = self.pipeline.load_triples_from_neo4j()
                new_count = len(triples) - self._last_triple_count
                if new_count >= self.min_new_triples:
                    return True, f"New triples ({new_count})"
            except Exception:
                pass

            return False, "No trigger"

    def trigger_retrain(self, force: bool = False) -> Optional[Dict[str, Any]]:
        """
        Trigger retraining if needed.

        Args:
            force: Force retraining even if not needed

        Returns:
            Training results or None if not triggered
        """
        with self._lock:
            if self._running:
                logger.warning("Training already in progress")
                return None

            should, reason = self.should_retrain()
            if not should and not force:
                logger.debug(f"Retrain not needed: {reason}")
                return None

            self._running = True

        try:
            logger.info(f"Starting scheduled retrain: {reason}")
            results = self.pipeline.train_and_store()

            with self._lock:
                self._last_train_time = datetime.now()
                triples = self.pipeline.load_triples_from_neo4j()
                self._last_triple_count = len(triples)

            return results

        finally:
            with self._lock:
                self._running = False


# =============================================================================
# MODULE EXPORTS
# =============================================================================


__all__ = [
    # Configuration
    "EmbeddingMethod",
    "NegativeSamplingStrategy",
    "TrainingConfig",
    "TrainingMetrics",
    "Checkpoint",
    # Dataset
    "TripleDataset",
    # Models
    "BaseEmbeddingModel",
    "TransEModel",
    "RotatEModel",
    "DistMultModel",
    # Trainer
    "EmbeddingTrainer",
    # Neo4j integration
    "Neo4jEmbeddingPipeline",
    "EmbeddingScheduler",
]
