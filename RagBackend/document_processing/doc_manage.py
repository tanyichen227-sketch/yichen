from pathlib import Path
import logging
import os
from typing import List

from fastapi import APIRouter
from langchain.schema import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "local-KLB-files"


class DocumentLoader:
    def __init__(self, directory_path: str):
        self.directory_path = Path(directory_path).resolve()
        logger.info("Scanning documents in %s", self.directory_path)

    @staticmethod
    def _looks_like_pdf(file_path: Path) -> bool:
        try:
            with file_path.open("rb") as f:
                return f.read(5).startswith(b"%PDF-")
        except OSError:
            return False

    @staticmethod
    def _load_text_file(file_path: Path) -> List[Document]:
        errors = []
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
            try:
                loader = TextLoader(str(file_path), encoding=encoding)
                return loader.load()
            except Exception as exc:
                errors.append(f"{encoding}: {exc}")
        raise ValueError(" | ".join(errors) or f"Unable to load text file: {file_path}")

    def _load_file(self, file_path: Path) -> List[Document]:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf" or (not suffix and self._looks_like_pdf(file_path)):
            return PyPDFLoader(str(file_path)).load()
        if suffix in ("", ".txt", ".md"):
            return self._load_text_file(file_path)
        return []

    def load_documents(self) -> List[Document]:
        docs: List[Document] = []
        if not self.directory_path.exists():
            logger.error("Directory does not exist: %s", self.directory_path)
            return []

        for root, _, files in os.walk(self.directory_path):
            root_path = Path(root)
            if "vectorstore" in root_path.parts:
                continue

            for name in files:
                if name == "knowledge_data.json" or name.startswith("."):
                    continue

                file_path = root_path / name
                try:
                    docs.extend(self._load_file(file_path))
                except Exception as exc:
                    logger.error("Failed to read %s: %s", name, exc)

        logger.info("Loaded %s document fragments", len(docs))
        return docs


@router.get("/api/documents-list-legacy/{KLB_id}")
@router.get("/api/documents-list-legacy/{KLB_id}/")
async def get_documents_list(KLB_id: str):
    docs = []
    target_dir = UPLOAD_DIR / KLB_id

    if target_dir.exists():
        for file_path in sorted(target_dir.iterdir(), key=lambda p: p.name):
            if (
                not file_path.is_file()
                or file_path.name == "knowledge_data.json"
                or file_path.name.startswith(".")
                or "vectorstore" in file_path.name
            ):
                continue

            docs.append(
                {
                    "name": file_path.name,
                    "status": "completed",
                    "size": file_path.stat().st_size,
                }
            )

    return docs
