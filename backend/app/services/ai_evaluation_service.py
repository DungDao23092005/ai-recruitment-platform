from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

RelevanceLabel = Literal["relevant", "partially_relevant", "not_relevant"]


@dataclass
class EvaluationSample:
    candidate_id: str
    job_id: str
    relevance: RelevanceLabel


@dataclass
class EvaluationMetrics:
    precision_at_k: float
    recall_at_k: float
    f1_score: float
    mrr: float
    ndcg_at_k: float


class AIEvaluationService:
    """Offline evaluation utilities for the AI Matching Engine."""

    def __init__(self, k: int = 10):
        self.k = k

    def _get_relevance_score(self, label: RelevanceLabel) -> float:
        if label == "relevant":
            return 1.0
        if label == "partially_relevant":
            return 0.5
        return 0.0

    def evaluate(
        self,
        ground_truth: list[EvaluationSample],
        predictions: list[str],  # Ordered list of retrieved candidate_ids or job_ids
    ) -> EvaluationMetrics:
        """
        Evaluate a single ranked list of predictions against ground truth labels.
        Predictions is a ranked list of IDs.
        """
        predictions_k = predictions[:self.k]

        # Build lookup for ground truth relevance
        truth_lookup = {sample.candidate_id: self._get_relevance_score(sample.relevance)
                       for sample in ground_truth}

        # Precision@K
        relevant_retrieved = sum(1 for pid in predictions_k if truth_lookup.get(pid, 0.0) >= 0.5)
        precision = relevant_retrieved / self.k if self.k > 0 else 0.0

        # Recall@K
        total_relevant = sum(1 for sample in ground_truth if self._get_relevance_score(sample.relevance) >= 0.5)
        recall = relevant_retrieved / total_relevant if total_relevant > 0 else 0.0

        # F1
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        # MRR
        mrr = 0.0
        for i, pid in enumerate(predictions):
            if truth_lookup.get(pid, 0.0) >= 0.5:
                mrr = 1.0 / (i + 1)
                break

        # NDCG@K
        dcg = 0.0
        for i, pid in enumerate(predictions_k):
            rel = truth_lookup.get(pid, 0.0)
            dcg += (2**rel - 1) / math.log2(i + 2)

        # IDCG@K (Ideal DCG)
        ideal_rels = sorted(truth_lookup.values(), reverse=True)[:self.k]
        idcg = 0.0
        for i, rel in enumerate(ideal_rels):
            idcg += (2**rel - 1) / math.log2(i + 2)

        ndcg = (dcg / idcg) if idcg > 0 else 0.0

        return EvaluationMetrics(
            precision_at_k=precision,
            recall_at_k=recall,
            f1_score=f1,
            mrr=mrr,
            ndcg_at_k=ndcg
        )