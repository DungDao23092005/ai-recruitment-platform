from __future__ import annotations

import asyncio
import math
import threading
from typing import Any, Optional

from app.ai.interfaces.base_provider import BaseReranker, RerankCandidate, RerankResult
from app.core.config import settings
from app.core.exceptions import AIError, InvalidDocumentError


# Module-level singleton for CrossEncoder model (lazy, thread-safe)
_cross_encoder_model: Any = None
_cross_encoder_model_lock = threading.Lock()


def _sigmoid(x: float) -> float:
    """Apply sigmoid normalization to convert raw logits to [0, 1] range.

    Handles numerical stability for extreme values.
    """
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        # For negative x, compute exp(x) / (1 + exp(x)) to avoid overflow
        exp_x = math.exp(x)
        return exp_x / (1.0 + exp_x)


def _get_shared_cross_encoder_model(model_name: str | None = None) -> Any:
    """Get the shared CrossEncoder model instance (lazy, thread-safe singleton).

    This function ensures the CrossEncoder model is initialized exactly once
    per process, even under concurrent access.

    Args:
        model_name: The model name to load. Defaults to settings.CROSS_ENCODER_MODEL_NAME.

    Returns:
        The shared CrossEncoder model instance.

    Raises:
        InvalidDocumentError: If sentence-transformers is not installed.
        AIError: If model loading fails.
    """
    global _cross_encoder_model

    # Use default model name from settings if not provided
    model_name = model_name or settings.CROSS_ENCODER_MODEL_NAME

    # Fast path: already initialized
    if _cross_encoder_model is not None:
        return _cross_encoder_model

    # Slow path: need to initialize (with lock for thread safety)
    with _cross_encoder_model_lock:
        # Double-check after acquiring lock
        if _cross_encoder_model is not None:
            return _cross_encoder_model

        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise InvalidDocumentError(
                f"sentence-transformers is not installed: {exc}"
            ) from exc

        try:
            _cross_encoder_model = CrossEncoder(model_name)
        except Exception as exc:
            raise AIError(
                f"Failed to load CrossEncoder model '{model_name}': {exc}"
            ) from exc

    return _cross_encoder_model


def _reset_cross_encoder_model_for_testing() -> None:
    """Reset the shared model for testing purposes.

    WARNING: Only use in tests. Not thread-safe for production use.
    """
    global _cross_encoder_model
    with _cross_encoder_model_lock:
        _cross_encoder_model = None


class CrossEncoderReranker(BaseReranker):
    """Cross-Encoder based reranker using sentence-transformers.

    This is a lightweight local reranker that does not require external API calls.
    Uses a CrossEncoder model to score query-candidate pairs for semantic relevance.

    The CrossEncoder model is shared across all instances via a module-level
    thread-safe singleton. Model is loaded lazily on first use.
    """

    def __init__(
        self,
        model_name: str | None = None,
        max_batch_size: int = 32,
    ) -> None:
        self.model_name = model_name
        self.max_batch_size = max_batch_size

    def _get_model(self) -> Any:
        """Get the shared CrossEncoder model instance."""
        return _get_shared_cross_encoder_model(self.model_name)

    def _build_reranking_text(self, candidate: RerankCandidate) -> str:
        """Build text representation for reranking based on entity type."""
        return candidate.text_for_reranking

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankResult]:
        """Rerank authorized candidates against the query using CrossEncoder.

        Args:
            query: The standalone query for retrieval.
            candidates: List of authorized, SQL-hydrated entities with text for reranking.

        Returns:
            List of RerankResult with entity_id and rerank_score, sorted by score descending.
        """
        if not candidates:
            return []

        model = self._get_model()

        # Build query-candidate pairs for cross-encoder
        pairs = []
        for candidate in candidates:
            candidate_text = self._build_reranking_text(candidate)
            pairs.append([query, candidate_text])

        # Offload blocking PyTorch inference to thread pool to avoid blocking event loop
        def _predict_batches():
            all_scores = []
            for i in range(0, len(pairs), self.max_batch_size):
                batch = pairs[i : i + self.max_batch_size]
                try:
                    batch_scores = model.predict(batch, show_progress_bar=False)
                    all_scores.extend(batch_scores)
                except Exception as exc:
                    raise AIError(f"CrossEncoder prediction failed: {exc}") from exc
            return all_scores

        all_scores = await asyncio.to_thread(_predict_batches)

        # Create results
        results = []
        for candidate, score in zip(candidates, all_scores):
            # Convert numpy float to Python float and apply sigmoid normalization
            # CrossEncoder returns raw logits; normalize to [0, 1] range
            raw_score = float(score)
            rerank_score = _sigmoid(raw_score)
            results.append(RerankResult(entity_id=candidate.entity_id, rerank_score=rerank_score))

        # Sort by rerank score descending
        results.sort(key=lambda r: r.rerank_score, reverse=True)

        return results