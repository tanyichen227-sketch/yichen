"""
chat_send.py — 对话消息发送接口（多模型统一路由版）

支持：
  - Ollama 本地模型（默认，兼容旧行为）
  - DeepSeek / OpenAI / 腾讯混元 等云端模型（通过 model_router 路由）

模型识别规则：
  - model 字段以 "cloud:" 开头 → 提取真实 model_id 走云端
  - 否则按 model_id 在 _MODEL_CATALOG 中查找 provider
  - 未匹配 → 仍走 Ollama（兼容旧行为）
"""

import os
import logging
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()
logger = logging.getLogger(__name__)

# sys.pathimport model_router
_backend_root = str(Path(__file__).resolve().parent.parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("MODEL", "qwen2:0.5b")


def _normalize_ollama_server_url(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    if not base:
        return "http://localhost:11434"
    suffixes = ("/api/chat", "/api/generate", "/api")
    changed = True
    while changed:
        changed = False
        lower = base.lower()
        for suffix in suffixes:
            if lower.endswith(suffix):
                base = base[: -len(suffix)].rstrip("/")
                changed = True
                break
    return base or "http://localhost:11434"


def _pick_installed_model(requested: str, installed: list[str]) -> str:
    if not installed:
        return requested
    if requested in installed:
        return requested

    family = requested.split(":")[0] if requested else ""
    if family:
        same_family = [name for name in installed if name.split(":")[0] == family]
        if same_family:
            family_latest = f"{family}:latest"
            if family_latest in same_family:
                return family_latest
            return same_family[0]

    for preferred in ("qwen2:latest", "qwen2:0.5b"):
        if preferred in installed:
            return preferred
    return installed[0]


def _messages_to_prompt(messages: list[dict]) -> str:
    role_map = {"system": "System", "user": "User", "assistant": "Assistant"}
    lines = []
    for msg in messages:
        role = role_map.get(msg.get("role", "user"), "User")
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    lines.append("Assistant:")
    return "\n\n".join(lines)


def _installed_models(server_url: str, timeout: int) -> list[str]:
    import requests as sync_requests

    try:
        resp = sync_requests.get(f"{server_url}/api/tags", timeout=max(3, min(timeout, 10)))
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class OllamaSettings(BaseModel):
    serverUrl: Optional[str] = None
    timeout: Optional[int] = 60


class SendMessageRequest(BaseModel):
    message: str
    sessionId: Optional[str] = None
    history: Optional[List[dict]] = []
    model: Optional[str] = None
    ollamaSettings: Optional[OllamaSettings] = None


def _resolve_model(raw_model: str) -> tuple[str, str]:
    """
    解析 model 字段，返回 (real_model_id, provider)。

    支持格式：
      - "qwen2:0.5b"           → ('qwen2:0.5b', 'ollama')
      - "deepseek-chat"         → ('deepseek-chat', 'deepseek')
      - "cloud:deepseek:deepseek-chat" → ('deepseek-chat', 'deepseek')
    """
    if not raw_model:
        return DEFAULT_MODEL, "ollama"

    # cloud:provider:model_id ModelSelector
    if raw_model.startswith("cloud:"):
        parts = raw_model.split(":", 2)
        provider = parts[1] if len(parts) > 1 else "ollama"
        model_id = parts[2] if len(parts) > 2 else DEFAULT_MODEL
        return model_id, provider

    # _MODEL_CATALOG provider
    try:
        from multi_model.model_router import _MODEL_CATALOG

        for m in _MODEL_CATALOG:
            if m["id"] == raw_model:
                return raw_model, m.get("provider", "ollama")
    except Exception:
        pass

    return raw_model, "ollama"


async def _call_cloud_model(
    model_id: str, provider: str, messages: list, timeout: int = 60
) -> str:
    """
    调用云端模型（复用 model_router 的流式函数，收集完整回复）。
    """
    try:
        from multi_model.model_router import (
            _stream_deepseek,
            _stream_openai,
            _stream_hunyuan,
            _collect_stream,
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"无法加载 model_router: {e}")

    stream_map = {
        "deepseek": _stream_deepseek,
        "openai": _stream_openai,
        "hunyuan": _stream_hunyuan,
    }
    stream_fn = stream_map.get(provider)
    if not stream_fn:
        raise HTTPException(
            status_code=400, detail=f"不支持的云端 provider: {provider}"
        )

    try:
        reply = await _collect_stream(
            stream_fn(model_id, messages, temperature=0.7, max_tokens=2048)
        )
        if not reply:
            raise HTTPException(status_code=500, detail="云端模型返回空回复")
        return reply
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"云端模型调用失败: {e}")


@router.post("/send-message")
async def send_message(req: SendMessageRequest):
    """
    发送消息到 AI 模型，返回回复。
    自动识别本地 Ollama 模型和云端模型（DeepSeek / OpenAI / 混元）。
    """
    import requests as sync_requests

    raw_model = req.model or DEFAULT_MODEL
    model_id, provider = _resolve_model(raw_model)

    messages = []
    if req.history:
        for msg in req.history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    if not messages or messages[-1].get("content") != req.message:
        messages.append({"role": "user", "content": req.message})

    # - Cloud model -
    if provider in ("deepseek", "openai", "hunyuan", "bailian", "xinghuo"):
        logger.info(f"[chat_send] 云端模型: provider={provider}, model={model_id}")
        reply = await _call_cloud_model(model_id, provider, messages)
        return {"reply": reply, "model": model_id, "provider": provider}

    # ── Ollama Local model ──────────────────────────────────────
    server_url = (
        req.ollamaSettings.serverUrl.rstrip("/")
        if req.ollamaSettings and req.ollamaSettings.serverUrl
        else OLLAMA_BASE_URL
    )
    server_url = _normalize_ollama_server_url(server_url)
    timeout = (
        req.ollamaSettings.timeout
        if req.ollamaSettings and req.ollamaSettings.timeout
        else 60
    )
    installed = _installed_models(server_url, timeout)
    resolved_model = _pick_installed_model(model_id, installed)

    try:
        logger.info(
            f"[chat_send] Ollama: {server_url}, model={resolved_model}, 消息数={len(messages)}"
        )
        response = sync_requests.post(
            f"{server_url}/api/chat",
            json={"model": resolved_model, "messages": messages, "stream": False},
            timeout=timeout,
        )

        if response.status_code == 404:
            response = sync_requests.post(
                f"{server_url}/api/generate",
                json={
                    "model": resolved_model,
                    "prompt": _messages_to_prompt(messages),
                    "stream": False,
                    "options": {"num_predict": 2048},
                },
                timeout=timeout,
            )

        if response.status_code != 200:
            err_text = response.text or ""
            if "more system memory" in err_text or "memory" in err_text.lower():
                detail = f"模型 [{resolved_model}] 所需内存不足，请关闭其他程序或换用更小的模型（如 qwen2:0.5b）"
            elif "model" in err_text.lower() and "not found" in err_text.lower():
                detail = f"模型 [{resolved_model}] 未安装，请先执行: ollama pull {resolved_model}"
                if installed:
                    detail += f"（当前已安装: {', '.join(installed[:5])}）"
            else:
                detail = f"Ollama 服务错误（状态码 {response.status_code}）: {err_text[:200]}"
            raise HTTPException(status_code=500, detail=detail)

        data = response.json()
        reply = data.get("message", {}).get("content", "")
        if not reply:
            reply = data.get("response", "（模型无回复）")

        logger.info(f"[chat_send] Ollama 回复成功，长度: {len(reply)}")
        return {
            "reply": reply,
            "model": resolved_model,
            "requested_model": model_id,
            "provider": "ollama",
            "model_fallback": resolved_model != model_id,
        }

    except sync_requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=500,
            detail=f"连接 Ollama 失败，请检查服务是否在运行: {server_url}",
        )
    except sync_requests.exceptions.Timeout:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama 响应超时（{timeout}s），请尝试更换更小的模型或增加超时时间",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"send_message 未知错误: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")
