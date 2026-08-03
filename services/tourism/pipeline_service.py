import time
from typing import Any

from services.tourism.chunk_service import ChunkService
from services.tourism.clean_service import CleanService
from services.tourism.document_service import TourismDocumentService
from services.tourism.event_cluster_service import EventClusterService
from services.tourism.extraction_service import ExtractionService
from services.tourism.graph_service import GraphService
from services.tourism.index_service import IndexService
from services.tourism.ingest_task import IngestTaskService


class TourismPipelineService:
    def __init__(self):
        self.task_service = IngestTaskService()
        self.document_service = TourismDocumentService()
        self.clean_service = CleanService()
        self.chunk_service = ChunkService()
        self.extraction_service = ExtractionService()
        self.event_cluster_service = EventClusterService()
        self.graph_service = GraphService()
        self.index_service = IndexService()

    async def run_uploaded_file(self, file_data, source_type: str = "manual", created_by: int | str | None = None) -> dict[str, Any]:
        start = time.perf_counter()
        task_no = self.task_service.new_task_no()
        raw_key = self.document_service.save_raw_file(file_data, task_no)
        self.task_service.create_task("pipeline", source_type, file_data.name or "", raw_key, created_by, task_no=task_no)
        task = self.task_service.get_task_by_no(task_no)
        task_id = task["id"] if task else None

        try:
            async with self.task_service.step(task_no, "import") as step:
                records = self.document_service.parse_uploaded_records(file_data)
                documents = self.document_service.build_documents(records, task_id, task_no, raw_key, source_type)
                created_count = self.document_service.create_raw_documents(documents, task_id)
                step["success_count"] = created_count
                step["failed_count"] = max(len(records) - len(documents), 0)

            async with self.task_service.step(task_no, "clean") as step:
                clean_documents, clean_manifest_key = self.clean_service.clean_and_deduplicate(documents, task_no)
                self.clean_service.update_document_clean_state(clean_documents)
                saved_count = len(clean_documents)
                self.task_service.update_clean_key(task_no, clean_manifest_key)
                self.task_service.update_task_counts(
                    task_no,
                    len(records),
                    saved_count,
                    max(len(records) - saved_count, 0),
                )
                step["success_count"] = saved_count
                step["failed_count"] = max(len(documents) - len(clean_documents), 0)

            async with self.task_service.step(task_no, "chunk") as step:
                chunks = self.chunk_service.split_documents(clean_documents)
                self.chunk_service.save_chunks(chunks)
                step["success_count"] = len(chunks)

            async with self.task_service.step(task_no, "extract") as step:
                extractions = self.extraction_service.extract_documents(clean_documents)
                self.extraction_service.update_document_extract_state(clean_documents)
                step["success_count"] = len(extractions)

            async with self.task_service.step(task_no, "cluster") as step:
                events = self.event_cluster_service.cluster_events(clean_documents, extractions)
                self.event_cluster_service.save_events(events)
                step["success_count"] = len(events)

            async with self.task_service.step(task_no, "graph") as step:
                relation_count = self.graph_service.build_graph(clean_documents, events)
                step["success_count"] = relation_count

            async with self.task_service.step(task_no, "index") as step:
                index_result = self.index_service.rebuild_indexes_from_mysql(task_no=task_no)
                index_version = index_result["index_version"]
                step["success_count"] = int(index_result.get("chunk_count") or 0)

            duration_ms = int((time.perf_counter() - start) * 1000)
            self.task_service.finish_task(task_no, "success", "", duration_ms)
            return {
                "task_no": task_no,
                "status": "success",
                "document_count": len(clean_documents),
                "chunk_count": len(chunks),
                "event_count": len(events),
                "index_version": index_version,
                "duration_ms": duration_ms,
            }
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self.task_service.finish_task(task_no, "failed", str(e), duration_ms)
            raise

    async def retry_task(self, task_no: str, created_by: int | str | None = None) -> dict[str, Any]:
        task = self.task_service.get_task_by_no(task_no)
        if not task:
            raise ValueError("任务不存在")
        raw_key = task.get("minio_raw_key")
        file_name = task.get("file_name") or "retry.json"
        if not raw_key:
            raise ValueError("任务缺少原始文件MinIO key，无法重试")
        file_data = self.document_service.load_raw_file(raw_key, file_name)
        return await self.run_uploaded_file(file_data, task.get("source_type") or "manual", created_by)

    async def rebuild_graph(self, created_by: int | str | None = None, clear_existing: bool = False) -> dict[str, Any]:
        start = time.perf_counter()
        task_no = self.task_service.new_task_no()
        self.task_service.create_task("rebuild_graph", "system", "Neo4j graph rebuild", "", created_by, task_no=task_no)
        try:
            async with self.task_service.step(task_no, "graph") as step:
                result = self.graph_service.rebuild_graph_from_mysql(clear_existing=clear_existing)
                step["success_count"] = int(result.get("relation_count") or result.get("node_count") or 0)
                step["failed_count"] = 0 if result.get("status") in {"success", "skipped"} else 1
            duration_ms = int((time.perf_counter() - start) * 1000)
            self.task_service.finish_task(task_no, result.get("status", "success"), result.get("reason", ""), duration_ms)
            return {"task_no": task_no, "duration_ms": duration_ms, **result}
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self.task_service.finish_task(task_no, "failed", str(e), duration_ms)
            raise

    async def rebuild_index(self, created_by: int | str | None = None) -> dict[str, Any]:
        start = time.perf_counter()
        task_no = self.task_service.new_task_no()
        self.task_service.create_task("rebuild_index", "system", "FAISS BM25 index rebuild", "", created_by, task_no=task_no)
        try:
            async with self.task_service.step(task_no, "index") as step:
                result = self.index_service.rebuild_indexes_from_mysql(task_no=task_no)
                step["success_count"] = int(result.get("chunk_count") or 0)
                step["failed_count"] = 0
            duration_ms = int((time.perf_counter() - start) * 1000)
            self.task_service.finish_task(task_no, "success", "", duration_ms)
            return {"task_no": task_no, "duration_ms": duration_ms, **result}
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self.task_service.finish_task(task_no, "failed", str(e), duration_ms)
            raise
