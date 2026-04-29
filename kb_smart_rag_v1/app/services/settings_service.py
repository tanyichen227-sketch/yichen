from app.models.settings import Settings
from app.services.base_service import BaseService
from app.config import Config


class SettingsService(BaseService[Settings]):
    def get(self):
        with self.session() as session:
            settings = session.query(Settings).filter_by(id="global").first()
            print("session.query settings", settings)
            if settings:
                return settings.to_dict()
            else:
                return self._get_default_settings()

    # 获取默认设置的方法
    def _get_default_settings(self) -> dict:
        """获取默认设置"""
        # 返回包含所有默认字段值的字典
        return {
            "id": "global",  # 设置主键
            "embedding_provider": "huggingface",  # 默认 embedding provider
            "embedding_model_name": "C:/Users/lenovo/.cache/modelscope/hub/models/sentence-transformers/all-MiniLM-L6-v2",  # 默认 embedding 模型
            # "embedding_model_name": "C:/Users/websk/.cache/modelscope/hub/models/sentence-transformers/all-MiniLM-L6-v2",  # 默认 embedding 模型
            "embedding_api_key": "embedding_api_key",  # 默认无 embedding API key
            "embedding_base_url": "embedding_base_url",  # 默认无 embedding base url
            "llm_provider": "deepseek",  # 默认 LLM provider
            "llm_model_name": Config.DEEPSEEK_CHAT_MODEL,  # 默认 LLM 模型
            "llm_api_key": Config.DEEPSEEK_API_KEY,  # 配置里的默认 LLM API key
            "llm_base_url": Config.DEEPSEEK_BASE_URL,  # 配置里的默认 LLM base url
            "llm_temperature": 0.7,  # 默认温度
            "chat_system_prompt": "你是一个专业的AI助手。请友好、准确地回答用户的问题。",  # 聊天系统默认提示词
            "rag_system_prompt": "你是一个专业的AI助手。请基于文档内容回答问题。",  # RAG系统提示词
            "rag_query_prompt": "文档内容：\n{context}\n\n问题：{question}\n\n请基于文档内容回答问题。如果文档中没有相关信息，请明确说明。",  # RAG查询提示词
            # "retrieval_mode": "vector",  # 默认检索模式
            "retrieval_mode": "hybrid",  # 默认检索模式
            "vector_threshold": 0.2,  # 向量检索阈值
            "keyword_threshold": 0.0,  # 关键词检索阈值
            "vector_weight": 0.7,  # 检索混合权重
            "top_k": 5,  # 返回结果数量
        }

    def update(self, data):
        with self.transaction() as session:
            settings = session.query(Settings).filter_by(id="global").first()
            if not settings:
                settings = Settings(id="global")
                session.add(settings)
            for key, value in data.items():
                if hasattr(settings, key) and value is not None:
                    setattr(settings, key, value)
            session.flush()
            session.refresh(settings)
            return settings.to_dict()


settings_service = SettingsService()
