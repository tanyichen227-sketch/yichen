import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests
from docx import Document
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from langchain_community.document_loaders import PyPDFLoader
from pydantic import BaseModel

router = APIRouter()

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from models.model_config import get_model_config


TYPE_PERSON = "\u4eba\u7269"
TYPE_FACTION = "\u95e8\u6d3e"
TYPE_ORG = "\u7ec4\u7ec7"
TYPE_EVENT = "\u4e8b\u4ef6"
TYPE_PLACE = "\u5730\u70b9"
TYPE_CONCEPT = "\u6982\u5ff5"

REL_RELATED = "\u76f8\u5173"
REL_BELONGS = "\u5c5e\u4e8e"
REL_PARTICIPATE = "\u53c2\u4e0e"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_KB_ROOT = PROJECT_ROOT / "test"
LOCAL_KB_ROOT = PROJECT_ROOT / "local-KLB-files"
SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk")
CHUNK_SIZE = int(os.getenv("KG_CHUNK_SIZE", "3500"))
DEFAULT_KG_CHUNK_TIMEOUT_SEC = int(os.getenv("KG_CHUNK_TIMEOUT_SEC", "45"))
DEFAULT_KG_DEADLINE_SEC = int(os.getenv("KG_DEADLINE_SEC", "120"))
DEFAULT_KG_MAX_CHUNKS_PER_FILE = int(os.getenv("KG_MAX_CHUNKS_PER_FILE", "10"))
MAX_ENTITIES_PER_CHUNK = int(os.getenv("KG_MAX_ENTITIES_PER_CHUNK", "25"))
TYPE_COMPLETION_ENABLED = os.getenv("KG_TYPE_COMPLETION_ENABLED", "1") != "0"

PERSON_STOPWORDS = {
    "\u6211\u4eec",
    "\u4f60\u4eec",
    "\u4ed6\u4eec",
    "\u5979\u4eec",
    "\u8fd9\u4e2a",
    "\u90a3\u4e2a",
    "\u53ef\u4ee5",
    "\u5c31\u662f",
    "\u4e0d\u662f",
    "\u5982\u679c",
    "\u56e0\u4e3a",
    "\u6240\u4ee5",
    "\u7136\u540e",
}

FACTION_SUFFIXES = (
    "\u6d3e",
    "\u95e8",
    "\u5b97",
    "\u5e2e",
    "\u6559",
    "\u76df",
    "\u5bab",
    "\u5c71\u5e84",
    "\u5e9c",
    "\u5802",
    "\u9601",
    "\u4f1a",
    "\u5b66\u9662",
    "\u5927\u5b66",
    "\u516c\u53f8",
    "\u96c6\u56e2",
)

EVENT_SUFFIXES = (
    "\u5927\u4f1a",
    "\u4f1a\u8bae",
    "\u4e4b\u6218",
    "\u6218\u5f79",
    "\u6218\u4e89",
    "\u4e8b\u4ef6",
    "\u884c\u52a8",
    "\u8d77\u4e49",
    "\u8ba1\u5212",
    "\u6bd4\u6b66",
    "\u51b3\u6218",
    "\u56f4\u653b",
    "\u6551\u63f4",
    "\u5e86\u5178",
)

RELATION_KEYWORDS = {
    "\u5e08\u7236": "\u5e08\u5f92",
    "\u5f1f\u5b50": "\u5e08\u5f92",
    "\u5f92\u5f1f": "\u5e08\u5f92",
    "\u7236\u4eb2": "\u4eb2\u5c5e",
    "\u6bcd\u4eb2": "\u4eb2\u5c5e",
    "\u5144\u5f1f": "\u4eb2\u5c5e",
    "\u59d0\u59b9": "\u4eb2\u5c5e",
    "\u4e08\u592b": "\u4f34\u4fa3",
    "\u59bb\u5b50": "\u4f34\u4fa3",
    "\u670b\u53cb": "\u670b\u53cb",
    "\u654c": "\u654c\u5bf9",
    "\u7ed3\u76df": "\u7ed3\u76df",
    "\u5408\u4f5c": "\u5408\u4f5c",
    "\u5bf9\u6297": "\u5bf9\u6297",
}

NODE_TYPE_ALIASES = {
    "person": TYPE_PERSON,
    "people": TYPE_PERSON,
    "\u4eba\u7269": TYPE_PERSON,
    "\u4eba\u540d": TYPE_PERSON,
    "role": TYPE_PERSON,
    "faction": TYPE_FACTION,
    "sect": TYPE_FACTION,
    "\u95e8\u6d3e": TYPE_FACTION,
    "organization": TYPE_ORG,
    "org": TYPE_ORG,
    "\u7ec4\u7ec7": TYPE_ORG,
    "\u52bf\u529b": TYPE_ORG,
    "event": TYPE_EVENT,
    "\u4e8b\u4ef6": TYPE_EVENT,
    "location": TYPE_PLACE,
    "place": TYPE_PLACE,
    "\u5730\u70b9": TYPE_PLACE,
    "concept": TYPE_CONCEPT,
    "\u6982\u5ff5": TYPE_CONCEPT,
}

NOISE_ENTITY_WORDS = {
    "\u6587\u672c",
    "\u5185\u5bb9",
    "\u6bb5\u843d",
    "\u7ae0\u8282",
    "\u7bc7\u7ae0",
    "\u6545\u4e8b",
    "\u60c5\u8282",
    "\u4e3b\u9898",
    "\u4e0a\u6587",
    "\u4e0b\u6587",
    "\u4f5c\u8005",
    "\u4eba\u7269",
    "\u89d2\u8272",
    "\u5bf9\u8bdd",
}

PERSON_NAME_BLOCK_CHARS = set("的是了在与和及并中上下而对将被为着把啊呢吗")


class ProcessFileRequest(BaseModel):
    filename: str


class ProcessFolderRequest(BaseModel):
    folder_path: str
    max_files: Optional[int] = None
    max_chunks_per_file: Optional[int] = None
    chunk_timeout_sec: Optional[int] = None
    deadline_sec: Optional[int] = None
    save_partial: bool = True


class ProcessFilesResponse(BaseModel):
    message: str
    graph_data: dict


def _empty_graph_data() -> dict:
    return {
        "nodes": [],
        "edges": [],
        "meta": {
            "total_chunks": 0,
            "processed_chunks": 0,
            "failed_chunks": 0,
            "is_partial": False,
        },
    }


