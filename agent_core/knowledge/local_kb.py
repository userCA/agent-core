"""Local semantic retriever — sentence-transformers + numpy cosine similarity.

Each document = a subdirectory under the knowledge base root:
  {name}/meta.json      — {name, original_name, created, chunk_count}
  {name}/chunk_000.txt  — chunk text
  {name}/chunk_000.npy  — embedding vector
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import numpy as np

from agent_core.retrieval.base import Query, RetrievedChunk, Retriever

# ---- chunking ----

_SENT_SPLIT = re.compile(r"(?<=[。！？.!?\n])\s*")
_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 80


def _chunk_text(text: str) -> list[str]:
    pieces: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= _CHUNK_SIZE:
            pieces.append(para)
        else:
            parts = [s.strip() for s in _SENT_SPLIT.split(para) if s.strip()]
            pieces.extend(parts)

    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        if len(piece) > _CHUNK_SIZE * 2:
            for i in range(0, len(piece), _CHUNK_SIZE - _CHUNK_OVERLAP):
                chunks.append(piece[i:i + _CHUNK_SIZE])
            buf = ""
            continue
        candidate = (buf + " " + piece).strip() if buf else piece
        if len(candidate) <= _CHUNK_SIZE:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            buf = piece
    if buf:
        chunks.append(buf)
    return chunks or [text]


# ---- model ----

logger = logging.getLogger(__name__)

_MODEL = None
_MODEL_LOCK = threading.Lock()


def _get_model():
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                import os as _os
                if not _os.environ.get("HF_ENDPOINT"):
                    _os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                from sentence_transformers import SentenceTransformer
                _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


class LocalKnowledgeBase:
    """Document store — one subdirectory per document."""

    CHUNK_SIZE = _CHUNK_SIZE

    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._migrate_flat()

    # -- migration from old flat layout --

    def _migrate_flat(self) -> None:
        """Migrate old docname__NNN.txt+npy flat files into subdirectories."""
        flat = list(self._dir.glob("*__000.txt")) + list(self._dir.glob("*__000.npy"))
        if not flat:
            return
        seen: set[str] = set()
        for path in sorted(flat):
            doc = re.sub(r"__\d+$", "", path.stem)
            if doc in seen:
                continue
            seen.add(doc)
            self._migrate_one(doc)
        # Clean up any remaining flat files
        for path in self._dir.glob("*__*.txt"):
            path.unlink(missing_ok=True)
        for path in self._dir.glob("*__*.npy"):
            path.unlink(missing_ok=True)

    def _migrate_one(self, name: str) -> None:
        doc_dir = self._dir / name
        doc_dir.mkdir(exist_ok=True)
        chunks = []
        for txt_path in sorted(self._dir.glob(f"{name}__*.txt")):
            idx = txt_path.stem.rsplit("__", 1)[-1]
            text = txt_path.read_text(encoding="utf-8")
            new_txt = doc_dir / f"chunk_{idx}.txt"
            txt_path.rename(new_txt)
            npy_path = self._dir / f"{txt_path.stem}.npy"
            if npy_path.exists():
                npy_path.rename(doc_dir / f"chunk_{idx}.npy")
            chunks.append({"index": idx, "text": text[:200]})
        meta = {
            "name": name,
            "original_name": name,
            "created": time.time(),
            "chunk_count": len(chunks),
        }
        (doc_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))

    # -- document management --

    def _doc_dir(self, name: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_\-. ]", "_", name).strip() or "doc"
        return self._dir / safe

    def _read_meta(self, name: str) -> dict | None:
        path = self._doc_dir(name) / "meta.json"
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def add(self, name: str, content: str) -> str:
        """Chunk and embed (synchronous, blocks)."""
        safe = re.sub(r"[^a-zA-Z0-9_\-. ]", "_", name).strip() or "doc"
        self.delete(safe)
        doc_dir = self._doc_dir(safe)
        doc_dir.mkdir(parents=True, exist_ok=True)
        # Store original content for later editing
        (doc_dir / "content.txt").write_text(content, encoding="utf-8")
        chunks = _chunk_text(content) or [content]
        model = _get_model()
        for i, chunk in enumerate(chunks):
            (doc_dir / f"chunk_{i:03d}.txt").write_text(chunk, encoding="utf-8")
            vec = model.encode(chunk, normalize_embeddings=True)
            np.save(str(doc_dir / f"chunk_{i:03d}.npy"), vec)
        meta = {
            "name": safe,
            "original_name": name,
            "created": time.time(),
            "chunk_count": len(chunks),
            "tags": [],
        }
        (doc_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
        return safe

    def set_tags(self, name: str, tags: list[str]) -> bool:
        """Set tags for a document."""
        meta = self._read_meta(name)
        if meta is None:
            return False
        meta["tags"] = tags
        (self._doc_dir(name) / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
        return True

    def chunk_and_save(self, name: str, content: str) -> tuple[str, int]:
        """Chunk text, save to disk. No embedding — call embed_all() async."""
        safe = re.sub(r"[^a-zA-Z0-9_\-. ]", "_", name).strip() or "doc"
        self.delete(safe)
        doc_dir = self._doc_dir(safe)
        doc_dir.mkdir(parents=True, exist_ok=True)
        chunks = _chunk_text(content) or [content]
        for i, chunk in enumerate(chunks):
            (doc_dir / f"chunk_{i:03d}.txt").write_text(chunk, encoding="utf-8")
        meta = {
            "name": safe,
            "original_name": name,
            "created": time.time(),
            "chunk_count": len(chunks),
        }
        (doc_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
        return safe, len(chunks)

    def embed_all(self, name: str) -> int:
        """Embed un-embedded chunks for a doc in a thread-safe way."""
        doc_dir = self._doc_dir(name)
        if not doc_dir.is_dir():
            return 0
        model = _get_model()
        count = 0
        for txt_path in sorted(doc_dir.glob("chunk_*.txt")):
            npy_path = doc_dir / f"{txt_path.stem}.npy"
            if npy_path.exists():
                continue
            text = txt_path.read_text(encoding="utf-8")
            vec = model.encode(text, normalize_embeddings=True)
            np.save(str(npy_path), vec)
            count += 1
        return count

    async def add_async(self, name: str, content: str) -> tuple[str, int]:
        """Non-blocking chunk + embed via thread pool."""
        import asyncio
        safe, count = await asyncio.to_thread(self.chunk_and_save, name, content)
        if count > 0:
            await asyncio.to_thread(self.embed_all, safe)
        return safe, count

    def list_docs(self) -> list[dict]:
        """List all documents with metadata."""
        docs = []
        for doc_dir in sorted(self._dir.iterdir()):
            if not doc_dir.is_dir():
                continue
            meta = self._read_meta(doc_dir.name)
            if meta is None:
                continue
            # Count actual chunk files
            txt_count = len(list(doc_dir.glob("chunk_*.txt")))
            docs.append({
                "name": meta["name"],
                "original_name": meta.get("original_name", meta["name"]),
                "created": meta.get("created", 0),
                "chunk_count": txt_count or meta.get("chunk_count", 0),
                "tags": meta.get("tags", []),
            })
        return docs

    def get_doc(self, name: str) -> dict | None:
        """Get a single document with chunk previews and full content."""
        meta = self._read_meta(name)
        if meta is None:
            return None
        doc_dir = self._doc_dir(name)
        content = ""
        content_file = doc_dir / "content.txt"
        if content_file.exists():
            content = content_file.read_text(encoding="utf-8")
        chunks = []
        for txt_path in sorted(doc_dir.glob("chunk_*.txt")):
            text = txt_path.read_text(encoding="utf-8")
            chunks.append({"index": txt_path.stem, "text": text[:200], "full_length": len(text)})
        return {**meta, "content": content, "chunks": chunks}

    def delete(self, name: str) -> bool:
        """Delete a document directory."""
        import shutil
        doc_dir = self._doc_dir(name)
        if doc_dir.is_dir():
            shutil.rmtree(doc_dir)
            return True
        return False

    # -- Retriever protocol --

    async def retrieve(self, query: Query) -> list[RetrievedChunk]:
        model = _get_model()
        q_vec = model.encode(query.text, normalize_embeddings=True)

        results: list[tuple[float, str, str, str]] = []
        for doc_dir in self._dir.iterdir():
            if not doc_dir.is_dir():
                continue
            for npy_path in sorted(doc_dir.glob("chunk_*.npy")):
                txt_path = doc_dir / f"{npy_path.stem}.txt"
                if not txt_path.exists():
                    continue
                try:
                    doc_vec = np.load(str(npy_path))
                    text = txt_path.read_text(encoding="utf-8")
                except Exception:
                    logger.debug("Failed to load chunk %s for doc %s", npy_path.stem, doc_dir.name)
                    continue
                score = float(np.dot(q_vec, doc_vec))
                if score < 0.2:
                    continue
                results.append((score, doc_dir.name, npy_path.stem, text))

        results.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievedChunk(
                text=text[:1200],
                score=round(score, 4),
                source=f"{source}/{chunk_id}",
            )
            for score, source, chunk_id, text in results[:query.top_k]
        ]


# ---- scoped access & root resolution ----

class ScopedKnowledgeBase:
    """Restrict a retriever to allowed doc names and tag chunk sources with a scope.

    LocalKnowledgeBase sources are ``{doc_name}/{chunk_id}``. This wrapper:
    - drops chunks whose doc_name is not in ``doc_names`` (None = allow all)
    - prefixes surviving sources with ``{scope}/{doc_name}/{chunk_id}`` so
      shared and private roots sharing a doc name do not collide in a
      CompositeKnowledgeBase (sources stay unique across scopes).
    """

    def __init__(self, retriever: Retriever, *, scope: str, doc_names: set[str] | None = None) -> None:
        self._retriever = retriever
        self._scope = scope
        self._doc_names = doc_names

    async def retrieve(self, query: Query) -> list[RetrievedChunk]:
        chunks = await self._retriever.retrieve(query)
        out: list[RetrievedChunk] = []
        for c in chunks:
            doc = c.source.split("/", 1)[0] if c.source else None
            if self._doc_names is not None and (doc is None or doc not in self._doc_names):
                continue
            src = f"{self._scope}/{c.source}" if c.source else c.source
            out.append(c.model_copy(update={"source": src}))
        return out


def _has_flat_docs(base: str) -> bool:
    """True if any doc subdir of base (excluding shared/agents) holds KB files."""
    try:
        entries = list(os.scandir(base))
    except OSError:
        return False
    for entry in entries:
        if not entry.is_dir() or entry.name in ("shared", "agents"):
            continue
        dirpath = os.path.join(base, entry.name)
        if os.path.exists(os.path.join(dirpath, "meta.json")):
            return True
        try:
            names = os.listdir(dirpath)
        except OSError:
            continue
        if any(n.startswith("chunk_") and n.endswith(".txt") for n in names):
            return True
    return False


def knowledge_shared_dir(cwd: str = "") -> str:
    """Shared KB root; falls back to the old flat .pi/knowledge layout."""
    base = os.path.join(cwd or os.getcwd(), ".pi", "knowledge")
    shared = os.path.join(base, "shared")
    # Prefer shared/ subdir. Fall back to base when it has flat doc dirs and
    # no shared/ subdir yet (old layout), so existing docs stay reachable.
    if os.path.isdir(shared):
        return shared
    if _has_flat_docs(base):
        return base
    return shared


def knowledge_agent_dir(agent_id: str, cwd: str = "") -> str:
    """Per-agent private KB root: ``.pi/knowledge/agents/<agent_id>/``."""
    return os.path.join(cwd or os.getcwd(), ".pi", "knowledge", "agents", agent_id)
