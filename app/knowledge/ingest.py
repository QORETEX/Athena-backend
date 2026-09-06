from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

CHROMA_AVAILABLE = False
_knowledge_collection = None

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    CHROMA_AVAILABLE = True
except ImportError:
    logger.warning("ChromaDB not available — knowledge ingestion disabled")


def _get_knowledge_collection():
    global _knowledge_collection
    if _knowledge_collection is not None:
        return _knowledge_collection

    if not CHROMA_AVAILABLE:
        return None

    try:
        settings = get_settings()
        client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _knowledge_collection = client.get_or_create_collection(
            name=settings.knowledge_collection,
            metadata={"hnsw:space": "cosine"},
        )
        return _knowledge_collection
    except Exception:
        logger.exception("Failed to initialize knowledge collection")
        return None


# ── Text extractors ──────────────────────────────────────


def extract_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                pages.append(text.strip())
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("pypdf not installed — cannot extract PDF")
        return ""
    except Exception:
        logger.exception("Failed to extract PDF: %s", path)
        return ""


def extract_docx(path: str) -> str:
    try:
        from docx import Document

        doc = Document(path)
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        logger.warning("python-docx not installed — cannot extract DOCX")
        return ""
    except Exception:
        logger.exception("Failed to extract DOCX: %s", path)
        return ""


def extract_text_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        logger.exception("Failed to read text file: %s", path)
        return ""


EXTRACTORS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".txt": extract_text_file,
    ".md": extract_text_file,
    ".markdown": extract_text_file,
}


# ── Chunking ─────────────────────────────────────────────


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    settings = get_settings()
    chunk_size = chunk_size or settings.knowledge_chunk_size
    overlap = overlap or settings.knowledge_chunk_overlap

    sentences = _SENTENCE_BOUNDARY.split(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if current_len + len(sentence) > chunk_size and current:
            chunks.append(" ".join(current))

            # Keep overlap by retaining trailing sentences
            overlap_parts: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len + len(s) > overlap:
                    break
                overlap_parts.insert(0, s)
                overlap_len += len(s)

            current = overlap_parts
            current_len = overlap_len

        current.append(sentence)
        current_len += len(sentence)

    if current:
        chunks.append(" ".join(current))

    return chunks


# ── Ingestion ────────────────────────────────────────────


async def ingest_file(file_path: str) -> int:
    collection = _get_knowledge_collection()
    if collection is None:
        logger.warning("Knowledge collection not available — skipping ingestion")
        return 0

    path = Path(file_path)
    ext = path.suffix.lower()
    extractor = EXTRACTORS.get(ext)
    if extractor is None:
        logger.warning("No extractor for file type: %s", ext)
        return 0

    text = extractor(str(path))
    if not text.strip():
        logger.warning("No text extracted from: %s", file_path)
        return 0

    chunks = chunk_text(text)
    if not chunks:
        return 0

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {"source": str(path.name), "chunk_index": i, "file_path": file_path}
        for i in range(len(chunks))
    ]

    try:
        collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info("Ingested %d chunks from %s", len(chunks), path.name)
        return len(chunks)
    except Exception:
        logger.exception("Failed to ingest file: %s", file_path)
        return 0


# ── Search ───────────────────────────────────────────────


async def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    collection = _get_knowledge_collection()
    if collection is None or collection.count() == 0:
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, collection.count()),
        )
        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []

        return [
            {"text": doc, "source": meta.get("source", ""), "chunk_index": meta.get("chunk_index", 0)}
            for doc, meta in zip(docs, metas)
        ]
    except Exception:
        logger.exception("Knowledge search failed")
        return []
