"""Embedding utilities for narrative drift detection."""

from .embedder import (
    Embedder,
    DocumentEmbedder,
    compute_centroid,
    exponential_decay_weights,
)

__all__ = [
    "Embedder",
    "DocumentEmbedder",
    "compute_centroid",
    "exponential_decay_weights",
]
