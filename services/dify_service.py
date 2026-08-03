import json
import logging

from agent.tourism.tourism_agent import TourismOpinionAgent
from common.exception import MyException
from constants.code_enum import DiFyAppEnum, SysCodeEnum
from services.user_service import decode_jwt_token


logger = logging.getLogger(__name__)
tourism_agent = TourismOpinionAgent()


class DiFyRequest:
    """SSE request adapter retained for frontend API compatibility."""

    async def exec_query(self, response):
        request = response.request
        try:
            payload = json.loads(request.body.decode("utf-8"))
            query = (payload.get("query") or "").strip()
            if not query:
                raise ValueError("query 不能为空")

            qa_type = payload.get("qa_type") or DiFyAppEnum.TOURISM_QA.value[0]
            if qa_type != DiFyAppEnum.TOURISM_QA.value[0]:
                raise ValueError("当前项目仅支持桂林旅游舆情问答")

            token = request.headers.get("Authorization")
            if not token:
                raise MyException(SysCodeEnum.c_401)
            if token.startswith("Bearer "):
                token = token.split(" ", 1)[1]

            await tourism_agent.run_agent(
                query,
                response,
                payload.get("chat_id"),
                payload.get("uuid"),
                token,
                payload.get("file_list") or [],
            )
        except Exception:
            logger.exception("Tourism opinion SSE request failed")
            raise


async def query_dify_suggested(_chat_id):
    return []


async def stop_dify_chat(request, task_id, qa_type) -> dict:
    if qa_type != DiFyAppEnum.TOURISM_QA.value[0]:
        return {"success": False, "message": "不支持的问答类型"}

    token = request.headers.get("Authorization")
    if not token:
        raise MyException(SysCodeEnum.c_401)
    if token.startswith("Bearer "):
        token = token.split(" ", 1)[1]
    user = await decode_jwt_token(token)
    if not isinstance(user, dict) or not user.get("id"):
        raise MyException(SysCodeEnum.c_401)

    success = await tourism_agent.cancel_task(task_id, user["id"])
    return {"success": success, "message": "任务已停止" if success else "未找到运行中的任务"}
