import logging
import os

from common.evidence_schema import NEO4J_TOURISM_CONSTRAINTS

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self):
        self.graph = self._connect()

    @staticmethod
    def _connect():
        try:
            from py2neo import Graph

            uri = os.getenv("NEO4J_URI")
            user = os.getenv("NEO4J_USER")
            password = os.getenv("NEO4J_PASSWORD")
            if not all([uri, user, password]):
                logger.warning("Neo4j环境变量未完整配置，图谱写入将跳过。")
                return None
            return Graph(uri, auth=(user, password))
        except Exception:
            logger.warning("Neo4j客户端初始化失败，图谱写入将跳过。", exc_info=True)
            return None

    def available(self) -> bool:
        return self.graph is not None

    def run(self, cypher: str, **params):
        if not self.graph:
            return None
        return self.graph.run(cypher, **params)

    def ensure_tourism_constraints(self):
        if not self.graph:
            return
        for cypher in NEO4J_TOURISM_CONSTRAINTS:
            self.graph.run(cypher)
