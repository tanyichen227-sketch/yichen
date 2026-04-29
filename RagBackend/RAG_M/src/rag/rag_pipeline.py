"""
RAG pipeline with hybrid retrieval, source tracing, and SSE streaming output.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Generator, List, Optional

import requests
from langchain.docstore.document import Document
from langchain.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_ollama.llms import OllamaLLM

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from models.model_config import get_model_config
from src.rag.hybrid_retriever import HybridRetriever

try:
    _BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)
    from document_processing.retrieval_strategy import (
        RetrievalConfig,
        RetrievalStrategyExecutor,
    )

    _STRATEGY_AVAILABLE = True
except ImportError:
    _STRATEGY_AVAILABLE = False
    RetrievalStrategyExecutor = None  # type: ignore
    RetrievalConfig = None  # type: ignore


_PROMPT_TEMPLATE = """You are a knowledge assistant.
Answer based on the provided context first.
If context is insufficient, state assumptions clearly.
Cite source file names naturally in your answer whenever possible.

Context:
{context}

Question:
{question}

Answer:
"""

PROMPT = PromptTemplate(template=_PROMPT_TEMPLATE, input_variables=["context", "question"])

DEFAULT_PROMPT_MAX_CHUNKS = int(os.getenv("RAG_PROMPT_MAX_CHUNKS", "4"))
DEFAULT_PROMPT_MAX_CHARS_PER_CHUNK = int(
    os.getenv("RAG_PROMPT_MAX_CHARS_PER_CHUNK", "1200")
)
DEFAULT_PROMPT_MAX_TOTAL_CHARS = int(os.getenv("RAG_PROMPT_MAX_TOTAL_CHARS", "8000"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TIMEOUT_SEC = int(os.getenv("RAG_OLLAMA_TIMEOUT_SEC", "90"))


def _sanitize_text_for_llm(text: str) -> str:
    # Keep line breaks and tabs, remove other control chars that may break model API.
    return "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)


def _format_context(
    docs_with_sources: List[Dict[str, Any]],
    max_chunks: Optional[int] = None,
    max_chars_per_chunk: Optional[int] = None,
    max_total_chars: Optional[int] = None,
) -> str:
    """Format retrieval results into LLM context with optional truncation."""
    parts: List[str] = []
    total_chars = 0
    selected_docs = docs_with_sources

    if max_chunks is not None and max_chunks > 0:
        selected_docs = selected_docs[:max_chunks]

    for item in selected_docs:
        src = item.get("source_info", {})
        rank = src.get("rank", "?")
        file_name = src.get("file_name", "unknown")
        page = src.get("page")
        page_info = f" (page {page})" if page is not None else ""
        header = f"[Source {rank}] {file_name}{page_info}"

        doc = item.get("document")
        content = getattr(doc, "page_content", "") or ""
        content = _sanitize_text_for_llm(content).strip()
        if max_chars_per_chunk is not None and max_chars_per_chunk > 0 and len(content) > max_chars_per_chunk:
            content = content[:max_chars_per_chunk] + "\n...[truncated]"

        block = f"{header}\n{content}"
        if max_total_chars is not None and max_total_chars > 0:
            remaining = max_total_chars - total_chars
            if remaining <= 0:
                break
            if len(block) > remaining:
                if remaining < 120:
                    break
                block = block[:remaining] + "\n...[truncated]"

        parts.append(block)
        total_chars += len(block)

    return "\n\n---\n\n".join(parts)


class RAGPipeline:
    """RAG pipeline supporting retrieval strategy, hybrid retrieval, and streaming generation."""

    def __init__(
        self,
        llm_model: Optional[str] = None,
        vectorstore: Optional[FAISS] = None,
        documents: Optional[List[Document]] = None,
        use_hybrid: bool = True,
        retrieval_config: Optional[dict] = None,
    ):
        if llm_model is None:
            model_config = get_model_config()
            llm_model = model_config.llm_model
            print(f"[RAGPipeline] Using default LLM model: {llm_model}")

        self._model_name = llm_model
        self.llm = OllamaLLM(model=llm_model)
        self.vectorstore = vectorstore
        self.use_hybrid = use_hybrid
        self.documents = documents or []

        self._prompt_max_chunks = max(1, DEFAULT_PROMPT_MAX_CHUNKS)
        self._prompt_max_chars_per_chunk = max(200, DEFAULT_PROMPT_MAX_CHARS_PER_CHUNK)
        self._prompt_max_total_chars = max(1000, DEFAULT_PROMPT_MAX_TOTAL_CHARS)

        self._retrieval_config = None
        if retrieval_config and _STRATEGY_AVAILABLE:
            self._retrieval_config = RetrievalConfig.from_dict(retrieval_config)
            print(
                f"[RAGPipeline] Retrieval strategy: {self._retrieval_config.strategy}, "
                f"topK={self._retrieval_config.topK}"
            )

        self._strategy_executor = None
        if _STRATEGY_AVAILABLE and vectorstore is not None:
            self._strategy_executor = RetrievalStrategyExecutor(
                vectorstore=vectorstore,
                documents=self.documents,
            )

        self._hybrid_retriever: Optional[HybridRetriever] = None
        if use_hybrid and vectorstore is not None and self.documents and not _STRATEGY_AVAILABLE:
            print(f"[RAGPipeline] Initialize hybrid retriever with {len(self.documents)} chunks")
            self._hybrid_retriever = HybridRetriever(
                documents=self.documents,
                vectorstore=vectorstore,
            )
        elif use_hybrid and vectorstore is not None and not self.documents and not _STRATEGY_AVAILABLE:
            print("[RAGPipeline] No documents provided, fallback to vector retrieval")
            self.use_hybrid = False

    def _retrieve(self, query: str) -> List[Dict[str, Any]]:
        if self._strategy_executor is not None:
            config = self._retrieval_config
            return self._strategy_executor.retrieve(query, config)

        if self.use_hybrid and self._hybrid_retriever:
            return self._hybrid_retriever.retrieve_with_scores(query)

        if self.vectorstore is None:
            return []

        raw = self.vectorstore.similarity_search_with_score(query, k=4)
        results: List[Dict[str, Any]] = []
        for rank, (doc, score) in enumerate(raw, start=1):
            meta = doc.metadata or {}
            results.append(
                {
                    "document": doc,
                    "source_info": {
                        "rank": rank,
                        "rrf_score": float(score),
                        "file_name": _extract_filename_from_meta(meta),
                        "page": meta.get("page"),
                        "chunk_index": meta.get("chunk_index"),
                        "source_path": meta.get("source", ""),
                    },
                    "content_preview": doc.page_content[:200],
                }
            )
        return results

    def _build_prompt_text(
        self, query: str, docs_with_sources: List[Dict[str, Any]], compact: bool = False
    ) -> str:
        if compact:
            context = _format_context(
                docs_with_sources,
                max_chunks=min(2, self._prompt_max_chunks),
                max_chars_per_chunk=min(600, self._prompt_max_chars_per_chunk),
                max_total_chars=min(2500, self._prompt_max_total_chars),
            )
        else:
            context = _format_context(
                docs_with_sources,
                max_chunks=self._prompt_max_chunks,
                max_chars_per_chunk=self._prompt_max_chars_per_chunk,
                max_total_chars=self._prompt_max_total_chars,
            )
        return PROMPT.format(context=context, question=query)

    def _invoke_with_retry(
        self, query: str, docs_with_sources: List[Dict[str, Any]]
    ) -> Optional[str]:
        tiny_context = _format_context(
            docs_with_sources,
            max_chunks=1,
            max_chars_per_chunk=350,
            max_total_chars=900,
        )
        prompt_candidates = [
            self._build_prompt_text(query, docs_with_sources, compact=False),
            self._build_prompt_text(query, docs_with_sources, compact=True),
            PROMPT.format(context=tiny_context, question=query),
        ]
        last_error: Optional[Exception] = None

        for prompt_text in prompt_candidates:
            try:
                return self._ollama_invoke(prompt_text)
            except Exception as e:
                last_error = e
                try:
                    return self.llm.invoke(prompt_text)
                except Exception as e2:
                    last_error = e2

        model_name = getattr(self.llm, "model", "")
        if isinstance(model_name, str) and model_name and ":" not in model_name:
            try:
                original_model_name = self._model_name
                self._model_name = f"{model_name}:latest"
                return self._ollama_invoke(prompt_candidates[-1])
            except Exception as e:
                last_error = e
            finally:
                self._model_name = original_model_name
            try:
                fallback_llm = OllamaLLM(model=f"{model_name}:latest")
                return fallback_llm.invoke(prompt_candidates[-1])
            except Exception as e:
                last_error = e

        if last_error:
            print(f"[RAGPipeline] LLM invoke failed after retry: {last_error}")
        return None

    def _ollama_invoke(self, prompt_text: str) -> str:
        payload = {"model": self._model_name, "prompt": prompt_text, "stream": False}
        resp = requests.post(
            OLLAMA_GENERATE_URL,
            json=payload,
            timeout=OLLAMA_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")

    def _ollama_stream(self, prompt_text: str) -> Generator[str, None, None]:
        payload = {"model": self._model_name, "prompt": prompt_text, "stream": True}
        with requests.post(
            OLLAMA_GENERATE_URL,
            json=payload,
            stream=True,
            timeout=OLLAMA_TIMEOUT_SEC,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                data = json.loads(line)
                text = data.get("response", "")
                if text:
                    yield text
                if data.get("done"):
                    break

    @staticmethod
    def _build_sources_payload(docs_with_sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "rank": item.get("source_info", {}).get("rank"),
                "file_name": item.get("source_info", {}).get("file_name"),
                "page": item.get("source_info", {}).get("page"),
                "source_path": item.get("source_info", {}).get("source_path"),
                "rrf_score": item.get("source_info", {}).get("rrf_score"),
                "content_preview": item.get("content_preview"),
            }
            for item in docs_with_sources
        ]

    def process_query(self, query: str) -> Dict[str, Any]:
        try:
            docs_with_sources = self._retrieve(query)
        except Exception as e:
            return {
                "answer": f"检索阶段失败：{e}",
                "sources": [],
                "retrieval_mode": "hybrid" if self.use_hybrid else "vector",
            }

        if not docs_with_sources:
            return {
                "answer": "未找到相关文档，无法回答该问题。",
                "sources": [],
                "retrieval_mode": "hybrid" if self.use_hybrid else "vector",
            }

        answer = self._invoke_with_retry(query, docs_with_sources)
        if not answer:
            answer = "模型服务暂时不可用（可能是上下文过长或模型负载过高），请稍后重试或切换模型。"

        return {
            "answer": answer,
            "sources": self._build_sources_payload(docs_with_sources),
            "retrieval_mode": "hybrid" if self.use_hybrid else "vector",
        }

    def stream_query(self, query: str) -> Generator[str, None, None]:
        yield f"data: 正在执行{'混合' if self.use_hybrid else '向量'}检索...\n\n"

        try:
            docs_with_sources = self._retrieve(query)
        except Exception as e:
            yield f"data: 检索失败: {e}\n\n"
            yield "data: COMPLETE\n\n"
            return

        if not docs_with_sources:
            yield "data: 未找到相关文档\n\n"
            yield "data: COMPLETE\n\n"
            return

        yield f"data: 检索完成，获取到 {len(docs_with_sources)} 个相关文档块\n\n"
        sources = self._build_sources_payload(docs_with_sources)
        for item in sources:
            item.pop("rrf_score", None)
        yield f"data: SOURCES: {json.dumps(sources, ensure_ascii=False)}\n\n"

        prompt_text = self._build_prompt_text(query, docs_with_sources, compact=False)
        yield "data: 正在生成回答...\n\n"

        try:
            for chunk in self._ollama_stream(prompt_text):
                if chunk:
                    yield f"data: {chunk}\n\n"
        except Exception as stream_error:
            yield "data: 模型响应异常，正在自动重试（降级上下文）...\n\n"
            answer = self._invoke_with_retry(query, docs_with_sources)
            if not answer:
                yield f"data: 模型服务暂时不可用: {stream_error}\n\n"
                yield "data: COMPLETE\n\n"
                return
            for paragraph in answer.split("\n"):
                if paragraph.strip():
                    yield f"data: {paragraph}\n\n"

        yield "data: COMPLETE\n\n"


def _extract_filename_from_meta(meta: Dict[str, Any]) -> str:
    for key in ("source", "file_path", "path", "filename", "file_name"):
        val = meta.get(key, "")
        if val:
            return os.path.basename(str(val))
    return "未知来源"
