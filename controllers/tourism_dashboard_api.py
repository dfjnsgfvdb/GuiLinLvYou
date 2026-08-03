from sanic import Blueprint, Request

from common.res_decorator import async_json_resp
from common.token_decorator import check_token
from services.tourism.dashboard_service import TourismDashboardService


bp = Blueprint("tourismDashboardApi", url_prefix="/tourism")
dashboard_service = TourismDashboardService()


@bp.post("/overview", name="tourism_overview")
@check_token
@async_json_resp
async def tourism_overview(_: Request):
    return dashboard_service.overview()


@bp.post("/events/search", name="tourism_events_search")
@check_token
@async_json_resp
async def tourism_events_search(request: Request):
    return dashboard_service.search_events(request.json or {})


@bp.post("/events/detail", name="tourism_event_detail")
@check_token
@async_json_resp
async def tourism_event_detail(request: Request):
    event_id = (request.json or {}).get("event_id")
    if not event_id:
        raise ValueError("event_id 不能为空")
    return dashboard_service.event_detail(event_id)


@bp.post("/graph/overview", name="tourism_graph_overview")
@check_token
@async_json_resp
async def tourism_graph_overview(request: Request):
    return dashboard_service.graph_overview((request.json or {}).get("limit", 80))


@bp.post("/system/status", name="tourism_system_status")
@check_token
@async_json_resp
async def tourism_system_status(_: Request):
    return dashboard_service.system_status()
