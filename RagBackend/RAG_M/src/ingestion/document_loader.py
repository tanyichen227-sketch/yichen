import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    CSVLoader,
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredExcelLoader,
    UnstructuredWordDocumentLoader,
)


class DocumentLoader:
    IGNORED_EXTENSIONS = {".json", ".log", ".tmp", ".bak", ".db", ".sqlite"}
    IGNORED_FILENAMES = {"knowledge_data.json", "metadata.json", "config.json"}
    IGNORED_DIRECTORIES = {"vectorstore", "__pycache__", ".git", "node_modules"}

    def __init__(
        self,
        docs_dir: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        config = self._load_config(docs_dir) if docs_dir else {}
        self.chunk_size = chunk_size or config.get("chunk_size", 1000)
        self.chunk_overlap = chunk_overlap or config.get("chunk_overlap", 200)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""],
        )
        self.google_drive_enabled = False
        self.google_drive_loader = None

        for import_path in (
            "RAG_M.src.ingestion.google_drive",
            "src.ingestion.google_drive",
            ".google_drive",
        ):
            try:
                if import_path == ".google_drive":
                    from .google_drive import GoogleDriveLoader  # type: ignore
                elif import_path == "RAG_M.src.ingestion.google_drive":
                    from RAG_M.src.ingestion.google_drive import GoogleDriveLoader  # type: ignore
                else:
                    from src.ingestion.google_drive import GoogleDriveLoader  # type: ignore

                self.google_drive_loader = GoogleDriveLoader()
                self.google_drive_enabled = True
                break
            except Exception:
                continue

    def _load_config(self, docs_dir: str) -> dict:
        config_path = Path(docs_dir) / "knowledge_data.json"
        if not config_path.exists():
            return {}

        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "chunk_size": data.get("chunk_size", 1000),
                "chunk_overlap": data.get("chunk_overlap", 200),
            }
        except Exception:
            return {}

    def should_skip_file(self, file_path: str) -> Tuple[bool, str]:
        path = Path(file_path)
        filename = path.name
        suffix = path.suffix.lower()

        if any(part in self.IGNORED_DIRECTORIES for part in path.parts):
            return True, "ignored directory"
        if filename.startswith("~$"):
            return True, "temporary file"
        if filename in self.IGNORED_FILENAMES:
            return True, "metadata file"
        if suffix in self.IGNORED_EXTENSIONS:
            return True, "ignored extension"
        return False, ""

    @staticmethod
    def _load_text_documents(file_path: str) -> List[Document]:
        normalized_path = os.path.normpath(file_path)
        errors = []
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
            try:
                loader = TextLoader(normalized_path, encoding=encoding)
                return loader.load()
            except Exception as exc:
                errors.append(f"{encoding}: {exc}")
        raise ValueError(" | ".join(errors) or f"Unable to load text file: {file_path}")

    @staticmethod
    def _load_pdf_documents(file_path: str) -> List[Document]:
        try:
            documents = PyPDFLoader(file_path).load()
            if documents and any(doc.page_content.strip() for doc in documents):
                return documents
        except Exception as pdf_err:
            pdf_loader_error = pdf_err
        else:
            pdf_loader_error = ValueError("PDF content is empty")

        try:
            import pdfplumber

            text_pages = []
            with pdfplumber.open(file_path) as pdf:
                for index, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        text_pages.append(
                            Document(
                                page_content=text,
                                metadata={"source": file_path, "page": index},
                            )
                        )
            if text_pages:
                return text_pages
        except ImportError as exc:
            raise ValueError(
                f"PDF parsing failed ({pdf_loader_error}). Install pdfplumber for fallback support."
            ) from exc
        except Exception as exc:
            raise ValueError(f"PDF parsing failed: {exc}") from exc

        raise ValueError(f"PDF content is empty: {os.path.basename(file_path)}")

    def _load_extensionless_document(self, file_path: str) -> List[Document]:
        with open(file_path, "rb") as f:
            header = f.read(8)

        if header.startswith(b"%PDF-"):
            return self._load_pdf_documents(file_path)

        if header.startswith(b"PK\x03\x04"):
            for loader_factory in (
                lambda: Docx2txtLoader(file_path),
                lambda: UnstructuredWordDocumentLoader(file_path),
            ):
                try:
                    return loader_factory().load()
                except Exception:
                    continue

        return self._load_text_documents(file_path)

    def load_document(self, file_path: str, is_google_drive: bool = False) -> List[Document]:
        should_skip, skip_reason = self.should_skip_file(file_path)
        if should_skip:
            raise ValueError(f"Skipped file ({skip_reason}): {os.path.basename(file_path)}")

        if is_google_drive:
            if not self.google_drive_enabled or self.google_drive_loader is None:
                raise ValueError("Google Drive integration is not configured")
            try:
                file_path = self.google_drive_loader.download_file(file_path)
            except (IOError, OSError) as exc:
                raise IOError(f"Error downloading from Google Drive: {exc}") from exc

        file_extension = Path(file_path).suffix.lower()

        if not file_extension:
            documents = self._load_extensionless_document(file_path)
        elif file_extension == ".pdf":
            documents = self._load_pdf_documents(file_path)
        elif file_extension in {".txt", ".md"}:
            documents = self._load_text_documents(file_path)
        elif file_extension in {".xlsx", ".xls"}:
            documents = UnstructuredExcelLoader(file_path).load()
        elif file_extension == ".csv":
            documents = CSVLoader(file_path).load()
        elif file_extension in {".docx", ".doc"}:
            try:
                documents = Docx2txtLoader(file_path).load()
            except Exception:
                documents = UnstructuredWordDocumentLoader(file_path).load()
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")

        return self.text_splitter.split_documents(documents)

    def load_and_split(self, file_path: str, is_google_drive: bool = False) -> List[Document]:
        return self.load_document(file_path, is_google_drive=is_google_drive)
