import hashlib
from collections import defaultdict
from datetime import datetime

from common.mysql_util import MysqlUtil
from services.tourism.schemas import ExtractedOpinion, TourismDocument, TourismEvent


class EventClusterService:
    def __init__(self):
        self.mysql = MysqlUtil()

    def cluster_events(
        self,
        documents: list[TourismDocument],
        extractions: list[ExtractedOpinion],
        time_window_days: int = 3,
    ) -> list[TourismEvent]:
        doc_map = {doc.doc_id: doc for doc in documents}
        groups = defaultdict(list)
        for item in extractions:
            doc = doc_map[item.doc_id]
            date_key = self._date_window(doc.publish_time, time_window_days)
            scenic_key = item.scenic_spots[0] if item.scenic_spots else "未知景区"
            location_key = item.locations[0] if item.locations else "桂林市"
            groups[(scenic_key, location_key, item.event_type, date_key)].append(item)

        events = []
        for key, items in groups.items():
            scenic_key, location_key, event_type, date_key = key
            for cluster_index, cluster_items in enumerate(self._split_by_similarity(items)):
                events.append(self._build_event(cluster_items, doc_map, scenic_key, location_key, event_type, date_key, cluster_index))
        return events

    def _build_event(
        self,
        items: list[ExtractedOpinion],
        doc_map: dict[str, TourismDocument],
        scenic_key: str,
        location_key: str,
        event_type: str,
        date_key: str,
        cluster_index: int,
    ) -> TourismEvent:
        doc_ids = [item.doc_id for item in items]
        source_names = {doc_map[doc_id].source_name for doc_id in doc_ids if doc_id in doc_map}
        sentiments = [item.sentiment for item in items]
        negative_count = sentiments.count("negative")
        negative_ratio = negative_count / len(items) if items else 0
        risk_level = self._risk_level(len(items), negative_ratio)
        first_seen = self._min_time([doc_map[doc_id].publish_time for doc_id in doc_ids if doc_id in doc_map])
        last_seen = self._max_time([doc_map[doc_id].publish_time for doc_id in doc_ids if doc_id in doc_map])
        event_hash = hashlib.sha256(
            "|".join([scenic_key, location_key, event_type, date_key, str(cluster_index), *sorted(doc_ids)]).encode("utf-8")
        ).hexdigest()[:16]
        return TourismEvent(
            event_id=f"evt_{event_hash}",
            event_name=f"{scenic_key}{event_type}",
            event_summary="；".join(item.summary for item in items[:3]),
            event_type=event_type,
            topic=items[0].topic,
            sentiment="negative" if negative_ratio >= 0.5 else "neutral",
            risk_level=risk_level,
            heat_score=float(len(items) * 10 + len(source_names) * 5 + negative_ratio * 20),
            negative_ratio=negative_ratio,
            growth_rate=0.0,
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            main_scenic_spot=scenic_key,
            main_location=location_key,
            source_count=len(source_names),
            document_count=len(doc_ids),
            doc_ids=doc_ids,
            scenic_spots=sorted({spot for item in items for spot in item.scenic_spots}),
            locations=sorted({loc for item in items for loc in item.locations}),
        )

    def _split_by_similarity(self, items: list[ExtractedOpinion], threshold: float = 0.25) -> list[list[ExtractedOpinion]]:
        clusters: list[list[ExtractedOpinion]] = []
        for item in items:
            placed = False
            for cluster in clusters:
                if self._jaccard(item.keywords, cluster[0].keywords) >= threshold:
                    cluster.append(item)
                    placed = True
                    break
            if not placed:
                clusters.append([item])
        return clusters

    @staticmethod
    def _jaccard(left: list[str], right: list[str]) -> float:
        left_set = set(left)
        right_set = set(right)
        if not left_set or not right_set:
            return 0.0
        return len(left_set & right_set) / len(left_set | right_set)

    def save_events(self, events: list[TourismEvent]) -> int:
        if not events:
            return 0
        event_sql = """
            INSERT INTO t_tourism_event
            (event_id, event_name, event_summary, topic, sentiment, risk_level, heat_score,
             negative_ratio, growth_rate, first_seen_at, last_seen_at, main_scenic_spot,
             main_location, source_count, document_count, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              event_summary=VALUES(event_summary),
              heat_score=VALUES(heat_score),
              negative_ratio=VALUES(negative_ratio),
              last_seen_at=VALUES(last_seen_at),
              source_count=VALUES(source_count),
              document_count=VALUES(document_count)
        """
        self.mysql.batch_insert(
            event_sql,
            [
                (
                    item.event_id,
                    item.event_name,
                    item.event_summary,
                    item.topic,
                    item.sentiment,
                    item.risk_level,
                    item.heat_score,
                    item.negative_ratio,
                    item.growth_rate,
                    item.first_seen_at,
                    item.last_seen_at,
                    item.main_scenic_spot,
                    item.main_location,
                    item.source_count,
                    item.document_count,
                    "active",
                )
                for item in events
            ],
        )
        rel_rows = []
        for event in events:
            for doc_id in event.doc_ids:
                rel_rows.append((event.event_id, doc_id, 1.0, "景区/地点/事件类型/时间窗口聚合"))
        if rel_rows:
            self.mysql.batch_insert(
                """
                INSERT INTO t_tourism_event_document (event_id, doc_id, match_score, match_reason)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE match_score=VALUES(match_score), match_reason=VALUES(match_reason)
                """,
                rel_rows,
            )
        return len(events)

    @staticmethod
    def _date_window(publish_time: datetime | None, days: int) -> str:
        if not publish_time:
            return "unknown"
        ordinal = publish_time.toordinal() // max(days, 1)
        return str(ordinal)

    @staticmethod
    def _risk_level(event_count: int, negative_ratio: float) -> str:
        if event_count >= 5 and negative_ratio >= 0.6:
            return "high"
        if event_count >= 3 or negative_ratio >= 0.5:
            return "medium"
        return "low"

    @staticmethod
    def _min_time(values):
        values = [item for item in values if item]
        return min(values) if values else None

    @staticmethod
    def _max_time(values):
        values = [item for item in values if item]
        return max(values) if values else None
