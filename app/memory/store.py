from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.config import get_settings

logger = logging.getLogger(__name__)

CHROMA_AVAILABLE = False

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    CHROMA_AVAILABLE = True
    logger.info("ChromaDB loaded — memory enabled")
except ImportError:
    logger.warning("ChromaDB not available — memory disabled")


class MemoryStore:
    def __init__(self):
        self._client = None
        self._short_term = None
        self._long_term = None

        if not CHROMA_AVAILABLE:
            return

        try:
            settings = get_settings()
            self._client = chromadb.PersistentClient(
                path=settings.chroma_persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._short_term = self._client.get_or_create_collection(
                name="athena_short_term",
                metadata={"hnsw:space": "cosine"},
            )
            self._long_term = self._client.get_or_create_collection(
                name="athena_long_term",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Memory store initialized (short-term + long-term)")
        except Exception:
            logger.exception("Failed to initialize ChromaDB memory store")
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    async def add_memory(
        self,
        text: str,
        metadata: dict | None = None,
        long_term: bool = False,
    ):
        if not self.available:
            return

        collection = self._long_term if long_term else self._short_term
        meta = metadata or {}
        meta["timestamp"] = datetime.now(timezone.utc).isoformat()
        doc_id = str(uuid.uuid4())

        try:
            collection.add(
                documents=[text],
                metadatas=[meta],
                ids=[doc_id],
            )
        except Exception:
            logger.exception("Failed to add memory")

    async def search(
        self,
        query: str,
        top_k: int = 5,
        long_term: bool = False,
    ) -> list[str]:
        if not self.available:
            return []

        collection = self._long_term if long_term else self._short_term

        try:
            if collection.count() == 0:
                return []

            results = collection.query(
                query_texts=[query],
                n_results=min(top_k, collection.count()),
            )
            return results["documents"][0] if results["documents"] else []
        except Exception:
            logger.exception("Memory search failed")
            return []

    async def search_all(self, query: str, top_k: int = 5) -> list[str]:
        short = await self.search(query, top_k=top_k, long_term=False)
        long = await self.search(query, top_k=top_k, long_term=True)

        seen = set()
        combined = []
        for doc in long + short:
            if doc not in seen:
                seen.add(doc)
                combined.append(doc)
        return combined[:top_k]

    async def cleanup_short_term(self, max_age_hours: int = 24):
        if not self.available or self._short_term is None:
            return

        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            ).isoformat()

            all_data = self._short_term.get(include=["metadatas"])
            if not all_data["ids"]:
                return

            ids_to_delete = []
            for doc_id, meta in zip(all_data["ids"], all_data["metadatas"]):
                ts = meta.get("timestamp", "")
                if ts and ts < cutoff:
                    ids_to_delete.append(doc_id)

            if ids_to_delete:
                self._short_term.delete(ids=ids_to_delete)
                logger.info("Cleaned up %d expired short-term memories", len(ids_to_delete))
        except Exception:
            logger.exception("Short-term memory cleanup failed")


_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore | None:
    global _memory_store
    if _memory_store is None and CHROMA_AVAILABLE:
        _memory_store = MemoryStore()
    return _memory_store
