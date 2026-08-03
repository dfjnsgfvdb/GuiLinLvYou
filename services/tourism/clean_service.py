import hashlib
import io
import json
import re
from datetime import datetime

from common.evidence_schema import TourismMinioPrefix, build_tourism_minio_key
from common.minio_util import MinioUtils
from common.mysql_util import MysqlUtil
from services.tourism.schemas import TourismDocument


class CleanService:
    def __init__(self):
        self.minio = MinioUtils()
        self.mysql = MysqlUtil()

    def clean_and_deduplicate(
        self,
        documents: list[TourismDocument],
        task_no: str,
        bucket_name: str = "filedata",
    ) -> tuple[list[TourismDocument], str]:
        seen_hashes: dict[str, str] = {}
        prepared_docs = []
        for item in documents:
            clean_text = self.clean_text(item.content)
            if not clean_text:
                self._delete_unprocessed_raw_row(item.doc_id)
                continue
            clean_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
            if clean_hash in seen_hashes:
                if seen_hashes[clean_hash] != item.doc_id:
                    self._delete_unprocessed_raw_row(item.doc_id)
                continue
            seen_hashes[clean_hash] = item.doc_id
            item.content = clean_text
            item.content_hash = clean_hash
            prepared_docs.append(item)

        existing_doc_ids = self._load_existing_doc_ids([item.content_hash for item in prepared_docs])
        cleaned_docs = []
        clean_records = []
        for item in prepared_docs:
            existing_doc_id = existing_doc_ids.get(item.content_hash)
            if existing_doc_id and existing_doc_id != item.doc_id:
                self._delete_unprocessed_raw_row(item.doc_id)
                continue
            clean_key = build_tourism_minio_key(
                TourismMinioPrefix.CLEAN,
                datetime.now().strftime("%Y/%m"),
                task_no,
                f"{item.doc_id}.txt",
            )
            uploaded_key = self.minio.upload_to_minio_form_stream(
                io.BytesIO(item.content.encode("utf-8")),
                bucket_name,
                clean_key,
            )
            item.clean_minio_key = uploaded_key or clean_key
            cleaned_docs.append(item)
            clean_records.append(
                {"doc_id": item.doc_id, "content": item.content, "clean_minio_key": item.clean_minio_key}
            )

        manifest_key = build_tourism_minio_key(
            TourismMinioPrefix.CLEAN,
            datetime.now().strftime("%Y/%m"),
            task_no,
            "clean_manifest.json",
        )
        self.minio.upload_to_minio_form_stream(
            io.BytesIO(json.dumps(clean_records, ensure_ascii=False).encode("utf-8")),
            bucket_name,
            manifest_key,
        )
        return cleaned_docs, manifest_key

    def _delete_unprocessed_raw_row(self, doc_id: str) -> None:
        self.mysql.update_params(
            "DELETE FROM t_tourism_document WHERE doc_id=%s AND content_hash IS NULL",
            (doc_id,),
        )

    def _load_existing_doc_ids(self, content_hashes: list[str]) -> dict[str, str]:
        if not content_hashes:
            return {}
        placeholders = ", ".join(["%s"] * len(content_hashes))
        rows = self.mysql.query_mysql_dict_params(
            f"SELECT doc_id, content_hash FROM t_tourism_document WHERE content_hash IN ({placeholders})",
            tuple(content_hashes),
        ) or []
        return {
            row["content_hash"]: row["doc_id"]
            for row in rows
            if row.get("content_hash") and row.get("doc_id")
        }

    def update_document_clean_state(self, documents: list[TourismDocument]):
        sql = """
            UPDATE t_tourism_document
            SET clean_minio_key=%s, content_hash=%s, extract_status=%s, update_time=NOW()
            WHERE doc_id=%s
        """
        for item in documents:
            self.mysql.update_params(sql, (item.clean_minio_key, item.content_hash, "pending", item.doc_id))

    @staticmethod
    def clean_text(text: str) -> str:
        text = str(text or "")
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[\u200b-\u200f\ufeff]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
