from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.knowledge.ingest import ingest_file, search_knowledge

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/search")
async def knowledge_search(q: str, top_k: int = 5):
    """Search the ingested knowledge base."""
    results = await search_knowledge(query=q, top_k=top_k)
    return {"query": q, "results": results, "count": len(results)}


@router.post("/ingest")
async def ingest_document(file: UploadFile = File(...)):
    """Upload and ingest a document (PDF, DOCX, TXT, MD) into the knowledge base."""
    suffix = Path(file.filename).suffix.lower() if file.filename else ""
    if suffix not in (".pdf", ".docx", ".txt", ".md", ".markdown"):
        return {"error": f"Unsupported file type: {suffix}. Supported: .pdf, .docx, .txt, .md"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        chunks = await ingest_file(tmp_path)
        return {
            "filename": file.filename,
            "chunks_ingested": chunks,
            "status": "success" if chunks > 0 else "no_content",
        }
    finally:
        Path(tmp_path).unlink(missing_ok=True)
