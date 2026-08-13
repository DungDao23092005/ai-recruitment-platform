from __future__ import annotations


def compute_cosine_similarity(
    vec1: list[float] | None,
    vec2: list[float] | None,
) -> float:
    """Compute cosine similarity between two vectors.

    Malformed inputs (empty, mismatched dimensions, zero magnitude)
    degrade to 0.0 instead of raising.
    """
    if not vec1 or not vec2:
        return 0.0

    if len(vec1) != len(vec2):
        return 0.0

    dot_product = 0.0
    magnitude1 = 0.0
    magnitude2 = 0.0
    for a, b in zip(vec1, vec2):
        dot_product += a * b
        magnitude1 += a * a
        magnitude2 += b * b

    if magnitude1 == 0.0 or magnitude2 == 0.0:
        return 0.0

    similarity = dot_product / ((magnitude1 ** 0.5) * (magnitude2 ** 0.5))
    return max(0.0, min(1.0, similarity))
