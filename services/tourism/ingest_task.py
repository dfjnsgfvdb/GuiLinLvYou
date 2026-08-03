import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from common.mysql_util import MysqlUtil


class IngestTaskService:
    def __init__(self):
        self.mysql = MysqlUtil()

    @staticmethod
    def new_task_no() -> str:
        return f"tourism_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def create_task(
        self,
        task_type: str,
        source_type: str,
        file_name: str,
        minio_raw_key: str,
        created_by: int | str | None,
        task_no: str | None = None,
    ) -> str:
        task_no = task_no or self.new_task_no()
        sql = """
            INSERT INTO t_tourism_ingest_task
            (task_no, task_type, source_type, file_name, minio_raw_key, status, created_by, started_at, step_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """
        self.mysql.insert(
            sql,
            (
                task_no,
                task_type,
                source_type,
                file_name,
                minio_raw_key,
                "running",
                created_by,
                json.dumps({}, ensure_ascii=False),
            ),
        )
        return task_no

    def get_task_by_no(self, task_no: str) -> dict[str, Any] | None:
        rows = self.mysql.query_mysql_dict_params(
            "SELECT * FROM t_tourism_ingest_task WHERE task_no=%s",
            (task_no,),
        )
        return rows[0] if rows else None

    def list_tasks(self, page: int = 1, limit: int = 20) -> dict[str, Any]:
        offset = max(page - 1, 0) * limit
        records = self.mysql.query_mysql_dict_params(
            """
            SELECT * FROM t_tourism_ingest_task
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        total = self.mysql.query_mysql_dict("SELECT COUNT(1) AS count FROM t_tourism_ingest_task")[0]["count"]
        return {"records": records, "total": total, "page": page, "limit": limit}

    def update_task_counts(self, task_no: str, total_count: int, success_count: int, failed_count: int):
        self.mysql.update_params(
            """
            UPDATE t_tourism_ingest_task
            SET total_count=%s, success_count=%s, failed_count=%s
            WHERE task_no=%s
            """,
            (total_count, success_count, failed_count, task_no),
        )

    def update_clean_key(self, task_no: str, clean_key: str):
        self.mysql.update_params(
            "UPDATE t_tourism_ingest_task SET minio_clean_key=%s WHERE task_no=%s",
            (clean_key, task_no),
        )

    def finish_task(self, task_no: str, status: str, error_message: str = "", duration_ms: int = 0):
        self.mysql.update_params(
            """
            UPDATE t_tourism_ingest_task
            SET status=%s, error_message=%s, duration_ms=%s, finished_at=NOW()
            WHERE task_no=%s
            """,
            (status, error_message, duration_ms, task_no),
        )

    def record_step(
        self,
        task_no: str,
        step_name: str,
        status: str,
        success_count: int = 0,
        failed_count: int = 0,
        duration_ms: int = 0,
        error_message: str = "",
    ):
        task = self.get_task_by_no(task_no)
        current = {}
        if task and task.get("step_status"):
            try:
                current = json.loads(task["step_status"]) if isinstance(task["step_status"], str) else task["step_status"]
            except Exception:
                current = {}
        current[step_name] = {
            "status": status,
            "success_count": success_count,
            "failed_count": failed_count,
            "duration_ms": duration_ms,
            "error_message": error_message,
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.mysql.update_params(
            "UPDATE t_tourism_ingest_task SET step_status=%s WHERE task_no=%s",
            (json.dumps(current, ensure_ascii=False), task_no),
        )

    @asynccontextmanager
    async def step(self, task_no: str, step_name: str):
        start = time.perf_counter()
        self.record_step(task_no, step_name, "running")
        try:
            result = {"success_count": 0, "failed_count": 0}
            yield result
            self.record_step(
                task_no,
                step_name,
                "success",
                int(result.get("success_count", 0)),
                int(result.get("failed_count", 0)),
                int((time.perf_counter() - start) * 1000),
            )
        except Exception as e:
            self.record_step(
                task_no,
                step_name,
                "failed",
                0,
                1,
                int((time.perf_counter() - start) * 1000),
                str(e),
            )
            raise
