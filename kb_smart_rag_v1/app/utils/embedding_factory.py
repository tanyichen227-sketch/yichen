import os
from app.services.settings_service import settings_service
from app.utils.logger import get_logger
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import OllamaEmbeddings

logger = get_logger(__name__)

class EmbeddingFactory:
    @staticmethod
    def create_embeddings():
        settings = settings_service.get()
        embedding_provider = settings.get("embedding_provider")
        # 这里从数据库拿到的是 "C:/Users/lenovo/..."
        embedding_model_name = settings.get("embedding_model_name")
        embedding_api_key = settings.get("embedding_api_key")
        embedding_base_url = settings.get("embedding_base_url")

        # --- 核心修复逻辑开始 ---
        # 如果是本地模型 provider，且给出的路径不存在，则提取模型名，尝试在线下载
        if embedding_provider == "huggingface":
            if os.path.isabs(embedding_model_name) and not os.path.exists(embedding_model_name):
                # 提取路径最后一部分，比如 "all-MiniLM-L6-v2"
                fallback_name = os.path.basename(embedding_model_name)
                logger.warning(f"本地路径不存在: {embedding_model_name}, 尝试使用模型名: {fallback_name}")
                embedding_model_name = fallback_name
        # --- 核心修复逻辑结束 ---

        try:
            if embedding_provider == "huggingface":
                embeddings = HuggingFaceEmbeddings(
                    model_name=embedding_model_name,
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True},
                )
                logger.info(f"创建HuggingFaceEmbeddings成功: {embedding_model_name}")
                
            elif embedding_provider == "openai":
                embeddings = OpenAIEmbeddings(
                    model_name=embedding_model_name, 
                    openai_api_key=embedding_api_key
                )
                logger.info(f"创建OpenAIEmbeddings成功: {embedding_model_name}")
                
            elif embedding_provider == "ollama":
                embeddings = OllamaEmbeddings(
                    model_name=embedding_model_name, 
                    base_url=embedding_base_url
                )
                logger.info(f"创建OllamaEmbeddings成功: {embedding_model_name}")
                
            else:
                logger.warning(f"未知的提供商 {embedding_provider}, 降级使用 huggingface")
                # 默认保底模型名
                default_model = "sentence-transformers/all-MiniLM-L6-v2"
                embeddings = HuggingFaceEmbeddings(
                    model_name=default_model,
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True},
                )
            return embeddings

        except Exception as e:
            logger.error(f"创建向量模型失败: {e}", exc_info=True)
            # 最后的保底措施：如果不论路径还是名称都失败了，使用固定的官方模型名强制尝试下载
            logger.info("正在尝试使用官方默认模型进行保底加载...")
            return HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )