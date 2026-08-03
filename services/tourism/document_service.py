import csv
import hashlib
import io
import json
from types import SimpleNamespace
from datetime import datetime
from typing import Any

from common.evidence_schema import TourismMinioPrefix, build_tourism_minio_key
from common.minio_util import MinioUtils
from common.mysql_util import MysqlUtil
from services.tourism.schemas import TourismDocument


class TourismDocumentService:
    TEXT_FIELDS = ["content", "text", "正文", "内容", "comment", "评论", "description"]
    TITLE_FIELDS = ["title", "标题", "name", "事件名称"]
    SOURCE_FIELDS = ["source", "source_name", "platform", "来源", "平台"]
    URL_FIELDS = ["url", "source_url", "link", "链接"]
    TIME_FIELDS = ["publish_time", "time", "发布时间", "created_at", "create_time"]

    def __init__(self):
        self.mysql = MysqlUtil()
        self.minio = MinioUtils()

    def save_raw_file(self, file_data, task_no: str, bucket_name: str = "filedata") -> str:
        file_name = file_data.name or f"{task_no}.json"
        key = build_tourism_minio_key(TourismMinioPrefix.RAW, datetime.now().strftime("%Y/%m"), task_no, file_name)
        return self.minio.upload_to_minio_form_stream(io.BytesIO(file_data.body), bucket_name, key)

    def load_raw_file(self, object_key: str, file_name: str, bucket_name: str = "filedata"):
        response = self.minio.client.get_object(bucket_name, object_key)
        try:
            body = response.read()
        finally:
            response.close()
            response.release_conn()
        return SimpleNamespace(name=file_name, body=body)

    def parse_uploaded_records(self, file_data) -> list[dict[str, Any]]:
        file_name = (file_data.name or "").lower()
        body = file_data.body
        if file_name.endswith(".csv"):
            return self._parse_csv(body)
        if file_name.endswith(".json") or file_name.endswith(".jsonl"):
            return self._parse_json(body, jsonl=file_name.endswith(".jsonl"))
        raise ValueError("仅支持 CSV、JSON、JSONL 文件")

    def build_documents(
        self,
        records: list[dict[str, Any]],
        task_id: int | None,
        task_no: str,
        raw_minio_key: str,
        source_type: str,
    ) -> list[TourismDocument]:
        documents = []
        for index, record in enumerate(records):
            content = self._first_value(record, self.TEXT_FIELDS)
            if not content:
                continue
            title = self._first_value(record, self.TITLE_FIELDS) or content[:50]
            source_name = self._first_value(record, self.SOURCE_FIELDS) or source_type or "unknown"
            source_url = self._first_value(record, self.URL_FIELDS)
            publish_time = self._parse_datetime(self._first_value(record, self.TIME_FIELDS))
            raw_hash = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
            doc_id = f"doc_{raw_hash[:32]}"
            documents.append(
                TourismDocument(
                    doc_id=doc_id,
                    title=str(title),
                    content=str(content),
                    source_type=source_type or "manual",
                    source_name=str(source_name),
                    source_url=str(source_url or ""),
                    author_name=str(record.get("author") or record.get("作者") or ""),
                    publish_time=publish_time,
                    raw_minio_key=raw_minio_key,
                    content_hash="",
                    metadata={
                        "task_no": task_no,
                        "task_id": task_id,
                        "row_index": index,
                        "raw_hash": raw_hash,
                        "raw_record": record,
                    },
                )
            )
        return documents

    def create_raw_documents(self, documents: list[TourismDocument], task_id: int | None = None) -> int:
        """Create document rows immediately after raw import, before cleaning and content-hash deduplication."""
        if not documents:
            return 0
        sql = """
            INSERT INTO t_tourism_document
            (doc_id, task_id, title, content_hash, source_type, source_name, source_url, author_name,
             publish_time, raw_minio_key, language, sentiment, sentiment_score,
             extract_status, graph_status, index_status)
            VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              task_id=VALUES(task_id), title=VALUES(title), source_type=VALUES(source_type),
              source_name=VALUES(source_name), source_url=VALUES(source_url),
              author_name=VALUES(author_name), publish_time=VALUES(publish_time),
              raw_minio_key=VALUES(raw_minio_key), update_time=NOW()
        """
        data = [
            (
                item.doc_id, task_id, item.title, item.source_type, item.source_name,
                item.source_url, item.author_name, item.publish_time, item.raw_minio_key,
                "zh", item.sentiment, item.sentiment_score, "raw", "pending", "pending",
            )
            for item in documents
        ]
        self.mysql.batch_insert(sql, data)
        return len(data)

    def save_documents(self, documents: list[TourismDocument], task_id: int | None = None) -> int:
        if not documents:
            return 0
        sql = """
            INSERT INTO t_tourism_document
            (doc_id, task_id, title, content_hash, source_type, source_name, source_url, author_name,
             publish_time, raw_minio_key, clean_minio_key, language, sentiment, sentiment_score,
             extract_status, graph_status, index_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              title=VALUES(title),
              source_type=VALUES(source_type),
              source_name=VALUES(source_name),
              source_url=VALUES(source_url),
              author_name=VALUES(author_name),
              publish_time=VALUES(publish_time),
              raw_minio_key=VALUES(raw_minio_key),
              clean_minio_key=VALUES(clean_minio_key),
              content_hash=VALUES(content_hash)
        """
        data = [
            (
                item.doc_id,
                task_id,
                item.title,
                item.content_hash,
                item.source_type,
                item.source_name,
                item.source_url,
                item.author_name,
                item.publish_time,
                item.raw_minio_key,
                item.clean_minio_key,
                "zh",
                item.sentiment,
                item.sentiment_score,
                "pending",
                "pending",
                "pending",
            )
            for item in documents
        ]
        self.mysql.batch_insert(sql, data)
        return len(data)

    @staticmethod
    def _parse_csv(body: bytes) -> list[dict[str, Any]]:
        last_error = None
        for encoding in ["utf-8-sig", "utf-8", "gbk", "gb2312"]:
            try:
                text = body.decode(encoding)
                reader = csv.DictReader(io.StringIO(text))
                return [dict(row) for row in reader]
            except UnicodeDecodeError as e:
                last_error = e
        raise ValueError(f"CSV 编码识别失败: {last_error}")

    @staticmethod
    def _parse_json(body: bytes, jsonl: bool = False) -> list[dict[str, Any]]:
        text = body.decode("utf-8-sig")
        if jsonl:
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ["records", "data", "items", "list"]:
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        raise ValueError("JSON 须为对象、数组或包含 records/data/items/list 数组的对象")

    @staticmethod
    def _first_value(record: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return value
        return ""

    @staticmethod
    def _parse_datetime(value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        value = str(value).strip()
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"]:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None
