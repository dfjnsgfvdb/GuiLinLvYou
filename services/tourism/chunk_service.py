import hashlib
import re

from common.mysql_util import MysqlUtil
from services.tourism.schemas import TourismChunk, TourismDocument


class ChunkService:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 80):
        self.chunk_size = max(int(chunk_size), 1)
        self.chunk_overlap = max(0, min(int(chunk_overlap), self.chunk_size - 1))
        self.mysql = MysqlUtil()

    def split_documents(self, documents: list[TourismDocument]) -> list[TourismChunk]:
        chunks = []
        for doc in documents:
            parts = self._split_text(doc.content)
            for index, content in enumerate(parts):
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                chunks.append(
                    TourismChunk(
                        chunk_id=f"chk_{doc.doc_id}_{index}",
                        doc_id=doc.doc_id,
                        chunk_index=index,
                        content=content,
                        content_hash=content_hash,
                        token_count=len(content),
                        char_count=len(content),
                        content_preview=content[:1000],
                    )
                )
        return chunks

    def save_chunks(self, chunks: list[TourismChunk], embedding_model: str = "hashing-384", index_version: str = "") -> int:
        if not chunks:
            return 0
        sql = """
            INSERT INTO t_tourism_chunk
            (chunk_id, doc_id, chunk_index, content_hash, content_preview, token_count, char_count,
             embedding_model, index_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              content_hash=VALUES(content_hash),
              content_preview=VALUES(content_preview),
              token_count=VALUES(token_count),
              char_count=VALUES(char_count),
              embedding_model=VALUES(embedding_model),
              index_version=VALUES(index_version)
        """
        self.mysql.batch_insert(
            sql,
            [
                (
                    item.chunk_id,
                    item.doc_id,
                    item.chunk_index,
                    item.content_hash,
                    item.content_preview,
                    item.token_count,
                    item.char_count,
                    embedding_model,
                    index_version,
                )
                for item in chunks
            ],
        )
        return len(chunks)

    def _split_text(self, text: str) -> list[str]:
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?；;])", text) if item.strip()]
        chunks = []
        current = ""
        for sentence in sentences or [text]:
            remaining = sentence
            while remaining:
                capacity = self.chunk_size - len(current)
                if capacity <= 0:
                    chunks.append(current)
                    current = current[-self.chunk_overlap :] if self.chunk_overlap else ""
                    capacity = self.chunk_size - len(current)
                current += remaining[:capacity]
                remaining = remaining[capacity:]
        if current:
            chunks.append(current)
        return chunks
