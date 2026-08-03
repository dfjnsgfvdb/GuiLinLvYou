import logging
import math
import os
from typing import Iterable

import httpx
import numpy as np
from openai import OpenAI

logger = logging.getLogger(__name__)


class EmbeddingService:
    """OpenAI-compatible semantic embedding client.

    The project uses DashScope/OpenAI-compatible endpoints elsewhere, so the
    embedding path follows the same configuration style. Hash vectors are kept
    only as an explicit local fallback for development.
    """

    def __init__(self):
        self.model_name = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4")
        self.base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv(
            "MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("MODEL_API_KEY")
        self.batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
        self.fallback_enabled = os.getenv("EMBEDDING_ENABLE_HASH_FALLBACK", "false").lower() == "true"
        self.fallback_dim = int(os.getenv("EMBEDDING_FALLBACK_DIM", "384"))
        self.client = (
            OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=httpx.Client(trust_env=False),
            )
            if self.api_key
            else None
        )

    def embed_documents(self, texts: Iterable[str]) -> np.ndarray:
        text_list = [self._normalize_text(text) for text in texts]
        if not text_list:
            return np.zeros((0, self.fallback_dim), dtype="float32")
        if not self.client:
            if self.fallback_enabled:
                logger.warning("Embedding API key is missing; using hash fallback.")
                return self._hash_embeddings(text_list)
            raise RuntimeError("缺少 EMBEDDING_API_KEY 或 MODEL_API_KEY，无法生成语义向量。")

        vectors: list[list[float]] = []
        try:
            for start in range(0, len(text_list), self.batch_size):
                batch = text_list[start : start + self.batch_size]
                response = self.client.embeddings.create(model=self.model_name, input=batch)
                ordered = sorted(response.data, key=lambda item: item.index)
                vectors.extend(item.embedding for item in ordered)
            embeddings = np.array(vectors, dtype="float32")
            self._normalize_l2(embeddings)
            return embeddings
        except Exception as exc:
            if self.fallback_enabled:
                logger.warning("Embedding service failed; using hash fallback: %s", exc, exc_info=True)
                return self._hash_embeddings(text_list)
            raise RuntimeError(f"语义向量生成失败: {exc}") from exc

    def embed_query(self, text: str) -> np.ndarray:
        embeddings = self.embed_documents([text])
        if embeddings.size == 0:
            return np.zeros(self.fallback_dim, dtype="float32")
        return embeddings[0]

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = str(text or "").strip()
        return text if text else " "

    @staticmethod
    def _normalize_l2(embeddings: np.ndarray) -> None:
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embeddings /= norms

    def _hash_embeddings(self, texts: list[str]) -> np.ndarray:
        vectors = np.array([self._hash_embed(text) for text in texts], dtype="float32")
        self._normalize_l2(vectors)
        return vectors

    def _hash_embed(self, text: str) -> np.ndarray:
        import hashlib

        vector = np.zeros(self.fallback_dim, dtype="float32")
        for token in text:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            vector[int(digest[:8], 16) % self.fallback_dim] += 1.0
        norm = math.sqrt(float(np.dot(vector, vector)))
        return vector / norm if norm else vector
