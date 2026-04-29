from app.utils.logger import get_logger
from app.services.settings_service import settings_service
from app.services.retrieval_service import retrieval_service
from app.utils.llm_factory import LLMFactory
from langchain_core.prompts import ChatPromptTemplate

logger = get_logger(__name__)


class RAGService:
    def __init__(self):
        self.settings = settings_service.get()
        print("self.settings", self.settings)
        rag_system_prompt = self.settings.get("rag_system_prompt")
        rag_query_prompt = self.settings.get("rag_query_prompt")
        self.rag_prompt = ChatPromptTemplate.from_messages(
            [("system", rag_system_prompt), ("human", rag_query_prompt)]
        )

    def _retrieve_documents(self, kb_id, question):
        # 获取此知识库对应的集合的名称
        collection_name = f"kb_{kb_id}"
        # 获取设置里的检索模型
        retrieval_mode = self.settings.get("retrieval_mode", "vector")
        if retrieval_mode == "vector":
            docs = retrieval_service.vector_search(
                collection_name=collection_name, query=question, rerank=True
            )
        elif retrieval_mode == "keyword":
            docs = retrieval_service.keyword_search(
                collection_name=collection_name, query=question, rerank=True
            )
        elif retrieval_mode == "hybrid":
            docs = retrieval_service.hybrid_search(
                collection_name=collection_name, query=question
            )
        else:
            logger.warning(f"未知的检索模型:{retrieval_mode},转化使用向量检索")
            docs = retrieval_service.vector_search(
                collection_name=collection_name, query=question
            )
        logger.info(f"使用{retrieval_mode}模型检索到{len(docs)}个文档")
        return docs

    def ask_stream(self, kb_id, question):
        llm = LLMFactory.create_llm(self.settings)
        yield {"type": "start", "content": ""}
        chain = self.rag_prompt | llm
        # 获取根据用户的提问检索到的相关的文档
        filtered_docs = self._retrieve_documents(kb_id, question)
        context = "\n\n".join(
            [
                f"文档{i+1} ({doc.metadata.get('doc_name','未知文档')}):\n{doc.page_content}"
                for i, doc in enumerate(filtered_docs)
            ]
        )
        for chunk in chain.stream({"context": context, "question": question}):
            content = chunk.content
            if content:
                yield {"type": "content", "content": content}
        # 提取引用信息
        sources = self._extract_citations(filtered_docs)
        yield {
            "type": "done",
            "content": "",
            "sources": sources,
            "metadata": {
                "kb_id": kb_id,
                "question": question,
                "retrieved_chunks": len(filtered_docs),
            },
        }

    def _extract_citations(self, docs):
        sources = []
        for doc in docs:
            metadata = doc.metadata
            retrieval_type = metadata.get("retrieval_type")
            rerank_score = metadata.get("rerank_score", 0)
            vector_score = metadata.get("vector_score", 0)
            keyword_score = metadata.get("keyword_score", 0)
            rrf_score = metadata.get("rrf_score", 0)
            chunk_id = metadata.get("chunk_id")
            doc_id = metadata.get("doc_id")
            doc_name = metadata.get("doc_name")
            content = doc.page_content
            sources.append(
                {
                    "retrieval_type": retrieval_type,
                    "rerank_score": round(rerank_score * 100, 2),
                    "vector_score": round(vector_score * 100, 2),
                    "keyword_score": round(keyword_score * 100, 2),
                    "rrf_score": round(rrf_score * 100, 2),
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "content": content,
                }
            )
        return sources


rag_service = RAGService()
