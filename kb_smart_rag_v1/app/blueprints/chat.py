"""
聊天相关的路由
"""

from flask import (
    Blueprint,
    request,
    flash,
    render_template,
    redirect,
    url_for,
    Response,
    stream_with_context,
)
import os
from app.blueprints.utils import (
    success_response,
    error_response,
    handle_api_error,
    get_pagination_params,
)
from app.utils.logger import get_logger
import json
from app.services.chat_service import chat_service
from app.services.knowledgebase_service import kb_service
from app.services.chat_session_service import session_service

logger = get_logger(__name__)

bp = Blueprint("chat", __name__)


@bp.route("/chat")
def chat_view():
    result = kb_service.list(page=1, page_size=100)
    return render_template("chat.html", knowledgebases=result["items"])


@bp.route("/api/v1/chat", methods=["POST"])
@handle_api_error
def common_chat():
    # 现在第一步只实现普通聊天，不支持知识库
    # 获取请求体JSON数据
    data = request.get_json()
    question = data["question"].strip()
    if not question:
        return error_response(f"用户的提问内容为空", 400)
    session_id = data.get("session_id")
    # 初始历史消息
    history = None
    if session_id:
        # 获取此会话的历史消息
        history_messages = session_service.get_messages(session_id)
        # 将历史消息转换为对话格式,仅保留最近的10条消息
        history = [
            {"role": message.get("role"), "content": message.get("content")}
            for message in history_messages[-10:]  # 只取最近的10条
        ]
    else:
        chat_session = session_service.create_session()
        session_id = chat_session["id"]
    # 将用户的问题消息保存到当前会话的消息表中
    session_service.add_message(session_id, "user", question)

    @stream_with_context
    def generate():
        try:
            # 用于缓存完整的答案内容
            full_answer = ""
            for chunk in chat_service.chat_stream(question=question, history=history):
                if chunk.get("type") == "content":
                    full_answer += chunk.get("content")
                yield f"data: {json.dumps(chunk,ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            if full_answer:
                session_service.add_message(session_id, "assistant", full_answer)
        except Exception as e:
            logger.error(f"流式输出出错:{e}")
            error_chunk = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_chunk,ensure_ascii=False)}\n\n"

    response = Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
    )
    return response


@bp.route("/api/v1/sessions", methods=["POST"])
@handle_api_error
def api_create_session():
    # 现在第一步只实现普通聊天，不支持知识库
    # 获取请求体JSON数据
    data = request.get_json()
    # 获取会话的标题
    title = data.get("title", "")

    session_dict = session_service.create_session(
        title=title
    )
    return success_response(session_dict)


@bp.route("/api/v1/sessions", methods=["GET"])
@handle_api_error
def api_list_sessions():
    # 现在第一步只实现普通聊天，不支持知识库
    page, page_size = get_pagination_params(max_page_size=1000)
    result = session_service.list_sessions(
        page=page, page_size=page_size
    )
    return success_response(result)


@bp.route("/api/v1/sessions/<session_id>", methods=["DELETE"])
@handle_api_error
def api_delete_session(session_id):
    success = session_service.delete_session(session_id)
    if success:
        return success_response(None, "会话删除成功")
    else:
        return error_response("会话删除失败", 404)


@bp.route("/api/v1/sessions", methods=["DELETE"])
@handle_api_error
def api_delete_all_session():
    success = session_service.delete_all_session()
    if success:
        return success_response(None, "会话全部删除成功")
    else:
        return error_response("会话全部删除失败", 404)


@bp.route("/api/v1/sessions/<session_id>", methods=["GET"])
@handle_api_error
def api_get_session(session_id):
    session_obj = session_service.get_session_by_id(session_id)
    if not session_obj:
        return error_response("会话不存在", 404)
    messages = session_service.get_messages(session_id)
    return success_response({"session": session_obj, "messages": messages})


@bp.route("/api/v1/knowledgebases/<kb_id>/chat", methods=["POST"])
@handle_api_error
def rag_chat(kb_id):
    # 支持知识库检索聊天
    kb = kb_service.get_by_id(kb_id)
    if not kb:
        return error_response("知识库未找到", 404)
    data = request.get_json()
    question = data.get("question", "").strip()
    session_id = data.get("session_id")
    max_tokens = int(data.get("max_tokens", 1024))
    max_tokens = max(1, min(max_tokens, 10240))
    # 创建新的会话
    if not session_id:
        chat_session = session_service.create_session(
            kb_id=kb_id
        )
        session_id = chat_session["id"]
    # 保存用户的问题到消息列表中
    session_service.add_message(session_id, "user", question)

    @stream_with_context
    def generate():
        try:
            # 初始完整的回答
            full_answer = ""
            for chunk in chat_service.ask_stream(kb_id, question=question):
                if chunk.get("type") == "content":
                    full_answer += chunk.get("content", "")
                elif chunk.get("type") == "done":
                    # 当回答结束的时候，把引用来文档来源返回
                    sources = chunk.get("sources")
                # 以SSE的方式输出该块的内容
                yield f"data: {json.dumps(chunk,ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            # 如果有回复内容，则保存AI的回复到数据库消息里
            if full_answer:
                session_service.add_message(
                    session_id, "assistant", full_answer, sources
                )

        except Exception as e:
            logger.error(f"流式输出时出错:{e}")
            error_chunk = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_chunk,ensure_ascii=False)}\n\n"

    response = Response(
        generate(),
        mimetype="text/event-stream",  ## 响应的内容类型
        headers={  # 响应头的类型
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
    )
    return response
