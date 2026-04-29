from app.utils.logger import get_logger
import spacy
import uuid
from datetime import datetime
from neo4j import GraphDatabase
import os
from app.config import Config

logger = get_logger(__name__)


class KnowledgeGraphService:
    def __init__(self):
        self.logger = logger
        # 尝试加载spaCy中文模型，如果不存在则下载
        try:
            self.logger.info(f"正在加载spaCy中文模型")
            self.nlp = spacy.load("zh_core_web_sm")
        except Exception as e:
            self.logger.warning(f"无法加载spaCy中文模型: {e}")
            self.logger.info("尝试下载spaCy中文模 型...")
            try:
                import subprocess

                subprocess.run(
                    ["python", "-m", "spacy", "download", "zh_core_web_sm"], check=True
                )
                self.nlp = spacy.load("zh_core_web_sm")
            except Exception as download_error:
                self.logger.error(f"下载spaCy中文模型失败: {download_error}")
                self.nlp = None

        # Neo4j连接配置
        self.neo4j_uri = Config.NEO4J_URI
        self.neo4j_user = Config.NEO4J_USER
        self.neo4j_password = Config.NEO4J_PASSWORD
        self.driver = None
        self._connect_neo4j()

    def _connect_neo4j(self):
        """连接到Neo4j数据库"""
        try:
            self.driver = GraphDatabase.driver(
                self.neo4j_uri, auth=(self.neo4j_user, self.neo4j_password)
            )
            # 测试连接
            with self.driver.session() as session:
                session.run("MATCH (n) RETURN count(n) AS count")
            self.logger.info("成功连接到Neo4j数据库")
        except Exception as e:
            self.logger.error(f"连接Neo4j数据库失败: {e}")
            self.driver = None

    def extract_entities(self, text):
        """从文本中提取实体"""
        if not self.nlp:
            self.logger.error("spaCy模型未加载，无法提取实体")
            return []

        try:
            doc = self.nlp(text)
            entities = []

            # 医疗领域实体类型定义
            medical_entities = {
                "疾病": [
                    "高血压",
                    "糖尿病",
                    "心脏病",
                    "癌症",
                    "肺炎",
                    "胃炎",
                    "肝炎",
                    "肾炎",
                    "关节炎",
                    "抑郁症",
                ],
                "症状": [
                    "头痛",
                    "发热",
                    "咳嗽",
                    "腹痛",
                    "恶心",
                    "呕吐",
                    "腹泻",
                    "便秘",
                    "乏力",
                    "失眠",
                ],
                "药物": [
                    "阿司匹林",
                    "布洛芬",
                    "对乙酰氨基酚",
                    "阿莫西林",
                    "头孢菌素",
                    "青霉素",
                    "胰岛素",
                    "降压药",
                    "降糖药",
                    "抗生素",
                ],
                "治疗方法": [
                    "手术",
                    "化疗",
                    "放疗",
                    "物理治疗",
                    "药物治疗",
                    "康复治疗",
                    "针灸",
                    "推拿",
                    "按摩",
                    "中药治疗",
                ],
                "身体部位": [
                    "头部",
                    "胸部",
                    "腹部",
                    "背部",
                    "四肢",
                    "心脏",
                    "肝脏",
                    "肾脏",
                    "肺脏",
                    "脾脏",
                ],
                "检查项目": [
                    "血常规",
                    "尿常规",
                    "心电图",
                    "CT",
                    "MRI",
                    "B超",
                    "X光",
                    "活检",
                    "肝功能",
                    "肾功能",
                ],
            }

            # 提取spaCy默认实体
            for ent in doc.ents:
                entities.append(
                    {
                        "text": ent.text,
                        "label": ent.label_,
                        "start": ent.start_char,
                        "end": ent.end_char,
                    }
                )

            # 提取医疗领域实体
            for entity_type, entity_list in medical_entities.items():
                for entity_name in entity_list:
                    start = text.find(entity_name)
                    while start != -1:
                        end = start + len(entity_name)
                        # 检查是否已经被spaCy提取
                        already_extracted = False
                        for ent in entities:
                            if ent["start"] <= start and ent["end"] >= end:
                                already_extracted = True
                                break
                        if not already_extracted:
                            entities.append(
                                {
                                    "text": entity_name,
                                    "label": entity_type,
                                    "start": start,
                                    "end": end,
                                }
                            )
                        start = text.find(entity_name, end)

            return entities
        except Exception as e:
            self.logger.error(f"提取实体失败: {e}")
            return []

    def extract_relationships(self, text, entities):
        """从文本中提取实体关系"""
        # 医疗领域关系提取逻辑
        relationships = []
        try:
            # 医疗领域关系类型定义
            medical_relationships = {
                "疾病-症状": {
                    "关系词": ["有", "表现为", "症状", "出现", "引起"],
                    "source_types": ["疾病"],
                    "target_types": ["症状"],
                },
                "疾病-治疗方法": {
                    "关系词": ["治疗", "采用", "使用", "通过", "需要"],
                    "source_types": ["疾病"],
                    "target_types": ["治疗方法"],
                },
                "药物-治疗疾病": {
                    "关系词": ["治疗", "用于", "缓解", "针对", "适用于"],
                    "source_types": ["药物"],
                    "target_types": ["疾病"],
                },
                "疾病-检查项目": {
                    "关系词": ["检查", "需要", "做", "进行", "通过"],
                    "source_types": ["疾病"],
                    "target_types": ["检查项目"],
                },
                "身体部位-疾病": {
                    "关系词": ["相关", "引起", "导致", "发生", "患有"],
                    "source_types": ["身体部位"],
                    "target_types": ["疾病"],
                },
                "药物-副作用": {
                    "关系词": ["副作用", "引起", "导致", "可能", "产生"],
                    "source_types": ["药物"],
                    "target_types": ["症状"],
                },
            }

            # 提取医疗领域关系
            for i, ent1 in enumerate(entities):
                for j, ent2 in enumerate(entities):
                    if i != j:
                        # 检查两个实体之间是否有关联
                        ent1_end = ent1["end"]
                        ent2_start = ent2["start"]
                        if ent1_end < ent2_start:
                            between_text = text[ent1_end:ent2_start]

                            # 检查医疗领域关系
                            for rel_type, rel_info in medical_relationships.items():
                                if (
                                    ent1["label"] in rel_info["source_types"]
                                    and ent2["label"] in rel_info["target_types"]
                                ):
                                    if any(
                                        rel_word in between_text
                                        for rel_word in rel_info["关系词"]
                                    ):
                                        relationships.append(
                                            {
                                                "source": ent1["text"],
                                                "target": ent2["text"],
                                                "type": rel_type,
                                            }
                                        )

                            # 检查通用关系
                            if any(
                                rel_word in between_text
                                for rel_word in [
                                    "是",
                                    "和",
                                    "与",
                                    "属于",
                                    "位于",
                                    "来自",
                                ]
                            ):
                                relationships.append(
                                    {
                                        "source": ent1["text"],
                                        "target": ent2["text"],
                                        "type": "关联",
                                    }
                                )
            return relationships
        except Exception as e:
            self.logger.error(f"提取关系失败: {e}")
            return []

    def store_entities(self, kb_id, doc_id, chunk_id, entities):
        """存储实体到Neo4j"""
        if not self.driver:
            self.logger.error("Neo4j驱动未初始化，无法存储实体")
            return

        try:
            with self.driver.session() as session:
                for entity in entities:
                    # 基于name、type和kb_id进行去重
                    session.run(
                        """
                        MERGE (e:Entity {
                            name: $name,
                            type: $type,
                            kb_id: $kb_id
                        })
                        ON CREATE SET 
                            e.id = $entity_id,
                            e.created_at = $created_at
                        ON MATCH SET 
                            e.updated_at = $updated_at
                        """,
                        entity_id=str(uuid.uuid4()),
                        name=entity["text"],
                        type=entity["label"],
                        kb_id=kb_id,
                        created_at=datetime.now().isoformat(),
                        updated_at=datetime.now().isoformat(),
                    )
            self.logger.info(f"成功存储{len(entities)}个实体")
        except Exception as e:
            self.logger.error(f"存储实体失败: {e}")

    def store_relationships(self, kb_id, doc_id, chunk_id, relationships):
        """存储关系到Neo4j"""
        if not self.driver:
            self.logger.error("Neo4j驱动未初始化，无法存储关系")
            return

        try:
            with self.driver.session() as session:
                for relationship in relationships:
                    rel_id = str(uuid.uuid4())
                    session.run(
                        """
                        MATCH (s:Entity {name: $source, kb_id: $kb_id})
                        MATCH (t:Entity {name: $target, kb_id: $kb_id})
                        MERGE (s)-[r:RELATIONSHIP {
                            id: $rel_id,
                            type: $type,
                            kb_id: $kb_id,
                            doc_id: $doc_id,
                            chunk_id: $chunk_id
                        }]->(t)
                        ON CREATE SET r.created_at = $created_at
                        """,
                        rel_id=rel_id,
                        source=relationship["source"],
                        target=relationship["target"],
                        type=relationship["type"],
                        kb_id=kb_id,
                        doc_id=doc_id,
                        chunk_id=chunk_id,
                        created_at=datetime.now().isoformat(),
                    )
            self.logger.info(f"成功存储{len(relationships)}个关系")
        except Exception as e:
            self.logger.error(f"存储关系失败: {e}")

    def search_entities(self, kb_id, query, limit=10):
        """在知识图谱中搜索实体"""
        if not self.driver:
            self.logger.error("Neo4j驱动未初始化，无法搜索实体")
            return []

        try:
            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH (e:Entity {kb_id: $kb_id})
                    WHERE e.name CONTAINS $query
                    RETURN e.id AS id, e.name AS name, e.type AS type,
                           e.doc_id AS doc_id, e.chunk_id AS chunk_id
                    LIMIT $limit
                    """,
                    parameters={
                        "kb_id": kb_id,
                        "query": query,
                        "limit": limit,
                    },
                )
                return [record.data() for record in result]
        except Exception as e:
            self.logger.error(f"搜索实体失败: {e}")
            return []

    def get_graph_data(self, kb_id, limit=50):
        """获取知识图谱可视化数据"""
        if not self.driver:
            self.logger.error("Neo4j驱动未初始化，无法获取图谱数据")
            return {"nodes": [], "links": []}

        try:
            with self.driver.session() as session:
                # 获取节点
                nodes_result = session.run(
                    """
                    MATCH (e:Entity {kb_id: $kb_id})
                    RETURN e.id AS id, e.name AS name, e.type AS type
                    LIMIT $limit
                    """,
                    kb_id=kb_id,
                    limit=limit,
                )

                nodes = []
                node_ids = set()
                for record in nodes_result:
                    node_id = record["id"]
                    nodes.append(
                        {"id": node_id, "name": record["name"], "type": record["type"]}
                    )
                    node_ids.add(node_id)

                # 获取关系
                links_result = session.run(
                    """
                    MATCH (s:Entity {kb_id: $kb_id})-[r:RELATIONSHIP]->(t:Entity {kb_id: $kb_id})
                    WHERE s.id IN $node_ids AND t.id IN $node_ids
                    RETURN r.id AS id, s.id AS source, t.id AS target, r.type AS type
                    """,
                    kb_id=kb_id,
                    node_ids=list(node_ids),
                )

                links = []
                for record in links_result:
                    links.append(
                        {
                            "id": record["id"],
                            "source": record["source"],
                            "target": record["target"],
                            "type": record["type"],
                        }
                    )

                return {"nodes": nodes, "links": links}
        except Exception as e:
            self.logger.error(f"获取图谱数据失败: {e}")
            return {"nodes": [], "links": []}

    def close(self):
        """关闭Neo4j连接"""
        if self.driver:
            self.driver.close()
            self.logger.info("已关闭Neo4j连接")

    def get_relationships(self, kb_id, skip=0, limit=10):
        """获取知识库关系列表"""
        if not self.driver:
            self.logger.error("Neo4j驱动未初始化，无法获取关系")
            return [], 0

        try:
            with self.driver.session() as session:
                # 获取总数
                total_result = session.run(
                    """
                    MATCH (s:Entity {kb_id: $kb_id})-[r:RELATIONSHIP]->(t:Entity {kb_id: $kb_id})
                    RETURN count(r) AS total
                    """,
                    kb_id=kb_id,
                )
                total = total_result.single()["total"]

                # 获取分页关系
                relationships_result = session.run(
                    """
                    MATCH (s:Entity {kb_id: $kb_id})-[r:RELATIONSHIP]->(t:Entity {kb_id: $kb_id})
                    RETURN r.id AS id, s.name AS source, t.name AS target, r.type AS type, r.created_at AS created_at
                    ORDER BY r.created_at DESC
                    SKIP $skip LIMIT $limit
                    """,
                    kb_id=kb_id,
                    skip=skip,
                    limit=limit,
                )

                relationships = []
                for record in relationships_result:
                    relationships.append(
                        {
                            "id": record["id"],
                            "source": record["source"],
                            "target": record["target"],
                            "type": record["type"],
                            "created_at": record["created_at"],
                        }
                    )

                return relationships, total
        except Exception as e:
            self.logger.error(f"获取关系失败: {e}")
            return [], 0


knowledge_graph_service = KnowledgeGraphService()
