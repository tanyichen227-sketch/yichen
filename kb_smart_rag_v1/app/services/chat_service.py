from app.services.settings_service import settings_service
from app.utils.llm_factory import LLMFactory
from langchain_core.prompts import ChatPromptTemplate
from app.utils.logger import get_logger
from app.services.rag_service import rag_service

logger = get_logger(__name__)


class ChatService:
    def __init__(self):
        self.settings = settings_service.get()

    def chat_stream(self, question, history=[]):
        temperature = float(self.settings.get("llm_temperature", " 0.7"))
        temperature = max(0.0, min(temperature, 2.0))
        chat_system_prompt = self.settings.get("chat_system_prompt")
        if not chat_system_prompt:
            chat_system_prompt = "你是一个专业的AI助手。请友好、准确地回答用户的问题。"
        llm = LLMFactory.create_llm(self.settings, temperature=temperature)
        messages = [("system", chat_system_prompt), ("human", question)]
        prompt = ChatPromptTemplate.from_messages(messages)
        chain = prompt | llm
        # 服务器准备开始向客户端发送消息
        yield {"type": "start", "content": ""}
        full_answer = ""
        try:
            # 遍历大模型生成的每一段代码
            for chunk in chain.stream({}):
                if hasattr(chunk, "content") and chunk.content:
                    content = chunk.content
                    full_answer += content
                    yield {"type": "content", "content": content}
        except Exception as e:
            logger.error(f"流式生成时出错:{e}")
            yield {"type": "error", "content": f"流式生成时出错:{e}"}
            return
        yield {"type": "done", "content": "", "metadata": {"question": question}}

    # 流式知识库问答接口
    def ask_stream(self, kb_id, question):
        return rag_service.ask_stream(kb_id=kb_id, question=question)


chat_service = ChatService()
