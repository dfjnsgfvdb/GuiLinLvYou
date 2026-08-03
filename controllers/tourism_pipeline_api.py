from sanic import Blueprint, Request

from common.res_decorator import async_json_resp
from common.token_decorator import check_token
from services.tourism.ingest_task import IngestTaskService
from services.tourism.pipeline_service import TourismPipelineService

bp = Blueprint("tourismPipelineApi", url_prefix="/tourism/pipeline")

pipeline_service = TourismPipelineService()
task_service = IngestTaskService()


@bp.post("/upload", name="tourism_pipeline_upload")
@check_token
@async_json_resp
async def upload_tourism_data(request: Request):
    file_data = request.files.get("file")
    if not file_data:
        raise ValueError("请上传 CSV、JSON 或 JSONL 文件")
    source_type = request.form.get("source_type") or request.args.get("source_type") or "manual"
    user_payload = getattr(request.ctx, "user_payload", {}) or {}
    return await pipeline_service.run_uploaded_file(file_data, source_type, user_payload.get("id"))


@bp.post("/task/list", name="tourism_pipeline_task_list")
@check_token
@async_json_resp
async def list_tourism_tasks(request: Request):
    page = int((request.json or {}).get("page", 1))
    limit = int((request.json or {}).get("limit", 20))
    return task_service.list_tasks(page, limit)


@bp.post("/task/detail", name="tourism_pipeline_task_detail")
@check_token
@async_json_resp
async def get_tourism_task(request: Request):
    task_no = (request.json or {}).get("task_no")
    if not task_no:
        raise ValueError("task_no不能为空")
    return task_service.get_task_by_no(task_no)


@bp.post("/task/retry", name="tourism_pipeline_task_retry")
@check_token
@async_json_resp
async def retry_tourism_task(request: Request):
    task_no = (request.json or {}).get("task_no")
    if not task_no:
        raise ValueError("task_no不能为空")
    user_payload = getattr(request.ctx, "user_payload", {}) or {}
    return await pipeline_service.retry_task(task_no, user_payload.get("id"))


@bp.post("/rebuild_graph", name="tourism_pipeline_rebuild_graph")
@check_token
@async_json_resp
async def rebuild_tourism_graph(request: Request):
    user_payload = getattr(request.ctx, "user_payload", {}) or {}
    clear_existing = bool((request.json or {}).get("clear_existing", False))
    return await pipeline_service.rebuild_graph(user_payload.get("id"), clear_existing=clear_existing)


@bp.post("/rebuild_index", name="tourism_pipeline_rebuild_index")
@check_token
@async_json_resp
async def rebuild_tourism_index(request: Request):
    user_payload = getattr(request.ctx, "user_payload", {}) or {}
    return await pipeline_service.rebuild_index(user_payload.get("id"))
