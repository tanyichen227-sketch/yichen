from app.utils.logger import get_logger
from app.services.vector_service import vector_service
from app.services.settings_service import settings_service
from app.services.knowledge_graph_service import knowledge_graph_service
from rank_bm25 import BM25Okapi
import jieba
import numpy as np
from langchain_core.documents import Document
from app.utils.rerank_factory import RerankFactory

logger = get_logger(__name__)


class RetrievalService:
    def __init__(self):
        self.settings = settings_service.get()
        # self.reranker = RerankFactory.create_reranker(self.settings)
        self.reranker = None

    def vector_search(self, collection_name, query, rerank=True):
        vector_store = vector_service.get_or_create_collection(collection_name)
        top_k = int(self.settings.get("top_k", "5"))
        vector_threshold = float(self.settings.get("vector_threshold", "0.1"))
        # 把向量相似度的阈值限定在0到1之间
        vector_threshold = max(0.0, min(vector_threshold, 1.0))
        # 以相似度得分的方式检索，返回结果，这里先扩大k以以便后缀过滤
        results = vector_store.similarity_search_with_score(query=query, k=top_k * 3)
        docs_with_scores = []
        for doc, distance in results:
            # distance其实是一个相似度的距离，一般来距离越近，越小越相似
            # 对分数进行归一化处理并加入元数据，score取值范围 0-1，越大越相似
            # distance是0，score就是1 就是最相似
            # distance正无穷大，score无限接近0，最不相似
            # score越大越相似
            vector_score = 1.0 / (1.0 + float(distance))
            doc.metadata["vector_score"] = vector_score
            doc.metadata["retrieval_type"] = "vector"
            docs_with_scores.append((doc, vector_score))
        # 按相似度从高到底排序
        docs_with_scores.sort(key=lambda x: x[1], reverse=True)
        # 根据阈值过滤掉低于阈值的文档
        filtered_docs = [
            (doc, score) for doc, score in docs_with_scores if score >= vector_threshold
        ]
        # 仅仅保留前top_k个文档
        docs = [doc for doc, _ in filtered_docs][:top_k]
        if self.reranker and rerank:
            docs = self._apply_rerank(query, docs, top_k)
        logger.info(f"向量检索 ：检索到{len(docs)}个文档")
        return docs

    def _apply_rerank(self, query, docs, top_k):
        if not self.reranker or not docs:
            if not self.reranker:
                logger.info(f"文档重排序实例不存在，跳过重排序")
            else:
                logger.info(f"检索到的文档为空")
            return docs
        try:
            reranked = self.reranker.rerank(query, docs, top_k=top_k)
            for doc, rerank_score in reranked:
                doc.metadata["rerank_score"] = rerank_score
            logger.info(f"已经应用了文档重排序:{len(reranked)}个文档进行了重排序")
            return [doc for doc, _ in reranked]
        except Exception as e:
            logger.error(f"应用重排序出现错误:{str(e)}")
            return docs

    def _tokenize_chinese(self, text: str):
        """
        中文分词（使用 jieba）

        Args:
            text: 输入文本

        Returns:
            分词后的词列表
        """
        # 使用 jieba 分词
        words = jieba.lcut(text)
        # 去除停用词和单字
        stopwords = set(
            [
                "的",
                "了",
                "在",
                "是",
                "和",
                "有",
                "与",
                "对",
                "等",
                "为",
                "也",
                "就",
                "都",
                "要",
                "可以",
                "会",
                "能",
                "而",
                "及",
                "与",
                "或",
            ]
        )
        tokens = [
            word.strip()
            for word in words
            if len(word.strip()) > 1 and word.strip() not in stopwords
        ]
        return tokens

    def keyword_search(self, collection_name, query, rerank=True):
        vector_store = vector_service.get_or_create_collection(collection_name)
        # 从底层的集合中获取所有的内容
        # 这一步是 获取集合所有文档块，组合成 langchain Document的格式吗
        results = vector_store._collection.get(
            include=["documents", "metadatas", "embeddings"]
        )
        top_k = int(self.settings.get("top_k", "5"))
        keyword_threshold = float(self.settings.get("keyword_threshold", "0.1"))
        # 把关键字相似度的阈值限定在0到1之间
        keyword_threshold = max(0.0, min(keyword_threshold, 1.0))
        # 初始化用于存储所有文档的列表
        langchain_docs = []
        # 获取文档的 ids 列表
        ids = results["ids"]
        # 获取文档内容的列表
        chroma_documents = results["documents"]
        # 获取元数据的列表
        metadatas = results["metadatas"]
        # 获取嵌入向量的列表
        embeddings = results["embeddings"]
        # 遍历所有的文档，结合 id、文档内容、元数据和嵌入向量一起输出
        for i, (id, chroma_document, meta, embedding) in enumerate(
            zip(ids, chroma_documents, metadatas, embeddings)
        ):
            langchain_doc = Document(
                page_content=chroma_document,
                metadata=meta,
            )
            langchain_docs.append(langchain_doc)
        # 提取所有的文档的文本内容
        documents = [doc.page_content for doc in langchain_docs]
        # 对每个文档进行分词处理
        tokenized_docs = [self._tokenize_chinese(doc) for doc in documents]
        # 构建BM25索引
        bm25 = BM25Okapi(tokenized_docs)
        # 对查询语句进行中文分词
        query_tokens = self._tokenize_chinese(query)
        # 获取每个文档与查询的BM25分数
        scores = bm25.get_scores(query_tokens)
        # 计算分数最大值，用于归一化分数到[0,1]之间
        max_score = (
            float(np.max(scores)) if len(scores) > 0 and np.max(scores) > 0 else 1.0
        )
        # 归一化BM25分数 [1,2,3,4,5]  /5 = [0.2,,,,1]
        normalized_scores = scores / max_score if max_score > 0 else scores
        # 取分数最高的top_k*3个索引,以便于后续过滤
        top_incices = np.argsort(normalized_scores)[::-1][: top_k * 3]
        # 初始化结果列表
        docs_with_scores = []
        # 遍历候选索引列表
        for idx in top_incices:
            normalized_score = float(normalized_scores[idx])
            normalized_score = max(0.0, min(1.0, normalized_score))
            # 只保留分数高于阈值的文档
            if normalized_score >= keyword_threshold:
                # 取出对应的文档
                doc = langchain_docs[idx]
                doc.metadata["keyword_score"] = normalized_score
                doc.metadata["retrieval_type"] = "keyword"
                docs_with_scores.append((doc, normalized_score))
        # 按相似度从高到底排序
        docs_with_scores.sort(key=lambda x: x[1], reverse=True)
        # 仅仅保留前top_k个文档
        docs = [doc for doc, _ in docs_with_scores][:top_k]
        if self.reranker and rerank:
            docs = self._apply_rerank(query, docs, top_k)
        logger.info(f"BM25关键词本文检索 ：检索到{len(docs)}个文档")
        return docs

    def knowledge_graph_search(self, kb_id, query, limit=10):
        """
        知识图谱检索，返回实体列表及相关文档块
        """
        # 从知识图谱中搜索相关实体
        entities = knowledge_graph_service.search_entities(kb_id, query, limit=limit)

        # 根据实体关联的文档块ID从向量库中提取对应文档
        docs = []
        if entities:
            chunk_ids = [ent.get("chunk_id") for ent in entities if ent.get("chunk_id")]
            # 去重并过滤空值
            chunk_ids = list({cid for cid in chunk_ids if cid})
            if chunk_ids:
                try:
                    vector_store = vector_service.get_or_create_collection(
                        f"kb_{kb_id}"
                    )
                    # Chroma 的 where 过滤支持列表，匹配任一
                    results = vector_store._collection.get(
                        where={"chunk_id": chunk_ids}
                    )
                    for text, meta in zip(
                        results.get("documents", []), results.get("metadatas", [])
                    ):
                        docs.append(Document(page_content=text, metadata=meta))
                except Exception as e:
                    logger.error(f"从向量库获取知识图谱关联文档失败: {e}")

        logger.info(
            f"知识图谱检索 ：检索到{len(entities)}个实体，对应{len(docs)}个文档块"
        )
        return {"entities": entities, "docs": docs}

    def hybrid_search(self, collection_name, query, rrf_k=60):
        """
        融合检索 使用RRF融合向量检索、全文检索和知识图谱检索
        """
        # 从collection_name中提取kb_id
        kb_id = collection_name.replace("kb_", "")

        # 调用向量检索方法，得到向量检索结果
        vector_results = self.vector_search(
            collection_name=collection_name, query=query, rerank=True
        )
        # 调用关键词检索方法，得到关键词检索结果
        keyword_results = self.keyword_search(
            collection_name=collection_name, query=query, rerank=True
        )
        # 调用知识图谱检索方法，得到知识图谱检索结果
        kg_search_output = self.knowledge_graph_search(kb_id, query, limit=10)
        # 结果包含实体列表以及关联文档块
        kg_results = kg_search_output.get("entities", [])
        kg_docs = kg_search_output.get("docs", [])

        # 创建字典用于存储文本及其排名信息
        doc_ranks = {}
        # 遍历向量检索结果，记录排名及分数
        for rank, doc in enumerate(vector_results, start=1):
            # 其实是上传的文档document,用split分割后得到的文本分块存到向量库中的分块ID
            chunk_id = doc.metadata.get("id")
            # 如果文档ID不在字典中，则进行初始化
            if chunk_id not in doc_ranks:
                doc_ranks[chunk_id] = {"doc": doc}
            # 记录此doc_id对应的文档在向量结果列表中的排名
            doc_ranks[chunk_id]["vector_rank"] = rank
            # 再记录一下向量结果中此文档的对应的分数
            doc_ranks[chunk_id]["vector_score"] = doc.metadata.get("vector_score", 0)

        # 遍历关键词检索结果，记录排名及分数
        for rank, doc in enumerate(keyword_results, start=1):
            # 其实是上传的文档document,用split分割后得到的文本分块存到向量库中的分块ID
            chunk_id = doc.metadata.get("id")
            # 如果文档ID不在字典中，则进行初始化
            if chunk_id not in doc_ranks:
                doc_ranks[chunk_id] = {"doc": doc}
            # 记录此doc_id对应的文档在向量结果列表中的排名
            doc_ranks[chunk_id]["keyword_rank"] = rank
            # 再记录一下向量结果中此文档的对应的分数
            doc_ranks[chunk_id]["keyword_score"] = doc.metadata.get("keyword_score", 0)

        # 将知识图谱检索返回的文档也作为候选项加入排名
        for doc in kg_docs:
            chunk_id = doc.metadata.get("id")
            if chunk_id not in doc_ranks:
                doc_ranks[chunk_id] = {"doc": doc}
            # 知识图谱文档初始相关性计数
            doc_ranks[chunk_id]["kg_relevance"] = (
                doc_ranks[chunk_id].get("kg_relevance", 0) + 1
            )

        # 处理知识图谱实体结果，为文档增加额外权重
        # 这里简化处理，实际应用中可能需要更复杂的逻辑
        for entity in kg_results:
            # 实体名称出现于文档内容，增加相关性分数
            for chunk_id, rank_info in doc_ranks.items():
                doc = rank_info["doc"]
                if entity["name"] in doc.page_content:
                    doc_ranks[chunk_id]["kg_relevance"] = (
                        doc_ranks[chunk_id].get("kg_relevance", 0) + 1
                    )

        # 从设置中读取权重，默认值为0.3, 0.3, 0.4
        vector_weight = float(self.settings.get("vector_weight", "0.3"))
        keyword_weight = float(self.settings.get("keyword_weight", "0.3"))
        kg_weight = float(self.settings.get("kg_weight", "0.4"))

        # 归一化权重
        total_weight = vector_weight + keyword_weight + kg_weight
        if total_weight > 0:
            vector_weight /= total_weight
            keyword_weight /= total_weight
            kg_weight /= total_weight

        # 遍历所有的文档，计算RRF融合分数
        for chunk_id, rank_info in doc_ranks.items():
            # 获取向量排名
            vector_rank = rank_info.get("vector_rank", rrf_k + 1)
            # 获取关键词排名
            keyword_rank = rank_info.get("keyword_rank", rrf_k + 1)
            # 获取知识图谱相关性
            kg_relevance = rank_info.get("kg_relevance", 0)
            # 初始化RRF分数
            rrf_score = 0.0
            rrf_score += vector_weight / (rrf_k + vector_rank)
            rrf_score += keyword_weight / (rrf_k + keyword_rank)
            # 知识图谱相关性作为额外分数
            rrf_score += kg_weight * (kg_relevance / 10.0)  # 归一化到0-0.1
            doc_ranks[chunk_id]["rrf_score"] = rrf_score
        # 组装所有的文档以及其排名信息
        combined_results = [
            (chunk_id, rank_info) for chunk_id, rank_info in doc_ranks.items()
        ]
        # 最终的排序依据是RRF分数，从高到底进行排序
        combined_results.sort(key=lambda x: x[1].get("rrf_score", 0), reverse=True)
        top_k = int(self.settings.get("top_k", "5"))
        docs = []
        for chunk_id, rank_info in combined_results[:top_k]:
            doc = rank_info["doc"]
            doc.metadata["vector_score"] = rank_info.get("vector_score", 0)
            doc.metadata["keyword_score"] = rank_info.get("keyword_score", 0)
            doc.metadata["kg_relevance"] = rank_info.get("kg_relevance", 0)
            doc.metadata["rrf_score"] = rank_info.get("rrf_score", 0)
            doc.metadata["retrieval_type"] = "hybrid"
            docs.append(doc)
        logger.info(f"混合检索(RRF):检索到{len(docs)}个文档")
        if self.reranker:
            docs = self._apply_rerank(query, docs, top_k)
        return docs


retrieval_service = RetrievalService()
