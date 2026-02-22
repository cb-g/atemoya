#!/usr/bin/env python3
"""
Sentence embedding wrapper using sentence-transformers MiniLM.

Provides fast CPU-optimized embeddings for narrative drift detection.

Usage:
    from embed.embedder import Embedder

    embedder = Embedder()
    embeddings = embedder.embed_texts(["text1", "text2"])
"""

import json
from pathlib import Path
from typing import Optional, Union
import numpy as np

from sentence_transformers import SentenceTransformer


# Default model - MiniLM is fast on CPU (22M params)
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder:
    """
    Sentence embedding wrapper.

    Uses MiniLM for fast CPU inference. Embeddings are 384-dimensional.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str = "cpu"):
        """
        Initialize embedder.

        Args:
            model_name: HuggingFace model name
            device: Device to use ("cpu" or "cuda")
        """
        self.model_name = model_name
        self.device = device
        self.model = SentenceTransformer(model_name, device=device)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()

    def embed_texts(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress: bool = False,
        normalize: bool = True,
    ) -> np.ndarray:
        """
        Embed a list of texts.

        Args:
            texts: List of text strings
            batch_size: Batch size for encoding
            show_progress: Show progress bar
            normalize: L2 normalize embeddings (required for cosine similarity)

        Returns:
            numpy array of shape (n_texts, embedding_dim)
        """
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
        )
        return embeddings

    def embed_text(self, text: str, normalize: bool = True) -> np.ndarray:
        """
        Embed a single text.

        Args:
            text: Text string
            normalize: L2 normalize embedding

        Returns:
            numpy array of shape (embedding_dim,)
        """
        return self.embed_texts([text], normalize=normalize)[0]

    def cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.

        Note: If embeddings are already L2-normalized, this is just dot product.

        Args:
            emb1: First embedding
            emb2: Second embedding

        Returns:
            Cosine similarity (-1 to 1)
        """
        return float(np.dot(emb1, emb2))

    def cosine_distance(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Compute cosine distance between two embeddings.

        Args:
            emb1: First embedding
            emb2: Second embedding

        Returns:
            Cosine distance (0 to 2, where 0 = identical)
        """
        return 1.0 - self.cosine_similarity(emb1, emb2)


class DocumentEmbedder:
    """
    Document-level embedding with paragraph and sentence granularity.

    Embeds documents at multiple levels for change detection.
    """

    def __init__(self, embedder: Optional[Embedder] = None):
        """
        Initialize document embedder.

        Args:
            embedder: Embedder instance (creates new one if None)
        """
        self.embedder = embedder or Embedder()

    def embed_document(
        self,
        text: str,
        ticker: str,
        filing_date: str,
        section: str,
        paragraph_min_length: int = 100,
    ) -> dict:
        """
        Embed a document at paragraph level.

        Args:
            text: Document text
            ticker: Stock ticker
            filing_date: Filing date
            section: Section type (mda, risk_factors, etc.)
            paragraph_min_length: Minimum paragraph length to include

        Returns:
            Dict with document metadata and embeddings
        """
        import re

        # Split into paragraphs
        paragraphs = re.split(r'\n\n+', text)
        paragraphs = [p.strip() for p in paragraphs if len(p.strip()) >= paragraph_min_length]

        if not paragraphs:
            return {
                "ticker": ticker,
                "filing_date": filing_date,
                "section": section,
                "paragraph_count": 0,
                "paragraphs": [],
                "document_embedding": None,
            }

        # Embed paragraphs
        embeddings = self.embedder.embed_texts(paragraphs, show_progress=False)

        # Compute document-level embedding (mean of paragraphs)
        doc_embedding = np.mean(embeddings, axis=0)
        doc_embedding = doc_embedding / np.linalg.norm(doc_embedding)  # L2 normalize

        # Build paragraph data
        paragraph_data = []
        for i, (para, emb) in enumerate(zip(paragraphs, embeddings)):
            paragraph_data.append({
                "index": i,
                "text": para,
                "word_count": len(para.split()),
                "embedding": emb,
            })

        return {
            "ticker": ticker,
            "filing_date": filing_date,
            "section": section,
            "paragraph_count": len(paragraphs),
            "paragraphs": paragraph_data,
            "document_embedding": doc_embedding,
        }

    def save_embeddings(self, embedded_doc: dict, output_path: Path):
        """
        Save embedded document to disk.

        Saves metadata as JSON and embeddings as numpy arrays.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Extract embeddings
        doc_emb = embedded_doc.get("document_embedding")
        para_embs = [p["embedding"] for p in embedded_doc.get("paragraphs", [])]

        # Save metadata (without embeddings)
        metadata = {
            "ticker": embedded_doc.get("ticker"),
            "filing_date": embedded_doc.get("filing_date"),
            "section": embedded_doc.get("section"),
            "paragraph_count": embedded_doc.get("paragraph_count"),
            "paragraphs": [
                {"index": p["index"], "text": p["text"], "word_count": p["word_count"]}
                for p in embedded_doc.get("paragraphs", [])
            ],
        }

        json_path = output_path.with_suffix(".json")
        with open(json_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Save embeddings
        if doc_emb is not None:
            np.save(output_path.with_suffix(".doc.npy"), doc_emb)

        if para_embs:
            np.save(output_path.with_suffix(".para.npy"), np.array(para_embs))

    def load_embeddings(self, input_path: Path) -> dict:
        """
        Load embedded document from disk.

        Returns dict with metadata and embeddings.
        """
        input_path = Path(input_path)

        # Load metadata
        json_path = input_path.with_suffix(".json")
        with open(json_path) as f:
            metadata = json.load(f)

        # Load embeddings
        doc_emb_path = input_path.with_suffix(".doc.npy")
        para_emb_path = input_path.with_suffix(".para.npy")

        doc_emb = None
        if doc_emb_path.exists():
            doc_emb = np.load(doc_emb_path)

        para_embs = None
        if para_emb_path.exists():
            para_embs = np.load(para_emb_path)

        # Reconstruct embedded doc
        embedded_doc = {
            **metadata,
            "document_embedding": doc_emb,
        }

        if para_embs is not None:
            for i, para in enumerate(embedded_doc.get("paragraphs", [])):
                if i < len(para_embs):
                    para["embedding"] = para_embs[i]

        return embedded_doc


def compute_centroid(
    embeddings: list[np.ndarray],
    weights: Optional[list[float]] = None,
) -> np.ndarray:
    """
    Compute weighted centroid of embeddings.

    Args:
        embeddings: List of embedding arrays
        weights: Optional weights (e.g., for recency weighting)

    Returns:
        Centroid embedding (L2 normalized)
    """
    if not embeddings:
        raise ValueError("No embeddings provided")

    emb_array = np.array(embeddings)

    if weights is not None:
        weights = np.array(weights)
        weights = weights / weights.sum()  # Normalize weights
        centroid = np.average(emb_array, axis=0, weights=weights)
    else:
        centroid = np.mean(emb_array, axis=0)

    # L2 normalize
    centroid = centroid / np.linalg.norm(centroid)
    return centroid


def exponential_decay_weights(n: int, decay_rate: float = 0.1) -> list[float]:
    """
    Generate exponential decay weights (most recent = highest weight).

    Args:
        n: Number of items
        decay_rate: Decay rate per period

    Returns:
        List of weights (most recent first, sums to 1)
    """
    weights = [np.exp(-decay_rate * i) for i in range(n)]
    total = sum(weights)
    return [w / total for w in weights]


if __name__ == "__main__":
    # Quick test
    print("Testing embedder...")

    embedder = Embedder()
    print(f"Model: {embedder.model_name}")
    print(f"Embedding dim: {embedder.embedding_dim}")

    texts = [
        "Revenue increased 15% year over year driven by strong demand.",
        "We expect continued growth in the coming quarters.",
        "Facing headwinds from supply chain constraints.",
    ]

    embeddings = embedder.embed_texts(texts, show_progress=True)
    print(f"Embedded {len(texts)} texts, shape: {embeddings.shape}")

    # Test similarity
    sim_01 = embedder.cosine_similarity(embeddings[0], embeddings[1])
    sim_02 = embedder.cosine_similarity(embeddings[0], embeddings[2])
    print(f"Similarity (0,1): {sim_01:.3f}")
    print(f"Similarity (0,2): {sim_02:.3f}")
