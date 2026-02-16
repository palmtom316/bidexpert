from __future__ import annotations


def estimate_knowledge_enhancement_cost(document_count: int) -> dict:
    if document_count <= 0:
        raise ValueError("document_count must be positive")

    scale = document_count / 100.0
    claude_min = round(10.0 * scale, 2)
    claude_max = round(35.0 * scale, 2)
    embedding_max = round(1.0 * scale, 2)

    return {
        "document_count": document_count,
        "claude_enhancement_usd": {"min": claude_min, "max": claude_max},
        "embedding_usd": {"max": embedding_max},
    }
