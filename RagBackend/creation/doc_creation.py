"""
Document creation module.

APIs:
- POST /api/creation/outline
- POST /api/creation/summary
- POST /api/creation/translate
- POST /api/creation/polish
- POST /api/creation/expand
- GET  /api/creation/templates
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/creation", tags=["文档创作"])

# Ensure backend root import path exists.
_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

_PROMPTS = {
    "outline": """你是专业中文写作助手。请根据用户提供的主题和要求，生成结构清晰的 Markdown 大纲。
要求：
1. 使用 # / ## / ### 分层；
2. 每个小节附 1-2 句说明；
3. 覆盖主题核心维度并保证逻辑连贯。

主题：{topic}
额外要求：{requirements}

请输出完整大纲：""",
    "summary": """你是专业中文摘要助手。请将以下文本压缩为高质量摘要。
要求：
1. 长度约 {length} 字；
2. 保留关键观点和重要信息；
3. 语言简洁、结构清楚（先总述再分点）。

原文：
{text}

摘要：""",
    "translate": """你是专业翻译助手。请将下列文本翻译为 {target_lang}。
要求：
1. 语义准确，不遗漏信息；
2. 表达自然流畅；
3. 专业术语尽量规范；
4. 保持原段落结构。

原文：
{text}

翻译结果：""",
    "polish": """你是专业中文润色助手。请对以下文本进行语言和格式优化。
目标：
1. 修复语法和用词问题；
2. 优化句式和连贯性；
3. 统一标点和段落格式；
4. 不改变原文核心含义。

风格：{style}
原文：
{text}

优化后：""",
    "expand": """你是专业内容创作助手。请根据大纲/要点扩写为完整 Markdown 文稿。
要求：
1. 内容充实、逻辑连贯；
2. 每个要点展开 2-3 段；
3. 使用自然过渡；
4. 目标长度约 {target_length} 字。

大纲/要点：
{outline}

扩写结果：""",
}


def _get_provider(model_id: str) -> tuple[str, str]:
    """Resolve model id and provider."""
    if model_id.startswith("cloud:"):
        parts = model_id.split(":", 2)
        provider = parts[1] if len(parts) > 1 else "ollama"
        real_model = parts[2] if len(parts) > 2 else "deepseek-chat"
        return real_model, provider

    lower = model_id.lower()
    cloud_prefixes = {
        "deepseek": "deepseek",
        "gpt": "openai",
        "o1": "openai",
        "o3": "openai",
        "hunyuan": "hunyuan",
        "claude": "openai",
    }
    for prefix, provider in cloud_prefixes.items():
        if lower.startswith(prefix):
            return model_id, provider
    return model_id, "ollama"


def _get_default_model() -> str:
    """Get default model from user config > env > fallback."""
    try:
        from models.user_model_config import get_effective_config

        cfg = get_effective_config()
        return cfg.llm_model or "deepseek-chat"
    except Exception:
        return os.getenv("MODEL", "deepseek-chat")


async def _stream_via_model_router(
    model: str,
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """Unified SSE stream for ollama and cloud providers."""
    real_model, provider = _get_provider(model)
    messages = [
        {
            "role": "system",
            "content": "你是专业的中文内容创作助手，请严格按照用户要求完成任务。",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        from multi_model.model_router import (
            _stream_ollama,
            _stream_deepseek,
            _stream_openai,
            _stream_hunyuan,
        )

        stream_map = {
            "ollama": _stream_ollama,
            "deepseek": _stream_deepseek,
            "openai": _stream_openai,
            "hunyuan": _stream_hunyuan,
        }
        stream_fn = stream_map.get(provider)
        if not stream_fn:
            yield f"data: [ERROR] 不支持的 provider: {provider}\n\n"
            return

        async for chunk in stream_fn(real_model, messages, temperature, max_tokens):
            if not chunk.startswith("data: "):
                continue

            raw = chunk[6:].strip()
            if not raw:
                continue
            if raw == "[DONE]":
                yield "data: [DONE]\n\n"
                return

            try:
                data = json.loads(raw)
            except Exception:
                yield f"data: {raw}\n\n"
                continue

            err = data.get("error")
            if err:
                yield f"data: [ERROR] {err}\n\n"
                return

            token = data.get("content", "")
            if token:
                yield f"data: {token}\n\n"
            if data.get("done"):
                yield "data: [DONE]\n\n"
                return

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"文档创作流式生成失败 model={model}: {e}")
        yield f"data: [ERROR] {e}\n\n"


class OutlineRequest(BaseModel):
    topic: str
    requirements: str = "适合学术/技术报告风格，约 3000 字"
    model: Optional[str] = None


class SummaryRequest(BaseModel):
    text: str
    length: int = 300
    model: Optional[str] = None


class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "英文"
    model: Optional[str] = None


class PolishRequest(BaseModel):
    text: str
    style: str = "正式学术风格"
    model: Optional[str] = None


class ExpandRequest(BaseModel):
    outline: str
    target_length: int = 1500
    model: Optional[str] = None


def _sse_response(stream: AsyncGenerator[str, None]) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/outline")
async def gen_outline(req: OutlineRequest):
    model = req.model or _get_default_model()
    prompt = _PROMPTS["outline"].format(topic=req.topic, requirements=req.requirements)
    return _sse_response(_stream_via_model_router(model, prompt))


@router.post("/summary")
async def gen_summary(req: SummaryRequest):
    model = req.model or _get_default_model()
    prompt = _PROMPTS["summary"].format(text=req.text[:4000], length=req.length)
    return _sse_response(_stream_via_model_router(model, prompt))


@router.post("/translate")
async def translate(req: TranslateRequest):
    model = req.model or _get_default_model()
    prompt = _PROMPTS["translate"].format(
        text=req.text[:4000],
        target_lang=req.target_lang,
    )
    return _sse_response(_stream_via_model_router(model, prompt))


@router.post("/polish")
async def polish(req: PolishRequest):
    model = req.model or _get_default_model()
    prompt = _PROMPTS["polish"].format(text=req.text[:4000], style=req.style)
    return _sse_response(_stream_via_model_router(model, prompt))


@router.post("/expand")
async def expand(req: ExpandRequest):
    model = req.model or _get_default_model()
    prompt = _PROMPTS["expand"].format(
        outline=req.outline[:3000],
        target_length=req.target_length,
    )
    return _sse_response(_stream_via_model_router(model, prompt))


@router.get("/templates")
async def get_templates():
    return {
        "types": [
            {"id": "outline", "name": "大纲生成", "desc": "根据主题自动生成结构化大纲", "icon": "📝"},
            {"id": "summary", "name": "摘要生成", "desc": "长文本压缩为关键摘要", "icon": "📄"},
            {"id": "translate", "name": "文本翻译", "desc": "多语言翻译并保持语义准确", "icon": "🌐"},
            {"id": "polish", "name": "格式优化", "desc": "润色措辞并统一文风", "icon": "✨"},
            {"id": "expand", "name": "内容扩写", "desc": "由大纲扩展为完整文稿", "icon": "📚"},
        ]
    }
