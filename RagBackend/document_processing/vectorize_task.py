from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterator, Optional

from document_processing.incremental_vectorizer import IncrementalVectorizer
from document_processing.task_queue import register_task

logger = logging.getLogger(__name__)

_SKIP_NAMES = {"knowledge_data.json", "vectorstore", "native_vectorstore", "__pycache__"}


def _iter_document_files(target_dir: str) -> Iterator[Path]:
    root = Path(target_dir)
    if not root.exists():
        return

    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name.startswith(".") or entry.name in _SKIP_NAMES:
            continue
        if entry.is_file():
            yield entry


def _vectorize_file(
    kb_id: str,
    file_path: str,
    doc_key: str = "",
    force: bool = False,
) -> Dict[str, object]:
    vectorizer = IncrementalVectorizer(kb_id)
    result = vectorizer.ingest_file(
        file_path=file_path,
        doc_key=doc_key or None,
        force=force,
    )
    logger.info(
        "[vectorize_task] Vectorized file for kb=%s path=%s status=%s",
        kb_id,
        file_path,
        result.get("status"),
    )
    return result


def _do_vectorize(kb_id: str, target_dir: str, force: bool = False) -> Dict[str, object]:
    summary: Dict[str, object] = {
        "kb_id": kb_id,
        "target_dir": target_dir,
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    for file_path in _iter_document_files(target_dir):
        try:
            result = _vectorize_file(kb_id=kb_id, file_path=str(file_path), force=force)
            status = str(result.get("status", "failed"))
        except Exception as exc:
            result = {"status": "failed", "file_path": str(file_path), "error": str(exc)}
            status = "failed"

        if status not in summary:
            summary[status] = 0
        if isinstance(summary.get(status), int):
            summary[status] = int(summary[status]) + 1
        summary["details"].append(result)

    logger.info(
        "[vectorize_task] Batch vectorization finished for kb=%s added=%s updated=%s skipped=%s failed=%s",
        kb_id,
        summary.get("added", 0),
        summary.get("updated", 0),
        summary.get("skipped", 0),
        summary.get("failed", 0),
    )
    return summary


def register_all() -> None:
    register_task("vectorize", _vectorize_file)
    logger.info("[vectorize_task] Registered task handler: vectorize")