def _normalize_ollama_base_url(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    if not base:
        return "http://localhost:11434"
    for suffix in ("/api/chat", "/api/generate", "/api"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
    return base or "http://localhost:11434"


def _list_installed_models(base_url: str, timeout_sec: int = 8) -> List[str]:
    try:
        res = requests.get(f"{base_url}/api/tags", timeout=timeout_sec)
        if res.status_code != 200:
            return []
        data = res.json()
        return [item.get("name", "") for item in data.get("models", []) if item.get("name")]
    except Exception:
        return []


def _pick_installed_model(requested: str, installed: List[str]) -> str:
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

    for preferred in (
        "qwen2.5:latest",
        "qwen2:latest",
        "qwen3:latest",
        "qwen2:0.5b",
        "llama3:latest",
        "mistral:latest",
    ):
        if preferred in installed:
            return preferred
    return installed[0]


def _pick_qwen_model(base_url: str, fallback_model: str) -> str:
    installed = _list_installed_models(base_url)
    if not installed:
        return fallback_model
    qwen = [name for name in installed if "qwen" in name.lower()]
    if qwen:
        for preferred in ("qwen2.5:latest", "qwen2:latest", "qwen3:latest", "qwen2:0.5b"):
            if preferred in qwen:
                return preferred
        latest = [name for name in qwen if name.lower().endswith(":latest")]
        if latest:
            return latest[0]
        return qwen[0]
    return _pick_installed_model(fallback_model, installed)


def _resolve_ollama_runtime() -> Tuple[str, str]:
    base_url = _normalize_ollama_base_url(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    model = get_model_config().kg_model
    try:
        from models.user_model_config import get_effective_config

        cfg = get_effective_config()
        base_url = _normalize_ollama_base_url(cfg.ollama_base_url or base_url)
        model = getattr(cfg, "kg_model", None) or cfg.llm_model or model
    except Exception:
        pass

    installed = _list_installed_models(base_url)
    model = _pick_installed_model(model, installed)
    return base_url, model


def _sanitize_entity_name(value: str) -> str:
    text = str(value or "").strip()
    text = text.strip("\"'`，。；、,.!?！？()（）[]{}")
    text = re.sub(r"\s+", "", text)
    if text in {"", "null", "None", "undefined"}:
        return ""
    return text[:60]


def _is_noise_entity(name: str) -> bool:
    text = _sanitize_entity_name(name)
    if not text:
        return True
    if text in NOISE_ENTITY_WORDS:
        return True
    if len(text) <= 1:
        return True
    if re.fullmatch(r"[0-9A-Za-z_\-]+", text):
        return False
    if len(text) > 12 and not any(text.endswith(s) for s in FACTION_SUFFIXES + EVENT_SUFFIXES):
        return True
    return False


def _looks_like_person_name(name: str) -> bool:
    text = _sanitize_entity_name(name)
    if not text:
        return False
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", text):
        return False
    if any(ch in PERSON_NAME_BLOCK_CHARS for ch in text):
        return False
    if text in PERSON_STOPWORDS:
        return False
    return True


def _normalize_node_type(raw_type: str) -> str:
    if not raw_type:
        return TYPE_CONCEPT

    value = str(raw_type).strip()
    key = value.lower()
    if key in NODE_TYPE_ALIASES:
        return NODE_TYPE_ALIASES[key]

    collapsed = value.replace("／", "/").replace("、", "/").replace("，", "/")
    if "/" in collapsed or "|" in collapsed or "," in collapsed:
        parts = [part for part in re.split(r"[\/|,，、\s]+", collapsed) if part]
        for part in parts:
            pkey = part.strip().lower()
            if pkey in NODE_TYPE_ALIASES and NODE_TYPE_ALIASES[pkey] != TYPE_CONCEPT:
                return NODE_TYPE_ALIASES[pkey]

    if TYPE_PERSON in value or "\u4eba" in value:
        return TYPE_PERSON
    if TYPE_FACTION in value:
        return TYPE_FACTION
    if TYPE_ORG in value or "\u52bf\u529b" in value:
        return TYPE_ORG
    if TYPE_EVENT in value:
        return TYPE_EVENT
    if TYPE_PLACE in value:
        return TYPE_PLACE

    for suffix in FACTION_SUFFIXES:
        if value.endswith(suffix):
            return TYPE_FACTION
    for suffix in EVENT_SUFFIXES:
        if value.endswith(suffix):
            return TYPE_EVENT
    return value if len(value) <= 8 else TYPE_CONCEPT


def _coerce_type_label(raw_type: str) -> str:
    normalized = _normalize_node_type(raw_type)
    if normalized in {TYPE_PERSON, TYPE_FACTION, TYPE_ORG, TYPE_EVENT, TYPE_PLACE, TYPE_CONCEPT}:
        return normalized
    return TYPE_CONCEPT


def split_text_into_chunks(text: str, chunk_size: int) -> List[str]:
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _score_chunk_priority(chunk: str) -> int:
    keywords = [
        "\u4eba\u7269",
        "\u5173\u7cfb",
        "\u95e8\u6d3e",
        "\u7ec4\u7ec7",
        "\u4e8b\u4ef6",
        "\u5e08\u7236",
        "\u5f1f\u5b50",
        "\u638c\u95e8",
        "\u5e2e\u4e3b",
        "\u7ed3\u76df",
        "\u5bf9\u6297",
        "\u6bd4\u6b66",
        "\u51b3\u6218",
    ]
    score = 0
    for kw in keywords:
        score += chunk.count(kw) * 3

    # Prefer chunks with possible person names.
    person_like = re.findall(r"[\u4e00-\u9fff]{2,4}", chunk)
    score += sum(1 for token in person_like if _looks_like_person_name(token))

    faction_count = len(_extract_faction_candidates(chunk))
    event_count = len(_extract_event_candidates(chunk))
    score += faction_count * 4 + event_count * 4

    # Penalize boilerplate/table-of-contents style chunks.
    boilerplate_hits = sum(chunk.count(word) for word in ("\u76ee\u5f55", "\u51fa\u7248", "\u4f5c\u8005", "\u524d\u8a00"))
    score -= boilerplate_hits * 3
    return score


def _select_chunk_indexes(chunks: List[str], max_chunks: Optional[int]) -> List[int]:
    if not chunks:
        return []
    if max_chunks is None or max_chunks <= 0 or len(chunks) <= max_chunks:
        return list(range(len(chunks)))
    scored = [(idx, _score_chunk_priority(chunk)) for idx, chunk in enumerate(chunks)]
    scored.sort(key=lambda item: (item[1], -item[0]), reverse=True)
    return sorted(idx for idx, _ in scored[:max_chunks])


def resolve_kb_dir(kb_id: str) -> Path:
    kb_id = str(kb_id).strip()
    exact = LOCAL_KB_ROOT / kb_id
    if exact.is_dir():
        return exact
    if LOCAL_KB_ROOT.exists():
        for child in LOCAL_KB_ROOT.iterdir():
            if child.is_dir() and child.name.lower() == kb_id.lower():
                return child
    return exact


def _resolve_folder_path(folder_path: str) -> Path:
    kb_path = resolve_kb_dir(folder_path)
    if kb_path.exists():
        return kb_path
    raw = Path(folder_path).expanduser()
    if raw.exists():
        return raw
    candidate = (PROJECT_ROOT / folder_path).resolve()
    if candidate.exists():
        return candidate
    return kb_path


def read_file_sample(file_path: str, size: int = 2048) -> bytes:
    try:
        with open(file_path, "rb") as f:
            return f.read(size)
    except Exception:
        return b""


def looks_like_text_bytes(sample: bytes) -> bool:
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    control = sum(1 for b in sample if b < 32 and b not in (9, 10, 13))
    return control / max(len(sample), 1) < 0.05


def detect_file_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in SUPPORTED_EXTENSIONS:
        return ext
    sample = read_file_sample(file_path)
    if sample.startswith(b"%PDF"):
        return ".pdf"
    if sample.startswith(b"PK\x03\x04"):
        return ".docx"
    if looks_like_text_bytes(sample):
        return ".txt"
    return ext


def should_process_file(file_path: Path) -> bool:
    if not file_path.is_file():
        return False
    if file_path.name.startswith("."):
        return False
    if file_path.name == "knowledge_data.json":
        return False
    if file_path.name.endswith("_graph.json"):
        return False
    return detect_file_type(str(file_path)) in SUPPORTED_EXTENSIONS


def list_processable_files(folder_path: Path) -> List[Path]:
    if not folder_path.exists():
        return []
    return sorted([item for item in folder_path.iterdir() if should_process_file(item)], key=lambda x: x.name.lower())


def list_graph_files(folder_path: Path) -> List[Path]:
    if not folder_path.exists():
        return []
    return sorted(
        [item for item in folder_path.iterdir() if item.is_file() and item.name.endswith("_graph.json")],
        key=lambda x: x.name.lower(),
    )


def _sample_text_segments(text: str, max_chars: Optional[int]) -> str:
    if not max_chars or max_chars <= 0 or len(text) <= max_chars:
        return text
    seg_count = 3
    seg_len = max(800, max_chars // seg_count)
    starts = [0, max((len(text) - seg_len) // 2, 0), max(len(text) - seg_len, 0)]
    parts = []
    seen = set()
    for start in starts:
        part = text[start : start + seg_len]
        if not part:
            continue
        key = part[:120]
        if key in seen:
            continue
        seen.add(key)
        parts.append(part)
    return "\n".join(parts)[:max_chars]


def _extract_pdf_text_pypdf(file_path: str, max_chars: Optional[int] = None) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        page_count = len(reader.pages)
        if page_count == 0:
            return ""

        if max_chars and max_chars > 0:
            sample_pages = min(page_count, max(6, max_chars // 1800))
            if sample_pages <= 1:
                page_indexes = [0]
            else:
                page_indexes = sorted(
                    {
                        int(round(i * (page_count - 1) / (sample_pages - 1)))
                        for i in range(sample_pages)
                    }
                )
        else:
            page_indexes = list(range(page_count))

        parts = []
        total = 0
        for idx in page_indexes:
            page = reader.pages[idx]
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            parts.append(text)
            total += len(text)
            if max_chars and total >= max_chars:
                break
        return "\n".join(parts)
    except Exception:
        return ""


def _extract_pdf_text_pdfplumber(file_path: str, max_chars: Optional[int] = None) -> str:
    try:
        import pdfplumber

        parts = []
        total = 0
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            if max_chars and max_chars > 0 and page_count > 0:
                sample_pages = min(page_count, max(6, max_chars // 1800))
                if sample_pages <= 1:
                    page_indexes = [0]
                else:
                    page_indexes = sorted(
                        {
                            int(round(i * (page_count - 1) / (sample_pages - 1)))
                            for i in range(sample_pages)
                        }
                    )
            else:
                page_indexes = list(range(page_count))

            for idx in page_indexes:
                page = pdf.pages[idx]
                text = (page.extract_text() or "").strip()
                if not text:
                    continue
                parts.append(text)
                total += len(text)
                if max_chars and total >= max_chars:
                    break
        return "\n".join(parts)
    except Exception:
        return ""


def extract_pdf_text(file_path: str, max_chars: Optional[int] = None) -> str:
    # Fast path for large files: incremental page extraction.
    text = _extract_pdf_text_pypdf(file_path, max_chars=max_chars)
    if text.strip():
        return text

    try:
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        parts = []
        total = 0
        for doc in docs:
            item = (doc.page_content or "").strip()
            if not item:
                continue
            parts.append(item)
            total += len(item)
            if max_chars and total >= max_chars:
                break
        text = "\n".join(parts)
        if text.strip():
            return text
    except Exception as e:
        print(f"[KG] PyPDFLoader failed: {e}")

    text = _extract_pdf_text_pdfplumber(file_path, max_chars=max_chars)
    if text.strip():
        return text
    return ""


def extract_doc_text(file_path: str) -> str:
    try:
        doc = Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs)
    except Exception as e:
        print(f"[KG] Failed to read doc/docx: {e}")
        return ""


def extract_text_file(file_path: str, max_chars: Optional[int] = None) -> str:
    for enc in TEXT_ENCODINGS:
        try:
            with open(file_path, "r", encoding=enc) as f:
                text = f.read()
                return _sample_text_segments(text, max_chars)
        except Exception:
            continue
    return ""


def extract_text(file_path: str, max_chars: Optional[int] = None) -> str:
    file_type = detect_file_type(file_path)
    if file_type == ".pdf":
        return extract_pdf_text(file_path, max_chars=max_chars)
    if file_type in {".doc", ".docx"}:
        return extract_doc_text(file_path)
    if file_type in {".txt", ".md"}:
        return extract_text_file(file_path, max_chars=max_chars)
    return ""


def _strip_json_noise(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "")
    cleaned = re.sub(r"(?m)^\s*//.*$", "", cleaned)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned.strip()


def _candidate_json_texts(generated_text: str) -> List[str]:
    candidates: List[str] = []
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", generated_text, flags=re.IGNORECASE):
        if block.strip():
            candidates.append(block.strip())
    start = generated_text.find("{")
    end = generated_text.rfind("}")
    if 0 <= start < end:
        candidates.append(generated_text[start : end + 1].strip())

    unique: List[str] = []
    seen = set()
    for item in candidates:
        key = item[:2000]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _safe_json_loads(text: str) -> Optional[dict]:
    cleaned = _strip_json_noise(text)
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if 0 <= start < end:
            return json.loads(cleaned[start : end + 1])
    except Exception:
        return None
    return None


def _normalize_nodes(raw_nodes) -> List[dict]:
    nodes: Dict[str, dict] = {}
    if isinstance(raw_nodes, dict):
        raw_nodes = [raw_nodes]
    if not isinstance(raw_nodes, list):
        return []

    for node in raw_nodes:
        if isinstance(node, str):
            entity_id = _sanitize_entity_name(node)
            if entity_id and not _is_noise_entity(entity_id):
                inferred_type = TYPE_PERSON if _looks_like_person_name(entity_id) else TYPE_CONCEPT
                nodes[entity_id] = {"id": entity_id, "label": entity_id, "type": inferred_type}
            continue

        if not isinstance(node, dict):
            continue
        entity_id = _sanitize_entity_name(
            node.get("id") or node.get("name") or node.get("label") or node.get("entity") or node.get("value")
        )
        if not entity_id or _is_noise_entity(entity_id):
            continue

        label = _sanitize_entity_name(node.get("label") or node.get("name") or entity_id) or entity_id
        if _is_noise_entity(label):
            label = entity_id
        raw_type = _sanitize_entity_name(node.get("type") or node.get("category") or "")
        if not raw_type and label in {TYPE_PERSON, TYPE_FACTION, TYPE_ORG, TYPE_EVENT, TYPE_PLACE, TYPE_CONCEPT}:
            raw_type = label
            label = entity_id

        node_type = _coerce_type_label(raw_type)
        if node_type == TYPE_PERSON and not _looks_like_person_name(entity_id):
            node_type = TYPE_CONCEPT
        if node_type == TYPE_CONCEPT:
            if _looks_like_person_name(entity_id):
                node_type = TYPE_PERSON
            elif any(entity_id.endswith(s) for s in FACTION_SUFFIXES):
                node_type = TYPE_FACTION
            elif any(entity_id.endswith(s) for s in EVENT_SUFFIXES):
                node_type = TYPE_EVENT

        if entity_id not in nodes:
            nodes[entity_id] = {"id": entity_id, "label": label, "type": node_type}
    return list(nodes.values())


def _normalize_edges(raw_edges) -> List[dict]:
    edges: Dict[Tuple[str, str, str], dict] = {}
    if isinstance(raw_edges, dict):
        raw_edges = [raw_edges]
    if not isinstance(raw_edges, list):
        return []

    for edge in raw_edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 3:
            source = _sanitize_entity_name(edge[0])
            label = _sanitize_entity_name(edge[1]) or REL_RELATED
            target = _sanitize_entity_name(edge[2])
        elif isinstance(edge, dict):
            source = _sanitize_entity_name(edge.get("source") or edge.get("from") or edge.get("subject") or edge.get("head"))
            target = _sanitize_entity_name(edge.get("target") or edge.get("to") or edge.get("object") or edge.get("tail"))
            label = _sanitize_entity_name(edge.get("label") or edge.get("relation") or edge.get("predicate") or edge.get("type"))
            label = label or REL_RELATED
        else:
            continue
        if not source or not target:
            continue
        edges[(source, target, label)] = {"source": source, "target": target, "label": label}
    return list(edges.values())


def _normalize_graph_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {"nodes": [], "edges": []}

    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if raw_nodes is None:
        raw_nodes = payload.get("entities") or payload.get("people") or payload.get("vertex")
    if raw_edges is None:
        raw_edges = payload.get("relationships") or payload.get("relations") or payload.get("triples")

    nodes = _normalize_nodes(raw_nodes)
    edges = _normalize_edges(raw_edges)

    node_map = {n["id"]: n for n in nodes if n.get("id")}
    for edge in edges:
        source = edge.get("source", "")
        target = edge.get("target", "")
        if source and source not in node_map:
            node_map[source] = {"id": source, "label": source, "type": TYPE_CONCEPT}
        if target and target not in node_map:
            node_map[target] = {"id": target, "label": target, "type": TYPE_CONCEPT}
    nodes = list(node_map.values())

    edge_map: Dict[Tuple[str, str, str], dict] = {}
    for edge in edges:
        source = edge.get("source", "")
        target = edge.get("target", "")
        label = edge.get("label", "") or REL_RELATED
        if source and target:
            edge_map[(source, target, label)] = {"source": source, "target": target, "label": label}

    if len(nodes) > MAX_ENTITIES_PER_CHUNK:
        nodes = nodes[:MAX_ENTITIES_PER_CHUNK]
        allowed = {n["id"] for n in nodes}
        edge_map = {k: e for k, e in edge_map.items() if e["source"] in allowed and e["target"] in allowed}

    return {"nodes": nodes, "edges": list(edge_map.values())}


def _extract_person_candidates(text: str) -> List[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
    out: List[str] = []
    seen = set()
    for token in tokens:
        if token in PERSON_STOPWORDS:
            continue
        if any(token.endswith(suffix) for suffix in FACTION_SUFFIXES + EVENT_SUFFIXES):
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= 8:
            break
    return out


def _extract_faction_candidates(text: str) -> List[str]:
    pattern = r"[\u4e00-\u9fffA-Za-z0-9]{2,16}(?:派|门|宗|帮|教|盟|宫|山庄|府|堂|阁|会|学院|大学|公司|集团)"
    out: List[str] = []
    seen = set()
    for item in re.findall(pattern, text):
        name = _sanitize_entity_name(item)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _extract_event_candidates(text: str) -> List[str]:
    pattern = r"[\u4e00-\u9fffA-Za-z0-9]{2,20}(?:大会|会议|之战|战役|战争|事件|行动|起义|计划|比武|决战|围攻|救援|庆典)"
    out: List[str] = []
    seen = set()
    for item in re.findall(pattern, text):
        name = _sanitize_entity_name(item)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _heuristic_extract_graph(text: str) -> dict:
    nodes: Dict[str, dict] = {}
    edges: Dict[Tuple[str, str, str], dict] = {}
    sentences = [s.strip() for s in re.split(r"[。！？!?;\n]+", text) if s.strip()]

    for sentence in sentences:
        persons = _extract_person_candidates(sentence)
        factions = _extract_faction_candidates(sentence)
        events = _extract_event_candidates(sentence)

        for person in persons:
            nodes.setdefault(person, {"id": person, "label": person, "type": TYPE_PERSON})
        for faction in factions:
            nodes.setdefault(faction, {"id": faction, "label": faction, "type": TYPE_FACTION})
        for event in events:
            nodes.setdefault(event, {"id": event, "label": event, "type": TYPE_EVENT})

        for person in persons:
            for faction in factions:
                edges[(person, faction, REL_BELONGS)] = {"source": person, "target": faction, "label": REL_BELONGS}
            for event in events:
                edges[(person, event, REL_PARTICIPATE)] = {"source": person, "target": event, "label": REL_PARTICIPATE}

        if len(persons) >= 2:
            relation = REL_RELATED
            for kw, mapped in RELATION_KEYWORDS.items():
                if kw in sentence:
                    relation = mapped
                    break
            p1, p2 = persons[0], persons[1]
            if p1 != p2:
                edges[(p1, p2, relation)] = {"source": p1, "target": p2, "label": relation}

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def _rule_extract_relationships_from_text(text: str, nodes: List[dict]) -> List[dict]:
    node_ids = [str(node.get("id", "")) for node in nodes if isinstance(node, dict) and node.get("id")]
    node_ids = [item for item in node_ids if item and not _is_noise_entity(item)]
    if len(node_ids) < 2:
        return []

    # Prefer longer names first to avoid partial substring conflicts.
    node_ids.sort(key=len, reverse=True)
    edges: Dict[Tuple[str, str, str], dict] = {}
    sentences = [s.strip() for s in re.split(r"[。！？!?;\n]+", text) if s.strip()]
    if not sentences:
        sentences = [text]

    for sentence in sentences:
        present = [entity for entity in node_ids if entity in sentence]
        # Deduplicate while preserving order.
        seen = set()
        ordered = []
        for entity in present:
            if entity in seen:
                continue
            seen.add(entity)
            ordered.append(entity)
        if len(ordered) < 2:
            continue

        relation = REL_RELATED
        for keyword, mapped in RELATION_KEYWORDS.items():
            if keyword in sentence:
                relation = mapped
                break

        for i in range(len(ordered) - 1):
            source = ordered[i]
            target = ordered[i + 1]
            if source == target:
                continue
            edges[(source, target, relation)] = {"source": source, "target": target, "label": relation}

    return list(edges.values())


def _infer_type_from_context(entity_id: str, text: str) -> str:
    if not entity_id:
        return TYPE_CONCEPT
    if any(entity_id.endswith(s) for s in FACTION_SUFFIXES):
        return TYPE_FACTION
    if any(entity_id.endswith(s) for s in EVENT_SUFFIXES):
        return TYPE_EVENT
    if re.search(rf"(在|到|来自|前往).{{0,8}}{re.escape(entity_id)}", text):
        return TYPE_PLACE
    if re.search(rf"{re.escape(entity_id)}.{{0,4}}(弟子|师父|掌门|帮主|王|将军|先生|姑娘|公子)", text):
        return TYPE_PERSON
    return TYPE_CONCEPT


def _extract_type_mapping(payload: Optional[dict]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not isinstance(payload, dict):
        return mapping

    for key in ("types", "nodes", "entities", "result"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            entity_id = _sanitize_entity_name(item.get("id") or item.get("entity") or item.get("name"))
            raw_type = item.get("type") or item.get("category")
            if not entity_id or not raw_type:
                continue
            mapping[entity_id] = _coerce_type_label(str(raw_type))

    if mapping:
        return mapping

    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            continue
        entity_id = _sanitize_entity_name(key)
        if not entity_id:
            continue
        mapping[entity_id] = _coerce_type_label(str(value))
    return mapping


def _complete_missing_node_types(graph_data: dict, text: str, base_url: str, fallback_model: str, timeout_sec: int) -> dict:
    if not TYPE_COMPLETION_ENABLED:
        return graph_data

    nodes = graph_data.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        return graph_data

    pending = [node for node in nodes if _coerce_type_label(node.get("type", "")) == TYPE_CONCEPT]
    if not pending:
        return graph_data

    model = _pick_qwen_model(base_url, fallback_model)
    pending_ids = [_sanitize_entity_name(node.get("id")) for node in pending if _sanitize_entity_name(node.get("id"))]
    if not pending_ids:
        return graph_data

    prompt = (
        "You are a classifier for knowledge graph entities.\n"
        "Classify each entity into one of these types: "
        f"{TYPE_PERSON}, {TYPE_FACTION}, {TYPE_ORG}, {TYPE_EVENT}, {TYPE_PLACE}, {TYPE_CONCEPT}.\n"
        "Return strict JSON only:\n"
        '{"types":[{"id":"entity","type":"type"}]}\n'
        f"Entities: {json.dumps(pending_ids, ensure_ascii=False)}\n"
        f"Context: {text[:6000]}"
    )
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.0}}

    llm_mapping: Dict[str, str] = {}
    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=max(10, min(timeout_sec, 40)),
        )
        if response.status_code == 200:
            generated_text = response.json().get("response", "")
            parsed = None
            for candidate in _candidate_json_texts(generated_text):
                parsed = _safe_json_loads(candidate)
                if parsed:
                    break
            llm_mapping = _extract_type_mapping(parsed)
    except Exception as e:
        print(f"[KG] Type completion skipped: {e}")

    for node in nodes:
        if not isinstance(node, dict):
            continue
        entity_id = _sanitize_entity_name(node.get("id"))
        if not entity_id:
            continue
        current_type = _coerce_type_label(node.get("type", ""))
        if current_type != TYPE_CONCEPT:
            node["type"] = current_type
            continue
        completed = _coerce_type_label(llm_mapping.get(entity_id, ""))
        if completed == TYPE_CONCEPT:
            completed = _infer_type_from_context(entity_id, text)
        final_type = _coerce_type_label(completed)
        if final_type == TYPE_PERSON and not _looks_like_person_name(entity_id):
            final_type = TYPE_CONCEPT
        node["type"] = final_type

    graph_data["nodes"] = nodes
    return graph_data


def extract_graph_data(chunk: str, timeout_sec: int = DEFAULT_KG_CHUNK_TIMEOUT_SEC) -> dict:
    base_url, model = _resolve_ollama_runtime()
    prompt = (
        "Extract a concise knowledge graph from text.\n"
        "Priority: people, person relationships, factions/organizations, events.\n"
        "Return strict JSON only (no markdown, no explanation):\n"
        "{"
        "\"nodes\":[{\"id\":\"entity\",\"label\":\"entity\",\"type\":\""
        f"{TYPE_PERSON}|{TYPE_FACTION}|{TYPE_ORG}|{TYPE_EVENT}|{TYPE_PLACE}|{TYPE_CONCEPT}"
        "\"}],"
        "\"edges\":[{\"source\":\"A\",\"target\":\"B\",\"label\":\"relation\"}]"
        "}\n"
        "If nothing can be extracted, return {\"nodes\":[],\"edges\":[]}.\n"
        f"Text:\n{chunk}"
    )
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}

    try:
        response = requests.post(f"{base_url}/api/generate", json=payload, timeout=timeout_sec)
        if response.status_code != 200:
            print(f"[KG] Ollama error {response.status_code}: {response.text[:200]}")
            heuristic = _normalize_graph_payload(_heuristic_extract_graph(chunk))
            return _complete_missing_node_types(heuristic, chunk, base_url, model, timeout_sec)

        generated_text = response.json().get("response", "")
        parsed = None
        for candidate in _candidate_json_texts(generated_text):
            parsed = _safe_json_loads(candidate)
            if parsed:
                break

        normalized = _normalize_graph_payload(parsed or {})
        if normalized["nodes"] or normalized["edges"]:
            rule_edges = _rule_extract_relationships_from_text(chunk, normalized["nodes"])
            if rule_edges:
                normalized["edges"] = _normalize_edges((normalized.get("edges") or []) + rule_edges)
            return _complete_missing_node_types(normalized, chunk, base_url, model, timeout_sec)

        heuristic = _normalize_graph_payload(_heuristic_extract_graph(chunk))
        rule_edges = _rule_extract_relationships_from_text(chunk, heuristic.get("nodes", []))
        if rule_edges:
            heuristic["edges"] = _normalize_edges((heuristic.get("edges") or []) + rule_edges)
        return _complete_missing_node_types(heuristic, chunk, base_url, model, timeout_sec)
    except Exception as e:
        print(f"[KG] extract_graph_data error: {e}")
        heuristic = _normalize_graph_payload(_heuristic_extract_graph(chunk))
        rule_edges = _rule_extract_relationships_from_text(chunk, heuristic.get("nodes", []))
        if rule_edges:
            heuristic["edges"] = _normalize_edges((heuristic.get("edges") or []) + rule_edges)
        return _complete_missing_node_types(heuristic, chunk, base_url, model, timeout_sec)


def process_file_to_graph(
    file_path: Path,
    *,
    max_chunks: Optional[int] = None,
    chunk_timeout_sec: int = DEFAULT_KG_CHUNK_TIMEOUT_SEC,
    deadline_at: Optional[float] = None,
    save_partial_cb: Optional[Callable[[dict, int, int], None]] = None,
) -> dict:
    target_chars = None
    if max_chunks and max_chunks > 0:
        # Sample enough context from head/middle/tail when partial extraction is requested.
        target_chars = CHUNK_SIZE * max(8, max_chunks * 4)

    content = extract_text(str(file_path), max_chars=target_chars)
    if not content:
        raise ValueError(f"Unable to extract content from {file_path.name}")

    chunks = split_text_into_chunks(content, CHUNK_SIZE)
    selected_indexes = _select_chunk_indexes(chunks, max_chunks)
    graph_data = _empty_graph_data()
    graph_data["meta"]["total_chunks"] = len(chunks)
    if len(selected_indexes) < len(chunks):
        graph_data["meta"]["is_partial"] = True

    processed_count = 0
    for idx in selected_indexes:
        if deadline_at is not None and time.monotonic() >= deadline_at:
            graph_data["meta"]["is_partial"] = True
            break

        chunk = chunks[idx]
        print(f"[KG] Processing chunk {idx + 1}/{len(chunks)} from {file_path.name}")
        result = extract_graph_data(chunk, timeout_sec=chunk_timeout_sec)
        if result and result.get("nodes") is not None and result.get("edges") is not None:
            if result["nodes"] or result["edges"]:
                graph_data["nodes"].extend(result["nodes"])
                graph_data["edges"].extend(result["edges"])
            else:
                graph_data["meta"]["failed_chunks"] += 1
        else:
            graph_data["meta"]["failed_chunks"] += 1

        processed_count += 1
        graph_data["meta"]["processed_chunks"] = processed_count
        if save_partial_cb:
            save_partial_cb(graph_data, processed_count, len(selected_indexes))

    merged = _merge_graph_data([graph_data])
    max_nodes_per_file = int(os.getenv("KG_MAX_NODES_PER_FILE", "80"))
    pruned = _prune_graph(merged, max_nodes=max_nodes_per_file)
    graph_data["nodes"] = pruned["nodes"]
    graph_data["edges"] = pruned["edges"]
    return graph_data


def _merge_graph_data(graph_list: List[dict]) -> dict:
    def _clean(value) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = "".join(text.split())
        return text.strip("\"'`，。；、,.!?！？()（）[]{}")

    def _norm_type(value) -> str:
        text = _clean(value).lower()
        type_map = {
            "person": "\u4eba\u7269",
            "people": "\u4eba\u7269",
            "\u4eba\u7269": "\u4eba\u7269",
            "faction": "\u95e8\u6d3e",
            "sect": "\u95e8\u6d3e",
            "\u95e8\u6d3e": "\u95e8\u6d3e",
            "organization": "\u7ec4\u7ec7",
            "org": "\u7ec4\u7ec7",
            "\u7ec4\u7ec7": "\u7ec4\u7ec7",
            "event": "\u4e8b\u4ef6",
            "\u4e8b\u4ef6": "\u4e8b\u4ef6",
            "location": "\u5730\u70b9",
            "place": "\u5730\u70b9",
            "\u5730\u70b9": "\u5730\u70b9",
            "concept": "\u6982\u5ff5",
            "\u6982\u5ff5": "\u6982\u5ff5",
        }
        return type_map.get(text, "\u6982\u5ff5")

    merged_nodes = {}
    merged_edges = {}

    for graph in graph_list or []:
        for node in graph.get("nodes", []):
            if not isinstance(node, dict):
                continue
            entity_id = _clean(node.get("id") or node.get("name") or node.get("label"))
            if not entity_id:
                continue
            if entity_id not in merged_nodes:
                label = _clean(node.get("label") or node.get("name") or entity_id) or entity_id
                merged_nodes[entity_id] = {"id": entity_id, "label": label, "type": _norm_type(node.get("type"))}

        for edge in graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            source = _clean(edge.get("source"))
            target = _clean(edge.get("target"))
            label = _clean(edge.get("label")) or REL_RELATED
            if not source or not target:
                continue
            key = (source, target, label)
            if key not in merged_edges:
                merged_edges[key] = {"source": source, "target": target, "label": label}
            if source not in merged_nodes:
                merged_nodes[source] = {"id": source, "label": source, "type": "\u6982\u5ff5"}
            if target not in merged_nodes:
                merged_nodes[target] = {"id": target, "label": target, "type": "\u6982\u5ff5"}

    return {"nodes": list(merged_nodes.values()), "edges": list(merged_edges.values())}


def _prune_graph(graph_data: dict, max_nodes: int) -> dict:
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return graph_data
    if max_nodes <= 0 or len(nodes) <= max_nodes:
        return graph_data

    degree: Dict[str, int] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source:
            degree[source] = degree.get(source, 0) + 1
        if target:
            degree[target] = degree.get(target, 0) + 1

    type_priority = {
        TYPE_PERSON: 4,
        TYPE_FACTION: 3,
        TYPE_ORG: 3,
        TYPE_EVENT: 3,
        TYPE_PLACE: 2,
        TYPE_CONCEPT: 1,
    }
    scored_nodes = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        node_type = _coerce_type_label(node.get("type", ""))
        score = degree.get(node_id, 0) * 10 + type_priority.get(node_type, 1)
        scored_nodes.append((score, node_id, node))

    scored_nodes.sort(key=lambda item: item[0], reverse=True)
    keep_ids = {node_id for _, node_id, _ in scored_nodes[:max_nodes]}
    kept_nodes = [node for _, node_id, node in scored_nodes[:max_nodes] if node_id in keep_ids]
    kept_edges = [
        edge
        for edge in edges
        if isinstance(edge, dict)
        and str(edge.get("source", "")) in keep_ids
        and str(edge.get("target", "")) in keep_ids
    ]
    return {"nodes": kept_nodes, "edges": _normalize_edges(kept_edges)}


def _graph_output_path(file_path: Path) -> Path:
    return file_path.with_name(f"{file_path.stem}_graph.json")


def _save_graph_data(file_path: Path, graph_data: dict) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)


def _load_graph_data(file_path: Path) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        normalized = _normalize_graph_payload(payload)
        if isinstance(payload, dict) and isinstance(payload.get("meta"), dict):
            normalized["meta"] = payload["meta"]
        return normalized
    except Exception:
        return {"nodes": [], "edges": []}


def _build_partial_save_callback(output_path: Path) -> Callable[[dict, int, int], None]:
    def _save_partial(graph_data: dict, processed_chunks: int, total_chunks: int) -> None:
        merged = _merge_graph_data([graph_data])
        payload = {
            "nodes": merged["nodes"],
            "edges": merged["edges"],
            "meta": {
                "total_chunks": int(graph_data.get("meta", {}).get("total_chunks", total_chunks)),
                "processed_chunks": processed_chunks,
                "failed_chunks": int(graph_data.get("meta", {}).get("failed_chunks", 0)),
                "is_partial": processed_chunks < total_chunks,
            },
        }
        _save_graph_data(output_path, payload)

    return _save_partial


def _resolve_input_file(filename: str) -> Optional[Path]:
    raw = Path(filename)
    candidates: List[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.extend(
            [
                (PROJECT_ROOT / filename).resolve(),
                (LOCAL_KB_ROOT / filename).resolve(),
                (TEST_KB_ROOT / filename).resolve(),
            ]
        )
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _resolve_graph_file(kb_dir: Path, filename: str) -> Optional[Path]:
    requested = Path(filename).name
    candidates = []
    if requested.endswith("_graph.json"):
        candidates.append(requested)
    else:
        base = Path(requested).stem
        candidates.append(f"{base}_graph.json")
        candidates.append(requested)

    for name in candidates:
        path = kb_dir / name
        if path.exists() and path.is_file():
            return path

    lower_map = {item.name.lower(): item for item in list_graph_files(kb_dir)}
    for name in candidates:
        matched = lower_map.get(name.lower())
        if matched:
            return matched
    return None


def _load_merged_kb_graph(kb_dir: Path) -> Tuple[dict, int]:
    graph_files = list_graph_files(kb_dir)
    if not graph_files:
        return {"nodes": [], "edges": []}, 0
    graph_list = [_load_graph_data(path) for path in graph_files]
    return _merge_graph_data(graph_list), len(graph_files)


@router.post("/process-file")
async def process_file_endpoint(request: ProcessFileRequest):
    file_path = _resolve_input_file(request.filename)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"File not found: {request.filename}")
    if not should_process_file(file_path):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_path.suffix}")

    try:
        deadline_at = time.monotonic() + DEFAULT_KG_DEADLINE_SEC
        graph_data = await asyncio.to_thread(
            process_file_to_graph,
            file_path,
            max_chunks=DEFAULT_KG_MAX_CHUNKS_PER_FILE,
            chunk_timeout_sec=DEFAULT_KG_CHUNK_TIMEOUT_SEC,
            deadline_at=deadline_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {e}") from e

    output_file = _graph_output_path(file_path)
    _save_graph_data(output_file, graph_data)
    return {"message": f"Processed {file_path.name}", "graph_data": graph_data, "output_file": str(output_file)}


@router.post("/process-all-files", response_model=ProcessFilesResponse)
async def process_all_files(request: ProcessFolderRequest):
    folder_path = _resolve_folder_path(request.folder_path)
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder not found: {request.folder_path}")

    files = list_processable_files(folder_path)
    if request.max_files and request.max_files > 0:
        files = files[: request.max_files]
    if not files:
        return ProcessFilesResponse(message="No supported files found", graph_data={"nodes": [], "edges": []})

    deadline_sec = request.deadline_sec if request.deadline_sec is not None else DEFAULT_KG_DEADLINE_SEC
    deadline_at = time.monotonic() + deadline_sec if deadline_sec and deadline_sec > 0 else None
    chunk_timeout = request.chunk_timeout_sec or DEFAULT_KG_CHUNK_TIMEOUT_SEC

    graph_list = []
    processed = 0
    for file_path in files:
        if deadline_at is not None and time.monotonic() >= deadline_at:
            break

        output_path = _graph_output_path(file_path)
        partial_cb = _build_partial_save_callback(output_path) if request.save_partial else None
        graph_data = await asyncio.to_thread(
            process_file_to_graph,
            file_path,
            max_chunks=request.max_chunks_per_file,
            chunk_timeout_sec=chunk_timeout,
            deadline_at=deadline_at,
            save_partial_cb=partial_cb,
        )
        _save_graph_data(output_path, graph_data)
        graph_list.append(graph_data)
        processed += 1

    merged = _merge_graph_data(graph_list)
    message = f"Processed {processed}/{len(files)} files"
    if processed < len(files):
        message += " (partial due deadline)"
    return ProcessFilesResponse(message=message, graph_data=merged)


@router.post("/process-knowledge-base")
async def process_knowledge_base(request: ProcessFolderRequest):
    folder_path = _resolve_folder_path(request.folder_path)
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Knowledge base folder not found: {request.folder_path}")

    files = list_processable_files(folder_path)
    if request.max_files and request.max_files > 0:
        files = files[: request.max_files]
    if not files:
        return JSONResponse(content={"message": "No supported files found in this knowledge base"})

    deadline_sec = request.deadline_sec if request.deadline_sec is not None else DEFAULT_KG_DEADLINE_SEC
    deadline_at = time.monotonic() + deadline_sec if deadline_sec and deadline_sec > 0 else None
    chunk_timeout = request.chunk_timeout_sec or DEFAULT_KG_CHUNK_TIMEOUT_SEC
    max_chunks = request.max_chunks_per_file or DEFAULT_KG_MAX_CHUNKS_PER_FILE

    results = []
    for file_path in files:
        if deadline_at is not None and time.monotonic() >= deadline_at:
            results.append(
                {
                    "filename": file_path.name,
                    "message": "Skipped due overall deadline",
                    "graph_data": {"nodes": [], "edges": []},
                }
            )
            continue

        output_path = _graph_output_path(file_path)
        partial_cb = _build_partial_save_callback(output_path) if request.save_partial else None
        try:
            graph_data = await asyncio.to_thread(
                process_file_to_graph,
                file_path,
                max_chunks=max_chunks,
                chunk_timeout_sec=chunk_timeout,
                deadline_at=deadline_at,
                save_partial_cb=partial_cb,
            )
            _save_graph_data(output_path, graph_data)
            results.append({"filename": file_path.name, "message": "ok", "graph_data": graph_data})
        except Exception as e:
            results.append({"filename": file_path.name, "message": f"failed: {e}", "graph_data": _empty_graph_data()})
    return results


@router.get("/get-kb-graph-data/{kb_id}/{filename}")
async def get_kb_graph_data(kb_id: str, filename: str):
    kb_dir = resolve_kb_dir(kb_id)
    if not kb_dir.exists() or not kb_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    graph_file = _resolve_graph_file(kb_dir, filename)
    if not graph_file:
        return JSONResponse(status_code=404, content={"message": f"Graph file not found for: {filename}"})

    graph_data = _load_graph_data(graph_file)
    if not graph_data.get("nodes") and not graph_data.get("edges"):
        return {"nodes": [], "edges": [], "message": "Graph exists but contains no entities yet"}
    return graph_data


@router.get("/get-kb-merged-graph/{kb_id}")
async def get_kb_merged_graph(kb_id: str):
    kb_dir = resolve_kb_dir(kb_id)
    if not kb_dir.exists() or not kb_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    merged, graph_file_count = _load_merged_kb_graph(kb_dir)
    if graph_file_count == 0:
        return {"nodes": [], "edges": [], "message": "No graph data found. Please generate graph first."}
    if not merged["nodes"] and not merged["edges"]:
        return {"nodes": [], "edges": [], "message": "Graph files exist, but no entities or relations were extracted."}
    return merged


@router.get("/search-nodes/{kb_id}")
async def search_nodes(kb_id: str, keyword: str):
    keyword = (keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword cannot be empty")

    kb_dir = resolve_kb_dir(kb_id)
    if not kb_dir.exists() or not kb_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    merged, graph_file_count = _load_merged_kb_graph(kb_dir)
    if graph_file_count == 0:
        return {"nodes": [], "edges": [], "matched_count": 0, "message": "No graph data found"}

    nodes = merged.get("nodes", [])
    edges = merged.get("edges", [])
    node_map = {str(node.get("id")): node for node in nodes if isinstance(node, dict) and node.get("id")}

    keyword_lower = keyword.lower()
    matched_ids = set()
    for node_id, node in node_map.items():
        label = str(node.get("label", ""))
        node_type = str(node.get("type", ""))
        if keyword_lower in node_id.lower() or keyword_lower in label.lower() or keyword_lower in node_type.lower():
            matched_ids.add(node_id)

    if not matched_ids:
        return {"nodes": [], "edges": [], "matched_count": 0, "message": f"No nodes matched keyword: {keyword}"}

    related_ids = set(matched_ids)
    filtered_edges = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source in matched_ids or target in matched_ids:
            filtered_edges.append(edge)
            if source:
                related_ids.add(source)
            if target:
                related_ids.add(target)

    filtered_nodes = [node_map[node_id] for node_id in related_ids if node_id in node_map]
    return {"nodes": filtered_nodes, "edges": filtered_edges, "matched_count": len(matched_ids)}


@router.get("/graph-stats/{kb_id}")
async def graph_stats(kb_id: str):
    kb_dir = resolve_kb_dir(kb_id)
    if not kb_dir.exists() or not kb_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    merged, graph_file_count = _load_merged_kb_graph(kb_dir)
    if graph_file_count == 0:
        return {"node_count": 0, "edge_count": 0, "isolated_node_count": 0, "type_distribution": {}}

    nodes = merged.get("nodes", [])
    edges = merged.get("edges", [])
    node_ids = {str(node.get("id", "")) for node in nodes if isinstance(node, dict) and node.get("id")}

    connected = set()
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source:
            connected.add(source)
        if target:
            connected.add(target)

    isolated_node_count = len([node_id for node_id in node_ids if node_id not in connected])

    type_distribution: Dict[str, int] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or TYPE_CONCEPT)
        type_distribution[node_type] = type_distribution.get(node_type, 0) + 1

    return {
        "node_count": len(node_ids),
        "edge_count": len(edges),
        "isolated_node_count": isolated_node_count,
        "type_distribution": type_distribution,
    }
