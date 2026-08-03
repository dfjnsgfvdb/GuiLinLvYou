import json
import logging
import os
import re

import httpx
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from common.mysql_util import MysqlUtil
from services.tourism.entity_normalize_service import EntityNormalizeService
from services.tourism.schemas import ExtractedOpinion, TourismDocument

logger = logging.getLogger(__name__)


class TourismOpinionExtraction(BaseModel):
    event_type: str = Field(description="事件类型")
    summary: str = Field(description="不超过120字的事件摘要")
    sentiment: str = Field(description="positive/neutral/negative")
    sentiment_score: float = Field(ge=0.0, le=1.0)
    topic: str = Field(description="舆情主题")
    scenic_spots: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list, max_length=10)


class ExtractionService:
    NEGATIVE_WORDS = ["投诉", "宰客", "排队", "拥堵", "差评", "退票", "价格高", "服务差", "脏乱", "安全", "纠纷"]
    POSITIVE_WORDS = ["满意", "推荐", "好评", "漂亮", "方便", "热情", "值得", "舒适"]
    EVENT_TYPES = {
        "交通拥堵": ["拥堵", "堵车", "停车难", "交通"],
        "价格争议": ["宰客", "价格", "收费", "门票", "加价"],
        "服务投诉": ["投诉", "服务差", "态度", "退票", "纠纷"],
        "安全风险": ["安全", "摔倒", "事故", "落水", "受伤"],
        "环境卫生": ["卫生", "脏乱", "垃圾", "异味"],
        "游览体验": ["排队", "拥挤", "体验", "预约", "限流"],
    }

    def __init__(self):
        self.normalizer = EntityNormalizeService()
        self.mysql = MysqlUtil()
        self.llm_enabled = os.getenv("TOURISM_EXTRACTION_LLM_ENABLED", "true").lower() == "true"
        self.llm_model = os.getenv("TOURISM_EXTRACTION_MODEL_NAME") or os.getenv("MODEL_NAME", "qwen-plus")
        self.llm_base_url = os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.llm_api_key = os.getenv("MODEL_API_KEY")
        self.llm_max_chars = int(os.getenv("TOURISM_EXTRACTION_MAX_CHARS", "2500"))
        self.llm_client = (
            OpenAI(
                api_key=self.llm_api_key,
                base_url=self.llm_base_url,
                http_client=httpx.Client(trust_env=False),
            )
            if self.llm_api_key
            else None
        )

    def extract_documents(self, documents: list[TourismDocument]) -> list[ExtractedOpinion]:
        results = []
        for doc in documents:
            rule_result = self._rule_extract(doc)
            extracted = self._llm_extract(doc, rule_result) or rule_result
            results.append(
                ExtractedOpinion(
                    doc_id=doc.doc_id,
                    event_type=extracted.event_type,
                    summary=extracted.summary,
                    sentiment=extracted.sentiment,
                    sentiment_score=extracted.sentiment_score,
                    topic=extracted.topic,
                    scenic_spots=extracted.scenic_spots,
                    locations=extracted.locations,
                    keywords=extracted.keywords,
                )
            )
            doc.sentiment = extracted.sentiment
            doc.sentiment_score = extracted.sentiment_score
        return results

    def _rule_extract(self, doc: TourismDocument) -> TourismOpinionExtraction:
        scenic_spots = self.normalizer.find_scenic_spots(doc.content)
        locations = self.normalizer.find_locations(doc.content)
        sentiment, sentiment_score = self._detect_sentiment(doc.content)
        event_type = self._detect_event_type(doc.content)
        return TourismOpinionExtraction(
            event_type=event_type,
            summary=self._summary(doc.title, doc.content),
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            topic=self._detect_topic(event_type, doc.content),
            scenic_spots=scenic_spots,
            locations=locations,
            keywords=self._keywords(doc.content),
        )

    def _llm_extract(self, doc: TourismDocument, rule_result: TourismOpinionExtraction) -> TourismOpinionExtraction | None:
        if not self.llm_enabled:
            return None
        if not self.llm_client:
            logger.warning("MODEL_API_KEY 未配置，旅游舆情抽取使用规则结果。")
            return None
        try:
            prompt = self._build_extraction_prompt(doc, rule_result)
            response = self.llm_client.chat.completions.create(
                model=self.llm_model,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": "你是旅游舆情结构化抽取器，只输出严格 JSON，不输出解释。",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or "{}"
            payload = self._loads_json_object(content)
            extracted = TourismOpinionExtraction.model_validate(payload)
            return self._merge_and_validate(rule_result, extracted)
        except (ValidationError, json.JSONDecodeError, Exception) as exc:
            logger.warning("旅游舆情 LLM 约束抽取失败，使用规则结果: %s", exc, exc_info=True)
            return None

    def _build_extraction_prompt(self, doc: TourismDocument, rule_result: TourismOpinionExtraction) -> str:
        allowed_event_types = list(self.EVENT_TYPES.keys()) + ["一般舆情"]
        schema_hint = {
            "event_type": "必须从给定事件类型中选择",
            "summary": "不超过120字",
            "sentiment": "positive/neutral/negative",
            "sentiment_score": "0到1之间的小数",
            "topic": "舆情主题",
            "scenic_spots": "景区名称数组",
            "locations": "地点名称数组",
            "keywords": "最多10个关键词",
        }
        return f"""
请从桂林旅游舆情文本中抽取结构化要素。

允许的事件类型：{json.dumps(allowed_event_types, ensure_ascii=False)}
规则/字典候选结果：{json.dumps(rule_result.model_dump(), ensure_ascii=False)}
输出 JSON Schema 说明：{json.dumps(schema_hint, ensure_ascii=False)}

硬性要求：
1. 只能输出 JSON 对象，不能输出 Markdown。
2. event_type 必须从允许的事件类型中选择。
3. sentiment 只能是 positive、neutral、negative。
4. scenic_spots 和 locations 优先保留规则候选；如文本中有明确别名，可补充标准名称。
5. 不确定的字段使用规则候选结果，不要编造不存在的景区、地点、来源或数字。

标题：{doc.title}
正文：{doc.content[: self.llm_max_chars]}
"""

    @staticmethod
    def _loads_json_object(content: str) -> dict:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?", "", content).strip()
            content = re.sub(r"```$", "", content).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end >= start:
            content = content[start : end + 1]
        return json.loads(content)

    def _merge_and_validate(
        self,
        rule_result: TourismOpinionExtraction,
        llm_result: TourismOpinionExtraction,
    ) -> TourismOpinionExtraction:
        allowed_event_types = set(self.EVENT_TYPES.keys()) | {"一般舆情"}
        event_type = llm_result.event_type if llm_result.event_type in allowed_event_types else rule_result.event_type
        sentiment = llm_result.sentiment if llm_result.sentiment in {"positive", "neutral", "negative"} else rule_result.sentiment
        scenic_spots = self.normalizer.normalize_scenic_spots(
            self._merge_unique(rule_result.scenic_spots, llm_result.scenic_spots)
        )
        locations = self.normalizer.normalize_locations(
            self._merge_unique(rule_result.locations, llm_result.locations)
        )
        keywords = self._merge_unique(llm_result.keywords, rule_result.keywords)[:10]
        return TourismOpinionExtraction(
            event_type=event_type,
            summary=(llm_result.summary or rule_result.summary)[:120],
            sentiment=sentiment,
            sentiment_score=max(0.0, min(float(llm_result.sentiment_score), 1.0)),
            topic=llm_result.topic or self._detect_topic(event_type, ""),
            scenic_spots=scenic_spots,
            locations=locations,
            keywords=keywords,
        )

    @staticmethod
    def _merge_unique(*groups: list[str]) -> list[str]:
        result = []
        for group in groups:
            for item in group or []:
                item = str(item).strip()
                if item and item not in result:
                    result.append(item)
        return result

    def update_document_extract_state(self, documents: list[TourismDocument]):
        sql = """
            UPDATE t_tourism_document
            SET sentiment=%s, sentiment_score=%s, extract_status=%s, update_time=NOW()
            WHERE doc_id=%s
        """
        for item in documents:
            self.mysql.update_params(sql, (item.sentiment, item.sentiment_score, "success", item.doc_id))

    def _detect_sentiment(self, text: str) -> tuple[str, float]:
        neg = sum(1 for word in self.NEGATIVE_WORDS if word in text)
        pos = sum(1 for word in self.POSITIVE_WORDS if word in text)
        if neg > pos:
            return "negative", min(1.0, 0.55 + neg * 0.08)
        if pos > neg:
            return "positive", min(1.0, 0.55 + pos * 0.08)
        return "neutral", 0.5

    def _detect_event_type(self, text: str) -> str:
        for event_type, words in self.EVENT_TYPES.items():
            if any(word in text for word in words):
                return event_type
        return "一般舆情"

    @staticmethod
    def _detect_topic(event_type: str, text: str) -> str:
        if event_type != "一般舆情":
            return event_type
        if "攻略" in text or "推荐" in text:
            return "旅游体验"
        return "综合舆情"

    @staticmethod
    def _summary(title: str, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return title if title and len(title) >= 8 else text[:120]

    @staticmethod
    def _keywords(text: str) -> list[str]:
        candidates = re.findall(r"[\u4e00-\u9fa5]{2,8}", text)
        result = []
        for item in candidates:
            if item not in result:
                result.append(item)
            if len(result) >= 10:
                break
        return result
