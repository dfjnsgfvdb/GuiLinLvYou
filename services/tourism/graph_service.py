import hashlib
from collections import defaultdict
from itertools import combinations
from typing import Any

from common.mysql_util import MysqlUtil
from common.neo4j_client import Neo4jClient
from services.tourism.schemas import TourismDocument, TourismEvent


class GraphService:
    """Neo4j graph service with fixed, parameterized Cypher templates."""

    MAX_QUERY_LIMIT = 100

    def __init__(self):
        self.neo4j = Neo4jClient()
        self.mysql = MysqlUtil()

    def ensure_constraints(self) -> None:
        self.neo4j.ensure_tourism_constraints()

    def build_graph(self, documents: list[TourismDocument], events: list[TourismEvent]) -> int:
        """Incrementally upsert graph data from in-memory pipeline results."""
        if not self.neo4j.available():
            return 0
        self.ensure_constraints()
        doc_map = {doc.doc_id: doc for doc in documents}
        relation_count = 0

        for event in events:
            self.upsert_event(event)
            for spot in event.scenic_spots or [event.main_scenic_spot]:
                if spot:
                    self.upsert_scenic_spot(spot)
                    self.link_event_scenic_spot(event.event_id, self.scenic_spot_id(spot))
                    relation_count += 1
            for location in event.locations or [event.main_location]:
                if location:
                    self.upsert_location(location)
                    self.link_event_location(event.event_id, self.location_id(location))
                    relation_count += 1
            if event.topic:
                self.upsert_topic(event.topic)
                self.link_event_topic(event.event_id, self.topic_id(event.topic))
                relation_count += 1
            for doc_id in event.doc_ids:
                doc = doc_map.get(doc_id)
                if not doc:
                    continue
                self.upsert_document(doc)
                self.upsert_source(doc.source_name, doc.source_type)
                self.link_document_reports_event(doc.doc_id, event.event_id)
                self.link_document_source(doc.doc_id, self.source_id(doc.source_name))
                relation_count += 2

        self._link_related_events(events)
        self._mark_documents_graph_success([doc.doc_id for doc in documents])
        return relation_count

    def clear_tourism_graph(self) -> None:
        """Delete only tourism graph nodes and relationships."""
        if not self.neo4j.available():
            return
        self.neo4j.run(
            """
            MATCH ()-[r:REPORTS|INVOLVES_SCENIC_SPOT|OCCURRED_AT|FROM_SOURCE|BELONGS_TO_TOPIC|RELATED_TO]-()
            DELETE r
            """
        )
        self.neo4j.run(
            """
            MATCH (n)
            WHERE n:Event OR n:ScenicSpot OR n:Location OR n:Document OR n:Source OR n:Topic
            DELETE n
            """
        )

    def rebuild_graph_from_mysql(self, clear_existing: bool = False) -> dict[str, int | str]:
        """Rebuild tourism graph from MySQL metadata. This method is idempotent."""
        if not self.neo4j.available():
            return {"status": "skipped", "reason": "neo4j_unavailable", "node_count": 0, "relation_count": 0}
        self.ensure_constraints()
        if clear_existing:
            self.clear_tourism_graph()
        events = self._load_events_from_mysql()
        documents = self._load_documents_from_mysql()
        event_doc_map = self._load_event_document_map()
        document_map = {doc["doc_id"]: doc for doc in documents}

        node_count = 0
        relation_count = 0
        event_objs = []
        for event in events:
            self.upsert_event_row(event)
            node_count += 1
            event_id = event["event_id"]
            scenic_spot = event.get("main_scenic_spot") or ""
            location = event.get("main_location") or ""
            topic = event.get("topic") or ""

            if scenic_spot:
                self.upsert_scenic_spot(scenic_spot)
                self.link_event_scenic_spot(event_id, self.scenic_spot_id(scenic_spot))
                node_count += 1
                relation_count += 1
            if location:
                self.upsert_location(location)
                self.link_event_location(event_id, self.location_id(location))
                node_count += 1
                relation_count += 1
            if topic:
                self.upsert_topic(topic)
                self.link_event_topic(event_id, self.topic_id(topic))
                node_count += 1
                relation_count += 1

            for doc_id in event_doc_map.get(event_id, []):
                doc = document_map.get(doc_id)
                if not doc:
                    continue
                self.upsert_document_row(doc)
                self.upsert_source(doc.get("source_name") or "unknown", doc.get("source_type") or "manual")
                self.link_document_reports_event(doc_id, event_id)
                self.link_document_source(doc_id, self.source_id(doc.get("source_name") or "unknown"))
                node_count += 2
                relation_count += 2

            event_objs.append(event)

        relation_count += self._link_related_event_rows(event_objs)
        self._mark_documents_graph_success([doc["doc_id"] for doc in documents])
        self._save_graph_index_version(len(events), len(documents))
        return {
            "status": "success",
            "event_count": len(events),
            "document_count": len(documents),
            "node_count": node_count,
            "relation_count": relation_count,
        }

    def upsert_event(self, event: TourismEvent) -> None:
        self.neo4j.run(
            """
            MERGE (e:Event {event_id: $event_id})
            SET e.name=$name,
                e.summary=$summary,
                e.sentiment=$sentiment,
                e.risk_level=$risk_level,
                e.heat_score=$heat_score,
                e.first_seen_at=$first_seen_at,
                e.last_seen_at=$last_seen_at
            """,
            event_id=event.event_id,
            name=event.event_name,
            summary=event.event_summary,
            sentiment=event.sentiment,
            risk_level=event.risk_level,
            heat_score=event.heat_score,
            first_seen_at=event.first_seen_at.isoformat() if event.first_seen_at else "",
            last_seen_at=event.last_seen_at.isoformat() if event.last_seen_at else "",
        )

    def upsert_event_row(self, event: dict[str, Any]) -> None:
        self.neo4j.run(
            """
            MERGE (e:Event {event_id: $event_id})
            SET e.name=$name,
                e.summary=$summary,
                e.sentiment=$sentiment,
                e.risk_level=$risk_level,
                e.heat_score=$heat_score,
                e.first_seen_at=$first_seen_at,
                e.last_seen_at=$last_seen_at
            """,
            event_id=event["event_id"],
            name=event.get("event_name") or "",
            summary=event.get("event_summary") or "",
            sentiment=event.get("sentiment") or "",
            risk_level=event.get("risk_level") or "",
            heat_score=float(event.get("heat_score") or 0),
            first_seen_at=str(event.get("first_seen_at") or ""),
            last_seen_at=str(event.get("last_seen_at") or ""),
        )

    def upsert_document(self, document: TourismDocument) -> None:
        self.neo4j.run(
            """
            MERGE (d:Document {doc_id: $doc_id})
            SET d.title=$title,
                d.source_type=$source_type,
                d.publish_time=$publish_time
            """,
            doc_id=document.doc_id,
            title=document.title,
            source_type=document.source_type,
            publish_time=document.publish_time.isoformat() if document.publish_time else "",
        )

    def upsert_document_row(self, document: dict[str, Any]) -> None:
        self.neo4j.run(
            """
            MERGE (d:Document {doc_id: $doc_id})
            SET d.title=$title,
                d.source_type=$source_type,
                d.publish_time=$publish_time
            """,
            doc_id=document["doc_id"],
            title=document.get("title") or "",
            source_type=document.get("source_type") or "",
            publish_time=str(document.get("publish_time") or ""),
        )

    def upsert_scenic_spot(self, name: str, aliases: list[str] | None = None) -> None:
        self.neo4j.run(
            """
            MERGE (s:ScenicSpot {spot_id: $spot_id})
            SET s.name=$name,
                s.aliases=$aliases
            """,
            spot_id=self.scenic_spot_id(name),
            name=name,
            aliases=aliases or [],
        )

    def upsert_location(self, name: str, aliases: list[str] | None = None) -> None:
        self.neo4j.run(
            """
            MERGE (l:Location {location_id: $location_id})
            SET l.name=$name,
                l.aliases=$aliases
            """,
            location_id=self.location_id(name),
            name=name,
            aliases=aliases or [],
        )

    def upsert_source(self, source_name: str, source_type: str) -> None:
        self.neo4j.run(
            """
            MERGE (s:Source {source_id: $source_id})
            SET s.name=$name,
                s.source_type=$source_type
            """,
            source_id=self.source_id(source_name),
            name=source_name,
            source_type=source_type,
        )

    def upsert_topic(self, topic_name: str) -> None:
        self.neo4j.run(
            """
            MERGE (t:Topic {topic_id: $topic_id})
            SET t.name=$name
            """,
            topic_id=self.topic_id(topic_name),
            name=topic_name,
        )

    def link_document_reports_event(self, doc_id: str, event_id: str, confidence: float = 1.0) -> None:
        self.neo4j.run(
            """
            MATCH (d:Document {doc_id: $doc_id})
            MATCH (e:Event {event_id: $event_id})
            MERGE (d)-[r:REPORTS]->(e)
            SET r.confidence=$confidence,
                r.updated_at=datetime()
            """,
            doc_id=doc_id,
            event_id=event_id,
            confidence=confidence,
        )

    def link_event_scenic_spot(self, event_id: str, spot_id: str, confidence: float = 1.0) -> None:
        self.neo4j.run(
            """
            MATCH (e:Event {event_id: $event_id})
            MATCH (s:ScenicSpot {spot_id: $spot_id})
            MERGE (e)-[r:INVOLVES_SCENIC_SPOT]->(s)
            SET r.confidence=$confidence,
                r.updated_at=datetime()
            """,
            event_id=event_id,
            spot_id=spot_id,
            confidence=confidence,
        )

    def link_event_location(self, event_id: str, location_id: str, confidence: float = 1.0) -> None:
        self.neo4j.run(
            """
            MATCH (e:Event {event_id: $event_id})
            MATCH (l:Location {location_id: $location_id})
            MERGE (e)-[r:OCCURRED_AT]->(l)
            SET r.confidence=$confidence,
                r.updated_at=datetime()
            """,
            event_id=event_id,
            location_id=location_id,
            confidence=confidence,
        )

    def link_document_source(self, doc_id: str, source_id: str) -> None:
        self.neo4j.run(
            """
            MATCH (d:Document {doc_id: $doc_id})
            MATCH (s:Source {source_id: $source_id})
            MERGE (d)-[r:FROM_SOURCE]->(s)
            SET r.updated_at=datetime()
            """,
            doc_id=doc_id,
            source_id=source_id,
        )

    def link_event_topic(self, event_id: str, topic_id: str) -> None:
        self.neo4j.run(
            """
            MATCH (e:Event {event_id: $event_id})
            MATCH (t:Topic {topic_id: $topic_id})
            MERGE (e)-[r:BELONGS_TO_TOPIC]->(t)
            SET r.updated_at=datetime()
            """,
            event_id=event_id,
            topic_id=topic_id,
        )

    def link_related_events(self, from_event_id: str, to_event_id: str, reason: str, score: float) -> None:
        if from_event_id == to_event_id:
            return
        self.neo4j.run(
            """
            MATCH (a:Event {event_id: $from_event_id})
            MATCH (b:Event {event_id: $to_event_id})
            MERGE (a)-[r:RELATED_TO]->(b)
            SET r.reason=$reason,
                r.score=$score,
                r.updated_at=datetime()
            """,
            from_event_id=from_event_id,
            to_event_id=to_event_id,
            reason=reason,
            score=score,
        )

    def query_event_relations(self, event_id: str, hop: int = 1, limit: int = 50) -> dict[str, Any]:
        hop = self._validate_hop(hop)
        limit = self._validate_limit(limit)
        if hop == 1:
            cursor = self.neo4j.run(
                """
                MATCH (e:Event {event_id: $event_id})
                OPTIONAL MATCH p1=(e)-[:INVOLVES_SCENIC_SPOT|OCCURRED_AT|BELONGS_TO_TOPIC|RELATED_TO]-(n1)
                OPTIONAL MATCH p2=(d:Document)-[:REPORTS]->(e)
                OPTIONAL MATCH p3=(d)-[:FROM_SOURCE]->(s:Source)
                RETURN collect(DISTINCT p1) + collect(DISTINCT p2) + collect(DISTINCT p3) AS paths
                LIMIT $limit
                """,
                event_id=event_id,
                limit=limit,
            )
        else:
            cursor = self.neo4j.run(
                """
                MATCH (e:Event {event_id: $event_id})
                MATCH p=(e)-[*1..2]-(n)
                RETURN collect(DISTINCT p)[0..$limit] AS paths
                """,
                event_id=event_id,
                limit=limit,
            )
        return self._cursor_to_graph_payload(cursor)

    def query_by_scenic_spot(self, scenic_spot: str, hop: int = 1, limit: int = 50) -> dict[str, Any]:
        hop = self._validate_hop(hop)
        limit = self._validate_limit(limit)
        if hop == 1:
            cursor = self.neo4j.run(
                """
                MATCH (s:ScenicSpot {name: $scenic_spot})
                MATCH p=(e:Event)-[:INVOLVES_SCENIC_SPOT]->(s)
                RETURN collect(DISTINCT p)[0..$limit] AS paths
                """,
                scenic_spot=scenic_spot,
                limit=limit,
            )
        else:
            cursor = self.neo4j.run(
                """
                MATCH (s:ScenicSpot {name: $scenic_spot})
                MATCH p=(s)<-[:INVOLVES_SCENIC_SPOT]-(e:Event)-[*1..1]-(n)
                RETURN collect(DISTINCT p)[0..$limit] AS paths
                """,
                scenic_spot=scenic_spot,
                limit=limit,
            )
        return self._cursor_to_graph_payload(cursor)

    def query_by_location(self, location: str, hop: int = 1, limit: int = 50) -> dict[str, Any]:
        hop = self._validate_hop(hop)
        limit = self._validate_limit(limit)
        if hop == 1:
            cursor = self.neo4j.run(
                """
                MATCH (l:Location {name: $location})
                MATCH p=(e:Event)-[:OCCURRED_AT]->(l)
                RETURN collect(DISTINCT p)[0..$limit] AS paths
                """,
                location=location,
                limit=limit,
            )
        else:
            cursor = self.neo4j.run(
                """
                MATCH (l:Location {name: $location})
                MATCH p=(l)<-[:OCCURRED_AT]-(e:Event)-[*1..1]-(n)
                RETURN collect(DISTINCT p)[0..$limit] AS paths
                """,
                location=location,
                limit=limit,
            )
        return self._cursor_to_graph_payload(cursor)

    def search_by_terms(self, terms: list[str], limit: int = 20) -> dict[str, Any]:
        """Recall graph evidence independently from vector and keyword routes."""
        clean_terms = list(dict.fromkeys(str(term).strip().lower() for term in terms if str(term).strip()))[:12]
        if not clean_terms or not self.neo4j.available():
            return {"nodes": [], "relationships": [], "paths": []}
        cursor = self.neo4j.run(
            """
            MATCH p=(n)-[r]-(m)
            WHERE (n:Event OR n:ScenicSpot OR n:Location OR n:Document OR n:Source OR n:Topic)
              AND any(term IN $terms WHERE
                    toLower(coalesce(n.name, '')) CONTAINS term
                 OR toLower(coalesce(n.summary, '')) CONTAINS term
                 OR toLower(coalesce(n.title, '')) CONTAINS term)
            RETURN collect(DISTINCT p)[0..$limit] AS paths
            """,
            terms=clean_terms,
            limit=self._validate_limit(limit),
        )
        return self._cursor_to_graph_payload(cursor)

    def _link_related_events(self, events: list[TourismEvent]) -> int:
        groups = defaultdict(list)
        for event in events:
            key = (event.main_scenic_spot, event.main_location, event.topic)
            groups[key].append(event)
        relation_count = 0
        for key, group in groups.items():
            for left, right in combinations(group, 2):
                self.link_related_events(left.event_id, right.event_id, "same_spot_location_topic", 1.0)
                self.link_related_events(right.event_id, left.event_id, "same_spot_location_topic", 1.0)
                relation_count += 2
        return relation_count

    def _link_related_event_rows(self, events: list[dict[str, Any]]) -> int:
        groups = defaultdict(list)
        for event in events:
            key = (event.get("main_scenic_spot"), event.get("main_location"), event.get("topic"))
            groups[key].append(event)
        relation_count = 0
        for key, group in groups.items():
            for left, right in combinations(group, 2):
                self.link_related_events(left["event_id"], right["event_id"], "same_spot_location_topic", 1.0)
                self.link_related_events(right["event_id"], left["event_id"], "same_spot_location_topic", 1.0)
                relation_count += 2
        return relation_count

    def _load_events_from_mysql(self) -> list[dict[str, Any]]:
        return self.mysql.query_mysql_dict("SELECT * FROM t_tourism_event WHERE status IS NULL OR status <> 'merged'")

    def _load_documents_from_mysql(self) -> list[dict[str, Any]]:
        return self.mysql.query_mysql_dict("SELECT * FROM t_tourism_document")

    def _load_event_document_map(self) -> dict[str, list[str]]:
        rows = self.mysql.query_mysql_dict("SELECT event_id, doc_id FROM t_tourism_event_document")
        result = defaultdict(list)
        for row in rows:
            result[row["event_id"]].append(row["doc_id"])
        return result

    def _mark_documents_graph_success(self, doc_ids: list[str]) -> None:
        for doc_id in doc_ids:
            self.mysql.update_params(
                "UPDATE t_tourism_document SET graph_status=%s, update_time=NOW() WHERE doc_id=%s",
                ("success", doc_id),
            )

    def _save_graph_index_version(self, event_count: int, document_count: int) -> None:
        self.mysql.insert(
            """
            INSERT INTO t_tourism_index_version
            (index_version, index_type, chunk_count, document_count, event_count, status, build_started_at, build_finished_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
              document_count=VALUES(document_count),
              event_count=VALUES(event_count),
              status=VALUES(status),
              build_finished_at=NOW()
            """,
            ("graph_active", "graph", 0, document_count, event_count, "active"),
        )

    @classmethod
    def _validate_hop(cls, hop: int) -> int:
        hop = int(hop)
        if hop not in (1, 2):
            raise ValueError("hop只允许为1或2")
        return hop

    @classmethod
    def _validate_limit(cls, limit: int) -> int:
        return min(max(int(limit), 1), cls.MAX_QUERY_LIMIT)

    @staticmethod
    def scenic_spot_id(name: str) -> str:
        return GraphService._node_id("spot", name)

    @staticmethod
    def location_id(name: str) -> str:
        return GraphService._node_id("loc", name)

    @staticmethod
    def source_id(name: str) -> str:
        return GraphService._node_id("source", name)

    @staticmethod
    def topic_id(name: str) -> str:
        return GraphService._node_id("topic", name)

    @staticmethod
    def _node_id(prefix: str, value: str) -> str:
        digest = hashlib.md5((value or "").encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}"

    @staticmethod
    def _cursor_to_graph_payload(cursor) -> dict[str, Any]:
        if cursor is None:
            return {"nodes": [], "relationships": [], "paths": []}
        nodes: dict[str, dict[str, Any]] = {}
        relationships: dict[str, dict[str, Any]] = {}
        path_payloads = []
        for record in cursor:
            for path in record.get("paths") or []:
                if path is None:
                    continue
                path_nodes, path_rels = GraphService._serialize_path(path)
                for node in path_nodes:
                    nodes[node["id"]] = node
                for rel in path_rels:
                    relationships[rel["id"]] = rel
                path_payloads.append(
                    {
                        "nodes": [node["id"] for node in path_nodes],
                        "relationships": [rel["id"] for rel in path_rels],
                    }
                )
        return {"nodes": list(nodes.values()), "relationships": list(relationships.values()), "paths": path_payloads}

    @staticmethod
    def _serialize_path(path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        path_nodes = []
        path_rels = []
        try:
            nodes = list(path.nodes)
            relationships = list(path.relationships)
        except Exception:
            return path_nodes, path_rels
        for node in nodes:
            labels = list(getattr(node, "labels", []))
            identity = str(getattr(node, "identity", None) or GraphService._node_identity(node))
            path_nodes.append({"id": identity, "labels": labels, "properties": dict(node)})
        for rel in relationships:
            identity = str(getattr(rel, "identity", None) or GraphService._rel_identity(rel))
            path_rels.append(
                {
                    "id": identity,
                    "type": rel.__class__.__name__,
                    "start_node": str(getattr(rel.start_node, "identity", GraphService._node_identity(rel.start_node))),
                    "end_node": str(getattr(rel.end_node, "identity", GraphService._node_identity(rel.end_node))),
                    "properties": dict(rel),
                }
            )
        return path_nodes, path_rels

    @staticmethod
    def _node_identity(node) -> str:
        labels = ",".join(sorted(list(getattr(node, "labels", []))))
        props = dict(node)
        return hashlib.md5(f"{labels}:{props}".encode("utf-8")).hexdigest()

    @staticmethod
    def _rel_identity(rel) -> str:
        payload = f"{getattr(rel.start_node, 'identity', '')}:{rel.__class__.__name__}:{getattr(rel.end_node, 'identity', '')}:{dict(rel)}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()
