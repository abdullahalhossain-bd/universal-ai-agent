"""
Backward-compatible re-export of the canonical KnowledgeChunk ORM model.

The canonical KnowledgeChunk model lives in app.knowledge.chunk.
"""

from app.knowledge.chunk import KnowledgeChunk

__all__ = ["KnowledgeChunk"]
