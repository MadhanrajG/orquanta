"""
OrQuanta Agentic v1.0 — Memory Manager

ChromaDB-backed vector memory for all agents.
Provides:
- Episodic memory: full job lifecycle events stored as embeddings
- Semantic search over past decisions
- Agent knowledge sharing layer
- Memory consolidation and pruning
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger("orquanta.memory")

# ChromaDB client (lazy import so other modules don't fail if not installed)
_chroma_client = None
_collection = None

COLLECTION_NAME = "orquanta_episodic_memory"
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8200"))
N_RESULTS_DEFAULT = 5


def _get_chroma():
    """Lazily initialise ChromaDB client."""
    global _chroma_client, _collection
    if _chroma_client is not None:
        return _chroma_client, _collection

    try:
        import chromadb  # type: ignore
        # Try HTTP client first (for Docker deployments)
        try:
            _chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            _chroma_client.heartbeat()
            logger.info(f"ChromaDB HTTP client connected to {CHROMA_HOST}:{CHROMA_PORT}")
        except Exception:
            # Fall back to in-process ephemeral client
            _chroma_client = chromadb.EphemeralClient()
            logger.info("ChromaDB: using EphemeralClient (in-memory mode)")

        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB collection '{COLLECTION_NAME}' ready.")
    except ImportError:
        logger.warning("chromadb not installed. MemoryManager will use in-memory fallback.")
        _chroma_client = "mock"
        _collection = "mock"

    return _chroma_client, _collection


# ---------------------------------------------------------------------------
# In-memory fallback (when ChromaDB is unavailable)
# ---------------------------------------------------------------------------

class _MockCollection:
    """Simple keyword-search fallback when ChromaDB is not available."""
    
    def __init__(self) -> None:
        self._store: list[dict] = []

    def add(self, documents, metadatas, ids) -> None:
        for doc, meta, eid in zip(documents, metadatas, ids):
            self._store.append({"id": eid, "doc": doc, "meta": meta})

    def query(self, query_texts, n_results=5) -> dict:
        q = query_texts[0].lower()
        hits = [
            e for e in self._store
            if any(word in e["doc"].lower() for word in q.split())
        ]
        hits = hits[:n_results]
        return {
            "ids": [[h["id"] for h in hits]],
            "documents": [[h["doc"] for h in hits]],
            "metadatas": [[h["meta"] for h in hits]],
            "distances": [[0.5] * len(hits)],
        }

    def count(self) -> int:
        return len(self._store)

    def peek(self, limit=5) -> dict:
        sliced = self._store[:limit]
        return {
            "ids": [e["id"] for e in sliced],
            "documents": [e["doc"] for e in sliced],
        }


# ---------------------------------------------------------------------------
# Memory Manager
# ---------------------------------------------------------------------------

class MemoryManager:
    """Vector memory for all OrQuanta agents.
    
    All agent decisions, job lifecycle events, failure diagnoses,
    and cost optimizations are stored here, enabling agents to learn
    from history via semantic search.
    
    Storage format: Each memory entry is a natural-language document
    (for embedding) with structured metadata (for filtering).
    
    Usage::
    
        mem = MemoryManager()
        
        # Store an event
        await mem.store_event({
            "type": "job_failure",
            "job_id": "job-abc",
            "reason": "OOM on A100-40GB",
            "action_taken": "migrated to H100",
        })
        
        # Search for similar past events  
        results = await mem.search("OOM failure on A100 training job")
        for r in results:
            print(r["document"], r["metadata"])
    """

    def __init__(self) -> None:
        self._mock_collection = _MockCollection()
        self._use_mock = False
        self._init_backend()

    def _init_backend(self) -> None:
        """Initialise ChromaDB or mock backend."""
        client, collection = _get_chroma()
        if client == "mock":
            self._use_mock = True
            logger.info("MemoryManager: using in-memory mock backend.")
        else:
            self._chroma_collection = collection
            self._use_mock = False

    @property
    def _collection(self):
        return self._mock_collection if self._use_mock else self._chroma_collection

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def store_event(self, event: dict[str, Any], agent_name: str = "system") -> str:
        """Store a structured event in vector memory.
        
        Args:
            event: Event dict. Will be serialised to a natural-language document.
            agent_name: Name of the agent storing this event.
            
        Returns:
            Memory entry ID.
        """
        entry_id = str(uuid4())
        document = self._event_to_document(event)
        metadata = {
            "agent": agent_name,
            "event_type": event.get("type", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload_json": json.dumps(event)[:1000],  # ChromaDB metadata max
        }

        try:
            self._collection.add(
                documents=[document],
                metadatas=[metadata],
                ids=[entry_id],
            )
            logger.debug(f"[Memory] Stored event {entry_id}: {event.get('type', '?')} by {agent_name}")
        except Exception as exc:
            logger.error(f"[Memory] Failed to store event: {exc}")

        return entry_id

    async def store_decision(
        self,
        agent_name: str,
        context: str,
        decision: str,
        outcome: str | None = None,
    ) -> str:
        """Store an agent decision for future reference.
        
        Args:
            agent_name: Deciding agent.
            context: What the agent was looking at.
            decision: What it decided to do.
            outcome: Result after execution (e.g., 'success', 'oom_error').
        """
        return await self.store_event(
            {
                "type": "agent_decision",
                "agent": agent_name,
                "context": context,
                "decision": decision,
                "outcome": outcome or "pending",
            },
            agent_name=agent_name,
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        n_results: int = N_RESULTS_DEFAULT,
        agent_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over stored memories.
        
        Args:
            query: Natural language query.
            n_results: Maximum results to return.
            agent_filter: If set, only return memories from this agent.
            
        Returns:
            List of dicts with keys: id, document, metadata, relevance_score.
        """
        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": min(n_results, max(1, self._collection.count())),
            }
            if agent_filter and not self._use_mock:
                kwargs["where"] = {"agent": agent_filter}

            results = self._collection.query(**kwargs)

            memories = []
            for i, doc_id in enumerate(results["ids"][0]):
                memories.append({
                    "id": doc_id,
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "relevance_score": 1.0 - results["distances"][0][i],
                })
            return memories

        except Exception as exc:
            logger.error(f"[Memory] Search failed: {exc}")
            return []

    async def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recently stored memory entries."""
        try:
            peek = self._collection.peek(limit=limit)
            results = []
            ids = peek.get("ids", [])
            docs = peek.get("documents", [])
            for eid, doc in zip(ids, docs):
                results.append({"id": eid, "document": doc})
            return results
        except Exception as exc:
            logger.error(f"[Memory] get_recent failed: {exc}")
            return []

    def get_stats(self) -> dict[str, Any]:
        """Return memory statistics."""
        try:
            count = self._collection.count()
        except Exception:
            count = 0
        return {
            "total_entries": count,
            "backend": "mock" if self._use_mock else "chromadb",
            "collection": COLLECTION_NAME,
        }

    # ------------------------------------------------------------------
    # Consolidation & Pruning
    # ------------------------------------------------------------------

    async def prune_old_entries(self, max_entries: int = 10000) -> int:
        """Remove oldest entries when collection exceeds max_entries.
        
        Returns:
            Number of entries removed.
        """
        if self._use_mock:
            current = len(self._mock_collection._store)
            if current > max_entries:
                remove_count = current - max_entries
                self._mock_collection._store = self._mock_collection._store[remove_count:]
                logger.info(f"[Memory] Pruned {remove_count} old entries (mock).")
                return remove_count
            return 0

        try:
            count = self._collection.count()
            if count <= max_entries:
                return 0

            peek = self._collection.peek(limit=count - max_entries)
            ids_to_remove = peek.get("ids", [])
            if ids_to_remove:
                self._collection.delete(ids=ids_to_remove)
                logger.info(f"[Memory] Pruned {len(ids_to_remove)} old entries from ChromaDB.")
            return len(ids_to_remove)

        except Exception as exc:
            logger.error(f"[Memory] Pruning failed: {exc}")
            return 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _event_to_document(self, event: dict[str, Any]) -> str:
        """Convert a structured event dict to a natural-language document for embedding."""
        event_type = event.get("type", "event")
        parts = [f"Event type: {event_type}."]

        for key, value in event.items():
            if key == "type":
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            parts.append(f"{key.replace('_', ' ').title()}: {value}.")

        return " ".join(parts)
