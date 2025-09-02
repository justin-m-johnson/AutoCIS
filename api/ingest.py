# api/ingest.py
import hashlib, io
from typing import List, Tuple, Dict, Any

from sqlalchemy import text as sql
from unstructured.partition.auto import partition

from llm_openai import embed_texts
from db import get_session

# ---------- helpers ----------

def file_sha256(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

def extract_title(elements, filename: str) -> str:
    """
    Try metadata -> H1/Title/Header -> fallback to filename.
    """
    # 1) Embedded metadata title if present
    try:
        for el in elements:
            meta = getattr(el, "metadata", None)
            if meta and getattr(meta, "title", None):
                t = (meta.title or "").strip()
                if t:
                    return t
    except Exception:
        pass

    # 2) First Title/Header element text
    for el in elements:
        cat = getattr(el, "category", "") or ""
        txt = (getattr(el, "text", None) or "").strip()
        if cat in ("Title", "Header") and txt:
            return txt

    # 3) Fallback
    return filename

def heading_aware_chunks(elements, target_tokens: int = 900, overlap_tokens: int = 120) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Build chunks using heading boundaries when possible.
    Returns list of (text, meta) where meta includes section_path + page.
    """
    chunks: List[Tuple[str, Dict[str, Any]]] = []
    buf: List[str] = []
    meta: Dict[str, Any] = {}
    tokens = 0

    def flush():
        nonlocal buf, tokens, meta
        if buf:
            text = " ".join(buf).strip()
            if text:
                chunks.append((text, meta.copy()))
        buf = []
        tokens = 0

    for el in elements:
        txt = (getattr(el, "text", None) or "").strip()
        if not txt:
            continue
        cat = getattr(el, "category", "") or ""
        page_no = 1
        try:
            md = getattr(el, "metadata", None)
            if md and getattr(md, "page_number", None):
                page_no = md.page_number
        except Exception:
            pass

        if cat in ("Title", "Header"):
            flush()
            meta = {"section_path": txt, "page": page_no}

        buf.append(txt)
        tokens += len(txt.split())
        if tokens >= target_tokens:
            flush()
            # keep small overlap to preserve context
            if overlap_tokens > 0:
                # crude overlap: keep last N words
                tail = " ".join(txt.split()[-overlap_tokens:])
                if tail:
                    buf = [tail]
                    tokens = len(tail.split())

    flush()
    return chunks

# ---------- main entry ----------

def ingest_bytes(filename: str, blob: bytes, creator: str = "api") -> Dict[str, Any]:
    """
    Parse -> title -> chunk -> embed -> store. Returns {document_id, title}.
    """
    elements = partition(file=io.BytesIO(blob), file_filename=filename)
    title = extract_title(elements, filename)
    sha = file_sha256(blob)
    chs = heading_aware_chunks(elements)

    texts = [t for t, _ in chs]
    vectors = embed_texts(texts) if texts else []

    with get_session() as s:
        # Insert document
        doc_row = s.execute(sql("""
            INSERT INTO documents (canonical_title, filename, sha256, filetype, created_by)
            VALUES (:title, :filename, :sha, :ft, :creator)
            ON CONFLICT (sha256) DO NOTHING
            RETURNING id
        """), {
            "title": title,
            "filename": filename,
            "sha": sha,
            "ft": (filename.split(".")[-1] if "." in filename else "bin"),
            "creator": creator
        }).mappings().first()

        if doc_row is None:
            # Document with same hash already exists; fetch its id
            doc_row = s.execute(sql("SELECT id FROM documents WHERE sha256 = :sha"), {"sha": sha}).mappings().first()

        doc_id = doc_row["id"]

        # Insert chunks and embeddings
        for (text, meta), vec in zip(chs, vectors):
            inserted = s.execute(sql("""
                INSERT INTO chunks (document_id, section_path, page, char_start, char_end, text)
                VALUES (:doc_id, :section_path, :page, :char_start, :char_end, :text)
                RETURNING id
            """), {
                "doc_id": doc_id,
                "section_path": meta.get("section_path"),
                "page": meta.get("page", 1),
                "char_start": 0,
                "char_end": len(text),
                "text": text
            }).mappings().first()

            s.execute(sql("UPDATE chunks SET embedding = :emb WHERE id = :id"), {
                "emb": vec,  # pgvector accepts Python list[float]
                "id": inserted["id"]
            })

        s.commit()

    return {"document_id": doc_id, "title": title}