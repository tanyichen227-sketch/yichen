from app.services.base_service import BaseService
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage
from app.utils.llm_factory import LLMFactory
from langchain_core.prompts import ChatPromptTemplate
from app.utils.logger import get_logger
from sqlalchemy import desc
from datetime import datetime
import json

logger = get_logger(__name__)


class ChatSessionService(BaseService[ChatSession]):
    def create_session(self, kb_id=None, title=None):
        with self.transaction() as session:
            if not title:
                title = "新对话"
            chat_session = ChatSession(title=title, kb_id=kb_id)
            session.add(chat_session)
            session.flush()
            session.refresh(chat_session)
            self.logger.info(f"已经创建聊天会话:{chat_session.id}")
            return chat_session.to_dict()

    def list_sessions(self, page=1, page_size=100):
        with self.transaction() as session:
            query = session.query(ChatSession)
            return self.paginate_query(
                query,
                page=page,
                page_size=page_size,
                order_by=desc(ChatSession.updated_at),
            )

    def delete_session(self, session_id):
        with self.transaction() as session:
            # TODO 应该先删除会话下面的消息再删除此会话
            chat_session = (
                session.query(ChatSession)
                .filter_by(id=session_id)
                .first()
            )
            if not chat_session:
                return False
            session.delete(chat_session)
            self.logger.info(f"删除会话{session_id}成功")
            return True

    def delete_all_session(self):
        with self.transaction() as session:
            count = session.query(ChatSession).delete()
            self.logger.info(f"已经删除了{count}个聊天会话")
            return count

    def get_messages(self, session_id):
        with self.session() as session:
            # 查询此对话的历史消息
            messages = (
                session.query(ChatMessage)
                .filter_by(session_id=session_id)
                .order_by(ChatMessage.created_at)
                .all()
            )
            return [message.to_dict() for message in messages]

    def add_message(self, session_id, role, content, sources=None):
        with self.transaction() as session:
            # 构建新的消息对象
            sources_str = json.dumps(sources) if sources is not None else None
            message = ChatMessage(
                session_id=session_id, role=role, content=content, sources=sources_str
            )
            session.add(message)
            # 查询出当前的会话对象
            chat_session = session.query(ChatSession).filter_by(id=session_id).first()
            if chat_session:
                # 更新会话的更新时间
                chat_session.updated_at = datetime.now()
                # 如果是此消息的用户角色是用户的话,并且此对话标题为空或者是新对话,说明还没有设置标题
                if role == "user" and (
                    not chat_session.title or chat_session.title == "新对话"
                ):
                    title = content[:30] + ("..." if len(content) > 30 else "")
                    chat_session.title = title
            session.flush()
            session.refresh(message)
            return message.to_dict()

    def get_session_by_id(self, session_id):
        with self.session() as session:
            query = session.query(ChatSession).filter_by(id=session_id)
            chat_session = query.first()
            if chat_session:
                return chat_session.to_dict()
            else:
                return None


session_service = ChatSessionService()
