import re
from dataclasses import asdict
from typing import Any

from common.evidence_schema import QueryContext


class TourismQueryProcessor:
    """Deterministic preprocessing, intent detection, parameter extraction and expansion."""

    SCENIC_SPOTS = ["漓江", "阳朔西街", "象鼻山", "龙脊梯田", "两江四湖", "遇龙河", "芦笛岩", "靖江王城"]
    LOCATIONS = ["桂林市", "阳朔县", "龙胜县", "秀峰区", "象山区", "七星区", "雁山区"]
    SYNONYMS = {
        "拥堵": ["排队", "客流集中", "人流拥挤"],
        "排队": ["拥堵", "候车", "等候"],
        "投诉": ["差评", "纠纷", "服务问题"],
        "差评": ["投诉", "负面评价"],
        "安全": ["风险", "事故", "隐患"],
        "客流": ["游客量", "人流", "客流集中"],
        "价格": ["收费", "票价", "消费纠纷"],
        "卫生": ["垃圾", "环境", "保洁"],
    }
    STOP_WORDS = {
        "请问", "请", "一下", "如何", "怎么样", "情况", "是否", "什么", "哪些", "目前", "有关",
        "关于", "一下子", "告诉", "分析", "看看", "最近", "现在",
    }

    def process(self, query: str, supplied_filters: Any = None) -> QueryContext:
        normalized = re.sub(r"\s+", " ", str(query or "")).strip()
        keywords = self._keywords(normalized)
        parameters = self._extract_parameters(normalized)
        if supplied_filters:
            filter_values = asdict(supplied_filters) if hasattr(supplied_filters, "__dataclass_fields__") else dict(supplied_filters)
            parameters.update({key: value for key, value in filter_values.items() if value not in (None, "")})
        rewritten = self._rewrite(normalized, keywords, parameters)
        expansions = self._expand(rewritten, keywords)
        return QueryContext(
            original_query=normalized,
            normalized_query=normalized.lower(),
            rewritten_query=rewritten,
            intent=self._detect_intent(normalized),
            parameters=parameters,
            expanded_queries=expansions,
            keywords=keywords,
        )

    def _detect_intent(self, query: str) -> str:
        if any(word in query for word in ["趋势", "变化", "增长", "下降", "对比"]):
            return "opinion_trend"
        if any(word in query for word in ["投诉", "差评", "舆情", "风险", "预警", "事件", "客流", "拥堵"]):
            return "opinion_event"
        if any(word in query for word in ["景区", "景点", "旅游", "游客", "行程", *self.SCENIC_SPOTS]):
            return "tourism_information"
        return "general_knowledge"

    def _extract_parameters(self, query: str) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for spot in self.SCENIC_SPOTS:
            if spot in query:
                params["scenic_spot"] = spot
                break
        for location in self.LOCATIONS:
            if location in query:
                params["location"] = location
                break
        for risk in ["critical", "high", "medium", "low"]:
            if risk in query.lower():
                params["risk_level"] = risk
                break
        if any(word in query for word in ["负面", "差评", "投诉"]):
            params["sentiment"] = "negative"
        elif any(word in query for word in ["好评", "正面"]):
            params["sentiment"] = "positive"
        if any(word in query for word in ["今天", "当前", "现在", "实时"]):
            params["time_scope"] = "realtime"
        elif any(word in query for word in ["最近", "近期", "本周"]):
            params["time_scope"] = "recent"
        return params

    def _rewrite(self, query: str, keywords: list[str], parameters: dict[str, Any]) -> str:
        core = [word for word in keywords if word not in self.STOP_WORDS]
        for key in ["scenic_spot", "location", "sentiment", "risk_level"]:
            value = parameters.get(key)
            if value and value not in core:
                core.append(str(value))
        return " ".join(core) if core else query

    def _expand(self, rewritten: str, keywords: list[str]) -> list[str]:
        expanded = [rewritten]
        synonyms = []
        for keyword in keywords:
            synonyms.extend(self.SYNONYMS.get(keyword, []))
        if synonyms:
            expanded.append(" ".join([rewritten, *dict.fromkeys(synonyms)]))
        return list(dict.fromkeys(item.strip() for item in expanded if item.strip()))[:3]

    @staticmethod
    def _keywords(text: str) -> list[str]:
        try:
            import jieba

            words = jieba.lcut(text)
        except Exception:
            words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", text)
        return list(
            dict.fromkeys(
                word.strip().lower()
                for word in words
                if len(word.strip()) >= 2 and not re.fullmatch(r"[，。！？、；：,.!?\s]+", word)
            )
        )[:20]
